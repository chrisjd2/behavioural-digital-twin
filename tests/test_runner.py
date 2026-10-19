import json
from collections.abc import Mapping
from pathlib import Path

from backend.data import DataSource
from backend.experiment import ExperimentConfig
from backend.llm import Cache, LLMClient, RawResponse, mock_backend
from backend.runner import RunEvent, run_experiment
from backend.runs import load_run, save_run

CONFIG = ExperimentConfig(n_dev=10, n_test=20)


def mock_client(tmp_path: Path) -> LLMClient:
    return LLMClient(
        model="mock",
        base_url="mock://",
        cache=Cache(tmp_path / "cache.sqlite"),
        backend=mock_backend,
        concurrency=4,
    )


async def test_run_scores_every_user_and_emits_events_in_order(
    sample_source: DataSource, tmp_path: Path
) -> None:
    events: list[RunEvent] = []

    run = await run_experiment(
        sample_source,
        CONFIG,
        population="dev",
        arms=["A", "random"],
        client=mock_client(tmp_path),
        base_rate_hint=False,
        on_event=events.append,
    )

    assert {u.arm for u in run.users} == {"A", "random"}
    assert len([u for u in run.users if u.arm == "A"]) == 10
    kinds = [e.kind for e in events]
    assert kinds.count("call_started") == 10
    assert kinds.count("reaction") == sum(len(u.labels) for u in run.users if u.arm == "A")
    assert kinds[-1] == "run_complete"
    assert "arm_progress" in kinds
    first_reaction = next(e for e in events if e.kind == "reaction")
    assert {"user_id", "arm", "news_id", "reaction", "p_click", "clicked"} <= set(
        first_reaction.data
    )


async def test_repeat_run_makes_zero_new_calls(sample_source: DataSource, tmp_path: Path) -> None:
    client = mock_client(tmp_path)
    kwargs = {"population": "dev", "arms": ["A"], "base_rate_hint": False}

    await run_experiment(sample_source, CONFIG, client=client, **kwargs)  # type: ignore[arg-type]
    calls_after_first = client.counters.calls
    await run_experiment(sample_source, CONFIG, client=client, **kwargs)  # type: ignore[arg-type]

    assert calls_after_first == 10
    assert client.counters.calls == 10


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

    run = await run_experiment(
        sample_source,
        CONFIG,
        population="dev",
        arms=["A"],
        client=client,
        base_rate_hint=False,
    )

    assert len(payloads) == 20  # one attempt + one retry per user
    assert all(u.parse_failures == len(u.labels) for u in run.users)
    assert all(set(u.scores.values()) == {0.0} for u in run.users)


async def test_run_file_round_trips_with_provenance(
    sample_source: DataSource, tmp_path: Path
) -> None:
    run = await run_experiment(
        sample_source,
        CONFIG,
        population="dev",
        arms=["A"],
        client=mock_client(tmp_path),
        base_rate_hint=False,
    )

    path = save_run(run, tmp_path / "runs")
    saved = json.loads(path.read_text(encoding="utf-8"))

    assert saved["mock"] is True
    assert saved["model"] == "mock"
    assert saved["config"]["test_seed"] == CONFIG.test_seed
    assert saved["prompt_hashes"]["A"]
    assert saved["git_sha"]
    assert saved["data_source"] == "synthetic"
    assert saved["users"][0]["reactions"]
    assert saved["users"][0]["labels"]
    assert saved["events"]
    assert "A" in saved["metrics"]
    assert load_run(path).run_id == run.run_id
