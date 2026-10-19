# ADR-0002: LLM provider — pinned Gemini Flash via an OpenAI-compatible client

- **Status:** Accepted
- **Date:** 2026-10-19
- **Deciders:** Chris Davies
- **Related:** ADR-0001, ADR-0006

## Context

The brief specifies an OpenAI-compatible client and suggests `gpt-4.1-mini` only as an example of a cheap small model. Chris has high-limit Gemini access on a personal account. Temperature 0 is not bit-for-bit deterministic on hosted APIs, so reproducibility must come from caching. Unparseable output is scored `p_click = 0`; if parse failures differ by arm (longer prompts in C/D/E), that would be an artefact, not a finding. OpenAI fine-tuning was raised as a reason to prefer OpenAI.

## Decision

- Use a **current stable Gemini Flash-class model**, referenced by its **exact versioned ID** (never a `-latest` alias), for every arm, profile distillation and the interview.
- Call it through the `openai` SDK at Gemini's OpenAI-compatible endpoint, configured via `.env` (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `EMBED_MODEL`, `CONCURRENCY`, `MOCK_LLM`). Switching provider is a config change.
- Request **JSON-schema structured output**; on failure, retry once with a "valid JSON only" reminder; then count a parse failure. Report parse-failure rate per arm.
- **SQLite cache** keyed by `sha256(model_id, base_url, full request payload)`. Every run file records model ID, base URL and prompt-template hashes.
- Concurrency via asyncio semaphore (default 8) with exponential backoff on HTTP 429/5xx.
- **No fine-tuning.** It is a "where this goes next" slide (Modecrua et al., 2026).

## Consequences

**Becomes easier:**
- Cost is a non-issue, so N=200 and the extra control arm are affordable.
- Re-runs are free and identical via the cache.

**Becomes harder:**
- Results are specific to one model; no cross-model robustness claim.
- Reviewers reproducing need their own Gemini key and may get slightly different numbers.

## Alternatives considered

- **OpenAI `gpt-4.1-mini`:** no particular advantage; costs money.
- **Fine-tuning a model on MIND:** changes the research question, needs a train/test split by user and time, and does not fit one week.
- **Second-model robustness run:** deferred to spare time.

## Amendment (2026-10-19)

Embeddings (ADR-0006) are cached per news item, not per request: the key is `(base URL, embed model, dimensions, sha256 of the item's text)`. A request is a batch of up to 100 items, and caching per item means a batch that overlaps an earlier one only embeds the new items. The embed model and dimensions are part of `LLMOptions`, so they are in the frozen fingerprint (ADR-0001).
