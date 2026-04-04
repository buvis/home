# Tool Usage

## Bash Tool

- **One command per Bash call. No multi-line scripts.** Each Bash tool invocation must contain exactly one command starting with the binary name. The permission prefix is the first token - anything before the binary (variable assignments, newlines, env vars) becomes the prefix and breaks permission matching.
- Never use shell variable assignments (`F=...`, `WD=...`) or env var prefixes in Bash calls. Inline all values directly. Wrong: `F=/path/to/file\nshowboat init "$F" "Title"`. Right: `showboat init /path/to/file "Title"`.
- **Never pipe commands.** `uv run pytest ... | head -30` breaks `Bash(uv run:*)` permission matching - the pipe makes it a different command. Use separate Bash calls or tool parameters instead.
- Never chain with `&&`, `;`, or newlines when sub-commands have different permission prefixes.
- Use separate parallel Bash calls when commands are independent, sequential when dependent.
- Don't add `2>&1` - the Bash tool captures both stdout and stderr by default.

## General

- ALWAYS read and understand relevant files before proposing edits. Do not speculate about code you have not inspected.

## Search and Documentation

- Check documentation for APIs and dependencies before writing code.
- `ast-grep` for structural search and codemods. `rg` for text search and recon.
