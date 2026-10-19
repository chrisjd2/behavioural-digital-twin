# Review protocol (shared)

The contract for every reviewer skill (`review-implementation`, `review-quality`, `review-architecture`, `review-experiment`). Reviewers produce findings. They do not fix code, re-run gates or give scores.

## Inputs

Read, in order:

1. The issue: `gh issue view <N>` (acceptance criteria, Relevant context).
2. The diff: `git diff $(git merge-base HEAD origin/main)..HEAD`.
3. `CONTEXT.md` and the ADRs the issue or your skill names.
4. Cached gate envelopes in `.reviews/<N>/gates/*.json`, if present. **Do not re-run gates.** If an envelope is missing, or its `extra.head` differs from the current HEAD, set `extra.gates_stale: true` and carry on.
5. Earlier comments on the issue (disagreements, see below).
6. Your skill's own checklist.

## Self-gate

`review-implementation` and `review-quality` always apply. The others first ask: *does this diff touch surfaces I review?* The surfaces are listed in each skill. If not, emit `applied: false` with a `summary` naming the surfaces you checked, and stop.

A reviewer may review a diff its self-gate rejects if it sees something its checklist covers; it records why in `extra.self_gate_note` so the gate can be fixed.

## Findings envelope (frozen)

Write to `.reviews/<N>/review-<name>.json` (gitignored) and print it:

```json
{
  "reviewer": "review-quality",
  "applied": true,
  "exit": 1,
  "summary": "1 blocker, 0 majors, 2 minors",
  "findings": [
    {
      "severity": "blocker",
      "file": "backend/metrics.py",
      "line": 42,
      "category": "premature_abstraction",
      "message": "MetricRegistry wraps one call site.",
      "recommendation": "Inline it at the call site."
    }
  ],
  "extra": {"head": "<short sha>", "gates_stale": false}
}
```

All six finding fields are required. `line` is 0 for a file-level finding. Optional details go in a per-finding `extra` object.

## Severity and exit codes

| severity | meaning | exit |
|----------|---------|------|
| `blocker` | must fix before merge | 1 |
| `major` | should fix before merge; pushback needs a reason | 1 |
| `minor` | fix when convenient | 0 |
| `nit` | preference; mention only | 0 |

Exit `0`: nothing blocking, or `applied: false`. Exit `1`: at least one blocker or major. Exit `2`: could not review (no ticket, empty diff, HEAD unresolvable). STOP and report.

## Disagreements

An implementer who disagrees comments on the issue:

    [Developer] DISAGREE on <reviewer>:<category> at <file>:<line>
    <reason>

On re-review, read these first. Drop the finding if the reason is sound; if you re-emit it, set `extra.escalate: true` so a human decides.

## What reviewers don't do

- Fix code. Recommendations only.
- Re-run gates.
- Guess runtime behaviour. Put questions in `extra.questions`.
- Grade. Findings or no findings.
- Widen scope. Things outside your concern go in `extra.notes`.
