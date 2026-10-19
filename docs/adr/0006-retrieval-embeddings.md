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
