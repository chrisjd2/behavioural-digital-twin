# ADR-0009: Stack, tooling and agent workflow

- **Status:** Accepted — Docker and deployment scope superseded by ADR-0011
- **Date:** 2026-10-19
- **Deciders:** Chris Davies
- **Related:** ADR-0010

## Context

Five build days, one developer working with a coding agent. Chris's `kleisi-ops-server` project has conventions, gates and review skills he likes, but much of it is Postgres/RLS/Vue-specific and heavier than a one-week demo needs. **Lightweight is the priority.**

## Decision

**Layout** (repo root):
```
backend/   config.py data.py retrieval.py personas.py arms.py llm.py metrics.py runner.py main.py
frontend/  Vite + React + TypeScript
scripts/   download_mind.py make_sample.py run_headless.py gates/
tests/     pytest
data/      MIND, cache.sqlite, runs/  (gitignored)
docs/      adr/ prd/
CONTEXT.md README.md AI_USAGE.md .env.example justfile
```

**Backend:** Python 3.12, `uv` (`pyproject.toml`, `[dependency-groups] dev`), FastAPI, `openai` SDK, asyncio. Borrowed patterns: pydantic-settings `Settings` with cached `get_settings()`; `build_app(settings)` factory for tests; a single `AppException` + handler. **Not** borrowed: response envelope, router/service/repository split, import-linter, mutation testing.

**Frontend:** React + Vite + TypeScript; d3-force for the population graph only; hand-rolled SVG charts; Vitest; typescript-eslint; Prettier. Assets bundled (ADR-0008).

**Quality:** ruff (same rule set as Kleisi), **basedpyright `standard`** mode, pytest with hand-computed metric tests, pre-commit (ruff format/check, gitleaks, basedpyright), `justfile` recipes. Minimal GitHub Actions CI: lint, typecheck, tests (synthetic sample, mock mode only), frontend build.

**Agent skills** (`.claude/skills/`), ported lightly from Kleisi:
- As-is: `run-lint`, `run-typecheck` (`tsc -b`), `run-tests`, `coverage-delta`, `review-implementation`, `review-quality`, implementer and review protocols, `scripts/gates/*.py`.
- Adapted: `fastapi-implement` (Kleisi checks stripped), `react-implement` (from `vue-implement`), `review-architecture` (against these ADRs).
- New: **`review-experiment`** — checks test-set leakage, post-freeze prompt changes, cache key includes model ID, shared order/tie-breaks across arms, popularity time filter.
- Dropped: `review-security`, `review-performance`, Kleisi conventions.

**Tracking:** GitHub Issues on `chrisjd2/behavioural-digital-twin`; one epic per PRD; labels `ready-for-agent`, `in-review`, `done` only.

## Consequences

**Becomes easier:**
- Familiar workflow; typed API seam between backend and frontend.

**Becomes harder:**
- Porting skills costs part of day 1 morning.

## Alternatives considered

- **Full Kleisi workflow (six-state labels, all reviewers):** too heavy for five days.
- **JavaScript frontend:** faster to start, but the API shapes are the riskiest seam.
- **basedpyright `all`:** numpy noise not worth fighting this week.
