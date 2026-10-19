"""Step 4 Report: the run's stored pre-registered report, and one user's predictions.

The report is aggregate. The predictions endpoint is the only read endpoint that reveals click
labels, so the label-free Population endpoints in `run_views` stay that way.
"""

from collections.abc import Sequence
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ValidationError

from backend.config import Settings
from backend.errors import AppError
from backend.metrics import auc, rank
from backend.report import PROBABILITY_ARMS, Bucket, Verdict, outcome_bucket
from backend.run_views import Headline, by_user, headlines, open_run, run_news
from backend.runner import Run, UserResult

RELIABILITY_BINS = 10
BUCKETS: tuple[Bucket, ...] = ("Twin better", "About the same", "Plain LLM better")

NotResultReason = Literal["mock", "dev", "synthetic", "unfrozen"]
ArmKind = Literal["llm", "baseline"]


class Estimate(BaseModel):
    mean: float
    low: float
    high: float


class Calibration(BaseModel):
    mean_p_click: float  # 0-1
    feed_ctr: float
    sample_ctr: float


class _StoredArm(BaseModel):
    """`backend.report.ArmSummary` as the run file stores it."""

    arm: str
    n: int
    metrics: dict[str, Estimate]
    tie_share: float
    parse_failure_rate: float
    calibration: Calibration | None


class _StoredDifference(BaseModel):
    arm: str
    reference: str
    auc: Estimate
    per_user: dict[str, float]


class _StoredPrimary(BaseModel):
    difference: Estimate
    verdict: Verdict
    buckets: dict[Bucket, int]
    median_user: str


class _StoredReport(BaseModel):
    arms: dict[str, _StoredArm]
    differences: list[_StoredDifference]
    primary: _StoredPrimary | None


class ArmReport(_StoredArm):
    kind: ArmKind


class PairedDifference(BaseModel):
    arm: str
    reference: str
    auc: Estimate


class BucketUser(BaseModel):
    user_id: str
    d_minus_a: float


class OutcomeBucket(BaseModel):
    bucket: Bucket
    users: list[BucketUser]  # largest D - A first


class PrimaryOutcome(BaseModel):
    difference: Estimate
    verdict: Verdict  # stored by the run, never re-derived here
    buckets: list[OutcomeBucket]
    median_user: str


class ReliabilityBin(BaseModel):
    low: float  # p_click range, 0-1
    high: float
    n: int
    clicks: int
    mean_p_click: float | None  # None for an empty bin


class Reliability(BaseModel):
    arm: str
    bins: list[ReliabilityBin]


class RunReport(BaseModel):
    run_id: str
    population: str
    data_source: str
    model: str
    mock: bool
    is_result: bool
    not_result_reasons: list[NotResultReason]
    n_users: int
    arms: list[ArmReport]  # in run order
    differences: list[PairedDifference]
    primary: PrimaryOutcome | None  # D - A; None unless both arms ran
    reliability: list[Reliability]  # LLM arms only
    identity_screen: dict[str, dict[str, int]]


class CandidateOutcome(Headline):
    clicked: bool


class Prediction(BaseModel):
    news_id: str
    rank: int  # 1 = the arm's top pick, ties broken by the shared seeded order
    p_click: float | None  # 0-100; None for baselines, whose scores are not probabilities
    reaction: str | None


class ArmPredictions(BaseModel):
    arm: str
    kind: ArmKind
    auc: float
    predictions: list[Prediction]  # display order


class UserPredictions(BaseModel):
    """One user's predictions in every arm against the real clicks: Report's reveal."""

    run_id: str
    user_id: str
    mock: bool
    is_result: bool
    data_source: str
    d_minus_a: float | None
    bucket: Bucket | None
    candidates: list[CandidateOutcome]  # display order
    arms: list[ArmPredictions]


def not_result_reasons(run: Run) -> list[NotResultReason]:
    reasons: list[NotResultReason] = []
    if run.mock:
        reasons.append("mock")
    if run.population != "test":
        reasons.append("dev")
    if run.data_source != "mind":
        reasons.append("synthetic")
    if not run.is_result and not reasons:
        reasons.append("unfrozen")
    return reasons


def stored_report(run: Run) -> _StoredReport:
    if not run.metrics:
        raise AppError(409, "report_unavailable", f"Run {run.run_id} has no report.")
    try:
        return _StoredReport.model_validate(run.metrics)
    except ValidationError as exc:
        raise AppError(
            422, "incompatible_run", f"Run {run.run_id} stores its report in an older shape: {exc}"
        ) from exc


def _kind(arm: str) -> ArmKind:
    return "llm" if arm in PROBABILITY_ARMS else "baseline"


def _d_minus_a(report: _StoredReport) -> dict[str, float] | None:
    return next(
        (d.per_user for d in report.differences if (d.arm, d.reference) == ("D", "A")), None
    )


def _primary(stored: _StoredPrimary, per_user: dict[str, float]) -> PrimaryOutcome:
    ranked = sorted(per_user.items(), key=lambda kv: (-kv[1], kv[0]))
    return PrimaryOutcome(
        difference=stored.difference,
        verdict=stored.verdict,
        buckets=[
            OutcomeBucket(
                bucket=bucket,
                users=[
                    BucketUser(user_id=u, d_minus_a=d)
                    for u, d in ranked
                    if outcome_bucket(d) == bucket
                ],
            )
            for bucket in BUCKETS
        ],
        median_user=stored.median_user,
    )


def reliability(arm: str, users: Sequence[UserResult]) -> Reliability:
    """Predictions binned by p_click, with how many of each bin were really clicked."""
    binned: list[list[tuple[float, int]]] = [[] for _ in range(RELIABILITY_BINS)]
    for user in users:
        for news_id, score in user.scores.items():
            # Floor-divide the 0-100 score: 30 lands in 30-40, never 20-30 by float rounding.
            index = min(int(score * RELIABILITY_BINS // 100), RELIABILITY_BINS - 1)
            binned[index].append((score / 100, user.labels[news_id]))
    return Reliability(
        arm=arm,
        bins=[
            ReliabilityBin(
                low=i / RELIABILITY_BINS,
                high=(i + 1) / RELIABILITY_BINS,
                n=len(b),
                clicks=sum(label for _, label in b),
                mean_p_click=sum(p for p, _ in b) / len(b) if b else None,
            )
            for i, b in enumerate(binned)
        ],
    )


def run_report(run: Run) -> RunReport:
    stored = stored_report(run)
    per_user = _d_minus_a(stored)
    return RunReport(
        run_id=run.run_id,
        population=run.population,
        data_source=run.data_source,
        model=run.model,
        mock=run.mock,
        is_result=run.is_result,
        not_result_reasons=not_result_reasons(run),
        n_users=len({u.user_id for u in run.users}),
        arms=[
            ArmReport(**stored.arms[arm].model_dump(), kind=_kind(arm))
            for arm in run.arms
            if arm in stored.arms
        ],
        differences=[
            PairedDifference(arm=d.arm, reference=d.reference, auc=d.auc)
            for d in stored.differences
        ],
        primary=_primary(stored.primary, per_user) if stored.primary and per_user else None,
        reliability=[
            reliability(arm, [u for u in run.users if u.arm == arm])
            for arm in run.arms
            if _kind(arm) == "llm"
        ],
        identity_screen=run.identity_screen,
    )


def _arm_predictions(result: UserResult) -> ArmPredictions:
    order = rank(result.scores, result.tie_rank)
    llm = _kind(result.arm) == "llm"
    return ArmPredictions(
        arm=result.arm,
        kind=_kind(result.arm),
        auc=auc(result.scores, result.labels),
        predictions=[
            Prediction(
                news_id=news_id,
                rank=order.index(news_id) + 1,
                p_click=result.scores[news_id] if llm else None,
                reaction=result.reactions.get(news_id) if llm else None,
            )
            for news_id in result.items
        ],
    )


def user_predictions(settings: Settings, run: Run, user_id: str) -> UserPredictions:
    results = by_user(run).get(user_id)
    if results is None:
        raise AppError(404, "agent_not_found", f"User {user_id} is not in run {run.run_id}.")
    first = results[0]
    news = run_news(settings, run)
    per_user = _d_minus_a(stored_report(run)) or {}
    difference = per_user.get(user_id)
    return UserPredictions(
        run_id=run.run_id,
        user_id=user_id,
        mock=run.mock,
        is_result=run.is_result,
        data_source=run.data_source,
        d_minus_a=difference,
        bucket=outcome_bucket(difference) if difference is not None else None,
        candidates=[
            CandidateOutcome(**h.model_dump(), clicked=bool(first.labels[h.news_id]))
            for h in headlines(first.items, news)
        ],
        arms=[_arm_predictions(r) for r in sorted(results, key=lambda r: run.arms.index(r.arm))],
    )


def report_router(settings: Settings) -> APIRouter:
    """Read-only, so the same in `DEMO_MODE`."""
    router = APIRouter()

    @router.get("/api/run/{run_id}/report")
    def report(run_id: str) -> RunReport:  # pyright: ignore[reportUnusedFunction]
        return run_report(open_run(settings, run_id))

    @router.get("/api/run/{run_id}/user/{user_id}/predictions")
    def predictions(run_id: str, user_id: str) -> UserPredictions:  # pyright: ignore[reportUnusedFunction]
        return user_predictions(settings, open_run(settings, run_id), user_id)

    return router
