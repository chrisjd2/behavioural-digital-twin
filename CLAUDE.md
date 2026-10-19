# Twin Lab: agent guide

Can an LLM agent impersonate a real news reader? Five LLM arms and two baselines vs real MIND clicks. Public repo; five-day build. **Lightweight beats thorough-but-late.**

## Read first

- `CONTEXT.md`: the glossary. Use its canonical terms in code, tests, UI copy and issues.
- `docs/adr/`: decisions. **An ADR wins over ticket text and over `CONTEXT.md`.** If they conflict, flag it; don't silently pick.
- `docs/prd/`: scope. 01 foundations, 02 experiment engine, 03 UI.

## Workflow (GitHub Issues, `chrisjd2/behavioural-digital-twin`)

Three labels only: `ready-for-agent` → `in-review` → `done`.

1. `gh issue view <N>`; branch `<N>-<slug>` from `main`.
2. Implement with `fastapi-implement` or `react-implement` (TDD).
3. Run the gates; all must exit 0.
4. Push; open a PR whose body starts `Closes #<N>.`
5. `gh issue edit <N> --remove-label ready-for-agent --add-label in-review`. Never merge your own PR.

## Commands (`just`)

| recipe | does |
|--------|------|
| `just install` | `uv sync`, `npm ci`, pre-commit hooks |
| `just dev` / `just down` | Docker Compose stack: API :8000, UI :5173, hot reload |
| `just lint` / `just fmt` | check / fix ruff + oxlint + prettier |
| `just typecheck` | basedpyright + `tsc -b` |
| `just test` | pytest + Vitest |
| `just check` | everything CI runs, plus the frontend build |
| `just gates --issue <N>` | the four agent gates, JSON envelopes to `.reviews/<N>/gates/` |

## Gates (`scripts/gates/`)

`run_lint.py` → `run_typecheck.py` → `run_tests.py` → `coverage_delta.py` (changed backend lines ≥ 80% per file vs `origin/main`). Run with `uv run python scripts/gates/<gate>.py [--issue <N>]`. Each prints `{gate, trees, exit, summary, failures, extra.head}`. Exit 0 pass, 1 failures to fix, 2 tool broke: stop and report. Contract: `.claude/skills/_shared/gate-protocol.md`.

## Skills (`.claude/skills/`)

- Implement: `fastapi-implement`, `react-implement` (spine: `.claude/skills/_shared/implementer-protocol.md`)
- Gates: `run-lint`, `run-typecheck`, `run-tests`, `coverage-delta`
- Review (`.claude/skills/_shared/review-protocol.md`, output `.reviews/<N>/review-<name>.json`): `review-implementation`, `review-quality`, `review-architecture`, `review-experiment`

Ported lightly from the owner's `kleisi-ops-server` workflow (ADR-0009), with its stack-specific conventions removed.

## Hard rules

- **Never commit** `data/` (MIND, `cache.sqlite`, runs), `.env`, `brief.md` or talk notes. The repo is public (ADR-0010). gitleaks runs in pre-commit and CI.
- `AI_USAGE.md` is gitignored until Chris has reviewed and approved it; never force-add it.
- **Never skip hooks** (`--no-verify`) or weaken a gate to get green.
- **Tests run in mock mode** (`MOCK_LLM=true`) on the synthetic sample: no API key, no network, no real MIND. Mock output is labelled `MOCK` and never presented as a result.
- **A failed read is not an empty result.** A failed fetch, file read or LLM call is an error state, never `[]`, `None` or a blank screen. (Only unparseable `p_click` → 0, and it is counted as a parse failure.)
- **The freeze is sacred.** After the `prompts-frozen` tag, prompts, retrieval and experiment config don't change (ADR-0001). See `review-experiment`.
- API response models in `backend/` are mirrored by types in `frontend/src/api/`; change both together.
- No CDN assets; the frontend works offline (ADR-0008).

## Dev environment (Windows + Docker)

- Development runs in Docker Compose (ADR-0011). Bind mounts from Windows/OneDrive don't deliver file events, so the stack polls: `WATCHFILES_FORCE_POLLING` for uvicorn, `VITE_POLL=1` for Vite. If hot reload stops, check those first.
- The `justfile` uses bash: on Windows, Git Bash.
- `uv run ...` and `npm` in `frontend/` work directly on the host too; gates and CI use them.
