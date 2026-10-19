# ADR-0010: Public repository, no data committed

- **Status:** Accepted — amended by ADR-0011 (data baked into a private demo image)
- **Date:** 2026-10-19
- **Deciders:** Chris Davies
- **Related:** ADR-0001, ADR-0002, ADR-0009

## Context

The repo `chrisjd2/behavioural-digital-twin` is intentionally **public**: panel members will be given the link to explore it themselves. MIND is under a research-use licence and should not be redistributed in bulk. Run files contain MIND headlines and abstracts.

## Decision

- `data/` (MIND, `cache.sqlite`, `runs/`) and `.env` are gitignored **from the first commit**; gitleaks runs in pre-commit and CI.
- **No run files are committed.** Results appear in the README as a metrics table with CIs, calibration numbers and one screenshot per step (a few headlines in screenshots is acceptable).
- Reproduction path: clone → `download_mind.py` → own Gemini key in `.env` → `run_headless.py` with the documented seeds. The README states that hosted LLMs are not perfectly deterministic, so numbers may differ slightly.
- Talk script and rehearsal notes stay out of the repo.
- The **README is written for a reviewer**: question → results → screenshots → design (arms, controls, pre-registration) → honest caveats → reproduce → links to `AI_USAGE.md` and `docs/adr/`.
- ADR-0001 is committed before the test run so history proves the order.

## Consequences

**Becomes easier:**
- The panel can verify decisions and AI usage themselves.

**Becomes harder:**
- Reviewers need their own key and a MIND download to see the app with real data.

## Alternatives considered

- **Private until after the panel:** loses the "go look for yourself" moment.
- **Commit a stripped run (IDs only) and rehydrate from local MIND:** more code for little benefit since a key is acceptable.
