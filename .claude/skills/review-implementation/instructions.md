# review-implementation

Read `_shared/review-protocol.md` first. This file adds what this reviewer looks for.

**Question:** does the diff implement what the issue asked, no more, no less, with tests that prove it?

**Self-gate:** always applies.

## What to look for

### Unimplemented acceptance criteria

For each `- [ ]` bullet under **Acceptance criteria**, find the change that implements it **and** the test that proves it. If the bullet says "endpoint returns Y", look for the route, its response model, the matching type in `frontend/src/api/`, and a test asserting the shape.

`unimplemented_ac` · `blocker` · name the bullet; recommend the missing piece (route, test, type, UI state).

### Scope creep

Trace each non-trivial change to an AC bullet, **What to build**, or Relevant context. Not scope creep: refactors that serve an AC, tests of an AC's unhappy path, type fixes on touched code. Scope creep: an endpoint, config flag, arm, metric or UI step nobody asked for; an unrelated refactor.

`scope_creep` · `major` · "link it to an AC bullet or split it into its own issue".

### Shallow tests

A test must assert the behaviour the AC promises, not just "no exception" or "status 200". For metric code, a test asserts a hand-computed value (e.g. AUC with a tie gets half credit), not just that a float came back.

`shallow_test` · `major` · describe the stronger assertion.

### Gaps

Work described in **What to build** that neither the ACs nor the diff cover.

`coverage_gap` · `major` · expand this issue or open a follow-up.

## Do not flag

- Refactors in service of an AC; renames to match `CONTEXT.md` terms.
- Untested code that existed before this branch.
- Style or naming (`review-quality`), layering or ADR conformance (`review-architecture`), experimental validity (`review-experiment`).

## Gate signal

- `run-tests` red → an AC is unverified; don't double-report the failing test.
- `coverage-delta` entries with `coverage_pct` are evidence an AC is untested; entries with `test` are failing tests, not coverage gaps.

## Before emitting

1. Every AC bullet is matched to a change or flagged.
2. Every significant change is traced or flagged.
3. Every new test is judged deep enough or flagged.
4. `summary` is counts: "<N> blockers, <M> majors, <K> minors".
