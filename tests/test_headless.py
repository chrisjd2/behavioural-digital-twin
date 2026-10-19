from pathlib import Path

import pytest

from backend.baselines import random_scores
from backend.data import build_candidate_set
from backend.experiment import ExperimentConfig, evaluate
from backend.sample import write_synthetic_sample
from scripts.run_headless import main
from tests.test_data import impression


@pytest.fixture(scope="module")
def sample_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("sample")
    write_synthetic_sample(directory, n_users=400, n_news=300, seed=1)
    return directory


def test_random_scores_cover_every_candidate_and_are_seeded() -> None:
    candidates = build_candidate_set(impression(), seed=1, max_candidates=8)

    scores = random_scores(candidates, seed=3)

    assert set(scores) == set(candidates.items)
    assert scores == random_scores(candidates, seed=3)
    assert scores != random_scores(candidates, seed=4)


def test_evaluate_random_is_near_chance(sample_dir: Path) -> None:
    config = ExperimentConfig(n_dev=30, n_test=100)

    result = evaluate(sample_dir, config, population="test", arms=["random"])

    aucs = result["random"]
    assert len(aucs) == 100
    assert 0.35 < sum(aucs) / len(aucs) < 0.65


def test_evaluate_rejects_unknown_arm(sample_dir: Path) -> None:
    with pytest.raises(ValueError, match="Unknown arm"):
        evaluate(sample_dir, ExperimentConfig(n_dev=30, n_test=100), population="dev", arms=["Z"])


def test_headless_prints_table(sample_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(
        [
            "--data-dir",
            str(sample_dir),
            "--population",
            "dev",
            "--arms",
            "random",
            "--n-test",
            "100",
        ]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "SYNTHETIC" in out
    assert "random" in out
    assert "AUC" in out
