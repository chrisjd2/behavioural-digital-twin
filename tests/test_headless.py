import statistics

import pytest

from backend.baselines import random_scores
from backend.data import CandidateSet, DataSource, build_candidate_set
from backend.experiment import ARMS, ExperimentConfig, evaluate
from scripts.run_headless import main
from tests.factories import make_impression

CONFIG = ExperimentConfig(n_dev=30, n_test=100)


def test_random_scores_cover_every_candidate_and_are_seeded() -> None:
    candidates = build_candidate_set(make_impression(), seed=1, max_candidates=8, max_clicked=2)

    scores = random_scores(candidates, seed=3)

    assert set(scores) == set(candidates.items)
    assert scores == random_scores(candidates, seed=3)
    assert scores != random_scores(candidates, seed=4)


def test_evaluate_random_is_near_chance(sample_source: DataSource) -> None:
    result = evaluate(sample_source, CONFIG, population="test", arms=["random"])

    aucs = result["random"]
    assert len(aucs) == 100
    assert 0.35 < statistics.fmean(aucs) < 0.65


def test_evaluate_dispatches_each_arm_to_its_own_scorer(
    sample_source: DataSource, monkeypatch: pytest.MonkeyPatch
) -> None:
    def scores_clicked_first(candidates: CandidateSet, *, seed: int) -> dict[str, float]:
        del seed
        return {i: float(candidates.labels[i]) for i in candidates.items}

    monkeypatch.setitem(ARMS, "oracle", scores_clicked_first)

    result = evaluate(sample_source, CONFIG, population="dev", arms=["random", "oracle"])

    assert set(result["oracle"]) == {1.0}
    assert result["random"] != result["oracle"]


def test_evaluate_rejects_unknown_arm(sample_source: DataSource) -> None:
    with pytest.raises(ValueError, match="Unknown arm"):
        evaluate(sample_source, CONFIG, population="dev", arms=["Z"])


def test_headless_prints_synthetic_banner_and_mean_auc(
    sample_source: DataSource, capsys: pytest.CaptureFixture[str]
) -> None:
    expected = statistics.fmean(
        evaluate(sample_source, CONFIG, population="dev", arms=["random"])["random"]
    )

    exit_code = main(
        ["--data-dir", str(sample_source.root.parent), "--population", "dev", "--n-test", "100"]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "SYNTHETIC SAMPLE (fake data)" in out
    assert f"random         30     {expected:.3f}" in out
