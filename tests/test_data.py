from datetime import datetime
from pathlib import Path

import pytest

from backend.data import (
    Impression,
    build_candidate_set,
    is_eligible,
    load_behaviors,
    load_news,
    sample_populations,
)
from backend.sample import write_synthetic_sample


@pytest.fixture(scope="module")
def sample_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("sample")
    write_synthetic_sample(directory, n_users=400, n_news=300, seed=1)
    return directory


def impression(
    history: int = 12, clicks: int = 2, non_clicks: int = 10, user_id: str = "U1"
) -> Impression:
    shown = tuple((f"C{i}", 1) for i in range(clicks)) + tuple(
        (f"N{i}", 0) for i in range(non_clicks)
    )
    return Impression(
        impression_id="1",
        user_id=user_id,
        time=datetime(2019, 11, 15, 9, 0),
        history=tuple(f"H{i}" for i in range(history)),
        shown=shown,
    )


def test_synthetic_sample_loads_in_mind_format(sample_dir: Path) -> None:
    news = load_news(sample_dir / "news.tsv")
    behaviors = load_behaviors(sample_dir / "behaviors.tsv")

    assert len(news) == 300
    assert all(item.title.startswith("[SYNTHETIC]") for item in news.values())
    assert behaviors
    first = behaviors[0]
    assert all(news_id in news for news_id in first.history)
    assert {label for _, label in first.shown} <= {0, 1}


@pytest.mark.parametrize(
    ("history", "clicks", "non_clicks", "eligible"),
    [
        (10, 1, 3, True),
        (9, 1, 3, False),
        (10, 0, 5, False),
        (10, 2, 2, False),
    ],
)
def test_eligibility(history: int, clicks: int, non_clicks: int, eligible: bool) -> None:
    assert is_eligible(impression(history, clicks, non_clicks)) is eligible


def test_populations_are_disjoint_deterministic_and_one_impression_per_user(
    sample_dir: Path,
) -> None:
    behaviors = load_behaviors(sample_dir / "behaviors.tsv")

    first = sample_populations(behaviors, n_dev=30, n_test=100, dev_seed=7, test_seed=11)
    again = sample_populations(behaviors, n_dev=30, n_test=100, dev_seed=7, test_seed=11)

    dev_users = {imp.user_id for imp in first.dev}
    test_users = {imp.user_id for imp in first.test}
    assert len(dev_users) == 30
    assert len(test_users) == 100
    assert not dev_users & test_users
    assert first == again
    assert all(is_eligible(imp) for imp in [*first.dev, *first.test])


def test_test_population_does_not_depend_on_dev_seed(sample_dir: Path) -> None:
    behaviors = load_behaviors(sample_dir / "behaviors.tsv")

    a = sample_populations(behaviors, n_dev=30, n_test=100, dev_seed=1, test_seed=11)
    b = sample_populations(behaviors, n_dev=30, n_test=100, dev_seed=2, test_seed=11)

    assert a.test == b.test
    assert a.dev != b.dev


def test_population_too_small_raises(sample_dir: Path) -> None:
    behaviors = load_behaviors(sample_dir / "behaviors.tsv")

    with pytest.raises(ValueError, match="eligible"):
        sample_populations(behaviors, n_dev=30, n_test=10_000, dev_seed=1, test_seed=2)


def test_candidate_set_composition() -> None:
    candidates = build_candidate_set(impression(clicks=3, non_clicks=10), seed=5, max_candidates=8)

    labels = [candidates.labels[i] for i in candidates.items]
    assert len(candidates.items) == 8
    assert sum(labels) == 2
    assert candidates.feed_ctr == pytest.approx(3 / 13)
    assert candidates.sample_ctr == pytest.approx(2 / 8)


def test_candidate_set_with_one_click_fills_with_non_clicks() -> None:
    candidates = build_candidate_set(impression(clicks=1, non_clicks=4), seed=5, max_candidates=8)

    assert len(candidates.items) == 5
    assert sum(candidates.labels.values()) == 1


def test_candidate_order_and_tie_break_are_seeded_and_independent() -> None:
    imp = impression(clicks=2, non_clicks=10)

    a = build_candidate_set(imp, seed=5, max_candidates=8)
    b = build_candidate_set(imp, seed=5, max_candidates=8)
    c = build_candidate_set(imp, seed=6, max_candidates=8)

    assert a == b
    assert a.items != c.items or a.tie_rank != c.tie_rank
    assert sorted(a.tie_rank) == sorted(a.items)
    assert sorted(a.tie_rank.values()) == list(range(len(a.items)))
    tie_order = sorted(a.items, key=lambda i: a.tie_rank[i])
    assert tie_order != list(a.items) or len(a.items) < 3
