import math

import pytest

from backend.metrics import (
    UserMetrics,
    UserScores,
    auc,
    hit_at_1,
    mrr,
    ndcg_at_5,
    rank,
    tied_count,
    user_metrics,
)


def test_auc_perfect_ranking() -> None:
    assert auc({"a": 0.9, "b": 0.1, "c": 0.2}, {"a": 1, "b": 0, "c": 0}) == 1.0


def test_auc_worst_ranking() -> None:
    assert auc({"a": 0.0, "b": 0.5, "c": 0.7}, {"a": 1, "b": 0, "c": 0}) == 0.0


def test_auc_hand_computed_two_positives() -> None:
    # Pairs (pos, neg): (a,c) win, (a,d) win, (b,c) loss, (b,d) win -> 3/4
    scores = {"a": 90, "b": 30, "c": 50, "d": 10}
    labels = {"a": 1, "b": 1, "c": 0, "d": 0}

    assert auc(scores, labels) == 0.75


def test_auc_ties_get_half_credit() -> None:
    # (a,b) tie -> 0.5, (a,c) win -> 1 -> 1.5/2
    assert auc({"a": 20, "b": 20, "c": 10}, {"a": 1, "b": 0, "c": 0}) == 0.75


def test_auc_all_tied_is_chance() -> None:
    assert auc({"a": 5, "b": 5, "c": 5}, {"a": 1, "b": 0, "c": 0}) == 0.5


def test_auc_requires_both_classes() -> None:
    with pytest.raises(ValueError, match="both"):
        auc({"a": 1, "b": 2}, {"a": 1, "b": 1})


# Rank metrics. Ranking is by score, ties broken by tie_rank (ADR-0005), never by position.
SCORES = {"a": 0.9, "b": 0.5, "c": 0.7, "d": 0.1}
IN_ORDER = {"a": 0, "b": 1, "c": 2, "d": 3}


def test_rank_orders_by_score_then_tie_rank() -> None:
    assert rank({"a": 50, "b": 50, "c": 90}, {"a": 1, "b": 0, "c": 2}) == ["c", "b", "a"]


def test_single_positive_ranked_third() -> None:
    # Ranking a, c, b, d; the click (b) is 3rd.
    labels = {"a": 0, "b": 1, "c": 0, "d": 0}

    assert mrr(SCORES, labels, IN_ORDER) == pytest.approx(1 / 3)
    assert hit_at_1(SCORES, labels, IN_ORDER) == 0.0
    assert ndcg_at_5(SCORES, labels, IN_ORDER) == pytest.approx(1 / math.log2(4))


def test_two_positives_ranked_first_and_fourth() -> None:
    labels = {"a": 1, "b": 0, "c": 0, "d": 1}

    assert mrr(SCORES, labels, IN_ORDER) == 1.0
    assert hit_at_1(SCORES, labels, IN_ORDER) == 1.0
    expected = (1 + 1 / math.log2(5)) / (1 + 1 / math.log2(3))
    assert ndcg_at_5(SCORES, labels, IN_ORDER) == pytest.approx(expected)


def test_perfect_ranking_scores_one() -> None:
    labels = {"a": 1, "b": 0, "c": 1, "d": 0}

    assert ndcg_at_5(SCORES, labels, IN_ORDER) == pytest.approx(1.0)
    assert mrr(SCORES, labels, IN_ORDER) == 1.0


def test_tie_broken_by_tie_rank_not_display_order() -> None:
    scores = {"a": 50, "b": 50, "c": 10}  # a is displayed first
    labels = {"a": 0, "b": 1, "c": 0}

    b_first = {"a": 1, "b": 0, "c": 2}
    assert hit_at_1(scores, labels, b_first) == 1.0
    assert mrr(scores, labels, b_first) == 1.0

    a_first = {"a": 0, "b": 1, "c": 2}
    assert hit_at_1(scores, labels, a_first) == 0.0
    assert mrr(scores, labels, a_first) == 0.5
    assert ndcg_at_5(scores, labels, a_first) == pytest.approx(1 / math.log2(3))


def test_click_below_top_five_gets_no_ndcg_but_keeps_mrr() -> None:
    scores = {f"n{i}": 10.0 - i for i in range(7)}
    labels = {k: int(k == "n5") for k in scores}  # 6th place
    tie_rank = {k: i for i, k in enumerate(scores)}

    assert ndcg_at_5(scores, labels, tie_rank) == 0.0
    assert mrr(scores, labels, tie_rank) == pytest.approx(1 / 6)


def test_rank_metrics_require_a_click() -> None:
    no_clicks = dict.fromkeys(SCORES, 0)
    for metric in (mrr, ndcg_at_5, hit_at_1):
        with pytest.raises(ValueError, match="click"):
            metric(SCORES, no_clicks, IN_ORDER)


def test_tied_count_counts_every_prediction_sharing_a_score() -> None:
    assert tied_count({"a": 50, "b": 50, "c": 10, "d": 10, "e": 3}) == 4
    assert tied_count({"a": 1, "b": 2}) == 0


def test_user_metrics_combines_every_per_user_metric() -> None:
    user = UserScores(
        user_id="U1",
        arm="D",
        scores={"a": 50, "b": 50, "c": 20},
        labels={"a": 0, "b": 1, "c": 0},
        tie_rank={"a": 1, "b": 0, "c": 2},
        feed_ctr=0.04,
        sample_ctr=1 / 3,
        parse_failures=1,
    )

    assert user_metrics(user) == UserMetrics(
        user_id="U1",
        auc=0.75,
        mrr=1.0,
        ndcg5=1.0,
        hit1=1.0,
        n_candidates=3,
        n_tied=2,
        parse_failures=1,
        mean_score=40.0,
    )


def test_user_scores_parse_failures_default_to_zero() -> None:
    user = UserScores("U1", "random", {"a": 1.0}, {"a": 1}, {"a": 0}, 0.1, 1.0)

    assert user.parse_failures == 0
