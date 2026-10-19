"""Step 0 Hook (ADR-0008): one dev-set reader, two headlines, their recent clicks, the reveal.

The example is picked by a person from `scripts.pick_hook`'s candidates and configured by id
in `config/hook.json`. It is illustrative, never evidence, so test and result runs are refused.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, ValidationError

from backend.config import Settings
from backend.data import NewsItem
from backend.errors import AppError
from backend.run_views import Headline, by_user, headlines, open_run, run_news
from backend.runner import Run, UserResult

HOOK_HISTORY = 6  # past clicks the toggle shows: the most recent ones
HOOK_ARMS = ("A", "D")  # plain LLM against the full twin


class HookConfig(BaseModel):
    """`config/hook.json`: ids only, so the repo holds no MIND text (ADR-0010)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    user_id: str
    clicked_id: str
    other_id: str


class HookCall(BaseModel):
    news_id: str
    p_click: float
    reaction: str


class HookPrediction(BaseModel):
    arm: str
    calls: list[HookCall]  # in headline order


class HookReveal(BaseModel):
    clicked_id: str
    predictions: list[HookPrediction]  # arm A, then arm D


class HookExample(BaseModel):
    """The presenter reveals the answer, so it is sent, but only under `reveal`."""

    run_id: str
    user_id: str
    mock: bool
    data_source: str
    headlines: list[Headline]  # the pair, in the run's display order
    history: list[Headline]  # the reader's most recent past clicks, oldest first
    reveal: HookReveal


def is_illustrative(run: Run) -> bool:
    """Only a dev run may be shown as an example; a test or result run is evidence."""
    return run.population == "dev" and not run.is_result


def recent_history(result: UserResult) -> tuple[str, ...]:
    return result.history[-HOOK_HISTORY:]


def read_config(path: Path) -> HookConfig:
    if not path.is_file():
        raise AppError(
            404,
            "hook_not_configured",
            f"No hook example configured: {path} is missing. Pick one with scripts.pick_hook.",
        )
    try:
        return HookConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise AppError(422, "hook_config_invalid", f"{path} is not a hook config: {exc}") from exc


def hook_example(settings: Settings, config: HookConfig) -> HookExample:
    run = open_run(settings, config.run_id)
    if not is_illustrative(run):
        raise AppError(
            409, "hook_not_dev", f"Run {run.run_id} is not a dev run; the hook is illustrative."
        )
    results = by_user(run).get(config.user_id)
    if results is None:
        raise AppError(404, "agent_not_found", f"User {config.user_id} is not in run {run.run_id}.")
    arms = {r.arm: r for r in results}
    if missing := [a for a in HOOK_ARMS if a not in arms]:
        raise AppError(409, "hook_arm_missing", f"Run {run.run_id} has no arm {missing[0]}.")
    first = arms[HOOK_ARMS[0]]  # arm A: labels, items and history are the same in every arm
    if first.labels.get(config.clicked_id) != 1 or first.labels.get(config.other_id) != 0:
        raise AppError(
            422,
            "hook_config_mismatch",
            f"In run {run.run_id}, {config.user_id} did not click {config.clicked_id} "
            f"and skip {config.other_id}.",
        )
    news = run_news(settings, run)
    pair = [i for i in first.items if i in (config.clicked_id, config.other_id)]
    shown = headlines(pair, news)
    if any(h.title is None for h in shown):
        raise AppError(
            422, "hook_headline_missing", f"A hook headline is not in {run.run_id}'s news."
        )
    return HookExample(
        run_id=run.run_id,
        user_id=config.user_id,
        mock=run.mock,
        data_source=run.data_source,
        headlines=shown,
        history=headlines(recent_history(first), news),
        reveal=HookReveal(
            clicked_id=config.clicked_id,
            predictions=[
                HookPrediction(
                    arm=arm,
                    calls=[
                        HookCall(
                            news_id=i, p_click=arms[arm].scores[i], reaction=arms[arm].reactions[i]
                        )
                        for i in pair
                    ],
                )
                for arm in HOOK_ARMS
            ],
        ),
    )


@dataclass(frozen=True)
class HookCandidate:
    user_id: str
    clicked_id: str
    other_id: str
    a_gap: float  # arm A's p_click for the other headline minus the clicked one (> 0: wrong)
    d_gap: float  # arm D's p_click for the clicked headline minus the other one (> 0: right)
    history_hits: int  # recent past clicks in the clicked headline's category
    history_misses: int  # recent past clicks in the other headline's category
    subcategory_hits: int  # recent past clicks in the clicked headline's subcategory too


def hook_candidates(run: Run, news: Mapping[str, NewsItem]) -> list[HookCandidate]:
    """ADR-0008's rule: arm A prefers the headline the reader skipped, arm D the one they
    clicked, and the recent clicks the toggle shows lean to the clicked one's topic: at least
    two in its category, more than in the other's, and at least one in its subcategory too
    (MIND's "news" category alone is too broad to see). Each reader's best pair only; most
    subcategory matches first, then the clearest category lean, then the widest disagreement."""
    plain, twin = HOOK_ARMS
    candidates: list[HookCandidate] = []
    for user_id, results in by_user(run).items():
        arms = {r.arm: r for r in results}
        if not all(a in arms for a in HOOK_ARMS):
            continue
        a, d = arms[plain], arms[twin]
        recent = [news[i] for i in recent_history(a) if i in news]
        clicked = [i for i in a.items if a.labels[i] == 1 and i in news]
        skipped = [i for i in a.items if a.labels[i] == 0 and i in news]
        for c in clicked:
            topic = (news[c].category, news[c].subcategory)
            hits = sum(n.category == topic[0] for n in recent)
            sub_hits = sum((n.category, n.subcategory) == topic for n in recent)
            for o in skipped:
                misses = sum(n.category == news[o].category for n in recent)
                a_gap, d_gap = a.scores[o] - a.scores[c], d.scores[c] - d.scores[o]
                if a_gap > 0 and d_gap > 0 and hits >= 2 and hits > misses and sub_hits >= 1:
                    candidates.append(
                        HookCandidate(user_id, c, o, a_gap, d_gap, hits, misses, sub_hits)
                    )
    ranked = sorted(
        candidates,
        key=lambda k: (
            -k.subcategory_hits,
            k.history_misses - k.history_hits,
            -(k.a_gap + k.d_gap),
            k.user_id,
            k.clicked_id,
            k.other_id,
        ),
    )
    best: dict[str, HookCandidate] = {}
    for k in ranked:
        best.setdefault(k.user_id, k)
    return list(best.values())


def hook_router(settings: Settings) -> APIRouter:
    """Read-only, so the same in `DEMO_MODE`."""
    router = APIRouter()

    @router.get("/api/hook")
    def hook() -> HookExample:  # pyright: ignore[reportUnusedFunction]
        return hook_example(settings, read_config(Path(settings.hook_config)))

    return router
