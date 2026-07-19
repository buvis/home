---
name: use-gemini
description: Use when running Google Gemini via the native Gemini CLI for code analysis, refactoring, or editing. Triggers on "run gemini", "gemini analyze", "ask gemini".
---

# Gemini Skill Guide

Gemini runs through the helper script `scripts/gemini-run.sh`, which maps a
stable flag interface onto two backends and resolves the mise-managed binary.

> **Backend:** The helper prefers the GitHub Copilot CLI (it is the only
> backend that serves the `gemini-3.1-pro-preview` model) and falls back to the
> native `gemini` CLI when copilot is absent. Force a backend with
> `GEMINI_BACKEND=copilot` or `GEMINI_BACKEND=gemini`. Both CLIs are
> mise-managed and may not be on PATH; the helper resolves them via `mise which`.

## Dependencies

- Files read from other skill dirs:
  `~/.claude/skills/use-codex/references/dispatch-contract.md` - mandatory,
  applies verbatim (see below)
- CLIs: `copilot` (preferred - the only backend serving
  `gemini-3.1-pro-preview`) or the native `gemini` CLI; `mise which` for
  resolution of either

## Dispatch Contract (shared)

Background dispatch and waiting (TaskOutput-only waiting), following up, error handling, and the always-use-`-f` prompt rule are defined once in `/Users/bob/.claude/skills/use-codex/references/dispatch-contract.md`. Read it before dispatching; it applies verbatim to this skill.

Gemini-specific delta: if the helper reports no backend CLI found, or the Copilot monthly quota is exhausted, report that and stop - do not silently fall back to another tool. For a quota error you may offer `GEMINI_BACKEND=gemini` (native CLI) as an alternative.

## Model Selection

- **Copilot backend (default):** spends Copilot AI credits per call (multiplier
  set by the model; not exposed headlessly - check the interactive `/model`
  picker). Default model is `gemini-3.1-pro-preview` ("Gemini 3.1 Pro
  (Preview)"). Per policy, Gemini-via-Copilot is allowed because Claude does not
  provide Gemini.
- **Native gemini backend** (`GEMINI_BACKEND=gemini`): bills your Google/Gemini
  API account, no Copilot multiplier; cannot serve the 3.1 Pro Preview model.
  With no `-m`, the CLI picks its own default.

Pass `-m MODEL` only when the user asks for a specific model.

## Running a Task

1. Select the permission mode required for the task; default to no special flags (interactive approval) unless edits are necessary.
2. Assemble the command with appropriate options:
   - `-m, --model MODEL` to override the CLI default model
   - `-f, --file FILE` to read the prompt from a file (preferred - avoids shell escaping)
   - `-i, --interactive` for interactive mode with an initial prompt
   - `-a, --allow-tools` to auto-approve edit tools (`--approval-mode auto_edit`)
   - `-y, --yolo` to auto-approve all tools (`--approval-mode yolo`)
   - `-d, --dir DIR` to include an extra directory in the workspace (repeatable)
   - `-s, --silent` accepted for compatibility (headless `-p` output is already clean)
3. When continuing a previous session, use `-c` (most recent) or `-r [ID]` (`latest` or an index).
4. Run the command, capture output, and summarize the outcome for the user.
5. **After Gemini completes**, inform the user: "You can resume this session with `gemini-run.sh -c`."

### Quick Reference

| Use case | Key flags |
| --- | --- |
| Read-only analysis | `-f prompt.txt` |
| Interactive with initial prompt | `-i "prompt"` |
| Auto-approve edit tools | `-a -f prompt.txt` |
| Full auto (all tools) | `-y -f prompt.txt` |
| Include extra directory | `-d <DIR> -f prompt.txt` |
| Resume recent session | `-c` |
| Resume specific session | `-r <ID>` |

Gotcha: in repos where `dev/local` is a symlink outside the workspace (buvis convention: `-> ~/.local/tmp/claude-dev`), gemini cannot read through it - pass `-d /Users/bob/.local/tmp/claude-dev` so those files resolve (verified fix).

## Helper Script

```bash
# Write prompt to temp file (see the shared dispatch contract), then run
~/.claude/skills/use-gemini/scripts/gemini-run.sh -f /tmp/gemini-prompt.txt

# With auto-approve edit tools
~/.claude/skills/use-gemini/scripts/gemini-run.sh -a -f /tmp/gemini-prompt.txt

# Full permissions (all tools)
~/.claude/skills/use-gemini/scripts/gemini-run.sh -y -f /tmp/gemini-prompt.txt

# Resume most recent session
~/.claude/skills/use-gemini/scripts/gemini-run.sh -c
```

Run `~/.claude/skills/use-gemini/scripts/gemini-run.sh --help` for all options.
