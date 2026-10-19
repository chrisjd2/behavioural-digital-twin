"""The single gateway for LLM calls: cache, concurrency, backoff, counters (ADR-0002).

A *backend* turns a request payload into raw text. The real backend calls an
OpenAI-compatible endpoint; the mock backend returns deterministic, visibly
labelled fake output; tests pass their own.
"""

import asyncio
import hashlib
import json
import re
import sqlite3
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import openai

MAX_ATTEMPTS = 5
FIRST_BACKOFF_SECONDS = 1.0


class TransientError(Exception):
    """A failure worth retrying: rate limit, server error or dropped connection."""


@dataclass(frozen=True)
class RawResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class Completion:
    content: str
    cached: bool


@dataclass
class Counters:
    calls: int = 0
    cache_hits: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


Backend = Callable[[Mapping[str, object]], Awaitable[RawResponse]]
Sleep = Callable[[float], Awaitable[None]]


def cache_key(model: str, base_url: str, payload: Mapping[str, object]) -> str:
    blob = json.dumps({"model": model, "base_url": base_url, "payload": payload}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class Cache:
    """SQLite store of raw responses, keyed by `cache_key`."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS calls (key TEXT PRIMARY KEY, model TEXT, content TEXT)"
        )

    def get(self, key: str) -> str | None:
        row = self._db.execute("SELECT content FROM calls WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def put(self, key: str, model: str, content: str) -> None:
        self._db.execute("INSERT OR REPLACE INTO calls VALUES (?, ?, ?)", (key, model, content))
        self._db.commit()


@dataclass
class LLMClient:
    model: str
    base_url: str
    cache: Cache
    backend: Backend
    concurrency: int
    sleep: Sleep = asyncio.sleep
    counters: Counters = field(default_factory=Counters)

    def __post_init__(self) -> None:
        self._semaphore = asyncio.Semaphore(self.concurrency)

    async def complete(self, payload: Mapping[str, object]) -> Completion:
        key = cache_key(self.model, self.base_url, payload)
        if (cached := self.cache.get(key)) is not None:
            self.counters.cache_hits += 1
            return Completion(cached, cached=True)

        async with self._semaphore:
            response = await self._call_with_backoff({**payload, "model": self.model})
        self.counters.calls += 1
        self.counters.prompt_tokens += response.prompt_tokens
        self.counters.completion_tokens += response.completion_tokens
        self.cache.put(key, self.model, response.content)
        return Completion(response.content, cached=False)

    async def _call_with_backoff(self, payload: Mapping[str, object]) -> RawResponse:
        delay = FIRST_BACKOFF_SECONDS
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return await self.backend(payload)
            except TransientError:
                if attempt == MAX_ATTEMPTS:
                    raise
                await self.sleep(delay)
                delay *= 2
        raise AssertionError("unreachable")


def openai_backend(
    base_url: str, api_key: str, *, http_client: httpx.AsyncClient | None = None
) -> Backend:
    """Retries only rate limits (429), server errors (5xx) and dropped connections; a 4xx such
    as an unsupported setting is a bug in the request and fails immediately."""
    client = openai.AsyncOpenAI(
        base_url=base_url,
        api_key=api_key,
        max_retries=0,
        http_client=http_client,  # pyright: ignore[reportArgumentType] -- reason: same httpx class, resolved via two paths
    )

    async def send(payload: Mapping[str, object]) -> RawResponse:
        try:
            response = await client.chat.completions.create(**payload)  # pyright: ignore[reportArgumentType, reportCallIssue]
        except (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError) as e:
            raise TransientError(str(e)) from e
        usage = response.usage
        # No choices (e.g. a safety block) becomes empty text: a parse failure, then the retry.
        message = response.choices[0].message.content if response.choices else None
        return RawResponse(
            content=message or "",
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )

    return send


_ID_PATTERN = re.compile(r'"id":\s*"([^"]+)"')


async def mock_backend(payload: Mapping[str, object]) -> RawResponse:
    """Deterministic fake reactions for every headline ID in the prompt. Never results."""
    messages = payload["messages"]
    assert isinstance(messages, list)
    prompt = json.dumps(messages, sort_keys=True)
    contents = (str(m.get("content", "")) for m in messages if isinstance(m, dict))
    ids = list(dict.fromkeys(i for text in contents for i in _ID_PATTERN.findall(text)))
    reactions = []
    for news_id in ids:
        digest = hashlib.sha256(f"{prompt}:{news_id}".encode()).digest()
        reactions.append(
            {"id": news_id, "reaction": f"MOCK reaction to {news_id}.", "p_click": digest[0] % 101}
        )
    return RawResponse(json.dumps({"reactions": reactions}), prompt_tokens=0, completion_tokens=0)
