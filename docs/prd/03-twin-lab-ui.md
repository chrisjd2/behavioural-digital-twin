# PRD-03: Twin Lab UI

- **Timebox:** Day 3 → Day 5
- **ADRs:** 0001, 0003, 0005, 0006, 0007, 0008, 0011

## Problem Statement

The experiment has to be **taught and shown** in about 10 minutes to a Salesforce panel, on a projector or screen share, with no dependence on venue network. The audience needs to see what each agent "knows", watch predictions meet reality, and read an honest result, including calibration, without auto-generated conclusions.

## Solution

A FastAPI backend serving a React app with a MiroFish-style stepper: **Step 0 Hook → 1 Seed → 2 Population → 3 Simulation → 4 Report → 5 Interview**. The simulation is replayed from the frozen run; everything except the live interview works offline.

## User Stories

### Step 0 — Hook
1. As the presenter, I open on "Can an AI impersonate a customer?", show two headlines with no context, then toggle "Show what this reader clicked before", then reveal the real click, optionally with arm A and D predictions. The view is labelled *illustrative example (dev set)*.

### Step 1 — Seed
2. As the presenter, I see data source status (real MIND vs synthetic), N, candidates per agent and seed, and plain-language cards for arms A–D and the baselines (E shown as a small "control" tag).

### Step 2 — Population
3. As the presenter, I see a force graph of agents linked to the categories they read.
4. As the presenter, clicking an agent opens a side panel with their click history and **tabs per arm** showing what that agent knows: nothing / invented persona ("made up — not from this user's data") / memories with retrieval reasons / profile with evidence + memories / wrong twin.

### Step 3 — Simulation
5. As the presenter, I choose a saved run and replay it at selectable speed (~2 min default): live feed of reaction cards (arm colour, headline, reaction, `p_click`) followed by the real click reveal, with per-arm progress.
6. As a developer, I can start a live run (SSE) from the UI.

### Step 4 — Report
7. As the presenter, I see per-metric bars per arm with 95% CIs, popularity and random as grey/dashed reference lines, and the **primary D − A** result called out by its pre-registered rule (stated, not interpreted).
8. As the presenter, I see a calibration chart: mean `p_click` per arm with feed CTR and sample CTR reference lines; reliability diagram collapsible.
9. As the presenter, I see the median user's rankings for all arms side by side against reality, and outcome buckets with counts that I can click into to show users from any bucket.
10. As the presenter, I see parse-failure rate, tie share and identity-screen hits per arm.

### Step 5 — Interview
11. As the presenter, I pick an agent and arm and chat in character under the trust guardrails; if the live call fails, a recorded exchange is shown labelled "recorded".

### Everywhere
12. As the audience, every agent view carries "Simulated from anonymised research data (MIND). Not a real person's voice." Mock mode shows `MOCK` on every screen.

### Hosted demo (ADR-0011)
13. As a panel member, I open a public Cloud Run URL for a few days after the panel and explore Hook, Seed, Population, Simulation replay and Report with no setup.
14. As the owner, in `DEMO_MODE` nobody can start runs or build populations; the interview is rate-limited (30 messages per IP per hour, 500 per day) and falls back to the recorded exchanges.
15. As the owner, `just deploy` builds a demo image (frozen run, needed MIND items, cache) into private Artifact Registry and deploys it with the key from Secret Manager; `just teardown` deletes the service and image.

## Implementation Decisions

- **API:** `GET /api/status`; `POST /api/experiment`; `GET /api/run/{id}/population`; `GET /api/run/{id}/agent/{user_id}?arm=` (no labels: the reveal belongs to Simulation and Report); `POST /api/run` → `{live_id}` (dev population only; 403 in `DEMO_MODE`); `GET /api/run/{live_id}/stream` (SSE: the live run's events, then `run_saved` or `run_failed`); `GET /api/run/{id}/events` (a saved run's events as gzipped JSON, fetched once and replayed client-side, decided on #19); `GET /api/run/{id}` (run summary); `GET /api/runs` (summaries plus run files that could not be opened); `POST /api/interview`; `GET /api/hook`. Built frontend served from `/`.
- Typed API client in `frontend/src/api/` with TS types mirroring pydantic models.
- **Design:** light theme, projector-legible type, arm colours A slate, B amber, C blue, D violet, E muted teal with "control" tag; baselines grey/dashed. Fonts bundled locally.
- No auto-generated conclusions anywhere; Report shows numbers and the pre-registered rule's outcome only.
- **Steps 2–4 are run-centric (decided on #17):** Population, Simulation and Report show the users, knowledge and results of one selected run file. By default this is the newest run with `is_result` true, or else the newest run. Their endpoints take a run id (`GET /api/population` and `GET /api/agent/{user_id}` gain a run id; #18–#20). Step 1's "Build population" (`POST /api/experiment`) is a stateless **dev-set preview** only. There is no server-side population state.

## Testing Decisions

- Backend: API tests via `build_app()` with mock LLM and synthetic sample; SSE event order; replay works with network calls disabled.
- Frontend: Vitest for data transforms (bucket counts, CI bar geometry, replay timing); a smoke test per step rendering from a fixture run.
- Manual: full rehearsal with Wi-Fi off before the panel.

## Out of Scope

- Auth, permanent hosting, dark theme, Salesforce integration, auto-written insights, multi-agent interaction.

## Further Notes

- If time runs short, cut in this order: live SSE run path → force graph (replace with agent grid) → reliability diagram.
- Record 2–3 interview exchanges and pick the Step 0 example on Day 5.
