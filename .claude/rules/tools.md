# Tool Usage

## Bash Tool

- **One command per Bash call. No multi-line scripts.** Each Bash tool invocation must contain exactly one command starting with the binary name. The permission prefix is the first token - anything before the binary (variable assignments, newlines, env vars) becomes the prefix and breaks permission matching.
- Never use shell variable assignments (`F=...`, `WD=...`) or env var prefixes in Bash calls. Inline all values directly. Wrong: `F=/path/to/file\nshowboat init "$F" "Title"`. Right: `showboat init /path/to/file "Title"`.
- **Never pipe commands.** `uv run pytest ... | head -30` breaks `Bash(uv run:*)` permission matching - the pipe makes it a different command. Use separate Bash calls or tool parameters instead.
- Never chain with `&&`, `;`, or newlines when sub-commands have different permission prefixes.
- Use separate parallel Bash calls when commands are independent, sequential when dependent.
- Don't add `2>&1` - the Bash tool captures both stdout and stderr by default.

## Tool vs. Bash (BLOCKING)

Hard-enforced by the **aegis** plugin's `prefer_tools.py` hook. See `aegis/rules/tools.md` for the full policy.

`rg` for ad-hoc shell recon is allowed (faster than grep, respects `.gitignore`). `ast-grep` for structural search and codemods.

## Search Strategy (Grep/Glob tools unavailable)

The native `Grep`/`Glob` tools are unregistered in this build (upstream bug, native 2.1.117+). Don't call them, and ignore any hook message that says "use the Grep tool" - it points at a tool that does not exist. Pick by search shape:

- **Known file, known rough location** -> `Read` with `offset`/`limit`.
- **Targeted pattern in a scope you can name, and you need the matching lines yourself** -> `rg` via Bash (allowed for recon; precise line numbers land in context).
- **Broad fan-out: sweeping many files or directories, or guessing naming conventions to reach a conclusion** -> `Explore` agent. It returns the answer, not the file dumps, so main context stays clean. Set breadth ("medium" or "very thorough"); launch several in one message for independent questions.

Don't spawn `Explore` for a one-line lookup (slow, token-heavy), and don't pull whole files into context when `Explore` can return the conclusion. `Explore` is read-only and locates code via excerpts, so `Read` the exact bytes yourself before any `Edit`.

- ALWAYS read and understand relevant files before proposing edits. Do not speculate about code you have not inspected.

## ripgrep Regex

- `rg` uses Rust regex (extended). Alternation is `|`, not `\|`. `rg "a\|b"` matches the **literal string** `a|b` and almost always returns nothing. Use `rg "a|b"` or `rg -e a -e b`.
- Treat `(Bash completed with no output)` as **unverified**, not **confirmed absent**. Before concluding a symbol does not exist, re-run the search with a term you know is present (or a single unambiguous term) to prove the pattern itself works. Repeated empty results from multi-term searches are a regex-syntax smell, not evidence.
