import asyncio
from pathlib import Path

import pytest

from backend.arms import LLMOptions
from backend.baselines import BaselineContext, random_scores
from backend.data import CandidateSet, DataSource, Populations, build_candidate_set
from backend.experiment import ARMS, ExperimentConfig
from backend.llm import Cache, LLMClient, mock_backend
from backend.metrics import auc
from backend.report import build_report
from backend.runner import UserResult, run_experiment
from scripts.run_headless import main
from tests.factories import make_impression

CONFIG = ExperimentConfig(n_dev=30, n_test=100)


def clicked_first(candidates: CandidateSet, **_: object) -> dict[str, float]:
    return {i: 90.0 * candidates.labels[i] for i in candidates.items}


def all_tied(candidates: CandidateSet, **_: object) -> dict[str, float]:
    return dict.fromkeys(candidates.items, 50.0)


async def by_arm(
    source: DataSource, arms: list[str], tmp_path: Path, population: str = "dev"
) -> dict[str, list[UserResult]]:
    client = LLMClient(
        model="mock",
        base_url="mock://",
        cache=Cache(tmp_path / "cache.sqlite"),
        backend=mock_backend,
        concurrency=4,
    )
    run = await run_experiment(
        source,
        CONFIG,
        population=population,  # type: ignore[arg-type]
        arms=arms,
        client=client,
        options=LLMOptions("medium", 4096, base_rate_hint=False),
        allow_unfrozen=population == "test",
    )
    return {arm: [u for u in run.users if u.arm == arm] for arm in arms}


def test_random_scores_cover_every_candidate_and_are_seeded(sample_source: DataSource) -> None:
    candidates = build_candidate_set(make_impression(), seed=1, max_candidates=8, max_clicked=2)
    context = BaselineContext(sample_source, Populations(dev=(), test=()))

    scores = random_scores(candidates, seed=3, context=context)

    assert set(scores) == set(candidates.items)
    assert scores == random_scores(candidates, seed=3, context=context)
    assert scores != random_scores(candidates, seed=4, context=context)


async def test_random_is_near_chance(sample_source: DataSource, tmp_path: Path) -> None:
    result = await by_arm(sample_source, ["random"], tmp_path, population="test")

    aucs = [auc(u.scores, u.labels) for u in result["random"]]
    assert len(aucs) == 100
    assert 0.35 < sum(aucs) / len(aucs) < 0.65


async def test_popularity_scores_every_candidate_as_a_smoothed_ctr(
    sample_source: DataSource, tmp_path: Path
) -> None:
    users = (await by_arm(sample_source, ["popularity"], tmp_path))["popularity"]

    assert len(users) == 30
    assert all(set(u.scores) == set(u.items) for u in users)
    assert all(0 < s < 1 for u in users for s in u.scores.values())
    assert len({s for u in users for s in u.scores.values()}) > 30  # not just the prior


async def test_arms_share_users_labels_and_tie_order(
    sample_source: DataSource, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(ARMS, "oracle", clicked_first)

    result = await by_arm(sample_source, ["random", "oracle", "A"], tmp_path)

    random_users, oracle_users, a_users = result["random"], result["oracle"], result["A"]
    assert len({u.user_id for u in random_users}) == 30
    for r, o, a in zip(random_users, oracle_users, a_users, strict=True):
        assert (r.user_id, r.labels, r.tie_rank, r.items) == (
            o.user_id,
            o.labels,
            o.tie_rank,
            o.items,
        )
        assert (r.user_id, r.labels, r.tie_rank, r.items) == (
            a.user_id,
            a.labels,
            a.tie_rank,
            a.items,
        )
        assert 0 < o.feed_ctr <= o.sample_ctr
    assert {auc(u.scores, u.labels) for u in oracle_users} == {1.0}


async def test_rejects_unknown_arm(sample_source: DataSource, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown arm"):
        await by_arm(sample_source, ["Z"], tmp_path)


@pytest.fixture
def isolated_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep headless runs and cache out of the session-wide data dir."""
    monkeypatch.setattr("scripts.run_headless.RUNS_SUBDIR", tmp_path / "runs")
    monkeypatch.setattr("scripts.run_headless.CACHE_FILE", tmp_path / "cache.sqlite")
    return tmp_path / "runs"


@pytest.mark.usefixtures("isolated_outputs")
def test_headless_prints_synthetic_banner_and_metrics_with_cis(
    data_dir: Path, sample_source: DataSource, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    results = asyncio.run(by_arm(sample_source, ["random"], tmp_path))
    summary = build_report(results, seed=CONFIG.bootstrap_seed).arms["random"]

    exit_code = main(["--data-dir", str(data_dir), "--population", "dev", "--n-test", "100"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "SYNTHETIC SAMPLE (fake data)" in out
    for name in ("AUC", "MRR", "nDCG@5", "Hit@1", "ties", "parse fail"):
        assert name in out
    hit1 = summary.metrics["hit1"]
    assert f"{hit1.mean:.3f} [{hit1.low:.3f}, {hit1.high:.3f}]" in out
    assert "random     n/a (baseline scores are not probabilities)" in out
    assert "Primary outcome" not in out
    assert "MOCK" not in out  # no LLM arm ran
    assert "NOT A RESULT" in out
    assert "train impressions: 2019-11-0" in out
    assert "dev impressions: 2019-11-15" in out


@pytest.mark.usefixtures("isolated_outputs")
def test_headless_prints_comparisons_and_primary_outcome_when_a_and_d_run(
    data_dir: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(ARMS, "A", all_tied)
    monkeypatch.setitem(ARMS, "D", clicked_first)

    main(["--data-dir", str(data_dir), "--arms", "A,D", "--n-test", "100"])

    out = capsys.readouterr().out
    assert "A            30  0.500 [0.500, 0.500]" in out
    assert "100.0%" in out  # A ties every prediction
    assert "A          0.500 | " in out  # mean p_click 50/100
    assert "D - A      +0.500 [+0.500, +0.500]" in out
    assert "Primary outcome, D - A AUC +0.500 [+0.500, +0.500]: twins beat plain LLM" in out
    assert "Outcome buckets: Twin better: 30 | About the same: 0 | Plain LLM better: 0" in out
    assert "Median user: " in out


@pytest.mark.usefixtures("isolated_outputs")
def test_headless_prints_popularity_alongside_random(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(
        ["--data-dir", str(data_dir), "--arms", "popularity,random", "--n-test", "100"]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "popularity   30  " in out
    assert "random       30  " in out
    assert "popularity n/a (baseline scores are not probabilities)" in out
