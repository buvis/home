---
name: use-codex
description: Use when the user asks to run Codex CLI (codex exec, codex resume) or references OpenAI Codex for code analysis, refactoring, or automated editing. Triggers on "run codex", "codex analyze", "use codex for", "codex refactor", "ask codex", or when user wants OpenAI's Codex model for code tasks.
---

# Codex Skill Guide

Codex is accessed via the `copilot` CLI. The helper script auto-detects the latest `gpt-*-codex` model from `copilot --help` (falls back to `gpt-5.3-codex`).

## Running a Task

1. Select the permission mode required for the task; default to no special flags (interactive approval) unless edits are necessary.
2. Assemble the command with appropriate options:
   - `--model` (auto-detected latest codex model)
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
