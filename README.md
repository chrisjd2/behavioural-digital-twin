# Twin Lab: can an AI impersonate a customer?

If a brand knows what a customer has opened, clicked and read before, can an LLM agent *impersonate* that customer and predict how they'll react to new content? And does grounding the agent in real behaviour beat invented personas?

Twin Lab tests this on real click data from the Microsoft News Dataset (MIND). It compares a plain LLM, an invented persona, two "digital twins" grounded in each reader's real click history, and a wrong-twin control, against non-AI baselines.

> **Status:** under construction. Results will appear here after the pre-registered test run ([ADR-0001](docs/adr/0001-pre-registration.md)).

## Results

*Pending the frozen test run.*

## What it looks like

*Screenshots of each step, to follow.*

## Design

- **The question and the plan:** [`CONTEXT.md`](CONTEXT.md) (glossary) and [`docs/adr/`](docs/adr/README.md) (every decision, with alternatives).
- **Pre-registration:** the primary metric and decision rule were committed before any test data was run ([ADR-0001](docs/adr/0001-pre-registration.md)).
- **Arms and controls:** [ADR-0003](docs/adr/0003-experimental-arms-and-controls.md). **Baselines:** [ADR-0004](docs/adr/0004-baselines-time-respecting-popularity.md).

## Honest caveats

*To be completed with the results.*

## Run it

### Prerequisites

- Docker (with Compose), [uv](https://docs.astral.sh/uv/), Node 24+, [just](https://just.systems/)
- For real runs: a Gemini API key. Without one, the app runs in clearly labelled **MOCK** mode.

### Setup

```bash
cp .env.example .env      # add LLM_API_KEY and LLM_MODEL for real runs
just install
just dev                  # UI at http://localhost:5173, API at http://localhost:8000
```

### Checks

```bash
just check                # lint, typecheck, tests, frontend build
just serve                # build and run the production image on :8080
```

### Reproduce the experiment

*Instructions for downloading MIND and running the headless experiment, to follow.*

## How AI was used

Built with Claude Code as a coding agent. The research question, experiment design and interpretation are mine; the details will be in `AI_USAGE.md`.

## Data and licence

MIND is distributed by Microsoft under the [Microsoft Research License](https://learn.microsoft.com/en-us/azure/open-datasets/dataset-microsoft-news) for research use. It is downloaded separately and never committed to this repository.
