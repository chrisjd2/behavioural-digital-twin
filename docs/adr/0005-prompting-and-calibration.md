# ADR-0005: Prompting, ordering, ties and calibration

- **Status:** Accepted
- **Date:** 2026-10-19
- **Deciders:** Chris Davies
- **Related:** ADR-0001, ADR-0002, ADR-0003

## Context

Maier et al. (2025) found direct numeric ratings collapse to the midpoint, while free-text-then-score works. LLMs show position bias in lists. Models favour round numbers, creating ties that break Hit@1 and MRR. Calibration only means something if the prompt states what the probability refers to: the candidate set (~25% clicked by construction) or the real feed (~4%).

## Decision

- **One call per user per arm** containing all candidates (≤ 8).
- **Order:** one seeded shuffle per user, **identical across arms**.
- **Output:** JSON `{"reactions":[{"id","reaction","p_click"}]}` — a one-sentence first-person reaction, then `p_click` 0–100. Temperature 0.
- **Feed framing** in every arm: "Each of these headlines appeared in your Microsoft News feed while you were browsing, among many others. For each, give your honest one-sentence gut reaction, then the probability (0–100) that you clicked it."
- **No base-rate hint** by default. A `BASE_RATE_HINT` config flag exists for a labelled follow-up experiment only.
- **Ties:** broken by a separate seeded random order per user, identical across arms (never by display position). Report **tie share** per arm. AUC uses the standard half-credit for ties.
- **Calibration:** primary reference is **feed CTR** (user's whole real impression); secondary is **sample CTR**, labelled "inflated by design". Report view: one bar per arm (mean `p_click`) with both reference lines; full reliability diagram collapsible.

## Consequences

**Becomes easier:**
- Paired comparisons are fair: position and tie effects hit every arm equally.
- "Twins are too positive" is measurable against a defensible reference.

**Becomes harder:**
- Absolute position bias is not removed, only equalised (an optional reversed-order check on dev is spare-day work).

## Alternatives considered

- **One call per headline (pointwise):** 8× calls and no comparison context.
- **Candidate-set framing:** makes ~25% the "fair" target, hiding the over-positivity the talk is about.
- **Per-arm shuffles:** would add position-bias noise to arm differences.
