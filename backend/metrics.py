"""Per-user ranking metrics (ADR-0001). Scores and labels are keyed by news ID."""

import math
import statistics
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

NDCG_CUTOFF = 5


@dataclass(frozen=True)
class UserScores:
    """One arm's predictions for one user, with what is needed to score them."""

    user_id: str
    arm: str
    scores: dict[str, float]
    labels: dict[str, int]
    tie_rank: dict[str, int]
    feed_ctr: float
    sample_ctr: float
    parse_failures: int = 0


@dataclass(frozen=True)
class UserMetrics:
    user_id: str
    auc: float
    mrr: float
    ndcg5: float
    hit1: float
    n_candidates: int
    n_tied: int
    parse_failures: int
    mean_score: float


def auc(scores: Mapping[str, float], labels: Mapping[str, int]) -> float:
    """Probability a clicked item outranks a non-clicked one; ties count half."""
    positives = [scores[i] for i, label in labels.items() if label == 1]
    negatives = [scores[i] for i, label in labels.items() if label == 0]
    if not positives or not negatives:
        raise ValueError("AUC needs both clicked and non-clicked items")
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in positives for n in negatives)
    return wins / (len(positives) * len(negatives))


def rank(scores: Mapping[str, float], tie_rank: Mapping[str, int]) -> list[str]:
    """Highest score first; ADR-0005: ties broken by the seeded tie order, never display position."""
    return sorted(scores, key=lambda news_id: (-scores[news_id], tie_rank[news_id]))


def _click_ranks(
    scores: Mapping[str, float], labels: Mapping[str, int], tie_rank: Mapping[str, int]
) -> list[int]:
    ranks = [r for r, news_id in enumerate(rank(scores, tie_rank), start=1) if labels[news_id]]
    if not ranks:
        raise ValueError("Rank metrics need at least one click")
    return ranks


def mrr(
    scores: Mapping[str, float], labels: Mapping[str, int], tie_rank: Mapping[str, int]
) -> float:
    return 1 / _click_ranks(scores, labels, tie_rank)[0]


def hit_at_1(
    scores: Mapping[str, float], labels: Mapping[str, int], tie_rank: Mapping[str, int]
) -> float:
    return float(_click_ranks(scores, labels, tie_rank)[0] == 1)


def ndcg_at_5(
    scores: Mapping[str, float], labels: Mapping[str, int], tie_rank: Mapping[str, int]
) -> float:
    ranks = _click_ranks(scores, labels, tie_rank)
    dcg = sum(1 / math.log2(r + 1) for r in ranks if r <= NDCG_CUTOFF)
    ideal = sum(1 / math.log2(r + 1) for r in range(1, min(len(ranks), NDCG_CUTOFF) + 1))
    return dcg / ideal


def tied_count(scores: Mapping[str, float]) -> int:
    """Number of predictions that share their score with another candidate."""
    return sum(n for n in Counter(scores.values()).values() if n > 1)


def user_metrics(user: UserScores) -> UserMetrics:
    args = (user.scores, user.labels, user.tie_rank)
    return UserMetrics(
        user_id=user.user_id,
        auc=auc(user.scores, user.labels),
        mrr=mrr(*args),
        ndcg5=ndcg_at_5(*args),
        hit1=hit_at_1(*args),
        n_candidates=len(user.scores),
        n_tied=tied_count(user.scores),
        parse_failures=user.parse_failures,
        mean_score=statistics.fmean(user.scores.values()),
    )
