"""Step 3 Simulation (PRD-03, ADR-0008): a saved run's events for in-browser replay, and live
dev runs streamed over SSE.

Replay is the demo path and works in `DEMO_MODE`. Live runs are for development only: refused
in `DEMO_MODE` (ADR-0011) and always on the dev population, never the test set (ADR-0001).
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from sse_starlette import EventSourceResponse

from backend.clients import build_llm
from backend.config import Settings
from backend.data import resolve_data_source
from backend.errors import AppError
from backend.experiment import ExperimentConfig
from backend.run_views import RunSummary, open_run, run_summary
from backend.runner import Run, RunEvent, run_experiment
from backend.runs import RUNS_SUBDIR, save_run

log = logging.getLogger(__name__)

CACHE_FILE = "cache.sqlite"
ArmName = Literal["A", "B", "C", "D", "E", "popularity", "random"]
ALL_ARMS: list[ArmName] = ["A", "B", "C", "D", "E", "popularity", "random"]


class CallStarted(BaseModel):
    seq: int
    kind: Literal["call_started"]
    user_id: str
    arm: str


class Reaction(BaseModel):
    seq: int
    kind: Literal["reaction"]
    user_id: str
    arm: str
    news_id: str
    headline: str
    reaction: str
    p_click: float
    clicked: bool  # the real label: the replay reveals it after the card


class ArmProgress(BaseModel):
    seq: int
    kind: Literal["arm_progress"]
    arm: str
    done: int
    total: int


class RunComplete(BaseModel):
    seq: int
    kind: Literal["run_complete"]
    run_id: str


# Only these fields leave the server; anything else a run file's event holds is dropped.
EventView = Annotated[
    CallStarted | Reaction | ArmProgress | RunComplete, Field(discriminator="kind")
]
_events = TypeAdapter(list[EventView])


class RunEvents(BaseModel):
    """Everything the browser needs to replay a run with no further requests."""

    run: RunSummary
    recorded_seconds: float  # how long the run really took, for the "sped up" label
    events: list[EventView]  # by seq


class LiveRunRequest(BaseModel):
    """A live run is always on the dev population: there is deliberately no population field."""

    model_config = ConfigDict(extra="forbid")

    arms: list[ArmName] = Field(default=list(ALL_ARMS), min_length=1)
    n_users: int = Field(default=ExperimentConfig.n_dev, ge=1, le=300)


class LiveRunStarted(BaseModel):
    live_id: str  # not a run id: the saved run's id arrives in the stream's `run_saved`


def event_views(events: list[RunEvent]) -> list[EventView]:
    ordered = sorted(events, key=lambda e: e.seq)
    return _events.validate_python([{"seq": e.seq, "kind": e.kind, **e.data} for e in ordered])


def run_events(run: Run) -> RunEvents:
    try:
        events = event_views(run.events)
    except ValidationError as exc:
        raise AppError(
            422, "incompatible_run", f"Run {run.run_id} stores events in an older shape: {exc}"
        ) from exc
    times = [datetime.fromisoformat(e.at) for e in run.events]
    recorded = (max(times) - min(times)).total_seconds() if times else 0.0
    return RunEvents(run=run_summary(run), recorded_seconds=recorded, events=events)


class RunSaved(BaseModel):
    """The stream's last message when the live run finished and was saved."""

    run_id: str


class RunFailed(BaseModel):
    """The stream's last message when the live run failed."""

    detail: str


@dataclass
class LiveRun:
    """A run in progress. Subscribers get every event so far, then each new one, in order."""

    messages: list[dict[str, str]] = field(default_factory=list)
    finished: bool = False
    subscribers: list[asyncio.Queue[dict[str, str] | None]] = field(default_factory=list)
    task: asyncio.Task[None] | None = None

    def publish(self, message: dict[str, str], *, last: bool = False) -> None:
        self.messages.append(message)
        self.finished = last
        for queue in self.subscribers:
            queue.put_nowait(message)
            if last:
                queue.put_nowait(None)

    async def stream(self) -> AsyncIterator[dict[str, str]]:
        # Snapshot and subscribe with no await in between, so no message is missed or repeated.
        backlog = list(self.messages)
        if self.finished:
            for message in backlog:
                yield message
            return
        queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()
        self.subscribers.append(queue)
        try:
            for message in backlog:
                yield message
            while (message := await queue.get()) is not None:
                yield message
        finally:
            self.subscribers.remove(queue)


async def execute(settings: Settings, request: LiveRunRequest, live: LiveRun) -> None:
    def on_event(event: RunEvent) -> None:
        view = event_views([event])[0]
        live.publish({"event": "run_event", "data": view.model_dump_json()})

    data_dir = Path(settings.data_dir)
    try:
        source = resolve_data_source(data_dir)
        if source.kind == "none":
            raise ValueError("No MIND data or synthetic sample found in DATA_DIR.")
        client, embeddings = build_llm(settings, data_dir / CACHE_FILE)
        run = await run_experiment(
            source,
            ExperimentConfig(n_dev=request.n_users),
            population="dev",
            arms=list(request.arms),
            client=client,
            options=settings.llm_options(),
            embeddings=embeddings,
            on_event=on_event,
        )
        save_run(run, data_dir / RUNS_SUBDIR)
    except Exception as exc:  # the failure is reported to every subscriber, not swallowed
        log.exception("Live run failed")
        failed = RunFailed(detail=str(exc) or type(exc).__name__)
        live.publish({"event": "run_failed", "data": failed.model_dump_json()}, last=True)
        return
    saved = RunSaved(run_id=run.run_id)
    live.publish({"event": "run_saved", "data": saved.model_dump_json()}, last=True)


def simulation_router(settings: Settings) -> APIRouter:
    router = APIRouter()
    live_runs: dict[str, LiveRun] = {}

    def dev_only() -> None:
        if settings.demo_mode:
            raise AppError(403, "demo_mode", "Live runs are disabled in the demo (ADR-0011).")

    @router.get("/api/run/{run_id}/events")
    def events(run_id: str) -> RunEvents:  # pyright: ignore[reportUnusedFunction]
        return run_events(open_run(settings, run_id))

    @router.post("/api/run", dependencies=[Depends(dev_only)])
    async def start(request: LiveRunRequest) -> LiveRunStarted:  # pyright: ignore[reportUnusedFunction]
        live_id = f"live-{uuid.uuid4().hex[:12]}"
        live = live_runs[live_id] = LiveRun()
        live.task = asyncio.create_task(execute(settings, request, live))
        return LiveRunStarted(live_id=live_id)

    @router.get("/api/run/{live_id}/stream", dependencies=[Depends(dev_only)])
    def stream(live_id: str) -> EventSourceResponse:  # pyright: ignore[reportUnusedFunction]
        live = live_runs.get(live_id)
        if live is None:
            raise AppError(404, "live_run_not_found", f"No live run {live_id} on this server.")
        return EventSourceResponse(live.stream())

    return router
