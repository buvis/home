---
name: use-codex
description: Use when running OpenAI Codex via the codex CLI (copilot CLI fallback) for code analysis, refactoring, or editing. Triggers on "run codex", "codex analyze", "ask codex", "copilot with codex".
---

# Codex Skill Guide

Always run Codex through the `codex-run.sh` helper. The helper auto-detects its backend: it uses the native `codex` CLI when installed, and falls back to the `copilot` CLI otherwise. Always invoke the helper - never call `codex` or `copilot` directly - so backend detection and flag mapping stay correct.

- **codex backend** (preferred): OpenAI ChatGPT subscription, no per-request billing multiplier. Uses codex's own configured default model unless `-m` is passed.
- **copilot backend** (fallback): GitHub Copilot, billed with a per-request multiplier - see below.

## Dispatch Contract (shared)

Background dispatch and waiting (TaskOutput-only waiting), following up, error handling, and the always-use-`-f` prompt rule are defined once in `/Users/bob/.claude/skills/use-codex/references/dispatch-contract.md`. Read it before dispatching; it applies verbatim to this skill.

Codex-specific delta: each run is independent by default; `--resume-thread` (codex backend only, requires `-o`) continues a prior codex session so its context carries over.

## Multiplier Policy (copilot backend only)

This applies only when the helper falls back to `copilot`. GitHub Copilot bills models with a per-request multiplier. The CLI does not expose multipliers locally, so the helper hardcodes a curated 1x default rather than auto-picking the highest version (which silently lands on premium tiers - `gpt-5.5` once burned 25% of a monthly quota in one run).

- **copilot default:** `gpt-5.4` (1x). Always use unless the user has explicitly approved a different model.
- **Before passing `-m` to opt into a higher-multiplier model** (e.g. `gpt-5.5` for harder reasoning), confirm with the user via `AskUserQuestion`. State the model name and that it carries a higher Copilot multiplier.
- Verify current multipliers in the GitHub Copilot dashboard if unsure - they change.
- The codex backend has no multiplier, so `-m` on codex needs no quota confirmation.

## Running a Task

Every run is non-interactive. By default each call is a fresh, one-shot Codex session; `--resume-thread` continues a prior codex session (codex backend only).

1. Select the permission mode required for the task; default to no special flags (read-only) unless edits are necessary.
2. Assemble the `codex-run.sh` command with appropriate helper flags:
   - `-m, --model MODEL` to override the model; on the copilot backend, ask the user first if the override is a higher-multiplier model
   - `-f, --file FILE` to pass the prompt (preferred - avoids shell escaping)
   - `-a, --allow-tools` to auto-approve tool use (codex: workspace-write sandbox)
   - `-y, --yolo` for full permissions (codex: bypass approvals and sandbox)
   - `-d, --dir DIR` to allow access to a specific directory (repeatable)
   - `-o, --output FILE` to capture output to a file
   - `-s, --silent` for clean scripting output (copilot backend only; ignored on codex)
   - `--emit-thread-id FILE` to capture the codex thread id from the JSON path (codex backend only; requires `-o`)
   - `--resume-thread VALUE` to resume a codex thread (VALUE is the thread id, or a file whose first line is the id; codex backend only; requires `-o`)
3. Run the command, capture output, and summarize the outcome for the user.

### Quick Reference (helper flags)

| Use case | Key flags |
| --- | --- |
| Read-only analysis | `-f prompt.txt` |
| Auto-approve tools | `-a -f prompt.txt` |
| Full auto (edits + tools) | `-y -f prompt.txt` |
| Allow specific directory | `-d <DIR> -f prompt.txt` |
| Scripting (clean output) | `-s -f prompt.txt` |

## Helper Script

```bash
# Write prompt to temp file (see the shared dispatch contract), then run
~/.claude/skills/use-codex/scripts/codex-run.sh -f /tmp/codex-prompt.txt

# With auto-approve tools
~/.claude/skills/use-codex/scripts/codex-run.sh -a -f /tmp/codex-prompt.txt

# Override model (on copilot backend, only after user approval - higher multiplier may apply)
~/.claude/skills/use-codex/scripts/codex-run.sh -m gpt-5.5 -f /tmp/codex-prompt.txt

# Full permissions
~/.claude/skills/use-codex/scripts/codex-run.sh -y -f /tmp/codex-prompt.txt

# Capture output to file
~/.claude/skills/use-codex/scripts/codex-run.sh -a -o /tmp/result.txt -f /tmp/codex-prompt.txt
```

Run `~/.claude/skills/use-codex/scripts/codex-run.sh --help` for all options.
