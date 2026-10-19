---
name: coverage-delta
description: Measure coverage of the backend Python lines changed on this branch (not total %) and fail any file below 80%. Returns the gate JSON envelope. Use after run-tests passes and before moving an issue to in-review.
---

# coverage-delta

Read `.claude/skills/_shared/gate-protocol.md` first. Verbs map to tools via `_shared/tool-mapping.md`.

## Why changed lines, per file

A repo can sit at 90% total and still ship an untested new function. This gate measures only the lines you added or changed, per file.

## Invoke

    uv run python scripts/gates/coverage_delta.py [--base <ref>] [--issue <N>]

1. Diffs the working tree against `git merge-base HEAD <base>` (default `origin/main`) with `-U0`, for `backend/**/*.py` (excluding `__init__.py`).
2. Runs `uv run coverage run -m pytest -q`, then `coverage json`.
3. For each changed file: covered changed executable lines / changed executable lines. Comments, blank lines and docstrings don't count.

**Backend only.** Frontend coverage is not measured; Vitest tests are still required by `run-tests` and `review-implementation`.

## Threshold

80% per changed file. Override for one run with `GATE_COVERAGE_MIN=70` (accepts `70`, `0.7`, `70%`). Lower it only deliberately, and say so in the PR.

## Failure shapes

Coverage miss:

```json
{"file": "backend/metrics.py", "line": 42, "message": "60% of changed lines covered (threshold 80%)",
 "changed_lines": 5, "covered_lines": 3, "coverage_pct": 0.6, "threshold": 0.8, "uncovered_ranges": [[42, 43]]}
```

Point at `uncovered_ranges` when reporting. A changed file no test imports shows as 0%.

Test failure during the coverage run: the entry has a `test` field and no `coverage_pct`. Report it as a failing test, not a coverage gap.

## Reporting

    <file>: <coverage_pct> (threshold <threshold>)
      uncovered lines: 42-43, 55

Runs last in the gate order.
