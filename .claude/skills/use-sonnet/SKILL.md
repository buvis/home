---
name: use-sonnet
description: Use when running Anthropic Claude Sonnet via the native claude CLI (headless) for code analysis, refactoring, or editing. Triggers on "run sonnet", "sonnet analyze", "ask sonnet".
---

# Sonnet Skill Guide

Sonnet is accessed via the native `claude` CLI (headless `-p`). The helper script defaults to the `sonnet` alias (latest base Sonnet) and exposes `-m/--model` for explicit overrides. This uses your Claude quota, not Copilot credits - never route Sonnet (or any model Claude already provides) through `copilot`.

## Model Policy

- **Default:** `sonnet` (latest base Sonnet). Use unless the user asks for a different model.
- **`-m/--model` override:** pass a `claude` alias (`opus`, `haiku`) or a full model id (`claude-sonnet-5`). Opus costs more of your Claude quota - confirm with the user before defaulting to it for routine work.

## Running a Task

1. Select the permission mode required for the task; default to no special flags (interactive approval) unless edits are necessary.
2. Assemble the command with appropriate options:
   - `-m, --model MODEL` to override the default (`sonnet`); ask the user first if the override is a costlier tier (e.g. `opus`)
   - `-p, --prompt <text>` for non-interactive mode
   - `-i, --interactive <prompt>` for interactive mode with initial prompt
   - `-a, --allow-tools` to auto-approve tool use (maps to `--permission-mode bypassPermissions`)
   - `-y, --yolo` for full permissions
   - `-d, --dir <DIR>` to allow access to specific directories (maps to `--add-dir`)
   - `-s, --silent` accepted for compatibility (claude `-p` output is already clean)
3. When continuing a previous session, use `-c`/`--continue` or `-r`/`--resume [sessionId]`.
4. Run the command, capture output, and summarize the outcome for the user.
5. **After Sonnet completes**, inform the user: "You can resume this session with 'sonnet resume' or 'claude --continue'."

### Quick Reference

| Use case | Key flags |
| --- | --- |
| Read-only analysis | `-p "prompt"` |
| Interactive with initial prompt | `-i "prompt"` |
| Auto-approve tools | `-a -p "prompt"` |
| Full auto (edits + tools) | `-y -p "prompt"` |
| Allow specific directory | `-d <DIR> -p "prompt"` |
| Resume recent session | `--continue` |
| Resume specific session | `--resume [sessionId]` |
| Scripting (clean output) | `-s -p "prompt"` |

## Background Dispatch and Waiting

A `sonnet-run.sh` call can run for many minutes. When you need to do other work while it runs, or you are inside an autopilot run:

1. Dispatch the helper script with `run_in_background: true`. The dispatch tool result returns the task's output file path.
2. Wait with the `TaskOutput` tool: `TaskOutput(task_id, block=true, timeout=600000)` (600000 ms = 10 min is the max per call). It returns when the task completes or at the deadline. It is the watchdog.
3. On completion, `Read` the output file. On a timeout return, treat it as an infrastructure hang (see Error Handling); do not silently re-dispatch.

**Never hand-roll a polling loop.** Do not pass a `while`/`if`/`wc -c` stability loop to `Monitor` or `Bash` to detect completion. Such commands contain shell control flow that Warden cannot statically analyze, so they prompt for approval, which stalls an unattended autopilot run. The harness already notifies you when a background task finishes; `TaskOutput` is the only wait primitive you need.

## Following Up

- After every Sonnet run, use `AskUserQuestion` to confirm next steps or decide whether to resume.
- When resuming, the session uses the same model and context from the original session.
- Restate the permission mode when proposing follow-up actions.

## Error Handling

- Stop and report failures whenever the `claude` command exits non-zero; request direction before retrying.
- Before using high-impact flags (`-y`/`--yolo`) ask user permission via AskUserQuestion unless already given.
- When output includes warnings or partial results, summarize them and ask how to adjust.

## Helper Script

**IMPORTANT**: Always use `-f` with a temp file for prompts to avoid shell escaping issues.

```bash
# Write prompt to temp file, then run
echo 'Your prompt here (can contain "quotes", parens(), etc.)' > /tmp/sonnet-prompt.txt
~/.claude/skills/use-sonnet/scripts/sonnet-run.sh -f /tmp/sonnet-prompt.txt

# With auto-approve tools
~/.claude/skills/use-sonnet/scripts/sonnet-run.sh -a -f /tmp/sonnet-prompt.txt

# Override model (only after user approval - costlier tier)
~/.claude/skills/use-sonnet/scripts/sonnet-run.sh -m opus -f /tmp/sonnet-prompt.txt

# Full permissions
~/.claude/skills/use-sonnet/scripts/sonnet-run.sh -y -f /tmp/sonnet-prompt.txt

# Resume session
~/.claude/skills/use-sonnet/scripts/sonnet-run.sh -r

# Capture output to file
~/.claude/skills/use-sonnet/scripts/sonnet-run.sh -a -o /tmp/result.txt -f /tmp/sonnet-prompt.txt

# Silent mode for scripting
~/.claude/skills/use-sonnet/scripts/sonnet-run.sh -s -f /tmp/sonnet-prompt.txt
```

Run `~/.claude/skills/use-sonnet/scripts/sonnet-run.sh --help` for all options.
