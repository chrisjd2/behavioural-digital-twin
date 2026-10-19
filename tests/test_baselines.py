from datetime import datetime

import pytest

from backend.baselines import (
    BaselineContext,
    BetaPrior,
    PopularityIndex,
    build_popularity_index,
    fit_beta_prior,
)
from backend.data import DataSource, Impression, load_behaviors
from backend.experiment import ExperimentConfig
from backend.runner import sampled_populations

TEST_TIME = datetime(2019, 11, 15, 9, 0)


def shown_at(user_id: str, time: datetime, *shown: tuple[str, int]) -> Impression:
    return Impression(impression_id="x", user_id=user_id, time=time, history=(), shown=shown)


# Train: item A clicked 2 of 20 times, item B 6 of 20. Per-item CTRs 0.1 and 0.3.
# Method of moments: mean m = pooled CTR 8/40 = 0.2, variance v = 0.01,
# alpha + beta = m(1 - m)/v - 1 = 15, so alpha = 3, beta = 12.
TRAIN = [
    shown_at("T", datetime(2019, 11, 10), ("A", int(i < 2)), ("B", int(i < 6))) for i in range(20)
]
PRIOR = BetaPrior(alpha=3.0, beta=12.0)


def index(dev: list[Impression]) -> PopularityIndex:
    return build_popularity_index(TRAIN, dev, exclude_users=frozenset())


def test_beta_prior_is_fitted_to_train_ctr_by_method_of_moments() -> None:
    prior = index([]).prior

    assert prior.alpha == pytest.approx(PRIOR.alpha)
    assert prior.beta == pytest.approx(PRIOR.beta)


def test_items_with_few_shows_count_toward_the_mean_but_not_the_spread() -> None:
    # C (1 click in 1 show) moves the pooled CTR to 9/41; its noisy CTR of 1.0 is ignored.
    prior = fit_beta_prior({"A": (2, 20), "B": (6, 20), "C": (1, 1)})

    m = 9 / 41
    assert prior.alpha + prior.beta == pytest.approx(m * (1 - m) / 0.01 - 1)
    assert prior.alpha / (prior.alpha + prior.beta) == pytest.approx(m)


def test_beta_prior_refuses_train_without_spread() -> None:
    with pytest.raises(ValueError, match="Beta prior"):
        fit_beta_prior({"A": (2, 20), "B": (2, 20)})


def test_cold_start_item_gets_the_prior_mean() -> None:
    assert index([]).score("NEW", before=TEST_TIME) == pytest.approx(3 / 15)


def test_train_impressions_are_counted() -> None:
    assert index([]).score("A", before=TEST_TIME) == pytest.approx((2 + 3) / (20 + 15))


def test_only_dev_impressions_strictly_before_the_test_impression_count() -> None:
    dev = [
        shown_at("O", datetime(2019, 11, 15, 10, 0), ("X", 1)),
        shown_at("O", datetime(2019, 11, 15, 8, 0), ("X", 1)),
        shown_at("O", TEST_TIME, ("X", 1)),  # same second: not earlier
        shown_at("O", datetime(2019, 11, 15, 8, 30), ("X", 0)),
    ]

    popularity = index(dev)

    assert popularity.score("X", before=TEST_TIME) == pytest.approx((1 + 3) / (2 + 15))
    assert popularity.score("X", before=datetime(2019, 11, 15, 8, 0)) == pytest.approx(0.2)
    assert popularity.score("X", before=datetime(2019, 11, 16)) == pytest.approx((3 + 3) / (4 + 15))


def test_dev_and_train_impressions_from_sampled_users_are_excluded() -> None:
    dev = [shown_at("S1", datetime(2019, 11, 15, 8, 0), ("X", 1))]
    train = [*TRAIN, shown_at("S2", datetime(2019, 11, 10), ("A", 1))]

    popularity = build_popularity_index(train, dev, exclude_users=frozenset({"S1", "S2"}))

    assert popularity.score("X", before=TEST_TIME) == pytest.approx(0.2)
    assert popularity.score("A", before=TEST_TIME) == pytest.approx((2 + 3) / (20 + 15))


def test_run_context_excludes_every_dev_and_test_user(sample_source: DataSource) -> None:
    populations = sampled_populations(sample_source, ExperimentConfig(n_dev=10, n_test=20))
    sampled = {imp.user_id for imp in populations.dev + populations.test}
    dev = load_behaviors(sample_source.dev_dir / "behaviors.tsv")

    popularity = BaselineContext(sample_source, populations).popularity

    assert len(sampled) == 30
    dev_shows = sum(len(times) for times in popularity.dev_times.values())
    assert dev_shows == sum(len(imp.shown) for imp in dev if imp.user_id not in sampled)
    assert dev_shows < sum(len(imp.shown) for imp in dev)
