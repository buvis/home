# Claude Code user-level memory

## General guidelines

- In all interactions and commit messages, be extremely concise and sacrifice grammar for the sake of brevity.

## Planning mode

- At the end of each plan, give me a list of unresolved questions you have about the task
- Make the questions extremely concise
- Sacrifice grammar for brevity

## Tools

Here are my preferences for tools to use when completing tasks.
In this context, tools don't refer to MCP offered tools,
but anything external to Claude that you might use to help complete the task.

### ast-grep vs ripgrep (quick guidance)

#### Structure matters

**Use `ast-grep` when structure matters.**
It parses code and matches AST nodes, so results ignore comments/strings, understand syntax,
and can **safely rewrite** code.

- Refactors/codemods: rename APIs, change import forms, rewrite call sites or variable kinds.
- Policy checks: enforce patterns across a repo (`scan` with rules + `test`).
- Editor/automation: LSP mode; `--json` output for tooling.

#### Text is enough

**Use `ripgrep` when text is enough.** It’s the fastest way to grep literals/regex across files.

- Recon: find strings, TODOs, log lines, config values, or non‑code assets.
- Pre-filter: narrow candidate files before a precise pass.

#### Rule of thumb

- Need correctness over speed, or you’ll **apply changes** → start with `ast-grep`.
- Need raw speed or you’re just **hunting text** → start with `rg`.
- Often combine: `rg` to shortlist files, then `ast-grep` to match/modify with precision.

#### Snippets

Find structured code (ignores comments/strings):

```bash
ast-grep run -l TypeScript -p 'import $X from "$P"'
```

Codemod (only real `var` declarations become `let`):

```bash
ast-grep run -l JavaScript -p 'var $A = $B' -r 'let $A = $B' -U
```

Quick textual hunt:

```bash
rg -n 'console\.log\(' -t js
```

Combine speed + precision:

```bash
rg -l -t ts 'useQuery\(' | xargs ast-grep run -l TypeScript -p 'useQuery($A)' -r 'useSuspenseQuery($A)' -U
```

#### Mental model

- Unit of match: `ast-grep` = node; `rg` = line.
- False positives: `ast-grep` low; `rg` depends on your regex.
- Rewrites: `ast-grep` first-class; `rg` requires ad‑hoc sed/awk and risks collateral edits.
