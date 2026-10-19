# PRD-01: Repo foundations

- **Timebox:** Day 1 morning
- **ADRs:** 0009, 0010

## Problem Statement

Twin Lab must be built in five days by one developer with a coding agent, in a **public** repo that panel members will inspect. Without a working toolchain, gates and data hygiene from the first commit, the agent will produce unchecked code, and MIND data or secrets could be published by accident.

## Solution

A minimal but complete skeleton: Python and frontend toolchains, quality gates, lightweight agent skills ported from `kleisi-ops-server`, CI, data hygiene, and the docs every later issue reads (`CONTEXT.md`, ADRs, README skeleton, `AI_USAGE.md`).

## User Stories

### Developer (Chris + agent)
1. As the developer, I can run `just install`, `just lint`, `just typecheck`, `just test`, `just dev` so every task has one command.
2. As the agent, I can run `run-lint`, `run-typecheck`, `run-tests` and `coverage-delta` gates that return the Kleisi JSON shape, so I know when a ticket is done.
3. As the agent, I can follow `fastapi-implement` / `react-implement` with the Kleisi implementer protocol (Kleisi-specific checks removed).
4. As the reviewer, I can run `review-implementation`, `review-quality`, `review-architecture` (against this repo's ADRs) and `review-experiment`.

### Public reader
5. As a panel member, I never find MIND data, run files or secrets in the repo.
6. As a panel member, I find a README skeleton, `CONTEXT.md`, ADRs and an `AI_USAGE.md` with dated entries.

## Implementation Decisions

- `pyproject.toml` (uv, Python 3.12): FastAPI, uvicorn, openai, pydantic-settings, numpy, sse-starlette (or equivalent); dev: pytest, pytest-asyncio, coverage, ruff, basedpyright (`standard`).
- `frontend/`: Vite React TS template, Vitest, typescript-eslint, Prettier; Node version pinned.
- `.gitignore`: `data/`, `.env`, `.venv/`, `node_modules/`, `dist/`, `.reviews/`.
- `.env.example`: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `EMBED_MODEL`, `CONCURRENCY`, `MOCK_LLM`, `BASE_RATE_HINT`.
- pre-commit: ruff format, ruff check, gitleaks, basedpyright.
- CI (`.github/workflows/ci.yml`): uv sync, ruff, basedpyright, pytest (mock + synthetic sample), frontend lint/typecheck/test/build. Never uses real MIND or a key.
- `review-experiment` skill checklist: test-set leakage; prompt/config change after `prompts-frozen`; cache key includes model ID and base URL; shared order and tie-break across arms; popularity strictly earlier and excluding sampled users; dev/test disjointness.
- GitHub labels: `ready-for-agent`, `in-review`, `done`.
- `AI_USAGE.md` entry format: *Date · What AI did · What I decided · What I verified by hand · Surprise / what broke*. Seeded with 2026-10-19.

## Testing Decisions

- A trivial `build_app()` health test and a frontend smoke test so every gate is green from the start.
- CI must pass on the first push.

## Out of Scope

- Docker, deployment, auth, Postgres, import-linter, mutation testing, bandit, six-state triage labels.

## Further Notes

- Porting skills should take hours, not a day; if it overruns, port only the gates and `review-experiment`.
