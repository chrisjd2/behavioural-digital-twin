# ADR-0001: Pre-registration of the experiment

- **Status:** Accepted
- **Date:** 2026-10-19
- **Deciders:** Chris Davies
- **Related:** ADR-0003, ADR-0005, [`CONTEXT.md`](../../CONTEXT.md)

## Context

The experiment reports several metrics (AUC, MRR, nDCG@5, Hit@1, calibration) across five arms and two baselines. Choosing the headline metric or the sample *after* seeing results invites forking-paths criticism and would undermine the "honest experiment" that the talk depends on. Per-user AUC rests on ~12 click/non-click pairs, so it is noisy: with a per-user SD of ~0.3 the 95% CI half-width on a paired difference is ±0.076 at N=60 and ±0.042 at N=200. Plausible grounding effects are +0.03 to +0.08 AUC.

## Decision

This ADR is committed **before** the test run; git history is the proof.

1. **Primary outcome:** mean paired per-user **AUC difference D − A**, with a bootstrap 95% CI (10,000 resamples of users, fixed seed).
2. **Decision rule:** "Twins beat the plain LLM" only if the CI on D − A excludes 0 and is positive. Otherwise the result is reported as "no detectable difference at N=200" (or "plain LLM better" if the CI is entirely negative).
3. **Secondary outcomes** (reported, not used for the headline): C − A, B − A, **D − E** (personalisation vs realism), Hit@1 per arm, MRR, nDCG@5, calibration, parse-failure rate, tie share. Popularity and random are reported as reference points.
4. **Sample:** test set N=200 users, one impression each, test seed fixed in config. Dev set N=30, separate seed, users **disjoint** from the test set. Eligibility and candidate construction as in the brief: history ≥ 10, ≥ 1 click and ≥ 3 non-clicks; up to 2 clicked + non-clicked to 8.
5. **Freeze:** all prompt, retrieval and config iteration happens on the dev set. When done, tag `prompts-frozen`. The test set is run **once** after that tag. Any later change is reported as a new, labelled experiment, not substituted.
6. **Power check:** if the dev-set per-user SD of D − A exceeds 0.4, raise test N to 300 *before* the freeze, and record the change here.
7. **Report example:** default to the **median user** (D − A AUC closest to the median). Users are grouped into **outcome buckets** — *Twin better* (> +0.1), *About the same* (within ±0.1), *Plain LLM better* (< −0.1) — with counts shown, browsable in the UI.

## Consequences

**Becomes easier:**
- Answering "did you pick the metric after seeing the results?" — point at the commit date.
- Presenting a null or negative result without it looking like a failure.

**Becomes harder:**
- No prompt tweaking on the test set, even if the result is disappointing.
- A second test run (e.g. base-rate hint) must be framed as a follow-up.

## Alternatives considered

- **N=60 (brief default):** too underpowered; likely "inconclusive".
- **Hit@1 as primary:** easier to explain but much noisier with 1–2 positives per user. Kept as the plain-English secondary.
- **Random "show another" example:** replaced by outcome buckets, which show the distribution honestly.
