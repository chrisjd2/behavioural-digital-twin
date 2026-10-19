# review-quality

Read `_shared/review-protocol.md` first. This file adds what this reviewer looks for.

The anti-bloat reviewer: keep new code lean, honest and free of premature complexity. Take the "do not flag" list as seriously as the catalogue; noisy reviews hide real findings.

**Self-gate:** always applies.

## What to look for

| category | severity | what | recommendation |
|----------|----------|------|----------------|
| `premature_abstraction` | major | A class, factory, protocol, base class or config knob with one caller / one implementation / one setting | Inline it. The helper appears at the second call site |
| `half_finished` | blocker | `NotImplementedError` on a path an AC needs; commented-out code; empty `except` | Finish or delete |
| `half_finished` | major | `TODO`/`FIXME` without an issue link (`Refs: #<N>`) | Link an issue or do it now |
| `swallowed_failure` | major | A failed read, fetch, parse or LLM call turned into an empty list, `None`, `0` or a blank UI with no error shown or recorded. **A failed read is not an empty result.** (The one sanctioned case: unparseable `p_click` scores 0 *and* is counted as a parse failure, ADR-0002) | Raise, surface an error state, or count it |
| `bw_compat_shim` | major | `_legacy`, deprecation branches or "old format" handling in code with no old callers | Delete |
| `comment_says_what` | minor | A comment restating the code | Delete, or replace with the *why* |
| `task_reference_in_code` | minor | `# added for #12`, `// part of the report rework` | Move to the PR description |
| `defensive_no_op` | minor | Checks for things the framework or types already guarantee; `except` that re-raises unchanged | Delete |
| `dead_code` | minor | Unused functions, exports, components, CSS the tools missed | Delete |
| `coupled_test` | minor | Asserts call structure (`mock.assert_called_once_with`) instead of observable results | Assert outputs or state |
| `file_growth` | minor | A backend module over ~400 lines, a function over ~80, a React component over ~250 lines, a test file over ~600 | Suggest a split |
| `removed_code_comment` | minor | `# was: ...`, `// removed X` | Delete; git is the record |

## Do not flag

- A helper extracted at the *second* call site.
- Comments that explain a non-obvious *why*, or cite an ADR (`# ADR-0005: ties broken by a seeded order, not position`).
- Long, sentence-like test names.
- Pydantic field descriptions and docstrings on public functions.
- Small presentational React components with no hook extracted.
- Seeds, constants and thresholds named after the ADR that fixes them.

## Gate signal

- `run-lint` with many formatting failures → suggest `just fmt`, not a finding per file.
- `coverage-delta` misses → a quality finding only if the uncovered lines match a category above (e.g. dead branch).

## Before emitting

1. Each category considered against the diff.
2. Each finding survives the "do not flag" list.
3. `summary` counts by severity; recommendations are one actionable sentence.
