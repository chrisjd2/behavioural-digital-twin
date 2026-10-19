"""Steps 2-4 read one saved run file (PRD-03, run-centric since #17): list, population, agent.

Nothing here reveals labels, scores or `p_click`: the reveal belongs to Simulation and Report.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, ValidationError

from backend.config import Settings
from backend.data import NewsItem, available_sources, load_news_cached
from backend.errors import AppError
from backend.runner import LLM_ARMS, Run, UserResult
from backend.runs import RUNS_SUBDIR, RunFileError, load_run, load_run_cached, run_path


class CategoryCount(BaseModel):
    category: str
    users: int  # users with at least one past click in this category


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


class AgentNode(BaseModel):
    user_id: str
    n_history: int
    categories: list[CategoryLink]  # most-clicked first


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


@lru_cache(maxsize=256)
def _summary(path: Path, _mtime_ns: int) -> RunSummary:
    """Run files are large (~11 MB at N=300): each is parsed once while it is unchanged."""
    return run_summary(load_run(path))


def list_runs(runs_dir: Path) -> RunList:
    runs: list[RunSummary] = []
    problems: list[RunProblem] = []
    for path in runs_dir.glob("*.json"):
        try:
            runs.append(_summary(path, path.stat().st_mtime_ns))
        except RunFileError as exc:
            problems.append(RunProblem(run_id=exc.run_id, problem=exc.problem, detail=exc.detail))
    runs.sort(key=lambda r: r.created, reverse=True)
    problems.sort(key=lambda p: p.run_id, reverse=True)
    return RunList(runs=runs, problems=problems)


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


def run_router(settings: Settings) -> APIRouter:
    """Read-only, so the same in `DEMO_MODE`."""
    router = APIRouter()
    runs_dir = Path(settings.data_dir) / RUNS_SUBDIR

    @router.get("/api/runs")
    def runs() -> RunList:  # pyright: ignore[reportUnusedFunction]
        return list_runs(runs_dir)

    @router.get("/api/run/{run_id}")
    def run(run_id: str) -> RunSummary:  # pyright: ignore[reportUnusedFunction]
        return run_summary(open_run(settings, run_id))

    @router.get("/api/run/{run_id}/population")
    def population(run_id: str) -> RunPopulation:  # pyright: ignore[reportUnusedFunction]
        return run_population(settings, open_run(settings, run_id))

    @router.get("/api/run/{run_id}/agent/{user_id}")
    def agent(run_id: str, user_id: str, arm: str | None = None) -> AgentDetail:  # pyright: ignore[reportUnusedFunction]
        return agent_detail(settings, open_run(settings, run_id), user_id, arm)

    return router
