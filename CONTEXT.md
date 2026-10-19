# Twin Lab — Domain Glossary

Twin Lab asks: **can an LLM agent impersonate a real news reader and predict which headlines they click?** It compares four LLM "arms", one control arm and two non-AI baselines against real click data from the MIND dataset.

## How to use this doc

- Use the **canonical term** in code, docs, UI copy and issues. Terms marked *Avoid:* cause confusion.
- This doc defines words; decisions live in [`docs/adr/`](docs/adr/README.md) and scope lives in [`docs/prd/`](docs/prd/). If this doc and an ADR disagree, the ADR wins — flag the conflict.
- Marketing translations (for the talk) are given in *italics*.

## 1. Data (MIND)

| Term | Definition |
|---|---|
| **MIND** | Microsoft News Dataset (Wu et al., ACL 2020). We use **MIND-small dev** for test impressions and **MIND-small train** as earlier history for the popularity baseline. Research-use licence; never committed to the repo. |
| **News item** | One row of `news.tsv`: `NewsID, Category, SubCategory, Title, Abstract, …`. *≈ an email or piece of content.* |
| **Impression** | One row of `behaviors.tsv`: a moment when a user was shown a feed. Has `ImpressionID, UserID, Time, History, Impressions`. *≈ a send.* |
| **History** | The news IDs a user clicked *before* the impression. The agent's raw **memory** source. *≈ engagement data in a unified profile (e.g. Data 360).* |
| **Label** | Whether a shown news item was clicked (1) or not (0). The **ground truth**. *≈ open/click.* |
| **Synthetic sample** | A tiny fake dataset in MIND format, for tests and CI only. Always labelled fake in the UI. |

## 2. Experiment

| Term | Definition |
|---|---|
| **User** / **agent** | A sampled MIND user (one impression each). "Agent" is the same user as seen through an arm. *Avoid:* "persona" for anything except arm B. |
| **Candidate set** | Up to 8 headlines from one impression shown to an agent: up to 2 clicked plus non-clicked to 8, in a seeded shuffle shared by all arms. |
| **Dev set** | 30 users (dev seed) used for prompt and retrieval iteration. Disjoint from the test set. |
| **Test set** | 200 users (test seed). Run **once**, after the freeze. |
| **Freeze** | The git tag `prompts-frozen` marking the point after which prompts, retrieval and config may not change before the test run. |
| **Run** | One execution of chosen arms over a population. Saved as `data/runs/<id>.json`. |
| **Frozen run** | The single test-set run made after the freeze. The source of every reported number. |
| **Replay** | Playing back a saved run in the UI with no network. |
| **Mock mode** | Fake LLM outputs for offline development. Visibly labelled `MOCK`; never presented as results. |

## 3. Arms, controls and baselines

| Term | Definition |
|---|---|
| **Arm** | One way of prompting the LLM. All arms share headlines, order and output format; only what the agent knows differs. |
| **Arm A — Plain LLM** | Knows nothing; predicts for "a typical Microsoft News reader". The bar to beat. |
| **Arm B — Invented persona** | A made-up person seeded from the user ID only (name, age, job, Big Five, values, news habit). **Not** derived from the user's data. |
| **Arm C — Twin + memory** | Retrieved **memories** of the user's real past clicks. |
| **Arm D — Twin + profile + memory** | Arm C plus a **distilled profile**. The primary arm. |
| **Arm E — Wrong twin** | Arm D given a *different* user's profile and memories. A **control**: tests whether gains are personal or just "realism". |
| **Twin** | An agent grounded in a real user's behaviour (arms C, D). *Avoid:* calling arm B a twin. |
| **Memory** | A past-click news item shown to a twin, with a **retrieval reason** ("similar to: …" or "recent"). |
| **Distilled profile** | A ≤120-word, structured, evidence-cited summary of a user's last ≤50 clicks. No demographics, personality or identity inference. |
| **Baseline** | A non-AI ranker: **popularity** or **random**. |
| **Popularity** | Smoothed (Beta prior) click-through rate per news item, using only other users' impressions **strictly earlier** than the test impression (MIND train + earlier dev). |
| **Random** | Chance ranking. AUC ≈ 0.5. |

## 4. Prediction and metrics

| Term | Definition |
|---|---|
| **Reaction** | A one-sentence first-person gut reaction to a headline, written before the number. |
| **p_click** | The agent's 0–100 probability that it clicked the headline in its feed. Missing/unparseable → 0, counted as a **parse failure**. |
| **Feed framing** | The prompt states the headlines appeared in the user's feed among many others. |
| **AUC** | Per-user probability a clicked item outranks a non-clicked one. **Primary metric** (as paired D − A). |
| **MRR / nDCG@5 / Hit@1** | Rank metrics. Hit@1 = top pick was clicked; the plain-English metric for the talk. |
| **Paired difference** | Per-user metric difference between two arms (e.g. D − A), averaged with a bootstrap 95% CI. |
| **Feed CTR** | Click rate across the user's whole real impression (~4%). Primary calibration reference. |
| **Sample CTR** | Click rate within our candidate sets (~25%), inflated by design. Secondary reference. |
| **Calibration** | Mean predicted `p_click` vs feed CTR / sample CTR. |
| **Tie share** | Fraction of an arm's predictions tied with another candidate's for the same user. |
| **Outcome bucket** | Users grouped by D − A AUC: *Twin better* (> +0.1), *About the same* (±0.1), *Plain LLM better* (< −0.1). |
| **Median user** | The user whose D − A AUC is closest to the median. Default Report example. |

## 5. App

| Term | Definition |
|---|---|
| **Step 0 — Hook** | "You be the twin": guess without context, toggle the reader's history, guess again, reveal. Dev-set example, labelled illustrative. |
| **Steps 1–5** | Seed · Population · Simulation · Report · Interview. |
| **Interview** | Chat with one agent in one arm, under trust guardrails. Live, with a recorded fallback. |
| **Identity screen** | Keyword check on distilled profiles for identity inference; hits are flagged and counted. |
