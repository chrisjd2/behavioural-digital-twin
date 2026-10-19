"""Aggregate per-user metrics into the pre-registered report (ADR-0001, ADR-0005)."""

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from backend.metrics import UserMetrics, UserScores, user_metrics

BOOTSTRAP_RESAMPLES = 10_000
BUCKET_THRESHOLD = 0.1
PROBABILITY_ARMS = frozenset({"A", "B", "C", "D", "E"})  # p_click 0-100; baselines are not
METRICS = ("auc", "mrr", "ndcg5", "hit1")

Verdict = Literal["twins beat plain LLM", "no detectable difference", "plain LLM better"]
Bucket = Literal["Twin better", "About the same", "Plain LLM better"]


@dataclass(frozen=True)
class Estimate:
    mean: float
    low: float
    high: float


@dataclass(frozen=True)
class Calibration:
    mean_p_click: float  # as a probability, 0-1
    feed_ctr: float
    sample_ctr: float


@dataclass(frozen=True)
class ArmSummary:
    arm: str
    n: int
    metrics: dict[str, Estimate]
    tie_share: float
    parse_failure_rate: float
    calibration: Calibration | None  # None for baselines, whose scores aren't probabilities


@dataclass(frozen=True)
class PairedDifference:
    arm: str
    reference: str
    auc: Estimate
    per_user: dict[str, float]


@dataclass(frozen=True)
class PrimaryOutcome:
    difference: Estimate
    verdict: Verdict
    buckets: dict[Bucket, int]
    median_user: str


@dataclass(frozen=True)
class Report:
    arms: dict[str, ArmSummary]
    differences: list[PairedDifference]
    primary: PrimaryOutcome | None  # D - A; None unless both arms ran


def bootstrap_mean(values: Sequence[float], *, seed: int) -> Estimate:
    """Mean with a percentile 95% CI from resampling users with replacement."""
    if not values:
        raise ValueError("Cannot bootstrap no users")
    data = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    means = data[rng.integers(0, len(data), size=(BOOTSTRAP_RESAMPLES, len(data)))].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return Estimate(statistics.fmean(values), float(low), float(high))


def _by_user(users: Sequence[UserScores]) -> dict[str, UserScores]:
    by_user: dict[str, UserScores] = {}
    for u in users:
        if u.user_id in by_user:
            raise ValueError(f"User {u.user_id} appears twice in arm {u.arm}")
        by_user[u.user_id] = u
    return by_user


def summarise_arm(arm: str, users: Sequence[UserScores], *, seed: int) -> ArmSummary:
    per_user = [user_metrics(u) for u in _by_user(users).values()]
    n_predictions = sum(m.n_candidates for m in per_user)

    def mean_of(metric: str) -> Estimate:
        return bootstrap_mean([getattr(m, metric) for m in per_user], seed=seed)

    return ArmSummary(
        arm=arm,
        n=len(per_user),
        metrics={metric: mean_of(metric) for metric in METRICS},
        tie_share=sum(m.n_tied for m in per_user) / n_predictions,
        parse_failure_rate=sum(m.parse_failures for m in per_user) / n_predictions,
        calibration=_calibration(users, per_user) if arm in PROBABILITY_ARMS else None,
    )


def _calibration(users: Sequence[UserScores], per_user: Sequence[UserMetrics]) -> Calibration:
    return Calibration(
        mean_p_click=statistics.fmean(m.mean_score / 100 for m in per_user),
        feed_ctr=statistics.fmean(u.feed_ctr for u in users),
        sample_ctr=statistics.fmean(u.sample_ctr for u in users),
    )


def paired_difference(
    arm: Sequence[UserScores], reference: Sequence[UserScores], *, seed: int
) -> PairedDifference:
    """Per-user AUC difference arm - reference, matched by user ID."""
    arm_users, ref_users = _by_user(arm), _by_user(reference)
    if set(arm_users) != set(ref_users):
        raise ValueError("Paired arms must cover the same users")
    per_user = {
        user_id: user_metrics(arm_users[user_id]).auc - user_metrics(ref_users[user_id]).auc
        for user_id in sorted(arm_users)
    }
    estimate = bootstrap_mean(list(per_user.values()), seed=seed)
    return PairedDifference(
        arm=arm[0].arm, reference=reference[0].arm, auc=estimate, per_user=per_user
    )


def verdict(difference: Estimate) -> Verdict:
    """ADR-0001: twins win only if the CI on D - A excludes 0 and is positive."""
    if difference.low > 0:
        return "twins beat plain LLM"
    if difference.high < 0:
        return "plain LLM better"
    return "no detectable difference"


def outcome_bucket(difference: float) -> Bucket:
    # AUCs are ratios of small counts; round so 0.8 - 0.7 lands on the boundary, not past it.
    difference = round(difference, 9)
    if difference > BUCKET_THRESHOLD:
        return "Twin better"
    if difference < -BUCKET_THRESHOLD:
        return "Plain LLM better"
    return "About the same"


def _primary(d_minus_a: PairedDifference) -> PrimaryOutcome:
    per_user = d_minus_a.per_user
    median = statistics.median(per_user.values())
    buckets: dict[Bucket, int] = {"Twin better": 0, "About the same": 0, "Plain LLM better": 0}
    for difference in per_user.values():
        buckets[outcome_bucket(difference)] += 1
    return PrimaryOutcome(
        difference=d_minus_a.auc,
        verdict=verdict(d_minus_a.auc),
        buckets=buckets,
        median_user=min(per_user, key=lambda u: (abs(per_user[u] - median), u)),
    )


def build_report(results: Mapping[str, Sequence[UserScores]], *, seed: int) -> Report:
    """Summaries per arm, paired AUC differences vs A and D - E, and the primary D - A outcome.

    Comparisons whose arms did not run are omitted.
    """
    pairs = [(arm, "A") for arm in results if arm != "A" and "A" in results]
    if "D" in results and "E" in results:
        pairs.append(("D", "E"))
    differences = [paired_difference(results[a], results[b], seed=seed) for a, b in pairs]
    d_minus_a = next((d for d in differences if (d.arm, d.reference) == ("D", "A")), None)
    return Report(
        arms={arm: summarise_arm(arm, users, seed=seed) for arm, users in results.items()},
        differences=differences,
        primary=_primary(d_minus_a) if d_minus_a else None,
    )
