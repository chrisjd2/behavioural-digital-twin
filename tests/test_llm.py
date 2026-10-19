import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from backend.llm import Cache, LLMClient, RawResponse, TransientError, cache_key, mock_backend

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


def make_client(tmp_path: Path, backend: FakeBackend, **kwargs: object) -> LLMClient:
    return LLMClient(
        model="gemini-test-001",
        base_url="https://example.test/v1/",
        cache=Cache(tmp_path / "cache.sqlite"),
        backend=backend,
        concurrency=2,
        sleep=no_sleep,
        **kwargs,  # type: ignore[arg-type]
    )


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
