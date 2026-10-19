"""Experiment configuration and the non-LLM scorers (ADR-0001). Orchestration lives in runner.py."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from backend.baselines import popularity_scores, random_scores

Population = Literal["dev", "test"]
Scorer = Callable[..., dict[str, float]]

# Arm name -> scorer(candidates, *, seed, context: BaselineContext) -> score per candidate ID.
ARMS: dict[str, Scorer] = {"popularity": popularity_scores, "random": random_scores}


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
    bootstrap_seed: int = 20261019
