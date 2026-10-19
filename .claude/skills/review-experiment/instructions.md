# review-experiment

Read `_shared/review-protocol.md` first. This file adds what this reviewer looks for.

**Question:** could this diff make a reported number wrong, unfair between arms, or chosen after seeing results? The talk's credibility rests on the experiment being honest. Read **ADR-0001 to ADR-0007** and `CONTEXT.md` §2–4 in full first.

## Self-gate

`applied: true` if the diff touches any of: `backend/` (except `backend/main.py` changes that only add routes with no experiment logic), `scripts/` (except `scripts/gates/`), `.env.example`, or `frontend/src/` code that renders metrics, run results, the Step 0 hook or the Report. Otherwise `applied: false`.

**Deliberately excluded:** `tests/` on its own (a test-only diff can't change a number; but when experiment code changes, check its tests prove the properties below), docs, CI, Docker.

## First: is the freeze in force?

Run `git tag -l prompts-frozen`. If the tag exists, run `git diff prompts-frozen..HEAD --stat` and check the freeze rule below before anything else.

## Checklist

| # | category | severity | check | ADR |
|---|----------|----------|-------|-----|
| 1 | `test_set_leakage` | blocker | Nothing tuned on the test set: prompts, retrieval, thresholds, the Step 0 example and any "illustrative" output come from the **dev** set only. No code reads test-set labels except the scorer. The test run is run once; no loop re-runs it with variations | 0001, 0008 |
| 2 | `post_freeze_change` | blocker | After `prompts-frozen` exists: any change to prompt templates, feed framing, arm builders, retrieval (method, k, cap), profile distillation, seeds, sample sizes, eligibility, candidate construction, model IDs or other frozen config. Such a change must be a separately labelled follow-up experiment, never a substitute. The test runner must refuse to start before the tag or with a dirty tree (except via an explicit, logged override) | 0001, 0006 |
| 3 | `cache_key_incomplete` | blocker | The LLM/embedding cache key includes the **model ID**, the **base URL** and the **full request payload** (messages, schema, temperature). Run files record model ID, base URL and prompt-template hashes | 0002 |
| 4 | `order_not_shared` | blocker | Each user's candidate display order is **one seeded shuffle, identical across all arms** (no per-arm shuffle, no reordering inside an arm builder). Tests assert identical order across arms | 0005 |
| 5 | `tiebreak_not_shared` | blocker | Ties in `p_click` are broken by a **separate seeded order per user, identical across arms**, never by display position or list index. AUC gives ties half credit. Tie share is reported per arm | 0005 |
| 6 | `popularity_leakage` | blocker | Popularity counts only impressions from MIND-small train or dev impressions **strictly earlier** (`<`, not `<=`) than the test impression, and **excludes every dev-set and test-set user**. Beta prior fitted on train; cold-start items get the prior. Tests cover the time boundary and exclusion | 0004 |
| 7 | `dev_test_overlap` | blocker | Dev (N=30, dev seed) and test (N=200, test seed) users are **disjoint**, with a test asserting it. Sampling is deterministic by seed. Eligibility: history ≥ 10, ≥ 1 click, ≥ 3 non-clicks; candidates ≤ 2 clicked + non-clicked to 8 | 0001 |
| 8 | `arm_b_reads_user_data` | blocker | Arm B's persona is generated only from a hash of the user ID. It never sees history, clicks, profile, memories or labels | 0003 |
| 9 | `arm_e_own_user` | blocker | Arm E uses a **seeded derangement** within the test set: no user ever gets their own profile or memories. Retrieval runs against the other user's history for this user's candidates. A test asserts no fixed points | 0003 |
| 10 | `arms_not_comparable` | major | All arms share candidates, order, output schema, feed framing, temperature and model; only the agent's knowledge differs. `BASE_RATE_HINT` off by default and only for a labelled follow-up | 0003, 0005 |
| 11 | `identity_screen_missing` | major | Distilled profiles pass through the identity screen (age, gender, partisan, religious, health and similar terms); hits are flagged in the run file and UI and counted, not blocked or silently dropped. Profiles are ≤ 120 words, cite ≥ 1 history headline ID per item, use the last ≤ 50 clicks | 0007 |
| 12 | `mock_as_result` | blocker | No MOCK, dev-set or synthetic-sample number is presented as a result in the UI, README or run summaries. Mock output is visibly labelled `MOCK`; reported numbers come only from the frozen run | 0001, 0008 |
| 13 | `metric_drift` | major | Primary outcome stays mean paired per-user AUC D − A with a 10,000-resample user bootstrap and fixed seed; the decision rule and outcome-bucket thresholds (±0.1) match ADR-0001. Parse failures score `p_click = 0` **and** are counted per arm | 0001, 0002 |
| 14 | `unseeded_randomness` | major | Any randomness in sampling, shuffles, tie-breaks, personas, derangement, random baseline or bootstrap without an explicit seed from config | 0001, 0005 |

For each check that the diff touches, look for the test that proves the property (PRD-02 "Testing Decisions" lists them). Missing proof for a blocker property is itself a `major` finding in the same category.

## Do not flag

- Prompt or retrieval changes **before** `prompts-frozen` exists, as long as they are evaluated on the dev set.
- Mock-mode and synthetic-sample code that is clearly labelled.
- A follow-up experiment after the freeze that is saved as a separate, labelled run and not substituted for the frozen one.
- Spare-day comparisons on the dev set (e.g. TF-IDF vs embeddings, reversed order), when labelled.

## Before emitting

1. Freeze status checked and stated in `extra.freeze` (`"not tagged"` or the tag's SHA).
2. Each checklist row the diff touches has been checked, with its ADR cited in `message`.
3. `summary` counts by severity.
