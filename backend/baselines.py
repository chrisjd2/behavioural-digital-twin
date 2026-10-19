"""Non-AI baselines (ADR-0004)."""

import random

from backend.data import CandidateSet


def random_scores(candidates: CandidateSet, *, seed: int) -> dict[str, float]:
    rng = random.Random(f"random:{seed}:{candidates.user_id}")
    return {news_id: rng.random() for news_id in candidates.items}
