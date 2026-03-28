---
name: use-sonnet
description: Use when the user asks to run Sonnet via copilot CLI for code analysis, refactoring, or automated editing. Triggers on "run sonnet", "sonnet analyze", "use sonnet for", "ask sonnet", "copilot with sonnet", or when user wants Claude Sonnet model via copilot for code tasks.
---

# Sonnet Skill Guide

Sonnet is accessed via the `copilot` CLI using the `claude-sonnet-4.6` model.

## Running a Task

1. Select the permission mode required for the task; default to no special flags (interactive approval) unless edits are necessary.
2. Assemble the command with appropriate options:
   - `--model claude-sonnet-4.6` (hardcoded)
   - `-p, --prompt <text>` for non-interactive mode
   - `-i, --interactive <prompt>` for interactive mode with initial prompt
   - `--allow-all-tools` to auto-approve tool use
   - `--allow-all-paths` to allow file access beyond current dir
   - `--allow-all` or `--yolo` for full permissions
   - `--add-dir <DIR>` to allow access to specific directories
   - `-s, --silent` for scripting (only agent response, no stats)
3. When continuing a previous session, use `copilot --continue` or `copilot --resume [sessionId]`.
4. Run the command, capture output, and summarize the outcome for the user.
5. **After Sonnet completes**, inform the user: "You can resume this session with 'sonnet resume' or 'copilot --continue'."

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
echo 'Your prompt here (can contain "quotes", parens(), etc.)' > /tmp/sonnet-prompt.txt
~/.claude/skills/use-sonnet/scripts/sonnet-run.sh -f /tmp/sonnet-prompt.txt

# With auto-approve tools
~/.claude/skills/use-sonnet/scripts/sonnet-run.sh -a -f /tmp/sonnet-prompt.txt

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
