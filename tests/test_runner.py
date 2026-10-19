import asyncio
import itertools
from collections.abc import Mapping
from pathlib import Path

import pytest

from backend.arms import LLMOptions
from backend.data import DataSource
from backend.experiment import ExperimentConfig
from backend.llm import Cache, LLMClient, RawResponse, TransientError, mock_backend
from backend.runner import FreezeError, RunEvent, run_experiment
from backend.runs import load_run, save_run

CONFIG = ExperimentConfig(n_dev=10, n_test=20)
OPTIONS = LLMOptions(reasoning_effort="medium", max_output_tokens=4096, base_rate_hint=False)


def mock_client(tmp_path: Path) -> LLMClient:
    return LLMClient(
        model="mock",
        base_url="mock://",
        cache=Cache(tmp_path / "cache.sqlite"),
        backend=mock_backend,
        concurrency=4,
    )


async def run_dev(source: DataSource, client: LLMClient, **kwargs: object):
    return await run_experiment(
        source,
        CONFIG,
        population="dev",
        arms=kwargs.pop("arms", ["A"]),  # type: ignore[arg-type]
        client=client,
        options=kwargs.pop("options", OPTIONS),  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )


async def test_run_scores_every_user_and_emits_ordered_events(
    sample_source: DataSource, tmp_path: Path
) -> None:
    events: list[RunEvent] = []

    run = await run_dev(
        sample_source, mock_client(tmp_path), arms=["A", "random"], on_event=events.append
    )

    assert {u.arm for u in run.users} == {"A", "random"}
    assert len([u for u in run.users if u.arm == "A"]) == 10
    kinds = [e.kind for e in events]
    assert kinds.count("call_started") == 10
    assert kinds.count("reaction") == sum(len(u.labels) for u in run.users if u.arm == "A")
    assert kinds[-1] == "run_complete"
    assert [e.seq for e in events] == list(range(len(events)))
    assert all(a.at <= b.at for a, b in itertools.pairwise(events))
    reaction = next(e for e in events if e.kind == "reaction")
    assert {"user_id", "arm", "news_id", "reaction", "p_click", "clicked"} <= set(reaction.data)


async def test_repeat_run_makes_zero_new_calls(sample_source: DataSource, tmp_path: Path) -> None:
    client = mock_client(tmp_path)

    await run_dev(sample_source, client)
    calls_after_first = client.counters.calls
    await run_dev(sample_source, client)

    assert calls_after_first == 10
    assert client.counters.calls == 10


async def test_options_change_the_request_and_so_the_cache_key(
    sample_source: DataSource, tmp_path: Path
) -> None:
    client = mock_client(tmp_path)

    await run_dev(sample_source, client)
    await run_dev(sample_source, client, options=LLMOptions("high", 4096, base_rate_hint=False))

    assert client.counters.calls == 20


async def test_unparseable_output_is_retried_once_then_counted(
    sample_source: DataSource, tmp_path: Path
) -> None:
    payloads: list[Mapping[str, object]] = []

    async def broken(payload: Mapping[str, object]) -> RawResponse:
        payloads.append(payload)
        return RawResponse(content="sorry, no JSON", prompt_tokens=1, completion_tokens=1)

    client = LLMClient(
        model="m", base_url="u", cache=Cache(tmp_path / "c.sqlite"), backend=broken, concurrency=2
    )

    run = await run_dev(sample_source, client)

    assert len(payloads) == 20  # one attempt + one retry per user
    assert all(u.parse_failures == len(u.labels) for u in run.users)
    assert all(set(u.scores.values()) == {0.0} for u in run.users)


async def test_a_call_that_fails_for_good_cancels_the_rest(
    sample_source: DataSource, tmp_path: Path
) -> None:
    started = 0

    async def failing(_: Mapping[str, object]) -> RawResponse:
        nonlocal started
        started += 1
        await asyncio.sleep(0)
        raise TransientError("503")

    async def no_sleep(_: float) -> None:
        return None

    client = LLMClient(
        model="m",
        base_url="u",
        cache=Cache(tmp_path / "c.sqlite"),
        backend=failing,
        concurrency=1,
        sleep=no_sleep,
    )

    with pytest.raises(ExceptionGroup):
        await run_dev(sample_source, client)
    assert started < 10 * 5  # did not exhaust retries for every user


async def test_test_population_refuses_without_freeze(
    sample_source: DataSource, tmp_path: Path
) -> None:
    with pytest.raises(FreezeError, match="prompts-frozen"):
        await run_experiment(
            sample_source,
            CONFIG,
            population="test",
            arms=["random"],
            client=mock_client(tmp_path),
            options=OPTIONS,
        )


async def test_run_file_round_trips_with_provenance(
    sample_source: DataSource, tmp_path: Path
) -> None:
    run = await run_dev(
        sample_source, mock_client(tmp_path), options=LLMOptions("low", 512, base_rate_hint=True)
    )

    loaded = load_run(save_run(run, tmp_path / "runs"))

    assert loaded == run
    assert run.mock is True
    assert run.is_result is False
    assert run.options == {
        "reasoning_effort": "low",
        "max_output_tokens": 512,
        "base_rate_hint": True,
    }
    assert run.fingerprint["options"] == run.options
    assert set(run.date_ranges) == {"train", "dev"}
    assert run.config["test_seed"] == CONFIG.test_seed
    assert run.git_sha
    assert run.data_source == "synthetic"
    assert run.users[0].reactions
    assert "A" in run.metrics["arms"]  # type: ignore[operator]
