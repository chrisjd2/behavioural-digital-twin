import pytest

from backend.metrics import UserScores
from backend.report import (
    Calibration,
    Estimate,
    bootstrap_mean,
    build_report,
    outcome_bucket,
    paired_difference,
    summarise_arm,
    verdict,
)


def user(user_id: str, arm: str, click_score: float, parse_failures: int = 0) -> UserScores:
    """One click scored `click_score` against one non-click scored 50: AUC 1, 0.5 or 0."""
    return UserScores(
        user_id=user_id,
        arm=arm,
        scores={"p": click_score, "n": 50.0},
        labels={"p": 1, "n": 0},
        tie_rank={"n": 0, "p": 1},
        feed_ctr=0.04,
        sample_ctr=0.5,
        parse_failures=parse_failures,
    )


def test_bootstrap_of_constant_values_collapses_to_the_value() -> None:
    assert bootstrap_mean([0.7] * 10, seed=1) == Estimate(0.7, 0.7, 0.7)


def test_bootstrap_ci_matches_normal_approximation_and_is_seeded() -> None:
    values = [i / 100 for i in range(101)]  # mean 0.5, SD 0.293, SE 0.029 -> CI about +/-0.057

    estimate = bootstrap_mean(values, seed=1)

    assert estimate.mean == pytest.approx(0.5)
    assert estimate.low == pytest.approx(0.443, abs=0.01)
    assert estimate.high == pytest.approx(0.557, abs=0.01)
    assert bootstrap_mean(values, seed=1) == estimate
    assert bootstrap_mean(values, seed=2) != estimate


def test_bootstrap_rejects_no_users() -> None:
    with pytest.raises(ValueError, match="no users"):
        bootstrap_mean([], seed=1)


def test_summarise_arm_reports_means_tie_share_and_parse_failures() -> None:
    users = [user("U1", "D", 100), user("U2", "D", 50, parse_failures=1)]

    summary = summarise_arm("D", users, seed=1)

    assert summary.n == 2
    assert summary.metrics["auc"].mean == 0.75
    # U2 ties: the non-click wins the tie-break, so the click ranks 2nd.
    assert summary.metrics["mrr"].mean == 0.75
    assert summary.metrics["hit1"].mean == 0.5
    assert summary.tie_share == 2 / 4
    assert summary.parse_failure_rate == 1 / 4


def test_calibration_compares_mean_p_click_with_feed_and_sample_ctr() -> None:
    users = [user("U1", "D", 100), user("U2", "D", 50)]

    summary = summarise_arm("D", users, seed=1)

    assert summary.calibration == Calibration(mean_p_click=0.625, feed_ctr=0.04, sample_ctr=0.5)


def test_calibration_not_applicable_to_baselines() -> None:
    summary = summarise_arm("random", [user("U1", "random", 100)], seed=1)

    assert summary.calibration is None


def test_paired_difference_matches_users_by_id_not_position() -> None:
    arm = [user("U1", "D", 100), user("U2", "D", 0)]
    reference = [user("U2", "A", 50), user("U1", "A", 0)]

    diff = paired_difference(arm, reference, seed=1)

    assert diff.arm == "D"
    assert diff.reference == "A"
    assert diff.per_user == {"U1": 1.0, "U2": -0.5}
    assert diff.auc.mean == 0.25


def test_paired_difference_rejects_mismatched_users() -> None:
    with pytest.raises(ValueError, match="same users"):
        paired_difference([user("U1", "D", 100)], [user("U2", "A", 0)], seed=1)


def test_duplicate_user_in_an_arm_is_rejected() -> None:
    with pytest.raises(ValueError, match="U1"):
        summarise_arm("D", [user("U1", "D", 100), user("U1", "D", 0)], seed=1)


@pytest.mark.parametrize(
    ("estimate", "expected"),
    [
        (Estimate(0.05, 0.01, 0.09), "twins beat plain LLM"),
        (Estimate(0.03, 0.0, 0.06), "no detectable difference"),
        (Estimate(0.01, -0.02, 0.04), "no detectable difference"),
        (Estimate(-0.05, -0.09, -0.01), "plain LLM better"),
    ],
)
def test_verdict_follows_the_pre_registered_rule(estimate: Estimate, expected: str) -> None:
    assert verdict(estimate) == expected


@pytest.mark.parametrize(
    ("difference", "expected"),
    [
        (0.5, "Twin better"),
        (0.1, "About the same"),
        (0.0, "About the same"),
        (-0.1, "About the same"),
        (-0.5, "Plain LLM better"),
    ],
)
def test_outcome_bucket_thresholds(difference: float, expected: str) -> None:
    assert outcome_bucket(difference) == expected


# D - A AUC per user: U1 +1, U2 +0.5, U3 0, U4 -0.5, U5 -1. E ties every user.
A_D_SCORES = {"U1": (0, 100), "U2": (0, 50), "U3": (50, 50), "U4": (50, 0), "U5": (100, 0)}


def three_arms() -> dict[str, list[UserScores]]:
    return {
        "A": [user(uid, "A", a) for uid, (a, _) in A_D_SCORES.items()],
        "D": [user(uid, "D", d) for uid, (_, d) in A_D_SCORES.items()],
        "E": [user(uid, "E", 50) for uid in A_D_SCORES],
        "random": [user(uid, "random", 100) for uid in A_D_SCORES],
    }


def test_report_compares_every_arm_with_a_plus_d_minus_e() -> None:
    report = build_report(three_arms(), seed=1)

    pairs = [(d.arm, d.reference) for d in report.differences]
    assert pairs == [("D", "A"), ("E", "A"), ("random", "A"), ("D", "E")]
    d_minus_e = report.differences[-1]
    assert d_minus_e.per_user == {"U1": 0.5, "U2": 0.0, "U3": 0.0, "U4": -0.5, "U5": -0.5}


def test_report_primary_outcome_buckets_and_median_user() -> None:
    primary = build_report(three_arms(), seed=1).primary

    assert primary is not None
    assert primary.difference.mean == 0.0
    assert primary.verdict == "no detectable difference"
    assert primary.buckets == {"Twin better": 2, "About the same": 1, "Plain LLM better": 2}
    assert primary.median_user == "U3"


def test_median_user_tie_goes_to_the_first_user_id() -> None:
    results = {
        "A": [user(u, "A", 0) for u in ("U2", "U1", "U3")],
        "D": [user("U1", "D", 100), user("U2", "D", 100), user("U3", "D", 50)],
    }

    primary = build_report(results, seed=1).primary

    assert primary is not None
    assert primary.median_user == "U1"


def test_report_says_twins_win_when_ci_is_entirely_positive() -> None:
    users = [f"U{i}" for i in range(20)]
    results = {"A": [user(u, "A", 0) for u in users], "D": [user(u, "D", 100) for u in users]}

    primary = build_report(results, seed=1).primary

    assert primary is not None
    assert primary.difference == Estimate(1.0, 1.0, 1.0)
    assert primary.verdict == "twins beat plain LLM"


def test_report_omits_comparisons_whose_arms_are_missing() -> None:
    report = build_report({"random": three_arms()["random"]}, seed=1)

    assert set(report.arms) == {"random"}
    assert report.differences == []
    assert report.primary is None
