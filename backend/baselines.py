"""Non-AI baselines (ADR-0004): seeded random and time-respecting popularity."""

import random
import statistics
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from functools import cached_property

from backend.data import CandidateSet, DataSource, Impression, Populations, load_behaviors

# Items shown fewer times than this in train have CTRs too noisy to measure the prior's spread.
MIN_SHOWS_FOR_PRIOR_SPREAD = 20


@dataclass(frozen=True)
class BetaPrior:
    alpha: float
    beta: float


def fit_beta_prior(counts: Mapping[str, tuple[int, int]]) -> BetaPrior:
    """Method of moments on train (news ID -> (clicks, shows)).

    The prior mean is the pooled train CTR; its spread is the variance of per-item CTRs over
    items with at least MIN_SHOWS_FOR_PRIOR_SPREAD shows. That variance still contains binomial
    noise, so the fitted prior is, if anything, weaker than the true one.
    """
    clicks = sum(c for c, _ in counts.values())
    shows = sum(s for _, s in counts.values())
    ctrs = [c / s for c, s in counts.values() if s >= MIN_SHOWS_FOR_PRIOR_SPREAD]
    if len(ctrs) < 2:  # a variance needs two items
        raise ValueError("Cannot fit the Beta prior: too few train items with enough shows")
    mean, variance = clicks / shows, statistics.pvariance(ctrs)
    if variance == 0 or variance >= mean * (1 - mean):
        raise ValueError(f"Cannot fit the Beta prior: train CTR variance {variance:.4g}")
    strength = mean * (1 - mean) / variance - 1
    return BetaPrior(alpha=mean * strength, beta=(1 - mean) * strength)


@dataclass(frozen=True)
class PopularityIndex:
    """Train counts plus, per item, dev shows in time order with cumulative clicks."""

    prior: BetaPrior
    train: Mapping[str, tuple[int, int]]  # news ID -> (clicks, shows)
    dev_times: Mapping[str, list[datetime]]  # sorted show times
    dev_clicks: Mapping[str, list[int]]  # dev_clicks[i][k] = clicks among the first k shows

    def score(self, news_id: str, *, before: datetime) -> float:
        """Smoothed CTR from train plus dev shows strictly earlier than `before`."""
        clicks, shows = self.train.get(news_id, (0, 0))
        if times := self.dev_times.get(news_id):
            earlier = bisect_left(times, before)
            clicks += self.dev_clicks[news_id][earlier]
            shows += earlier
        return (clicks + self.prior.alpha) / (shows + self.prior.alpha + self.prior.beta)


def build_popularity_index(
    train: Iterable[Impression], dev: Iterable[Impression], *, exclude_users: frozenset[str]
) -> PopularityIndex:
    train_counts: dict[str, tuple[int, int]] = {}
    for imp in train:
        if imp.user_id not in exclude_users:
            for news_id, label in imp.shown:
                clicks, shows = train_counts.get(news_id, (0, 0))
                train_counts[news_id] = (clicks + label, shows + 1)

    dev_times: dict[str, list[datetime]] = defaultdict(list)
    dev_clicks: dict[str, list[int]] = defaultdict(lambda: [0])
    for imp in sorted(dev, key=lambda imp: imp.time):
        if imp.user_id not in exclude_users:
            for news_id, label in imp.shown:
                dev_times[news_id].append(imp.time)
                cumulative = dev_clicks[news_id]
                cumulative.append(cumulative[-1] + label)

    return PopularityIndex(fit_beta_prior(train_counts), train_counts, dev_times, dev_clicks)


@dataclass
class BaselineContext:
    """What a baseline may know beyond the candidate set; the index is built on first use."""

    source: DataSource
    populations: Populations

    @cached_property
    def popularity(self) -> PopularityIndex:
        sampled = self.populations.dev + self.populations.test
        return build_popularity_index(
            load_behaviors(self.source.train_dir / "behaviors.tsv"),
            load_behaviors(self.source.dev_dir / "behaviors.tsv"),
            exclude_users=frozenset(imp.user_id for imp in sampled),
        )


def random_scores(
    candidates: CandidateSet, *, seed: int, context: BaselineContext
) -> dict[str, float]:
    del context
    rng = random.Random(f"random:{seed}:{candidates.user_id}")
    return {news_id: rng.random() for news_id in candidates.items}


def popularity_scores(
    candidates: CandidateSet, *, seed: int, context: BaselineContext
) -> dict[str, float]:
    del seed
    return {
        news_id: context.popularity.score(news_id, before=candidates.time)
        for news_id in candidates.items
    }
