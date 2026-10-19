"""Run arms over a population, emitting events for the headless table and the live feed."""

import asyncio
import hashlib
import statistics
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from backend.arms import (
    arm_a_messages,
    parse_reactions,
    prompt_hashes,
    request_payload,
    retry_messages,
)
from backend.data import (
    CandidateSet,
    DataSource,
    build_candidate_set,
    load_behaviors,
    load_news,
    sample_populations,
)
from backend.experiment import ARMS as BASELINES, ExperimentConfig, Population
from backend.llm import LLMClient, mock_backend
from backend.metrics import auc

LLM_ARMS = {"A": arm_a_messages}


@dataclass(frozen=True)
class RunEvent:
    kind: str  # call_started | reaction | arm_progress | run_complete
    data: dict[str, object]


@dataclass(frozen=True)
class UserResult:
    user_id: str
    arm: str
    items: tuple[str, ...]
    scores: dict[str, float]
    reactions: dict[str, str]
    labels: dict[str, int]
    tie_rank: dict[str, int]
    feed_ctr: float
    sample_ctr: float
    parse_failures: int = 0


@dataclass
class Run:
    run_id: str
    created: str
    population: str
    arms: list[str]
    config: dict[str, object]
    model: str
    base_url: str
    mock: bool
    data_source: str
    prompt_hashes: dict[str, str]
    git_sha: str
    users: list[UserResult] = field(default_factory=list)
    events: list[RunEvent] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)
    metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    unfrozen_override: bool = False


def git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown (not a git checkout)"


def candidate_sets(
    source: DataSource, config: ExperimentConfig, population: Population
) -> list[CandidateSet]:
    populations = sample_populations(
        load_behaviors(source.dev_dir / "behaviors.tsv"),
        n_dev=config.n_dev,
        n_test=config.n_test,
        dev_seed=config.dev_seed,
        test_seed=config.test_seed,
    )
    return [
        build_candidate_set(
            imp,
            seed=config.candidate_seed,
            max_candidates=config.max_candidates,
            max_clicked=config.max_clicked,
        )
        for imp in (populations.dev if population == "dev" else populations.test)
    ]


async def run_experiment(  # noqa: PLR0913 — keyword-only run options
    source: DataSource,
    config: ExperimentConfig,
    *,
    population: Population,
    arms: list[str],
    client: LLMClient,
    base_rate_hint: bool,
    on_event: Callable[[RunEvent], object] | None = None,
) -> Run:
    unknown = sorted(set(arms) - set(LLM_ARMS) - set(BASELINES))
    if unknown:
        raise ValueError(f"Unknown arm(s): {', '.join(unknown)}")

    created = datetime.now(UTC)
    sets = candidate_sets(source, config, population)
    news = load_news(source.dev_dir / "news.tsv")
    digest = hashlib.sha256(f"{created.isoformat()}{arms}".encode()).hexdigest()[:6]
    run = Run(
        run_id=f"{created:%Y%m%d-%H%M%S}-{population}-{digest}",
        created=created.isoformat(),
        population=population,
        arms=arms,
        config=asdict(config),
        model=client.model,
        base_url=client.base_url,
        mock=client.backend is mock_backend,
        data_source=source.kind,
        prompt_hashes=prompt_hashes(),
        git_sha=git_sha(),
    )

    def emit(kind: str, **data: object) -> None:
        event = RunEvent(kind, data)
        run.events.append(event)
        if on_event:
            on_event(event)

    def result(arm: str, c: CandidateSet, scores: dict[str, float], **extra: object) -> UserResult:
        return UserResult(
            user_id=c.user_id,
            arm=arm,
            items=c.items,
            scores=scores,
            labels=c.labels,
            tie_rank=c.tie_rank,
            feed_ctr=c.feed_ctr,
            sample_ctr=c.sample_ctr,
            **extra,  # pyright: ignore[reportArgumentType]
        )

    for arm in arms:
        if arm in BASELINES:
            run.users.extend(
                result(arm, c, BASELINES[arm](c, seed=config.baseline_seed), reactions={})
                for c in sets
            )
            emit("arm_progress", arm=arm, done=len(sets), total=len(sets))
            continue

        done = 0

        async def score(c: CandidateSet, arm: str = arm) -> UserResult:
            nonlocal done
            emit("call_started", user_id=c.user_id, arm=arm)
            messages = LLM_ARMS[arm](c, news, base_rate_hint=base_rate_hint)
            completion = await client.complete(request_payload(messages))
            parsed = parse_reactions(completion.content, c.items)
            if not parsed.ok:
                retry = request_payload(retry_messages(messages, completion.content))
                parsed = parse_reactions((await client.complete(retry)).content, c.items)
            for news_id in c.items:
                emit(
                    "reaction",
                    user_id=c.user_id,
                    arm=arm,
                    news_id=news_id,
                    headline=news[news_id].title,
                    reaction=parsed.reactions[news_id],
                    p_click=parsed.p_click[news_id],
                    clicked=c.labels[news_id],
                )
            done += 1
            emit("arm_progress", arm=arm, done=done, total=len(sets))
            return result(
                arm,
                c,
                parsed.p_click,
                reactions=parsed.reactions,
                parse_failures=len(parsed.missing),
            )

        run.users.extend(await asyncio.gather(*(score(c) for c in sets)))

    run.counters = asdict(client.counters)
    run.metrics = summarise(run.users)
    emit("run_complete", run_id=run.run_id)
    return run


def summarise(users: list[UserResult]) -> dict[str, dict[str, float]]:
    """Interim per-arm summary; the full report (CIs, comparisons) comes from #7."""
    summary: dict[str, dict[str, float]] = {}
    for arm in dict.fromkeys(u.arm for u in users):
        rows = [u for u in users if u.arm == arm]
        predictions = sum(len(u.items) for u in rows)
        summary[arm] = {
            "n": len(rows),
            "mean_auc": statistics.fmean(auc(u.scores, u.labels) for u in rows),
            "parse_failure_rate": sum(u.parse_failures for u in rows) / predictions,
        }
    return summary
