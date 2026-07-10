---
name: use-sonnet
description: Use when running Anthropic Claude Sonnet via the native claude CLI (headless) for code analysis, refactoring, or editing. Triggers on "run sonnet", "sonnet analyze", "ask sonnet".
---

# Sonnet Skill Guide

Sonnet is accessed via the native `claude` CLI (headless `-p`). The helper script defaults to the `sonnet` alias (latest base Sonnet) and exposes `-m/--model` for explicit overrides. This uses your Claude quota, not Copilot credits - never route Sonnet (or any model Claude already provides) through `copilot`.

## Dispatch Contract (shared)

Background dispatch and waiting (TaskOutput-only waiting), following up, error handling, and the always-use-`-f` prompt rule are defined once in `/Users/bob/.claude/skills/use-codex/references/dispatch-contract.md`. Read it before dispatching; it applies verbatim to this skill.

## Model Policy

- **Default:** `sonnet` (latest base Sonnet). Use unless the user asks for a different model.
- **`-m/--model` override:** pass a `claude` alias (`opus`, `haiku`) or a full model id (`claude-sonnet-5`). Opus costs more of your Claude quota - confirm with the user before defaulting to it for routine work.

## Running a Task

1. Select the permission mode required for the task; default to no special flags (interactive approval) unless edits are necessary.
2. Assemble the command with appropriate options:
   - `-m, --model MODEL` to override the default (`sonnet`); ask the user first if the override is a costlier tier (e.g. `opus`)
   - `-f, --file FILE` to read the prompt from a file (preferred - avoids shell escaping)
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
| Read-only analysis | `-f prompt.txt` |
| Interactive with initial prompt | `-i "prompt"` |
| Auto-approve tools | `-a -f prompt.txt` |
| Full auto (edits + tools) | `-y -f prompt.txt` |
| Allow specific directory | `-d <DIR> -f prompt.txt` |
| Resume recent session | `--continue` |
| Resume specific session | `--resume [sessionId]` |
| Scripting (clean output) | `-s -f prompt.txt` |

## Helper Script

```bash
# Write prompt to temp file (see the shared dispatch contract), then run
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
```

Run `~/.claude/skills/use-sonnet/scripts/sonnet-run.sh --help` for all options.
