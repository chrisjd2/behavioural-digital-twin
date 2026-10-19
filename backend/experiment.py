"""Experiment configuration and evaluation (ADR-0001)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from backend.baselines import random_scores
from backend.data import build_candidate_set, load_behaviors, sample_populations
from backend.metrics import auc

Population = Literal["dev", "test"]
KNOWN_ARMS = ("random",)


@dataclass(frozen=True)
class ExperimentConfig:
    """Pre-registered defaults; changing any of these after the freeze is a new experiment."""

    n_dev: int = 30
    n_test: int = 200
    dev_seed: int = 20261019
    test_seed: int = 20261020
    candidate_seed: int = 1
    baseline_seed: int = 1
    max_candidates: int = 8


def evaluate(
    data_dir: Path, config: ExperimentConfig, *, population: Population, arms: list[str]
) -> dict[str, list[float]]:
    """Per-user AUC for each arm, in population order."""
    unknown = sorted(set(arms) - set(KNOWN_ARMS))
    if unknown:
        raise ValueError(f"Unknown arm(s): {', '.join(unknown)}")

    populations = sample_populations(
        load_behaviors(data_dir / "behaviors.tsv"),
        n_dev=config.n_dev,
        n_test=config.n_test,
        dev_seed=config.dev_seed,
        test_seed=config.test_seed,
    )
    candidate_sets = [
        build_candidate_set(imp, seed=config.candidate_seed, max_candidates=config.max_candidates)
        for imp in (populations.dev if population == "dev" else populations.test)
    ]
    return {
        arm: [auc(random_scores(c, seed=config.baseline_seed), c.labels) for c in candidate_sets]
        for arm in arms
    }
