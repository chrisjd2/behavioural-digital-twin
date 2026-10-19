from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.config import Settings, get_settings
from backend.data import (
    TEST_RESERVE,
    DataKind,
    is_eligible,
    load_behaviors_cached,
    load_news_cached,
    resolve_data_source,
)
from backend.errors import AppError
from backend.experiment import ExperimentConfig
from backend.run_views import CategoryCount, run_router
from backend.runner import candidate_sets, sampled_populations

DEFAULTS = ExperimentConfig()


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


class PopulationSummary(BaseModel):
    population: Literal["dev"]
    data_source: DataKind
    n_users: int
    seed: int
    max_candidates: int
    user_ids: list[str]  # in sampling order
    eligible_users: int  # outside the held-out test reserve: the pool dev is drawn from
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
    total = len({i.user_id for i in impressions if is_eligible(i)})
    # Dev is drawn from outside the whole test reserve, not just the scored test users.
    eligible = total - max(config.n_test, min(TEST_RESERVE, total - config.n_dev))
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

    app.include_router(run_router(settings))

    # Mounted last so /api routes take precedence.
    dist = Path(settings.frontend_dist)
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")

    return app


app = build_app(get_settings())
