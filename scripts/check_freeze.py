"""Fail if experiment code changed since the `prompts-frozen` tag (ADR-0001).

Runs in CI on every PR. Before the tag exists it passes. After it, any change to a file in
`backend.freeze.EXPERIMENT_PATHS` fails the check, because it would make the frozen test
run unreproducible (and the runner would refuse to start). A deliberate follow-up
experiment skips the check with the PR label `post-freeze-experiment`.

    uv run python -m scripts.check_freeze
"""

import subprocess
import sys

from backend.freeze import EXPERIMENT_PATHS, FREEZE_TAG, REPO_ROOT


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )


def main() -> int:
    if git("rev-parse", "-q", "--verify", f"refs/tags/{FREEZE_TAG}").returncode != 0:
        print(f"No '{FREEZE_TAG}' tag yet: nothing is frozen.")
        return 0
    changed = git("diff", "--name-only", FREEZE_TAG, "HEAD", "--", *EXPERIMENT_PATHS)
    if changed.returncode != 0:
        print(changed.stderr)
        return 2
    if files := changed.stdout.split():
        print(f"Experiment code changed since '{FREEZE_TAG}' (ADR-0001): {', '.join(files)}")
        print("Move the change out of these files, or label the PR post-freeze-experiment.")
        return 1
    print(f"No experiment code changed since '{FREEZE_TAG}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
