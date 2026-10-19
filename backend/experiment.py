"""Experiment configuration and evaluation (ADR-0001)."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from backend.baselines import random_scores
from backend.data import CandidateSet, build_candidate_set, load_behaviors, sample_populations
from backend.metrics import auc

Population = Literal["dev", "test"]
Scorer = Callable[..., dict[str, float]]

# Arm name -> scorer(candidates, *, seed) returning a score per candidate news ID.
ARMS: dict[str, Scorer] = {"random": random_scores}


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
    max_clicked: int = 2


def evaluate(
    data_dir: Path, config: ExperimentConfig, *, population: Population, arms: list[str]
) -> dict[str, list[float]]:
    """Per-user AUC for each arm, in population order."""
    unknown = sorted(set(arms) - set(ARMS))
    if unknown:
        raise ValueError(f"Unknown arm(s): {', '.join(unknown)}")

    populations = sample_populations(
        load_behaviors(data_dir / "behaviors.tsv"),
        n_dev=config.n_dev,
        n_test=config.n_test,
        dev_seed=config.dev_seed,
        test_seed=config.test_seed,
    )
    candidate_sets: list[CandidateSet] = [
        build_candidate_set(
            imp,
            seed=config.candidate_seed,
            max_candidates=config.max_candidates,
            max_clicked=config.max_clicked,
        )
        for imp in (populations.dev if population == "dev" else populations.test)
    ]
    return {
        arm: [auc(ARMS[arm](c, seed=config.baseline_seed), c.labels) for c in candidate_sets]
        for arm in arms
    }
