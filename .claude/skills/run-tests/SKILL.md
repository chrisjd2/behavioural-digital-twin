---
name: run-tests
description: Run pytest (backend) and Vitest (frontend) and return the gate JSON envelope. Pass/fail gate. Use after implementing and before moving an issue to in-review.
---

# run-tests

Read `.claude/skills/_shared/gate-protocol.md` first. Verbs map to tools via `_shared/tool-mapping.md`.

## Invoke

    uv run python scripts/gates/run_tests.py [--tree backend|frontend] [--issue <N>]

- **backend:** `uv run pytest -q` (config in `pyproject.toml`; tests in `tests/`).
- **frontend:** `npm run -s test` (`vitest run`) in `frontend/`.

Tests run in **mock mode** on the synthetic sample. They must never need a real API key, the network or real MIND data (ADR-0010; CI sets `MOCK_LLM=true`).

## Failures are real

There is no flake re-run. Every entry in `failures[]` is a regression until shown otherwise. Each carries `test` (the test name) and `tool`. If a test is genuinely flaky, report it: the fix is to make it deterministic (seed it, mock the clock or the LLM), not to retry it.

## Reporting failures

    <file>
      <test>: <message>

If `exit` is 0, say "tests green" and move on. Runs third, before `coverage-delta`.
