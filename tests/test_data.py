from pathlib import Path

import pytest

from backend.data import (
    build_candidate_set,
    is_eligible,
    load_behaviors,
    load_news,
    sample_populations,
)
from backend.sample import is_synthetic
from tests.factories import make_impression


def test_synthetic_sample_loads_in_mind_format(sample_dir: Path) -> None:
    news = load_news(sample_dir / "news.tsv")
    behaviors = load_behaviors(sample_dir / "behaviors.tsv")

    assert len(news) == 300
    assert all(item.title.startswith("[SYNTHETIC]") for item in news.values())
    assert behaviors
    first = behaviors[0]
    assert all(news_id in news for news_id in first.history)
    assert {label for _, label in first.shown} <= {0, 1}
    assert is_synthetic(sample_dir)


def test_real_data_dir_is_not_synthetic(tmp_path: Path) -> None:
    assert not is_synthetic(tmp_path)


def test_duplicate_news_in_one_impression_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "behaviors.tsv"
    path.write_text("1\tU1\t11/15/2019 9:00:00 AM\tN1 N2\tN3-1 N4-0 N3-0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="N3"):
        load_behaviors(path)


def test_empty_history_and_crlf_are_parsed(tmp_path: Path) -> None:
    path = tmp_path / "behaviors.tsv"
    path.write_bytes(b"1\tU1\t11/15/2019 9:00:00 PM\t\tN3-1 N4-0\r\n")

    (imp,) = load_behaviors(path)

    assert imp.history == ()
    assert imp.shown == (("N3", 1), ("N4", 0))
    assert imp.time.hour == 21


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
    assert is_eligible(make_impression(history, clicks, non_clicks)) is eligible


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


CANDIDATES = {"seed": 5, "max_candidates": 8, "max_clicked": 2}


def test_candidate_set_composition() -> None:
    candidates = build_candidate_set(make_impression(clicks=3, non_clicks=10), **CANDIDATES)

    labels = [candidates.labels[i] for i in candidates.items]
    assert len(candidates.items) == 8
    assert sum(labels) == 2
    assert candidates.feed_ctr == pytest.approx(3 / 13)
    assert candidates.sample_ctr == pytest.approx(2 / 8)


def test_candidate_set_with_one_click_fills_with_non_clicks() -> None:
    candidates = build_candidate_set(make_impression(clicks=1, non_clicks=4), **CANDIDATES)

    assert len(candidates.items) == 5
    assert sum(candidates.labels.values()) == 1


def test_max_clicked_is_configurable() -> None:
    candidates = build_candidate_set(
        make_impression(clicks=5, non_clicks=10), seed=5, max_candidates=8, max_clicked=3
    )

    assert sum(candidates.labels.values()) == 3


def test_candidate_order_and_tie_break_are_seeded() -> None:
    imp = make_impression(clicks=2, non_clicks=10)

    a = build_candidate_set(imp, **CANDIDATES)
    b = build_candidate_set(imp, **CANDIDATES)
    c = build_candidate_set(imp, **{**CANDIDATES, "seed": 6})

    assert a == b
    assert a.items != c.items
    assert a.tie_rank != c.tie_rank
    assert sorted(a.tie_rank) == sorted(a.items)
    assert sorted(a.tie_rank.values()) == list(range(len(a.items)))


def test_tie_break_order_is_independent_of_display_order() -> None:
    users = [make_impression(user_id=f"U{n}") for n in range(200)]
    sets = [build_candidate_set(imp, **CANDIDATES) for imp in users]

    # Ranking by tie-break order must not just reproduce the display order...
    same = sum(sorted(c.items, key=c.tie_rank.__getitem__) == list(c.items) for c in sets)
    assert same <= 2
    # ...and each display slot's tie-rank should average near the middle (3.5 for 8 items).
    for slot in range(8):
        mean_rank = sum(c.tie_rank[c.items[slot]] for c in sets) / len(sets)
        assert 2.8 < mean_rank < 4.2
