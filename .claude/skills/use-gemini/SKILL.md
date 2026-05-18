---
name: use-gemini
description: Use when running Google Gemini via the copilot CLI for code analysis, refactoring, or editing. Triggers on "run gemini", "gemini analyze", "ask gemini", "copilot with gemini".
---

# Gemini Skill Guide

Gemini is accessed via the `copilot` CLI. The helper script defaults to `gemini-3-pro-preview` and exposes `-m/--model` for explicit overrides.

> **Heads up:** GitHub removed Gemini models from the Copilot CLI around 2026-03-26. Calls will fail until/unless GitHub re-adds them. Confirm availability before invoking.

## Multiplier Policy

GitHub Copilot bills models with a per-request multiplier. The CLI does not expose multipliers locally, so the helper hardcodes a curated default rather than auto-picking the latest version. Before passing `-m` to override, confirm with the user via `AskUserQuestion` if the target model carries a higher Copilot multiplier. Verify current multipliers in the GitHub Copilot dashboard.

## Running a Task

1. Select the permission mode required for the task; default to no special flags (interactive approval) unless edits are necessary.
2. Assemble the command with appropriate options:
   - `-m, --model MODEL` to override the default (`gemini-3-pro-preview`); ask the user first if the override is a higher-multiplier model
   - `-p, --prompt <text>` for non-interactive mode
   - `-i, --interactive <prompt>` for interactive mode with initial prompt
   - `--allow-all-tools` to auto-approve tool use
   - `--allow-all-paths` to allow file access beyond current dir
   - `--allow-all` or `--yolo` for full permissions
   - `--add-dir <DIR>` to allow access to specific directories
   - `-s, --silent` for scripting (only agent response, no stats)
3. When continuing a previous session, use `copilot --continue` or `copilot --resume [sessionId]`.
4. Run the command, capture output, and summarize the outcome for the user.
5. **After Gemini completes**, inform the user: "You can resume this session with 'gemini resume' or 'copilot --continue'."

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

A `gemini-run.sh` call can run for many minutes. When you need to do other work while it runs, or you are inside an autopilot run:

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
echo 'Your prompt here (can contain "quotes", parens(), etc.)' > /tmp/gemini-prompt.txt
~/.claude/skills/use-gemini/scripts/gemini-run.sh -f /tmp/gemini-prompt.txt

# With auto-approve tools
~/.claude/skills/use-gemini/scripts/gemini-run.sh -a -f /tmp/gemini-prompt.txt

# Full permissions
~/.claude/skills/use-gemini/scripts/gemini-run.sh -y -f /tmp/gemini-prompt.txt

# Resume session
~/.claude/skills/use-gemini/scripts/gemini-run.sh -r

# Silent mode for scripting
~/.claude/skills/use-gemini/scripts/gemini-run.sh -s -f /tmp/gemini-prompt.txt
```

Run `~/.claude/skills/use-gemini/scripts/gemini-run.sh --help` for all options.
