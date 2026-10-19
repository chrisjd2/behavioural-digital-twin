# ADR-0006: Retrieval — Gemini embeddings by default, TF-IDF fallback

- **Status:** Accepted
- **Date:** 2026-10-19
- **Deciders:** Chris Davies
- **Related:** ADR-0002, ADR-0003

## Context

Arms C, D and E show the agent memories retrieved from a user's click history. Weak retrieval would hand critics "the twins lost because retrieval was poor". With free Gemini access, embeddings cost nothing beyond a one-off pass.

## Decision

- **Default:** embed each news item once (`category · subcategory · title · abstract`) with the pinned `EMBED_MODEL`; store vectors in SQLite; cosine similarity.
- **Fallback:** built-in TF-IDF over the same text, used in mock mode, tests and CI, and as a spare-day comparison on the dev set.
- **Selection:** for each candidate, top-3 most similar history items; plus the 3 most recent; deduplicate; cap at 12 (most recent kept on overflow).
- Each memory carries a **retrieval reason** (`similar to: <candidate title>` or `recent`), shown in the agent panel.
- The retrieval method is part of the frozen config (ADR-0001).

## Consequences

**Becomes easier:**
- Twins get a fair shot; semantic matches ("Patriots" ↔ "NFL playoffs").
- Retrieval reasons make a strong teaching visual.

**Becomes harder:**
- A one-off embedding pass over MIND news items before the first real run.

## Alternatives considered

- **TF-IDF default (brief):** fully offline but literal matching only.
- **Dump the whole history into the prompt:** Deng et al. (2026) suggest compact beats full; also long prompts.

## Amendment (2026-10-19, before the freeze)

Selection, as implemented after the PR #33 experiment review:

- **Order:** the 3 most recent clicks first, then **round-robin** across candidates in display order: every candidate's best match, then every candidate's second-best, then third-best, until 12. Filling candidate by candidate starved later display positions (positions 4–7 got a tailored memory for 9, 1, 4 and 0 of 30 dev users; round-robin gives 25, 21, 22 and 20).
- **Exclusion:** a candidate the user already clicked before (it appears in their MIND History) is never shown as a memory. The question is how a person reacts to *new* content. This drops a real signal on about 1.8% of dev impressions and makes C, D and E slightly harder, not easier.
- **Ties:** equal similarities go to the older click (stable sort over history order).
- **Embeddings:** 768 dimensions (Gemini's reduced output size), unit-normalised, cached per item (see ADR-0002 amendment).
