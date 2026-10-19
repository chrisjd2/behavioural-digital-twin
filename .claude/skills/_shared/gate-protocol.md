# Gate protocol (shared)

The contract for the four gate skills (`run-lint`, `run-typecheck`, `run-tests`, `coverage-delta`). Each gate is a thin wrapper over a deterministic script in `scripts/gates/`. Your job is to run it, read the JSON envelope, and report failures. The gate reports; it never fixes.

## Invocation

Run from the repo root:

    uv run python scripts/gates/<gate>.py [--tree backend|frontend] [--issue <N>]

- `--tree` limits the run to one tree (repeatable). Default: both trees.
- `--issue <N>` also writes the envelope to `.reviews/<N>/gates/<gate>.json` (gitignored) for reviewers.
- `coverage_delta.py` also takes `--base <ref>` (default `origin/main`).
- `just gates --issue <N>` runs all four in order.

Trees:

| tree | lint | typecheck | tests |
|------|------|-----------|-------|
| `backend` (`backend/`, `scripts/`, `tests/`) | `uv run ruff format --check`, `uv run ruff check` | `uv run basedpyright` | `uv run pytest` |
| `frontend` (`frontend/`) | `npm run -s lint` (oxlint), `npm run -s format:check` (prettier) | `npm run -s typecheck` (`tsc -b`) | `npm run -s test` (Vitest) |

The gates run the same commands as CI, so a green gate means a green CI job.

## Output envelope (frozen)

```json
{
  "gate": "run-lint",
  "trees": ["backend", "frontend"],
  "exit": 0,
  "summary": "ruff format: ok · ruff check: ok · oxlint: ok · prettier: ok",
  "failures": [{"file": "backend/x.py", "line": 3, "message": "...", "rule": "F401", "tool": "ruff check"}],
  "extra": {"head": "<short sha>"}
}
```

Every failure has `file` (repo-relative), `line` (0 when unknown) and `message`, plus gate-specific fields (`rule`, `test`, `tool`, `coverage_pct`, `uncovered_ranges`, ...).

## Exit codes (frozen)

| code | meaning | what to do |
|------|---------|------------|
| 0 | passed (or no-op) | proceed |
| 1 | `failures[]` is non-empty | group failures by file, report them, go back and fix |
| 2 | a tool could not run, or failed with output the gate could not parse | STOP and report `summary` and `extra.errors` verbatim. It is an environment problem, not a code problem. Do not install tools or work around it. `failures[]` may still hold real findings from the other tools: report those too |

## Rules

- Do not call `ruff`, `pytest`, `tsc` etc. directly to "double-check" a gate. The script is the source of truth.
- Lint warnings (oxlint warnings, basedpyright warnings) do not fail a gate, matching CI.
- Envelopes are tied to a commit by `extra.head`. An envelope for a different SHA is stale.
- Never edit a gate script to make it pass. A gate bug is its own issue.
