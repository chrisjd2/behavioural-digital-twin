from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.config import Settings, get_settings
from backend.data import (
    DataKind,
    Impression,
    NewsItem,
    build_candidate_set,
    is_eligible,
    load_behaviors,
    load_news,
    resolve_data_source,
    sample_populations,
)
from backend.experiment import ExperimentConfig

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
    eligible_users: int
    n_candidates: int
    categories: list[CategoryCount]
    mean_feed_ctr: float
    mean_sample_ctr: float


@lru_cache(maxsize=2)
def load_dev_split(dev_dir: Path, _mtime_ns: int) -> tuple[list[Impression], dict[str, NewsItem]]:
    """Real MIND dev takes seconds to parse; keep it while the file is unchanged."""
    return load_behaviors(dev_dir / "behaviors.tsv"), load_news(dev_dir / "news.tsv")


def summarise_population(settings: Settings, request: ExperimentRequest) -> PopulationSummary:
    """Sample the dev population exactly as the runner would. Never the test population."""
    source = resolve_data_source(Path(settings.data_dir))
    if source.kind == "none":
        raise AppError(409, "no_data", "No MIND data or synthetic sample found in DATA_DIR.")

    impressions, news = load_dev_split(
        source.dev_dir, (source.dev_dir / "behaviors.tsv").stat().st_mtime_ns
    )
    eligible = len({i.user_id for i in impressions if is_eligible(i)})
    try:
        # Same draw as runner.candidate_sets (test users first, so dev stays disjoint);
        # sampled here so the loaded split is reused across builds.
        dev = sample_populations(
            impressions,
            n_dev=request.n_users,
            n_test=DEFAULTS.n_test,
            dev_seed=request.seed,
            test_seed=DEFAULTS.test_seed,
        ).dev
    except ValueError as exc:
        raise AppError(422, "not_enough_users", str(exc)) from exc
    sets = [
        build_candidate_set(
            imp,
            seed=DEFAULTS.candidate_seed,
            max_candidates=request.max_candidates,
            max_clicked=DEFAULTS.max_clicked,
        )
        for imp in dev
    ]

    history = {i.impression_id: i.history for i in impressions}
    readers: Counter[str] = Counter()
    for c in sets:
        # History items missing from news.tsv have no category to count.
        readers.update({news[n].category for n in history[c.impression_id] if n in news})

    return PopulationSummary(
        population="dev",
        data_source=source.kind,
        n_users=len(sets),
        seed=request.seed,
        max_candidates=request.max_candidates,
        eligible_users=eligible,
        n_candidates=sum(len(c.items) for c in sets),
        categories=[CategoryCount(category=k, users=v) for k, v in readers.most_common()],
        mean_feed_ctr=sum(c.feed_ctr for c in sets) / len(sets),
        mean_sample_ctr=sum(c.sample_ctr for c in sets) / len(sets),
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

    # Mounted last so /api routes take precedence.
    dist = Path(settings.frontend_dist)
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")

    return app


app = build_app(get_settings())
