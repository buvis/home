# Tool Usage

## Bash Tool

- **One command per Bash call. No multi-line scripts.** Each Bash tool invocation must contain exactly one command starting with the binary name. The permission prefix is the first token - anything before the binary (variable assignments, newlines, env vars) becomes the prefix and breaks permission matching.
- Never use shell variable assignments (`F=...`, `WD=...`) or env var prefixes in Bash calls. Inline all values directly. Wrong: `F=/path/to/file\nshowboat init "$F" "Title"`. Right: `showboat init /path/to/file "Title"`.
- **Never pipe commands.** `uv run pytest ... | head -30` breaks `Bash(uv run:*)` permission matching - the pipe makes it a different command. Use separate Bash calls or tool parameters instead.
- Never chain with `&&`, `;`, or newlines when sub-commands have different permission prefixes.
- Use separate parallel Bash calls when commands are independent, sequential when dependent.
- Don't add `2>&1` - the Bash tool captures both stdout and stderr by default.
- **Don't pipe command output to `tail`/`head`/`grep` to trim it.** The `prefer_tools.py` hook blocks this, and the Read/Grep tools can't read a process's stdout. To inspect a long test or build run:
  - Run the command bare (`cargo test -p ddb-core`) - the Bash tool already truncates long output.
  - If you need a specific slice, redirect to a file (`cargo test -p ddb-core > /tmp/ddb-test.log`) and `Read` it with `offset`/`limit`.

## Tool vs. Bash (BLOCKING)

Hard-enforced by the **aegis** plugin's `prefer-tools.py` hook. See `aegis/rules/tools.md` for the full policy.

`rg` for ad-hoc shell recon is allowed (faster than grep, respects `.gitignore`). `ast-grep` for structural search and codemods.

## General

- ALWAYS read and understand relevant files before proposing edits. Do not speculate about code you have not inspected.

## Search and Documentation

- Check documentation for APIs and dependencies before writing code.

## ripgrep Regex

- `rg` uses Rust regex (extended). Alternation is `|`, not `\|`. `rg "a\|b"` matches the **literal string** `a|b` and almost always returns nothing. Use `rg "a|b"` or `rg -e a -e b`.
- Treat `(Bash completed with no output)` as **unverified**, not **confirmed absent**. Before concluding a symbol does not exist, re-run the search with a term you know is present (or a single unambiguous term) to prove the pattern itself works. Repeated empty results from multi-term searches are a regex-syntax smell, not evidence.
