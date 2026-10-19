---
name: run-typecheck
description: Run basedpyright (backend) and tsc -b (frontend) and return the gate JSON envelope. Pass/fail gate, no judgement. Use after implementing and before moving an issue to in-review.
---

# run-typecheck

Read `.claude/skills/_shared/gate-protocol.md` first. Verbs map to tools via `.claude/skills/_shared/tool-mapping.md`.

## Invoke

    uv run python scripts/gates/run_typecheck.py [--tree backend|frontend] [--issue <N>]

- **backend:** `uv run basedpyright` (`standard` mode, per ADR-0009; `include` covers `backend`, `scripts`, `tests`).
- **frontend:** `npm run -s typecheck`, which is `tsc -b` in `frontend/`.

## No judgement

Type errors never flake. Every entry in `failures[]` is real. Each carries `tool` and, where the tool gives one, `rule` (e.g. `TS2322`). Warnings do not fail the gate.

A missing-import error on a new module almost always means the code reaches for something that doesn't exist. Report it as it is.

## Reporting failures

    <file>
      line <line>: [<rule>] <message>

Runs second, after `run-lint` and before `run-tests`.
