"""The freeze guard (ADR-0001): the test population only runs on frozen, committed prompts."""

import subprocess
from pathlib import Path

FREEZE_TAG = "prompts-frozen"


def freeze_problem(repo: Path | None = None) -> str | None:
    """Why the test set may not run yet, or None when HEAD is at/after the tag on a clean tree."""

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)

    if git("rev-parse", "-q", "--verify", f"refs/tags/{FREEZE_TAG}").returncode != 0:
        return f"tag '{FREEZE_TAG}' does not exist"
    if git("merge-base", "--is-ancestor", FREEZE_TAG, "HEAD").returncode != 0:
        return f"HEAD does not contain '{FREEZE_TAG}'"
    if git("status", "--porcelain").stdout.strip():
        return "working tree has uncommitted changes"
    return None
