# fastapi-implement

Backend implementation. The workflow is `_shared/implementer-protocol.md`; this file adds the backend rules.

## Always read

- `CONTEXT.md`, and the issue's Relevant context.
- **ADR-0009** (stack and layout), **ADR-0010** (no data committed), **ADR-0011** (Docker, `DEMO_MODE`).
- For experiment code (everything except `config.py` and `main.py`): **PRD-02** and **ADR-0001 to ADR-0007**. These fix the seeds, arms, ordering, tie-breaks, cache key and guardrails. They are not suggestions.
- `backend/config.py` and `backend/main.py`: the primitives you extend.

## Layout (ADR-0009, PRD-02)

Flat modules in `backend/`, one per concern. No packages per feature, no router/service/repository layers.

```
backend/  config.py data.py retrieval.py personas.py profiles.py arms.py llm.py
          baselines.py metrics.py runner.py runs.py main.py
scripts/  download_mind.py make_sample.py run_headless.py gates/
tests/    test_<module>.py
data/     MIND, cache.sqlite, runs/   (gitignored, never committed)
```

Add a new module only when a concern doesn't fit an existing one. Say so in the discovery summary.

## Patterns to reuse

- **Settings:** `Settings` (pydantic-settings) + cached `get_settings()` in `backend/config.py`. New config goes there and in `.env.example`, with a safe default. Never read `os.environ` elsewhere.
- **App factory:** `build_app(settings)` in `backend/main.py`. Tests build their own app with explicit settings; never rely on the module-level `app` or a real `.env`.
- **Errors:** raise `AppError(status_code, code, detail)`; the single handler returns `{"code", "detail"}`. No other error shape, no per-route `try/except` translating errors.
- **Responses:** route handlers return Pydantic models directly (no envelope). Every response model has a matching TypeScript type in `frontend/src/api/` with a `/** Mirrors backend.main.X */` comment. Change both in the same PR.
- **`DEMO_MODE` (ADR-0011):** when on, `POST /api/run` and `POST /api/experiment` are disabled, and the interview is the only LLM caller, rate-limited. Any new write or LLM-calling endpoint must say what it does in demo mode, with a test for both modes.

## Stack rules

- Python 3.12, type hints everywhere, basedpyright `standard` clean. No `# type: ignore` without a reason.
- LLM calls go through one module (`llm.py`) using the `openai` SDK and the configured `LLM_BASE_URL`/`LLM_MODEL`. Async, behind a semaphore (`CONCURRENCY`), with backoff on 429/5xx (ADR-0002).
- The LLM cache key is `sha256(model_id, base_url, full request payload)` (ADR-0002). Don't build another cache.
- **Mock mode** (`MOCK_LLM=true`) returns deterministic fake outputs, visibly labelled `MOCK`. All tests and CI run in mock mode on the synthetic sample.
- Randomness takes an explicit seed from config. No unseeded `random` / `numpy.random`.
- Paths under `data/` come from `Settings.data_dir`; never hard-code them, never write outside `data/`.
- **A failed read is not an empty result.** A missing MIND file, a corrupt run file or a failed LLM call raises (or becomes an `AppError`), not `[]` or `None`. The one sanctioned exception is unparseable `p_click` → 0, counted as a parse failure (ADR-0002).

## Tests

- `pytest` (+ `pytest-asyncio`, `asyncio_mode = "auto"`), FastAPI `TestClient` or `httpx` for routes.
- One `tests/test_<module>.py` per module.
- Metric tests use small hand-computed examples (AUC with ties, MRR, nDCG@5, Hit@1, bootstrap CI with a fixed seed).
- Mock the LLM at the `llm.py` boundary only. No network in tests.
- Use `tmp_path` for any file I/O. Tests never touch `data/`.

## Commits

Conventional commits, scope = module: `feat(metrics): paired AUC difference`. `Refs: #<N>` in the body.

## Refuse and report when

- The ticket would change a frozen decision (seeds, arms, prompts, retrieval, metrics) after the `prompts-frozen` tag exists. See `review-experiment`.
- The ticket needs a response shape the frontend can't mirror, or an endpoint with no defined `DEMO_MODE` behaviour.
- A test would need a real key, the network or real MIND data.
