# review-architecture

Read `.claude/skills/_shared/review-protocol.md` first. This file adds what this reviewer looks for.

**Question:** does the diff fit the decisions in `docs/adr/`? Read the ADRs cited below in full before reviewing. If the diff contradicts an ADR, the ADR wins unless the PR also adds a superseding ADR.

## Self-gate

`applied: true` if the diff touches any of: `backend/`, `frontend/src/`, `frontend/vite.config.ts`, `frontend/index.html`, `scripts/`, `pyproject.toml`, `frontend/package.json`, `Dockerfile`, `docker-compose.yml`, `.gitignore`, `.dockerignore`, `.env.example`, `.github/workflows/`, `.claude/skills/`, `CLAUDE.md`. Otherwise `applied: false`.

**Deliberately excluded:** `tests/` (test layout is unowned by any reviewer; test *depth* is `review-implementation`'s), `docs/` (ADRs are decisions, not code; drift between them and code is `docs_drift` when a code change exposes it).

## What to look for

| category | severity | check | ADR |
|----------|----------|-------|-----|
| `data_committed` | blocker | Anything under `data/`, a run file, MIND rows, `cache.sqlite`, `.env`, `brief.md`, `AI_USAGE.md` drafts or talk notes added to git; or a `.gitignore` / `.dockerignore` change that would let them in | 0010 |
| `secret_in_code` | blocker | An API key, token or real `LLM_API_KEY` value anywhere; a key baked into the image | 0010, 0011 |
| `cdn_asset` | blocker | A `<script>`, `<link>`, font, CSS `@import` or `fetch` to a CDN or third-party host from the frontend | 0008 |
| `api_shape_drift` | blocker | A backend response model added or changed without the matching TypeScript type in `frontend/src/api/` (with its ``/** Mirrors `backend.main.X`. */`` comment), or vice versa | 0009 |
| `demo_mode_unguarded` | blocker | A new write endpoint, run/experiment trigger or LLM-calling path that works when `DEMO_MODE=1`; UI run controls not hidden in demo mode; interview without the per-IP / daily rate limits and recorded fallback | 0011, 0008 |
| `cache_key_incomplete` | blocker | An LLM or embedding cache whose key is not `sha256(model_id, base_url, full request payload)`, or a second cache alongside the SQLite one | 0002 |
| `unpinned_model` | major | A `-latest` model alias, or a model ID hard-coded outside `Settings` | 0002 |
| `layout_drift` | major | Backend split into packages / router-service-repository layers, a response envelope, import-linter, or a new top-level directory not in ADR-0009 | 0009 |
| `settings_bypass` | major | `os.environ` / `os.getenv` read outside `backend/config.py`; config not added to `Settings` and `.env.example` | 0009 |
| `error_shape_drift` | major | Errors not raised as `AppError`, or a second error response shape | 0009 |
| `component_fetches_directly` | major | A React component calling `fetch` instead of a function in `frontend/src/api/` | 0009 |
| `chart_library` | major | A chart library added; charts are hand-rolled SVG, d3-force only for the population graph | 0009 |
| `missing_trust_label` | major | An agent view or interview screen without the persistent "Simulated from anonymised research data (MIND). Not a real person's voice." label; arm B interview not stated as invented | 0007 |
| `dockerfile_drift` | major | More than one image, frontend not served by FastAPI from `/`, data copied into the public build, CI pushing an image, or CI using a real API key or MIND data (`.github/workflows/`) | 0010, 0011 |
| `skill_contract_drift` | major | A skill or `CLAUDE.md` change that breaks the gate or review envelope, the 3-label workflow, or reintroduces stack conventions this repo doesn't use, or a `CLAUDE.md` rule that contradicts an ADR | 0009 |

Experimental validity (leakage, freeze, ordering, popularity) belongs to `review-experiment`; note it in `extra.notes` rather than flagging it here.

## Do not flag

- Small helpers inside an existing module; a new flat module in `backend/` when no existing one fits.
- Direct `uv`/`vite` runs alongside Docker (ADR-0011 keeps them as a secondary path).
- Mock-mode code paths, as long as their output is labelled `MOCK`.

## Before emitting

1. Every touched surface checked against the table.
2. Each finding cites its ADR in `message`.
3. `summary` is the four counts from `.claude/skills/_shared/review-protocol.md`.
