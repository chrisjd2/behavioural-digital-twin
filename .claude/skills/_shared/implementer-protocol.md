# Implementer protocol (shared)

The workflow every implement skill (`fastapi-implement`, `react-implement`) follows. Stack rules live in each skill; this file is the spine. Verbs ("read the file", "run command") map to tools via `_shared/tool-mapping.md`.

## 1. Load the ticket

- `gh issue view <N>`. Read the body, acceptance criteria and **Relevant context**.
- If Relevant context is missing or empty, STOP: *"Issue #<N> is not ready-for-agent: no Relevant context."*
- If the issue lists **Blocked by** issues that are still open, STOP and say so.
- Create a branch `<N>-<short-slug>` from `main`.

## 2. Discovery

Read in full, in this order:

1. `CONTEXT.md` (glossary). Use its canonical terms in code, tests and UI copy.
2. Every ADR and PRD in Relevant context, plus the always-read ADRs named by your stack skill.
3. Every code surface in Relevant context, and the existing modules you will touch. Extend existing primitives; do not fork them.

**ADRs win over ticket text.** If the ticket contradicts an ADR (or `CONTEXT.md` contradicts an ADR), do not silently pick one: flag it to the orchestrator.

Then give a short summary:

> *Reusing:* ... *Extending:* ... *Diverging:* ... (with reason) *Gaps / conflicts:* ...

If the orchestrator is interactive, wait for confirmation. If you are running AFK, continue unless there is a gap or conflict, in which case STOP and report.

## 3. Plan tests

At least one test per acceptance-criteria bullet, plus edge cases the ADRs imply (e.g. ties, empty histories, parse failures, `DEMO_MODE` on/off). List them; no gate.

## 4. TDD loop

For each test: **red** (write it, see it fail for the right reason) → **green** (minimum code) → **refactor**. Commit in small steps with conventional messages (`feat(metrics): ...`) and `Refs: #<N>` in the body.

Do not write implementation ahead of a failing test. If a test would be tautological (pure wiring), say so in the commit message instead of skipping silently.

Tests run in **mock mode** with the synthetic sample. Never call a real LLM or read real MIND data from a test.

## 5. Run gates

Follow `_shared/gate-protocol.md`, in this order: `run-lint` → `run-typecheck` → `run-tests` → `coverage-delta`, each with `--issue <N>`.

- `exit 0` → next gate.
- `exit 1` → fix (step 4) and re-run from the first gate.
- `exit 2` → STOP and report. Do not work around it.

Do not finish with a red gate. If a failure is outside the ticket's scope (already red on `main`), STOP and report it.

## 6. Finalise

- Push the branch. Open a PR whose body starts `Closes #<N>.` and summarises what changed and how it was verified.
- `gh issue edit <N> --remove-label ready-for-agent --add-label in-review`.
- Stop. Do not merge. Reviewers take over.

## Labels

Only three: `ready-for-agent` → `in-review` → `done`. The label is the only place workflow state lives.

## Refuse and report when

- Relevant context is missing, or a referenced file or ADR doesn't exist.
- The ticket conflicts with an ADR.
- A gate exits 2, or is red for reasons outside the ticket.
- The work would need `data/`, `.env` or a real API key committed, or would make tests depend on the network.
