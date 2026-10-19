# ADR-0011: Docker everywhere and a temporary Cloud Run demo

- **Status:** Accepted
- **Date:** 2026-10-19
- **Deciders:** Chris Davies
- **Related:** Partly supersedes ADR-0009 (Docker and deployment were out of scope). Amends ADR-0010 (data location). Extends ADR-0008.

## Context

Chris wants to give panel members a link to the running app, live for a few days after the panel and then switched off. Having Docker run the app locally as well keeps local and hosted behaviour identical. The hosted app must not let anonymous visitors spend the Gemini quota, and it must not put MIND data into git.

## Decision

- **One container image, built in stages:** Node builds `frontend/` and Python serves the built assets from `/` via FastAPI. The same image runs locally and on Cloud Run.
- **Local:** `docker compose up` for development, with hot reload via mounted source and `data/` mounted read-write. The `just` recipes wrap compose. Running directly with `uv` and `vite` still works but is secondary.
- **Hosted:** Cloud Run, a single service, **public URL with no authentication**, minimum 0 and maximum 2 instances.
  - **`DEMO_MODE=1`:** the app is read-only. Replay, Hook, Seed, Population and Report work. `POST /api/run` and `POST /api/experiment` are disabled and the UI hides them.
  - **The interview is the only Gemini caller.** It is rate-limited in the app: 30 messages per IP per hour, and 500 per day overall. Past those limits it falls back to the recorded exchanges (ADR-0008).
  - **Data:** the frozen run, the MIND news items needed by the frozen run's users, and `cache.sqlite` are copied into a **demo image** pushed to a **private Artifact Registry** repository. They are never committed to git (ADR-0010 still holds for the repo).
  - **Secrets:** `LLM_API_KEY` comes from Secret Manager, never from the image.
  - **Teardown:** `just deploy` and `just teardown` (which deletes the service and the image). The README states the hosted demo was temporary.
- **CI** builds the image without data to check that the Dockerfile works. It never pushes.

## Consequences

**Becomes easier:**
- Panel members can explore the real app with no setup.
- Local and hosted environments match.

**Becomes harder:**
- Docker setup and the deploy step cost time on day 1 and day 5.
- Showing MIND headlines to a handful of reviewers in a non-commercial demo is within the spirit of research use, and the README notes it.

## Alternatives considered

- **Cloud Run IAM / IAP:** reviewers would need Google identities added by email, which is clunky for Salesforce staff.
- **A shared password:** adds friction for little gain, since the app is read-only and rate-limited.
- **Live runs enabled when hosted:** risks quota abuse and shows numbers other than the pre-registered ones.
