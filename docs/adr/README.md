# Architecture Decision Records

Format: Michael Nygard short form — Status / Context / Decision / Consequences / Alternatives considered. Accepted ADRs are not edited; they are marked `Superseded by ADR-NNNN`.

## Experiment design
- [ADR-0001](0001-pre-registration.md) — Pre-registration: primary metric, decision rule, sample, freeze, example selection
- [ADR-0003](0003-experimental-arms-and-controls.md) — Arms A–D and the wrong-twin control E
- [ADR-0004](0004-baselines-time-respecting-popularity.md) — Time-respecting popularity and random baselines
- [ADR-0005](0005-prompting-and-calibration.md) — Prompting, ordering, ties and calibration
- [ADR-0006](0006-retrieval-embeddings.md) — Embedding retrieval with TF-IDF fallback
- [ADR-0007](0007-trust-guardrails.md) — Trust guardrails for profiles and interviews

## Platform and delivery
- [ADR-0002](0002-llm-provider-gemini.md) — Pinned Gemini Flash via an OpenAI-compatible client
- [ADR-0008](0008-demo-strategy-replay-first.md) — Replay-first demo, interview as a bonus
- [ADR-0009](0009-stack-and-tooling.md) — Stack, tooling and lightweight agent workflow
- [ADR-0010](0010-public-repo-no-data-committed.md) — Public repo, no data committed
- [ADR-0011](0011-docker-and-cloud-run-demo.md) — Docker everywhere and a temporary public Cloud Run demo
- [ADR-0012](0012-talk-structure-presenter-deck.md) — Talk structure: a presenter deck over the existing steps
