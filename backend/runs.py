"""Run files: `data/runs/<run_id>.json` holds everything needed to report or replay a run."""

import json
from dataclasses import asdict
from pathlib import Path

from backend.runner import Run, RunEvent, UserResult


def save_run(run: Run, runs_dir: Path) -> Path:
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{run.run_id}.json"
    path.write_text(json.dumps(asdict(run), indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def load_run(path: Path) -> Run:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["users"] = [UserResult(**{**u, "items": tuple(u["items"])}) for u in data["users"]]
    data["events"] = [RunEvent(**e) for e in data["events"]]
    return Run(**data)
