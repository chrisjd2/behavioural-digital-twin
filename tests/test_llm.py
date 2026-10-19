import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

import httpx
import openai
import pytest

from backend.llm import (
    Cache,
    LLMClient,
    RawResponse,
    TransientError,
    cache_key,
    mock_backend,
    openai_backend,
)

PAYLOAD = {"messages": [{"role": "user", "content": 'ids: [{"id": "N1"}, {"id": "N2"}]'}]}


class FakeBackend:
    def __init__(self, *responses: str | Exception) -> None:
        self.responses = list(responses)
        self.payloads: list[Mapping[str, object]] = []

    async def __call__(self, payload: Mapping[str, object]) -> RawResponse:
        self.payloads.append(payload)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return RawResponse(content=response, prompt_tokens=10, completion_tokens=5)


async def no_sleep(_: float) -> None:
    return None


def make_client(tmp_path: Path, backend: FakeBackend) -> LLMClient:
    return LLMClient(
        model="gemini-test-001",
        base_url="https://example.test/v1/",
        cache=Cache(tmp_path / "cache.sqlite"),
        backend=backend,
        concurrency=2,
        sleep=no_sleep,
    )


async def test_semaphore_limits_concurrent_calls(tmp_path: Path) -> None:
    in_flight = peak = 0

    async def slow(_: Mapping[str, object]) -> RawResponse:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return RawResponse("{}", 0, 0)

    client = LLMClient(
        model="m", base_url="u", cache=Cache(tmp_path / "c.sqlite"), backend=slow, concurrency=3
    )

    await asyncio.gather(*(client.complete({"n": n}) for n in range(12)))

    assert peak == 3


def gemini_stub(status: int, body: Mapping[str, object]) -> httpx.AsyncClient:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_rate_limits_and_server_errors_are_transient(status: int) -> None:
    send = openai_backend("https://stub.test/v1/", "k", http_client=gemini_stub(status, {}))

    with pytest.raises(TransientError):
        await send({"model": "m", "messages": []})


async def test_bad_requests_fail_immediately_without_retry() -> None:
    error = {"error": {"message": "Thinking level MINIMAL is not supported"}}
    send = openai_backend("https://stub.test/v1/", "k", http_client=gemini_stub(400, error))

    with pytest.raises(openai.BadRequestError):
        await send({"model": "m", "messages": []})


async def test_no_choices_becomes_empty_text_for_the_parse_retry() -> None:
    body = {"id": "x", "object": "chat.completion", "created": 0, "model": "m", "choices": []}
    send = openai_backend("https://stub.test/v1/", "k", http_client=gemini_stub(200, body))

    assert (await send({"model": "m", "messages": []})).content == ""


def test_cache_key_covers_model_base_url_and_payload() -> None:
    base = cache_key("m1", "https://a/", PAYLOAD)

    assert base == cache_key("m1", "https://a/", PAYLOAD)
    assert base != cache_key("m2", "https://a/", PAYLOAD)
    assert base != cache_key("m1", "https://b/", PAYLOAD)
    assert base != cache_key("m1", "https://a/", {**PAYLOAD, "temperature": 0})


async def test_second_identical_call_is_served_from_cache(tmp_path: Path) -> None:
    backend = FakeBackend('{"ok": 1}')
    client = make_client(tmp_path, backend)

    first = await client.complete(PAYLOAD)
    second = await client.complete(PAYLOAD)

    assert first.content == second.content == '{"ok": 1}'
    assert len(backend.payloads) == 1
    assert client.counters.calls == 1
    assert client.counters.cache_hits == 1
    assert client.counters.prompt_tokens == 10


async def test_cache_persists_across_clients(tmp_path: Path) -> None:
    await make_client(tmp_path, FakeBackend('{"ok": 1}')).complete(PAYLOAD)
    backend = FakeBackend()

    again = await make_client(tmp_path, backend).complete(PAYLOAD)

    assert again.cached
    assert backend.payloads == []


async def test_transient_errors_back_off_then_succeed(tmp_path: Path) -> None:
    delays: list[float] = []

    async def record_sleep(seconds: float) -> None:
        delays.append(seconds)

    backend = FakeBackend(TransientError("429"), TransientError("503"), '{"ok": 1}')
    client = LLMClient(
        model="m",
        base_url="u",
        cache=Cache(tmp_path / "c.sqlite"),
        backend=backend,
        concurrency=1,
        sleep=record_sleep,
    )

    result = await client.complete(PAYLOAD)

    assert result.content == '{"ok": 1}'
    assert delays == [1.0, 2.0]


async def test_gives_up_after_max_attempts(tmp_path: Path) -> None:
    backend = FakeBackend(*[TransientError("429")] * 5)
    client = make_client(tmp_path, backend)

    with pytest.raises(TransientError):
        await client.complete(PAYLOAD)
    assert len(backend.payloads) == 5


async def test_mock_backend_is_deterministic_and_labelled() -> None:
    first = await mock_backend(PAYLOAD)
    second = await mock_backend(PAYLOAD)

    body = json.loads(first.content)
    assert first == second
    assert [r["id"] for r in body["reactions"]] == ["N1", "N2"]
    assert all(r["reaction"].startswith("MOCK") for r in body["reactions"])
    assert all(0 <= r["p_click"] <= 100 for r in body["reactions"])
