"""The freeze (ADR-0001): the test population only runs with exactly the frozen setup.

At freeze time `scripts.freeze` writes `frozen.json`: a fingerprint of everything that
determines predictions. It is committed and tagged `prompts-frozen`. A test run then
refuses unless HEAD contains the tag, the tree is clean, and the live fingerprint equals
`frozen.json` *as committed at the tag*, so neither later commits nor `.env` changes can
alter the frozen setup unnoticed.
"""

import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from backend.arms import LLMOptions, prompt_hashes
from backend.data import DataSource
from backend.experiment import ExperimentConfig

FREEZE_TAG = "prompts-frozen"
FROZEN_FILE = "frozen.json"
REPO_ROOT = Path(__file__).resolve().parents[1]
# Code that picks the test users or turns model output into numbers. Any change to these
# after the tag refuses the test run; UI and API code (main.py, runs.py, frontend) may change.
EXPERIMENT_PATHS = (
    *(
        f"backend/{module}.py"
        for module in (
            "arms",
            "baselines",
            "data",
            "experiment",
            "freeze",
            "identity",
            "llm",
            "metrics",
            "personas",
            "profiles",
            "report",
            "retrieval",
            "runner",
        )
    ),
    "uv.lock",
)
_CHUNK = 1 << 20


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def data_hashes(source: DataSource) -> dict[str, str]:
    return {
        f"{split}/{name}": file_sha256(directory / name)
        for split, directory in (("dev", source.dev_dir), ("train", source.train_dir))
        for name in ("behaviors.tsv", "news.tsv")
    }


def fingerprint(
    source: DataSource, config: ExperimentConfig, *, model: str, base_url: str, options: LLMOptions
) -> dict[str, object]:
    """Everything that determines the test set and its predictions. No secrets, no data."""
    return {
        "config": asdict(config),
        "model": model,
        "base_url": base_url,
        "options": asdict(options),
        "prompt_hashes": prompt_hashes(options),
        "data_source": source.kind,
        "data_sha256": data_hashes(source),
    }


def _git(repo: Path | None, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo or REPO_ROOT, capture_output=True, text=True, check=False
    )


def tag_sha(repo: Path | None = None) -> str | None:
    result = _git(repo, "rev-parse", "-q", "--verify", f"refs/tags/{FREEZE_TAG}^{{commit}}")
    return result.stdout.strip() if result.returncode == 0 else None


def freeze_problem(  # noqa: PLR0911 - one return per distinct refusal reason
    current: dict[str, object], repo: Path | None = None
) -> str | None:
    """Why the test set may not run, or None when everything matches the frozen setup."""
    if tag_sha(repo) is None:
        return f"tag '{FREEZE_TAG}' does not exist"
    if _git(repo, "merge-base", "--is-ancestor", FREEZE_TAG, "HEAD").returncode != 0:
        return f"HEAD does not contain '{FREEZE_TAG}'"
    if _git(repo, "status", "--porcelain").stdout.strip():
        return "working tree has uncommitted changes"
    changed_code = _git(repo, "diff", "--name-only", FREEZE_TAG, "HEAD", "--", *EXPERIMENT_PATHS)
    if changed_code.stdout.strip():
        files = ", ".join(changed_code.stdout.split())
        return f"experiment code changed since '{FREEZE_TAG}': {files}"
    frozen = _git(repo, "show", f"{FREEZE_TAG}:{FROZEN_FILE}")
    if frozen.returncode != 0:
        return f"'{FREEZE_TAG}' has no {FROZEN_FILE}"
    expected = json.loads(frozen.stdout)
    changed = sorted(
        k for k in expected.keys() | current.keys() if expected.get(k) != current.get(k)
    )
    if changed:
        return f"setup differs from {FROZEN_FILE} at '{FREEZE_TAG}': {', '.join(changed)}"
    return None
