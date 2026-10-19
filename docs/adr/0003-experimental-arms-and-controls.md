# ADR-0003: Experimental arms and the wrong-twin control

- **Status:** Accepted
- **Date:** 2026-10-19
- **Deciders:** Chris Davies
- **Related:** ADR-0001, ADR-0005, ADR-0006, ADR-0007

## Context

The talk's question is whether grounding an agent in real behaviour beats a plain LLM and invented personas. Maiorano (2026) found a 10-persona invented panel did worse than a plain LLM at *audience-level* headline ranking. Park et al. (2024) and Toubia et al. (2025) show grounding in real individual data works. Deng et al. (2026) found a compact profile beat a full transcript. If D beats A, it could be because the agent knows *this* person, or merely because seeing *any* real click history makes the model more realistic.

## Decision

Five arms share the same candidates, order, output format and model; only the agent's knowledge differs.

| Arm | Knows |
|---|---|
| **A — Plain LLM** | Nothing; "a typical Microsoft News reader". |
| **B — Invented persona** | One made-up person per user, generated deterministically from a hash of the user ID: name, age, job, location, Big Five levels, two Schwartz values, a news habit. Independent of the user's data. |
| **C — Twin + memory** | Up to ~12 retrieved memories: top-3 most similar past clicks per candidate plus the 3 most recent, deduplicated. |
| **D — Twin + profile + memory** | Distilled profile (ADR-0007) plus the same memories as C. |
| **E — Wrong twin (control)** | D's prompt built from a **different** user's profile and memories, assigned by a seeded derangement within the test set (nobody gets their own). Retrieval runs against the other user's history for this user's candidates. |

- B is described as **"inspired by"** Maiorano, not a reproduction: it asks the individual-level version of their question.
- E appears in the Report and in "how I tested my own result", but is visually low-key (a "control" tag), not one of the four teaching cards.

## Consequences

**Becomes easier:**
- Answering "is it personalisation or just realism?" via D − E.

**Becomes harder:**
- One extra arm of calls and UI states (cheap; ADR-0002).

## Alternatives considered

- **B as a 10-persona averaged panel (closer to Maiorano):** 10× calls, and averaging compresses `p_click` toward the middle, muddying calibration.
- **No control arm:** leaves the realism explanation open.
- **E as a shuffled-history arm without profile:** less directly comparable to D.
