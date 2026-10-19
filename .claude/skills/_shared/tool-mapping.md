# Tool mapping

Skills use stack-neutral verbs. This is the only place agent-specific tool names live.

| Verb | Claude Code |
|------|-------------|
| read file | `Read` |
| search file contents | `Grep` |
| find files by pattern | `Glob` |
| edit file | `Edit` |
| write new file | `Write` |
| run command | `Bash` (or `PowerShell` on Windows) |
| ask user / orchestrator | `AskUserQuestion` |
| track task progress | `TaskCreate` / `TaskUpdate` |
| delegate to sub-agent | `Agent` |

Another agent = another column. Skill content stays the same.

## Shell notes (Windows)

- The `justfile` uses bash (`set shell := ["bash", "-cu"]`); on Windows that is Git Bash.
- Gate scripts are plain Python and work from either shell: `uv run python scripts/gates/<gate>.py`.
- Prefer the dedicated file tools over shell commands for reading and editing files.
