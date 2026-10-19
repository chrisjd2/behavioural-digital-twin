# ADR-0007: Trust guardrails for profiles and interviews

- **Status:** Accepted
- **Date:** 2026-10-19
- **Deciders:** Chris Davies
- **Related:** ADR-0003

## Context

Trust is central to the audience (Salesforce). Two places can drift into inferring identity about real (anonymised) users: the free-text distilled profile for arm D, and the live interview, where an in-character LLM will happily invent an age or a vote. Di Cursi et al. (2025) show personality inference from text is unreliable anyway.

## Decision

- **Distilled profile** (one call per user, cached): structured JSON with fields `interests`, `rarely_clicks`, `style_preferences`, `recent_shifts`; each item **cites ≥ 1 history headline ID** as evidence; ≤ 120 words total; built from the last ≤ 50 clicks. Explicitly banned: demographics, personality, political or religious affiliation, health status, sexuality. Topic descriptions are allowed ("follows election coverage"); identity claims are not.
- **Identity screen:** a keyword/regex check on generated profiles (age, gender, partisan, religious, health and similar terms). Hits are flagged in the run file and UI and counted in the Report; they do not block the run.
- **Interview system prompt:** "You are a simulation built only from this person's news-click history. Talk only about news interests and reading habits; cite past clicks where you can. If asked about identity, demographics, beliefs or anything not in the evidence, say you don't know because it is not in the data." Arm B interviews state openly that the character is invented.
- **Persistent label** on every agent view and in the interview: "Simulated from anonymised research data (MIND). Not a real person's voice."
- Data 360 / Einstein Trust Layer is a **talking point only**.

## Consequences

**Becomes easier:**
- A Trust slide with a concrete number (identity-screen hits out of 200).
- Live interview is safer in front of the panel.

**Becomes harder:**
- Structured profile output is slightly more prompt work than free text.

## Alternatives considered

- **Free-text profile (brief):** easier but drifts into identity inference unnoticed.
- **Blocking runs on identity-screen hits:** hides the problem instead of measuring it.

## Amendment (2026-10-19, before the freeze)

After two adversarial reviews (PR #37), the identity screen is a rule-based check in `backend/identity.py`, not a keyword list. Profiles describe reading habits, so a claim about the *reader* appears in three places, and only those are screened: after a claim word ("is a devout Christian", "presumably female"), as an item-opening fragment that ends its clause ("Married", "Wealthy homeowner", "Gen Z", "A 45-year-old"), or as a verb about the reader at the start of an item ("Votes Republican", "Lives in Ohio", "Has young kids"). Topics, which follow reading verbs or run on into a topic noun ("Likely clicks Republican primary coverage", "Gen Z trends", "a 40-year-old record"), are not flagged. Location, personality, family and occupation are screened as well as the original kinds. Every phrasing reported by the reviewers is pinned in `tests/test_identity.py` in both directions. The screen is still imperfect; it measures and a person reviews every flag.

Profiles are built from the last 50 clicks *excluding the headlines being predicted* (the same rule as memories, ADR-0006 amendment). An unusable profile is never shown to the agent; that user's Arm D prompt is then exactly Arm C's.
