# PRD-02: Experiment engine

- **Timebox:** Day 1 afternoon → end of Day 3 (frozen test run complete)
- **ADRs:** 0001, 0002, 0003, 0004, 0005, 0006, 0007

## Problem Statement

To answer "can an AI impersonate a customer?" honestly, Chris needs a reproducible experiment that compares five LLM arms and two baselines on real MIND click data, with pre-registered metrics, confidence intervals and calibration, at low cost, and with results that can be replayed offline in front of a panel.

## Solution

A Python package (`backend/`) plus CLI scripts that load MIND, sample dev and test populations, build each arm's prompt, call a pinned Gemini model through a cached OpenAI-compatible client, score predictions against labels, and save complete run files. `scripts/run_headless.py` produces the metrics table without the UI.

## User Stories

### Data
1. As the experimenter, `download_mind.py` fetches and unpacks MIND-small **dev and train** into `data/mind/`, and the app detects it automatically.
2. As the experimenter, I can generate a synthetic sample in MIND format for tests, clearly marked fake.
3. As the experimenter, I can sample a test population (N=200, test seed) and a disjoint dev population (N=30, dev seed) under the eligibility rules.

### Arms and baselines
4. As the experimenter, each user gets a candidate set (≤ 2 clicked + non-clicked to 8) in a seeded order shared by all arms.
5. As the experimenter, I can run arms **A, B, C, D, E** with identical output format and only knowledge differing.
6. As the experimenter, arm B's invented persona is deterministic per user ID and independent of their data.
7. As the experimenter, arm D's distilled profile is structured, evidence-cited, cached and passed through the identity screen.
8. As the experimenter, arm E receives a different user's profile and memories via a seeded derangement.
9. As the experimenter, popularity scores use only earlier impressions (train + earlier dev) from users outside the sample, with a Beta prior; random is seeded.

### LLM client
10. As the experimenter, every LLM and embedding call is cached in SQLite keyed by model, base URL and full payload, so re-running a config makes **0 new calls**.
11. As the experimenter, outputs use JSON-schema mode with one retry; parse failures become `p_click = 0` and are counted per arm.
12. As the experimenter, calls run concurrently with a semaphore and back off on 429/5xx; a call and token counter is available.
13. As a developer without a key, `MOCK_LLM=1` produces fake outputs labelled `MOCK` throughout.

### Metrics and runs
14. As the experimenter, I get per-user AUC, MRR, nDCG@5, Hit@1 per arm and baseline; means with bootstrap 95% CIs; paired differences vs A and D − E; tie share; parse-failure rate; calibration vs feed CTR and sample CTR; identity-screen hits; outcome buckets and median user.
15. As the experimenter, each run is saved to `data/runs/<id>.json` with config, model ID, prompt hashes, git SHA, per-user predictions and reactions, labels, events and metrics.
16. As the experimenter, `run_headless.py --population dev|test --arms A,B,C,D,E` prints the metrics table.
17. As the experimenter, the test run refuses to start unless HEAD is at or after the `prompts-frozen` tag and the working tree is clean (overridable with an explicit, logged flag).

## Implementation Decisions

- Modules: `config.py` (Settings), `data.py` (load, sample, candidates, CTRs), `retrieval.py` (embeddings + TF-IDF, retrieval reasons), `personas.py` (arm B), `profiles.py` (arm D distillation + identity screen), `arms.py` (prompt builders A–E), `llm.py` (client, cache, retry, counters, mock), `baselines.py`, `metrics.py`, `runner.py` (async orchestration, event stream), `runs.py` (save/load).
- Runner emits events (`call_started`, `reaction`, `arm_progress`, `run_complete`) consumed by both the headless script and the SSE endpoint (PRD-03).
- Bootstrap: resample users, 10,000 iterations, fixed seed.
- Verify MIND-small train/dev date ranges in the loader and record them in the run file.
- Dev iteration log: any prompt or retrieval change on dev is noted in `AI_USAGE.md`.

## Testing Decisions

- **Metrics** tested against hand-computed examples (including ties and single-positive users).
- **Popularity** tested for no future leakage and exclusion of sampled users.
- **Sampling** tested for dev/test disjointness, eligibility, determinism by seed.
- **Arms** tested that order and tie-break are identical across arms and that E never receives its own user.
- **Cache** tested: second identical run → 0 calls.
- **Parse handling** tested with malformed and missing-ID responses.
- All tests use the synthetic sample and mock LLM.

## Out of Scope

- Fine-tuning, multi-round agent interaction, a second model, personality inference, base-rate-hint experiment (spare time only), embeddings-vs-TF-IDF comparison (spare time only).

## Further Notes

- Milestones: Day 1 — data, sampling, baselines, metrics, headless (mock). Day 2 — LLM client, cache, arms, first real dev run; check parse rate and SD. Day 3 — retrieval/profile polish on dev, commit ADR-0001, tag `prompts-frozen`, **run the test set once**.
