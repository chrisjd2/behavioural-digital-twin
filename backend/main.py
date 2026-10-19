from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from backend.config import Settings, get_settings
from backend.data import (
    DataKind,
    NewsItem,
    available_sources,
    is_eligible,
    load_behaviors_cached,
    load_news_cached,
    resolve_data_source,
)
from backend.experiment import ExperimentConfig
from backend.runner import LLM_ARMS, Run, UserResult, candidate_sets, sampled_populations
from backend.runs import RUNS_SUBDIR, RunFileError, list_runs, load_run_cached, run_path

DEFAULTS = ExperimentConfig()


class AppError(Exception):
    """An error with an HTTP status and a stable machine-readable code."""

    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


class ExperimentRequest(BaseModel):
    """What Step 1 Seed may vary; everything else keeps the `ExperimentConfig` defaults."""

    n_users: int = Field(default=DEFAULTS.n_dev, ge=1, le=5000)
    seed: int = DEFAULTS.dev_seed
    max_candidates: int = Field(default=DEFAULTS.max_candidates, ge=2, le=20)


class Status(BaseModel):
    mock: bool
    demo_mode: bool
    model: str
    data_source: DataKind
    call_count: int
    experiment_defaults: ExperimentRequest


class CategoryCount(BaseModel):
    category: str
    users: int  # sampled users with at least one past click in this category


class PopulationSummary(BaseModel):
    population: Literal["dev"]
    data_source: DataKind
    n_users: int
    seed: int
    max_candidates: int
    user_ids: list[str]  # in sampling order
    eligible_users: int  # outside the held-out test set
    n_candidates: int
    categories: list[CategoryCount]
    mean_feed_ctr: float
    mean_sample_ctr: float


def summarise_population(settings: Settings, request: ExperimentRequest) -> PopulationSummary:
    """Preview the dev population the runner would sample. Never the test population."""
    source = resolve_data_source(Path(settings.data_dir))
    if source.kind == "none":
        raise AppError(409, "no_data", "No MIND data or synthetic sample found in DATA_DIR.")

    config = replace(
        DEFAULTS,
        n_dev=request.n_users,
        dev_seed=request.seed,
        max_candidates=request.max_candidates,
    )
    try:
        populations = sampled_populations(source, config)
    except ValueError as exc:
        raise AppError(422, "not_enough_users", str(exc)) from exc
    sets = candidate_sets(populations, config, "dev")

    impressions = load_behaviors_cached(source.dev_dir / "behaviors.tsv")
    eligible = len({i.user_id for i in impressions if is_eligible(i)}) - len(populations.test)
    news = load_news_cached(source.dev_dir / "news.tsv")
    readers: Counter[str] = Counter()
    for impression in populations.dev:
        # History items missing from news.tsv have no category to count.
        readers.update({news[n].category for n in impression.history if n in news})

    return PopulationSummary(
        population="dev",
        data_source=source.kind,
        n_users=len(sets),
        seed=request.seed,
        max_candidates=request.max_candidates,
        user_ids=[c.user_id for c in sets],
        eligible_users=eligible,
        n_candidates=sum(len(c.items) for c in sets),
        categories=[CategoryCount(category=k, users=v) for k, v in readers.most_common()],
        mean_feed_ctr=sum(c.feed_ctr for c in sets) / len(sets),
        mean_sample_ctr=sum(c.sample_ctr for c in sets) / len(sets),
    )


# Steps 2-4 are run-centric: they read one saved run file (PRD-03, decided on #17).


class RunSummary(BaseModel):
    run_id: str
    created: str
    population: str
    arms: list[str]
    model: str
    mock: bool
    data_source: str
    is_result: bool
    n_users: int


class RunProblem(BaseModel):
    """A run file that could not be loaded: listed, never silently dropped."""

    run_id: str
    problem: Literal["unreadable", "incompatible"]
    detail: str


class RunList(BaseModel):
    runs: list[RunSummary]  # newest first
    problems: list[RunProblem]


class CategoryLink(BaseModel):
    category: str
    clicks: int  # this agent's past clicks in the category


class ArmSummary(BaseModel):
    arm: str
    memories: int
    profile_items: int
    invented: bool  # arm B: made up, not from this user's data
    donor: str | None  # arm E: whose clicks this agent borrowed


class AgentNode(BaseModel):
    user_id: str
    n_history: int
    categories: list[CategoryLink]
    knowledge: list[ArmSummary]  # LLM arms only, in run order


class RunPopulation(BaseModel):
    run_id: str
    population: str
    data_source: str
    mock: bool
    is_result: bool
    agents: list[AgentNode]
    categories: list[CategoryCount]  # most-read first


class Headline(BaseModel):
    news_id: str
    category: str | None  # None: the item is not in the run's news.tsv
    subcategory: str | None
    title: str | None


class Persona(BaseModel):
    name: str
    life_stage: str
    age: int
    job: str
    location: str
    big_five: dict[str, str]
    values: list[str]
    news_habit: str


class MemoryView(BaseModel):
    news_id: str
    headline: str
    category: str
    reason: str  # "recent" or "similar to: <candidate headline>"


class ProfileItem(BaseModel):
    text: str
    evidence: list[Headline]


class ProfileField(BaseModel):
    field: str
    items: list[ProfileItem]


class IdentityHit(BaseModel):
    kind: str
    term: str
    text: str


class ProfileView(BaseModel):
    ok: bool  # an unusable profile was never shown to the agent
    fields: list[ProfileField]
    identity_hits: list[IdentityHit]
    dropped_items: int
    word_count: int


class WrongTwin(BaseModel):
    control: Literal[True] = True
    donor: str
    # Real clicks the donor and this user have in common; None in runs saved before #14 counted it.
    shared_history: int | None = None


class KnowsNothing(BaseModel):
    arm: str
    kind: Literal["nothing"] = "nothing"


class KnowsPersona(BaseModel):
    arm: str
    kind: Literal["persona"] = "persona"
    invented: Literal[True] = True
    persona: Persona


class KnowsMemories(BaseModel):
    arm: str
    kind: Literal["memories"] = "memories"
    memories: list[MemoryView]


class KnowsProfile(BaseModel):
    arm: str
    kind: Literal["profile"] = "profile"
    profile: ProfileView
    memories: list[MemoryView]
    wrong_twin: WrongTwin | None


ArmKnowledge = Annotated[
    KnowsNothing | KnowsPersona | KnowsMemories | KnowsProfile, Field(discriminator="kind")
]


class AgentDetail(BaseModel):
    """What one agent saw and knew. Never its labels: the reveal is Simulation's and Report's."""

    run_id: str
    user_id: str
    mock: bool
    data_source: str
    history: list[Headline]  # oldest first
    candidates: list[Headline]  # display order
    arms: list[ArmKnowledge]


class _ProfileItem(BaseModel):
    text: str
    evidence: list[str]


class _StoredProfile(BaseModel):
    """A distilled profile as the run file stores it (`backend.profiles.Profile`)."""

    ok: bool
    fields: dict[str, list[_ProfileItem]]
    identity_hits: list[IdentityHit]
    dropped_items: int
    word_count: int


def run_summary(run: Run) -> RunSummary:
    return RunSummary(
        run_id=run.run_id,
        created=run.created,
        population=run.population,
        arms=run.arms,
        model=run.model,
        mock=run.mock,
        data_source=run.data_source,
        is_result=run.is_result,
        n_users=len({u.user_id for u in run.users}),
    )


def open_run(settings: Settings, run_id: str) -> Run:
    path = run_path(Path(settings.data_dir) / RUNS_SUBDIR, run_id)
    if path is None:
        raise AppError(404, "run_not_found", f"No run {run_id} in DATA_DIR/runs.")
    try:
        return load_run_cached(path)
    except RunFileError as exc:
        raise AppError(422, f"{exc.problem}_run", str(exc)) from exc


def run_news(settings: Settings, run: Run) -> Mapping[str, NewsItem]:
    """The news.tsv of the data source the run was made from."""
    for source in available_sources(Path(settings.data_dir)):
        if source.kind == run.data_source:
            return load_news_cached(source.dev_dir / "news.tsv")
    raise AppError(
        409, "news_unavailable", f"Run {run.run_id} used {run.data_source} data, not in DATA_DIR."
    )


def by_user(run: Run) -> dict[str, list[UserResult]]:
    """Each user's results (one per arm), in the order users first appear in the run."""
    users: dict[str, list[UserResult]] = {}
    for result in run.users:
        users.setdefault(result.user_id, []).append(result)
    return users


def arm_summary(result: UserResult) -> ArmSummary:
    knowledge = result.knowledge
    memories = knowledge.get("memories")
    profile = knowledge.get("profile")
    fields = profile.get("fields") if isinstance(profile, dict) else None
    donor = knowledge.get("donor")
    return ArmSummary(
        arm=result.arm,
        memories=len(memories) if isinstance(memories, list) else 0,
        profile_items=sum(len(v) for v in fields.values() if isinstance(v, list))
        if isinstance(fields, dict)
        else 0,
        invented=knowledge.get("invented") is True,
        donor=donor if isinstance(donor, str) else None,
    )


def run_population(settings: Settings, run: Run) -> RunPopulation:
    news = run_news(settings, run)
    agents: list[AgentNode] = []
    readers: Counter[str] = Counter()
    for user_id, results in by_user(run).items():
        history = results[0].history
        # History items missing from news.tsv have no category to link.
        clicks = Counter(news[n].category for n in history if n in news)
        readers.update(clicks.keys())
        agents.append(
            AgentNode(
                user_id=user_id,
                n_history=len(history),
                categories=[CategoryLink(category=k, clicks=v) for k, v in clicks.most_common()],
                knowledge=[arm_summary(r) for r in results if r.arm in LLM_ARMS],
            )
        )
    return RunPopulation(
        run_id=run.run_id,
        population=run.population,
        data_source=run.data_source,
        mock=run.mock,
        is_result=run.is_result,
        agents=agents,
        categories=[CategoryCount(category=k, users=v) for k, v in readers.most_common()],
    )


def headlines(ids: Sequence[str], news: Mapping[str, NewsItem]) -> list[Headline]:
    return [
        Headline(news_id=i, category=n.category, subcategory=n.subcategory, title=n.title)
        if (n := news.get(i))
        else Headline(news_id=i, category=None, subcategory=None, title=None)
        for i in ids
    ]


def profile_view(stored: object, news: Mapping[str, NewsItem]) -> ProfileView:
    profile = _StoredProfile.model_validate(stored)
    return ProfileView(
        ok=profile.ok,
        fields=[
            ProfileField(
                field=name,
                items=[
                    ProfileItem(text=i.text, evidence=headlines(i.evidence, news)) for i in items
                ],
            )
            for name, items in profile.fields.items()
            if items
        ],
        identity_hits=profile.identity_hits,
        dropped_items=profile.dropped_items,
        word_count=profile.word_count,
    )


def arm_knowledge(result: UserResult, news: Mapping[str, NewsItem]) -> ArmKnowledge:
    knowledge, arm = result.knowledge, result.arm
    if arm == "A":
        return KnowsNothing(arm=arm)
    if arm == "B":
        return KnowsPersona(arm=arm, persona=Persona.model_validate(knowledge))
    memories = [MemoryView.model_validate(m) for m in knowledge["memories"]]  # pyright: ignore[reportGeneralTypeIssues]
    if arm == "C":
        return KnowsMemories(arm=arm, memories=memories)
    return KnowsProfile(
        arm=arm,
        profile=profile_view(knowledge["profile"], news),
        memories=memories,
        wrong_twin=WrongTwin.model_validate(knowledge) if knowledge.get("borrowed") else None,
    )


def agent_detail(settings: Settings, run: Run, user_id: str, arm: str | None) -> AgentDetail:
    results = by_user(run).get(user_id)
    if results is None:
        raise AppError(404, "agent_not_found", f"User {user_id} is not in run {run.run_id}.")
    shown = [r for r in results if r.arm in LLM_ARMS and arm in (None, r.arm)]
    if arm is not None and not shown:
        raise AppError(404, "arm_not_in_run", f"Arm {arm} is not an LLM arm of run {run.run_id}.")
    news = run_news(settings, run)
    try:
        arms = [arm_knowledge(r, news) for r in shown]
    except (KeyError, ValidationError) as exc:
        raise AppError(
            422, "incompatible_run", f"Run {run.run_id} stores knowledge in an older shape: {exc}"
        ) from exc
    return AgentDetail(
        run_id=run.run_id,
        user_id=user_id,
        mock=run.mock,
        data_source=run.data_source,
        history=headlines(results[0].history, news),
        candidates=headlines(results[0].items, news),
        arms=arms,
    )


def build_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Twin Lab")

    @app.exception_handler(AppError)
    async def handle_app_exception(_: Request, exc: AppError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse(
            status_code=exc.status_code, content={"code": exc.code, "detail": exc.detail}
        )

    @app.get("/api/status")
    def status() -> Status:  # pyright: ignore[reportUnusedFunction]
        return Status(
            mock=settings.mock_llm,
            demo_mode=settings.demo_mode,
            model=settings.llm_model,
            data_source=resolve_data_source(Path(settings.data_dir)).kind,
            call_count=0,
            experiment_defaults=ExperimentRequest(),
        )

    @app.post("/api/experiment")
    def experiment(request: ExperimentRequest) -> PopulationSummary:  # pyright: ignore[reportUnusedFunction]
        if settings.demo_mode:
            raise AppError(403, "demo_mode", "Building populations is disabled in the demo.")
        return summarise_population(settings, request)

    @app.get("/api/runs")
    def runs() -> RunList:  # pyright: ignore[reportUnusedFunction]
        found, problems = list_runs(Path(settings.data_dir) / RUNS_SUBDIR)
        return RunList(
            runs=[run_summary(r) for r in found],
            problems=[
                RunProblem(run_id=p.run_id, problem=p.problem, detail=p.detail) for p in problems
            ],
        )

    @app.get("/api/run/{run_id}/population")
    def population(run_id: str) -> RunPopulation:  # pyright: ignore[reportUnusedFunction]
        return run_population(settings, open_run(settings, run_id))

    @app.get("/api/run/{run_id}/agent/{user_id}")
    def agent(run_id: str, user_id: str, arm: str | None = None) -> AgentDetail:  # pyright: ignore[reportUnusedFunction]
        return agent_detail(settings, open_run(settings, run_id), user_id, arm)

    # Mounted last so /api routes take precedence.
    dist = Path(settings.frontend_dist)
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")

    return app


app = build_app(get_settings())
