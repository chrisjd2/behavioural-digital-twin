---
name: review-experiment
description: Review a diff for threats to the experiment's validity - test-set leakage, changes after the prompts-frozen tag, cache key, shared order and tie-breaks across arms, time-respecting popularity, dev/test disjointness, arm B/E isolation, identity screen, MOCK numbers shown as results. Writes .reviews/<N>/review-experiment.json.
---

Read `.claude/skills/review-experiment/instructions.md` and follow it exactly. Verbs map to tools via `.claude/skills/_shared/tool-mapping.md`.
