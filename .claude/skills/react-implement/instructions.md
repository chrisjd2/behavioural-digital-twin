# react-implement

Frontend implementation. The workflow is `.claude/skills/_shared/implementer-protocol.md`; this file adds the frontend rules.

## Always read

- `CONTEXT.md` (UI copy uses its terms: arm, twin, memory, `p_click`, Feed CTR, ...), and the issue's Relevant context.
- **PRD-03** (`docs/prd/03-twin-lab-ui.md`) for the screen being built.
- **ADR-0007** (persistent "Simulated from anonymised research data" label, interview guardrails), **ADR-0008** (replay first, no CDN), **ADR-0009** (stack), **ADR-0011** (`DEMO_MODE` hides run controls).
- `frontend/src/api/`: the typed API layer you extend.

## Layout

```
frontend/
  src/
    api/          one file per endpoint group: types mirroring backend models + fetch functions
    App.tsx       steps 0-5
    *.test.tsx    next to the component they test
  vite.config.ts  dev proxy to the API, polling for Docker on Windows
```

## Stack rules

- **React + TypeScript**, function components and hooks only. No `any` in new code; narrow `unknown` at the API boundary.
- **API types mirror the backend.** Each backend response model has a TypeScript type in `frontend/src/api/` with a ``/** Mirrors `backend.main.X`. */`` comment. Change both sides in the same PR. Components never call `fetch` directly; they call the functions in `src/api/`.
- **A failed read is not an empty state.** A fetch that fails (network error, non-2xx, bad JSON) shows an error state; it never renders as "no runs" / "no users" / an empty chart. Loading, error and empty are three different states, each tested.
- **No CDN assets** (ADR-0008). Fonts, scripts, icons and data are bundled or served by the app. The UI must work with no internet beyond the API.
- **Charts:** hand-rolled SVG; d3-force only for the population graph (ADR-0009). No chart library.
- **Labels that must always show:** `MOCK` whenever the API reports mock mode; "Simulated from anonymised research data (MIND). Not a real person's voice." on every agent view and the interview (ADR-0007); "illustrative" on the Step 0 hook; "recorded" for replayed interview exchanges; synthetic data marked as fake.
- **`DEMO_MODE`** (from `/api/status`): hide run / experiment controls; the app is read-only (ADR-0011).
- Never show numbers from a mock or dev run as results. Reported numbers come only from the frozen run (ADR-0001).

## Tests

- **Vitest + Testing Library** (`@testing-library/react`, `jest-dom`). Query by role and text, the way a user would.
- Stub `fetch` (`vi.stubGlobal`) per test. Never hit the network.
- Test loading, error and empty states separately, plus `DEMO_MODE` and `MOCK` labelling where the screen has them.
- No snapshot tests as the only assertion.

## Tooling

- `npm run lint` (oxlint), `npm run format` / `format:check` (prettier), `npm run typecheck` (`tsc -b`), `npm test` (Vitest), `npm run build`.
- In Docker on Windows, file watching uses polling (`VITE_POLL=1`, set by `docker-compose.yml`).

## Commits

Conventional commits, scope = screen or area: `feat(report): calibration bars`. `Refs: #<N>` in the body.

## Refuse and report when

- The screen needs an endpoint or field the backend doesn't have yet. Don't invent the shape; report the gap.
- The ticket asks for a CDN asset, a chart library, or for mock/dev numbers to be presented as results.
