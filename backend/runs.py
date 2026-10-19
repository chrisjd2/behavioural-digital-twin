"""Run files: `data/runs/<run_id>.json` holds everything needed to report or replay a run."""

import json
import re
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Literal

from backend.runner import Run, RunEvent, UserResult

RUNS_SUBDIR = "runs"
RUN_ID = re.compile(r"[A-Za-z0-9_-]+")


class RunFileError(Exception):
    """A run file that exists but cannot be used: never treated as an empty run."""

    def __init__(self, run_id: str, problem: Literal["unreadable", "incompatible"], detail: str):
        super().__init__(f"Run {run_id} is {problem}: {detail}")
        self.run_id = run_id
        self.problem: Literal["unreadable", "incompatible"] = problem
        self.detail = detail


def save_run(run: Run, runs_dir: Path) -> Path:
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{run.run_id}.json"
    path.write_text(json.dumps(asdict(run), indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def load_run(path: Path) -> Run:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunFileError(path.stem, "unreadable", str(exc)) from exc
    try:
        data["users"] = [
            UserResult(**{**u, "items": tuple(u["items"]), "history": tuple(u["history"])})
            for u in data["users"]
        ]
        data["events"] = [RunEvent(**e) for e in data["events"]]
        return Run(**data)
    except (KeyError, TypeError) as exc:
        # Usually a file saved before a field existed (e.g. `history`): re-run to view it.
        raise RunFileError(path.stem, "incompatible", f"missing or unexpected field {exc}") from exc


def load_run_cached(path: Path) -> Run:
    """`load_run`, reused while the file is unchanged. Treat the result as read-only."""
    return _run(path, path.stat().st_mtime_ns)


@lru_cache(maxsize=4)
def _run(path: Path, _mtime_ns: int) -> Run:
    return load_run(path)


def run_path(runs_dir: Path, run_id: str) -> Path | None:
    """The file for `run_id`, or None if there is no such run (or the id is not a run id)."""
    path = runs_dir / f"{run_id}.json"
    return path if RUN_ID.fullmatch(run_id) and path.is_file() else None


def list_runs(runs_dir: Path) -> tuple[list[Run], list[RunFileError]]:
    """Every run, newest first, and every run file that could not be loaded."""
    runs: list[Run] = []
    problems: list[RunFileError] = []
    for path in sorted(runs_dir.glob("*.json"), reverse=True):
        try:
            runs.append(load_run(path))
        except RunFileError as exc:
            problems.append(exc)
    runs.sort(key=lambda r: r.created, reverse=True)
    return runs, problems
