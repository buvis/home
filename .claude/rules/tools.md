# Tool Usage

## Bash Tool

- **One command per Bash call. No multi-line scripts.** Each Bash tool invocation must contain exactly one command starting with the binary name. The permission prefix is the first token - anything before the binary (variable assignments, newlines, env vars) becomes the prefix and breaks permission matching.
- Never use shell variable assignments (`F=...`, `WD=...`) or env var prefixes in Bash calls. Inline all values directly. Wrong: `F=/path/to/file\nshowboat init "$F" "Title"`. Right: `showboat init /path/to/file "Title"`.
- **Never pipe commands.** `uv run pytest ... | head -30` breaks `Bash(uv run:*)` permission matching - the pipe makes it a different command. Use separate Bash calls or tool parameters instead.
- Never chain with `&&`, `;`, or newlines when sub-commands have different permission prefixes.
- Use separate parallel Bash calls when commands are independent, sequential when dependent.
- Don't add `2>&1` - the Bash tool captures both stdout and stderr by default.

## Tool vs. Bash (BLOCKING)

These are hard-enforced by `~/.claude/hooks/prefer-tools.py`. Naked single-command invocations are denied; use the dedicated tool.

| Bash command | Use instead | Why |
|---|---|---|
| `cat file` | `Read` | Returns line-numbered output, respects size limits |
| `head -n file` / `tail -n file` | `Read` with `offset`/`limit` | Same |
| `grep -r pattern path` | `Grep` | Faster, respects ignores, structured output |
| `find path -name "*.x"` | `Glob` | Designed for filename patterns |

Chained or piped invocations (`cat x | jq`, `find x | xargs y`) bypass the hook because they need shell context. Don't pipe just to get around the rule — use the dedicated tool.

`rg` for ad-hoc shell recon is allowed (faster than grep, respects `.gitignore`). For code search inside the model, prefer `Grep`.

`ast-grep` for structural search and codemods.

## General

- ALWAYS read and understand relevant files before proposing edits. Do not speculate about code you have not inspected.

## Search and Documentation

- Check documentation for APIs and dependencies before writing code.
