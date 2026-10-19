import pytest

from backend.metrics import auc


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
