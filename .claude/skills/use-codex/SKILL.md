---
name: use-codex
description: Use when running OpenAI GPT via the copilot CLI for code analysis, refactoring, or editing. Triggers on "run codex", "codex analyze", "ask codex", "copilot with codex".
---

# Codex Skill Guide

Codex is accessed via the `copilot` CLI. The helper script defaults to `gpt-5.4` (Copilot's recommended 1x-multiplier model) and exposes `-m/--model` for explicit overrides.

## Multiplier Policy

GitHub Copilot bills models with a per-request multiplier. The CLI does not expose multipliers locally, so the helper hardcodes a curated 1x default rather than auto-picking the highest version (which silently lands on premium tiers - `gpt-5.5` once burned 25% of a monthly quota in one run).

- **Default:** `gpt-5.4` (1x). Always use unless the user has explicitly approved a different model.
- **Before passing `-m` to opt into a higher-multiplier model** (e.g. `gpt-5.5` for harder reasoning), confirm with the user via `AskUserQuestion`. State the model name and that it carries a higher Copilot multiplier.
- Verify current multipliers in the GitHub Copilot dashboard if unsure - they change.

## Running a Task

1. Select the permission mode required for the task; default to no special flags (interactive approval) unless edits are necessary.
2. Assemble the command with appropriate options:
   - `-m, --model MODEL` to override the default (`gpt-5.4`); ask the user first if the override is a higher-multiplier model
   - `-p, --prompt <text>` for non-interactive mode
   - `-i, --interactive <prompt>` for interactive mode with initial prompt
   - `--allow-all-tools` to auto-approve tool use
   - `--allow-all-paths` to allow file access beyond current dir
   - `--allow-all` or `--yolo` for full permissions
   - `--add-dir <DIR>` to allow access to specific directories
   - `-s, --silent` for scripting (only agent response, no stats)
3. When continuing a previous session, use `copilot --continue` or `copilot --resume [sessionId]`.
4. Run the command, capture output, and summarize the outcome for the user.
5. **After Codex completes**, inform the user: "You can resume this session with 'codex resume' or 'copilot --continue'."

### Quick Reference

| Use case | Key flags |
| --- | --- |
| Read-only analysis | `-p "prompt"` |
| Interactive with initial prompt | `-i "prompt"` |
| Auto-approve tools | `--allow-all-tools -p "prompt"` |
| Full auto (edits + tools) | `--allow-all -p "prompt"` or `--yolo -p "prompt"` |
| Allow specific directory | `--add-dir <DIR> -p "prompt"` |
| Resume recent session | `--continue` |
| Resume specific session | `--resume [sessionId]` |
| Scripting (clean output) | `-s -p "prompt"` |

## Background Dispatch and Waiting

A `codex-run.sh` call can run for many minutes. When you need to do other work while it runs, or you are inside an autopilot run:

1. Dispatch the helper script with `run_in_background: true`. The dispatch tool result returns the task's output file path.
2. Wait with the `TaskOutput` tool: `TaskOutput(task_id, block=true, timeout=600000)` (600000 ms = 10 min is the max per call). It returns when the task completes or at the deadline. It is the watchdog.
3. On completion, `Read` the output file. On a timeout return, treat it as an infrastructure hang (see Error Handling); do not silently re-dispatch.

**Never hand-roll a polling loop.** Do not pass a `while`/`if`/`wc -c` stability loop to `Monitor` or `Bash` to detect completion. Such commands contain shell control flow that Warden cannot statically analyze, so they prompt for approval, which stalls an unattended autopilot run. The harness already notifies you when a background task finishes; `TaskOutput` is the only wait primitive you need.

## Following Up

- After every `copilot` command, use `AskUserQuestion` to confirm next steps or decide whether to resume.
- When resuming, the session uses the same model and context from the original session.
- Restate the permission mode when proposing follow-up actions.

## Error Handling

- Stop and report failures whenever a `copilot` command exits non-zero; request direction before retrying.
- Before using high-impact flags (`--allow-all`, `--yolo`, `--allow-all-paths`) ask user permission via AskUserQuestion unless already given.
- When output includes warnings or partial results, summarize them and ask how to adjust.

## Helper Script

**IMPORTANT**: Always use `-f` with a temp file for prompts to avoid shell escaping issues.

```bash
# Write prompt to temp file, then run
echo 'Your prompt here (can contain "quotes", parens(), etc.)' > /tmp/codex-prompt.txt
~/.claude/skills/use-codex/scripts/codex-run.sh -f /tmp/codex-prompt.txt

# With auto-approve tools
~/.claude/skills/use-codex/scripts/codex-run.sh -a -f /tmp/codex-prompt.txt

# Override model (only after user approval - higher multiplier may apply)
~/.claude/skills/use-codex/scripts/codex-run.sh -m gpt-5.5 -f /tmp/codex-prompt.txt

# Full permissions
~/.claude/skills/use-codex/scripts/codex-run.sh -y -f /tmp/codex-prompt.txt

# Resume session
~/.claude/skills/use-codex/scripts/codex-run.sh -r

# Capture output to file
~/.claude/skills/use-codex/scripts/codex-run.sh -a -o /tmp/result.txt -f /tmp/codex-prompt.txt

# Silent mode for scripting
~/.claude/skills/use-codex/scripts/codex-run.sh -s -f /tmp/codex-prompt.txt
```

Run `~/.claude/skills/use-codex/scripts/codex-run.sh --help` for all options.
