---
name: run-lint
description: Run ruff format/check (backend) and oxlint + prettier (frontend) and return the gate JSON envelope. Pass/fail gate; never auto-fixes. Use after implementing and before moving an issue to in-review.
---

# run-lint

Read `.claude/skills/_shared/gate-protocol.md` first. Verbs map to tools via `.claude/skills/_shared/tool-mapping.md`.

## Invoke

    uv run python scripts/gates/run_lint.py [--tree backend|frontend] [--issue <N>]

- **backend:** `uv run ruff format --check .` and `uv run ruff check .` from the repo root (covers `backend/`, `scripts/`, `tests/`).
- **frontend:** `npm run -s lint` (oxlint) and `npm run -s format:check` (prettier) in `frontend/`.

## Never auto-fix

The gate only reports. To fix, run `just fmt` (ruff format + `ruff check --fix` + prettier) out of band, then re-run the gate. Each failure carries `tool` and, for ruff/oxlint, `rule`.

## Reporting failures

Group by file:

    backend/metrics.py
      line 12: [F401] `numpy` imported but unused
    frontend/src/App.tsx
      line 0: file needs `npm run format`

If most failures are formatting, say "run `just fmt`" rather than listing each one.

Lint runs first in the gate order because it is the fastest and cheapest to fix.
