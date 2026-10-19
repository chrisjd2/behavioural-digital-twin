"""Run arms over a population, emitting events for the headless table and the live feed."""

import asyncio
import hashlib
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from backend.arms import (
    ARM_SPECS,
    ArmResources,
    LLMOptions,
    parse_reactions,
    request_payload,
    retry_messages,
)
from backend.data import (
    CandidateSet,
    DataSource,
    NewsItem,
    build_candidate_set,
    date_range,
    load_behaviors,
    load_news,
    sample_populations,
)
from backend.experiment import ARMS as BASELINES, ExperimentConfig, Population
from backend.freeze import REPO_ROOT, fingerprint, freeze_problem, tag_sha
from backend.llm import LLMClient, mock_backend
from backend.metrics import UserScores
from backend.report import build_report
from backend.retrieval import EmbeddingStore, Retriever

LLM_ARMS = ARM_SPECS
RETRIEVAL_ARMS = frozenset({"C", "D", "E"})


class FreezeError(Exception):
    """The test population was requested without the frozen setup (ADR-0001)."""


@dataclass(frozen=True)
class RunEvent:
    seq: int
    at: str  # ISO timestamp, for replay pacing
    kind: str  # call_started | reaction | arm_progress | run_complete
    data: dict[str, object]


@dataclass(frozen=True, kw_only=True)
class UserResult(UserScores):
    """One user's scores in one arm, plus what the feed and run file show."""

    items: tuple[str, ...]  # display order
    reactions: dict[str, str]
    knowledge: dict[str, object]  # what this agent knew (memories, persona, profile)
    history: tuple[str, ...]  # the user's clicks before the impression, for the UI panel


@dataclass
class Run:
    run_id: str
    created: str
    population: str
    arms: list[str]
    config: dict[str, object]
    model: str
    base_url: str
    options: dict[str, object]
    mock: bool
    data_source: str
    retrieval: str  # "embeddings:<model>:<dims>", "tfidf" or "none"
    date_ranges: dict[str, list[str]]
    fingerprint: dict[str, object]
    git_sha: str
    freeze_tag_sha: str | None
    unfrozen_override: bool
    is_result: bool  # frozen, real model, real MIND, test population
    users: list[UserResult] = field(default_factory=list)
    events: list[RunEvent] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)
    metrics: dict[str, object] = field(default_factory=dict)  # asdict(report.Report)


def git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
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


def check_embeddings(
    options: LLMOptions, embeddings: EmbeddingStore | None, *, base_url: str
) -> None:
    """The retrieval actually used must be the one the options (and fingerprint) describe."""
    wanted = (base_url, options.embed_model, options.embed_dimensions)
    if not options.embed_model:
        if embeddings is not None:
            raise ValueError("An embedding store was given but EMBED_MODEL is empty (TF-IDF)")
        return
    if embeddings is None:
        raise ValueError(f"EMBED_MODEL={options.embed_model} but no embedding store was given")
    if (embeddings.base_url, embeddings.model, embeddings.dimensions) != wanted:
        raise ValueError("The embedding store does not match the embedding options")


async def make_retriever(  # noqa: PLR0913 - the run's pieces retrieval depends on
    arms: list[str],
    sets: list[CandidateSet],
    news: Mapping[str, NewsItem],
    *,
    client: LLMClient,
    options: LLMOptions,
    embeddings: EmbeddingStore | None,
    mock: bool,
) -> Retriever | None:
    """One retriever per run; every item the population needs is embedded up front."""
    if not RETRIEVAL_ARMS & set(arms):
        return None
    if not mock:
        check_embeddings(options, embeddings, base_url=client.base_url)
    # Mock runs never call the embedding API: TF-IDF instead (ADR-0006).
    retriever = Retriever(news, None if mock else embeddings)
    await retriever.prepare([i for c in sets for i in (*c.history, *c.items)])
    return retriever


def check_freeze(
    current: dict[str, object],
    source: DataSource,
    population: Population,
    *,
    allow_unfrozen: bool,
) -> str | None:
    """Raise unless this run may go ahead; return why it is not a frozen run (or None)."""
    if population != "test":
        return "not the test population"
    problem = freeze_problem(current)
    if problem and not allow_unfrozen:
        raise FreezeError(f"Refusing to run the test set: {problem} (ADR-0001).")
    if problem and source.kind == "mind" and tag_sha() is None:
        # Peeking at real test data before freezing would defeat the pre-registration.
        raise FreezeError("--allow-unfrozen is refused on real MIND until the freeze tag exists.")
    return problem


async def run_experiment(  # noqa: PLR0913 — keyword-only run options
    source: DataSource,
    config: ExperimentConfig,
    *,
    population: Population,
    arms: list[str],
    client: LLMClient,
    options: LLMOptions,
    embeddings: EmbeddingStore | None = None,
    allow_unfrozen: bool = False,
    on_event: Callable[[RunEvent], object] | None = None,
) -> Run:
    unknown = sorted(set(arms) - set(LLM_ARMS) - set(BASELINES))
    if unknown:
        raise ValueError(f"Unknown arm(s): {', '.join(unknown)}")

    mock = client.backend is mock_backend
    current = fingerprint(
        source, config, model=client.model, base_url=client.base_url, options=options
    )
    problem = check_freeze(current, source, population, allow_unfrozen=allow_unfrozen)

    created = datetime.now(UTC)
    sets = candidate_sets(source, config, population)
    news = load_news(source.dev_dir / "news.tsv")
    retriever = await make_retriever(
        arms, sets, news, client=client, options=options, embeddings=embeddings, mock=mock
    )
    resources = ArmResources(retriever=retriever)
    digest = hashlib.sha256(f"{created.isoformat()}{arms}".encode()).hexdigest()[:6]
    run = Run(
        run_id=f"{created:%Y%m%d-%H%M%S}-{population}-{digest}",
        created=created.isoformat(),
        population=population,
        arms=arms,
        config=asdict(config),
        model=client.model,
        base_url=client.base_url,
        options=asdict(options),
        mock=mock,
        data_source=source.kind,
        retrieval=retriever.method if retriever else "none",
        date_ranges={
            split: [t.isoformat() for t in date_range(load_behaviors(d / "behaviors.tsv"))]
            for split, d in (("train", source.train_dir), ("dev", source.dev_dir))
        },
        fingerprint=current,
        git_sha=git_sha(),
        freeze_tag_sha=tag_sha(),
        unfrozen_override=allow_unfrozen and problem is not None,
        is_result=problem is None and not mock and source.kind == "mind",
    )

    def emit(kind: str, **data: object) -> None:
        event = RunEvent(len(run.events), datetime.now(UTC).isoformat(), kind, data)
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
            history=c.history,
            **extra,  # pyright: ignore[reportArgumentType]
        )

    for arm in arms:
        if arm in BASELINES:
            run.users.extend(
                result(
                    arm, c, BASELINES[arm](c, seed=config.baseline_seed), reactions={}, knowledge={}
                )
                for c in sets
            )
            emit("arm_progress", arm=arm, done=len(sets), total=len(sets))
            continue

        done = 0

        async def score(c: CandidateSet, arm: str = arm) -> UserResult:
            nonlocal done
            emit("call_started", user_id=c.user_id, arm=arm)
            spec = LLM_ARMS[arm]
            knowledge = await spec.prepare(c, resources)
            messages = spec.render(c, news, knowledge, base_rate_hint=options.base_rate_hint)
            completion = await client.complete(request_payload(messages, options))
            parsed = parse_reactions(completion.content, c.items)
            if not parsed.ok:
                retry = request_payload(retry_messages(messages, completion.content), options)
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
                knowledge=knowledge,
                parse_failures=len(parsed.missing),
            )

        # TaskGroup cancels the remaining calls if one fails for good.
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(score(c)) for c in sets]
        run.users.extend(task.result() for task in tasks)

    run.counters = asdict(client.counters)
    if retriever and retriever.store:
        run.counters["embedding_calls"] = retriever.store.calls
    by_arm = {arm: [u for u in run.users if u.arm == arm] for arm in arms}
    run.metrics = asdict(build_report(by_arm, seed=config.bootstrap_seed))
    emit("run_complete", run_id=run.run_id)
    return run
