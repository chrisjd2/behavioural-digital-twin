# ADR-0004: Baselines — time-respecting popularity and random

- **Status:** Accepted
- **Date:** 2026-10-19
- **Deciders:** Chris Davies
- **Related:** ADR-0001

## Context

Popularity is a strong news-recommendation baseline and is the honest answer to "is the twin better than a simple engagement score?". The brief computed it from other users' same-period impressions, which uses clicks that happened *after* the test impression — information no agent has. MIND-small dev appears to cover a single day, so a strictly time-respecting version built on dev alone would be near-random for early-morning impressions. (Split dates to be verified in the loader.)

## Decision

- **Popularity:** for each test impression, score each candidate by smoothed CTR = (clicks + α) / (shows + α + β), counting only impressions that are
  - from **MIND-small train** or from **MIND-small dev with a timestamp strictly earlier** than the test impression, and
  - **not** from any test-set or dev-set user.
- The Beta prior (α, β) is fitted to the global CTR in MIND-small train. Items with no earlier shows get the prior (cold start).
- **Random:** seeded shuffle; expected AUC 0.5.
- Both are drawn as grey/dashed reference lines in the Report.
- **"Popularity beats the twins" is an acceptable headline.** The Salesforce translation: a simple engagement score from the unified profile beat the AI twin — validate before you trust.
- Caveat in the README: brand-new stories cold-start, which is a genuine limitation of popularity scoring.

## Consequences

**Becomes easier:**
- Defending the baseline as fair against "it peeked at the future".

**Becomes harder:**
- Requires downloading MIND-small train as well as dev (~extra 50 MB).
- Per-impression popularity needs a time-sorted index rather than one global count.

## Alternatives considered

- **Concurrent (leaky) popularity:** rejected as the main baseline; could be shown as a dashed "uses future data" reference, but omitted to reduce clutter.
- **Dev-only time-respecting popularity:** baseline strength would depend on time of day.
