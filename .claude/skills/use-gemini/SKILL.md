---
name: use-gemini
description: Use when the user asks to run Gemini via copilot CLI for code analysis, refactoring, or automated editing. Triggers on "run gemini", "gemini analyze", "use gemini for", "ask gemini", "copilot with gemini", or when user wants Google's Gemini model for code tasks.
---

# Gemini Skill Guide

Gemini is accessed via the `copilot` CLI with `--model gemini-3-pro-preview`.

## Running a Task

1. Select the permission mode required for the task; default to no special flags (interactive approval) unless edits are necessary.
2. Assemble the command with appropriate options:
   - `--model gemini-3-pro-preview`
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

## Following Up

- After every `copilot` command, use `AskUserQuestion` to confirm next steps or decide whether to resume.
- When resuming, the session uses the same model and context from the original session.
- Restate the permission mode when proposing follow-up actions.

## Error Handling

- Stop and report failures whenever a `copilot` command exits non-zero; request direction before retrying.
- Before using high-impact flags (`--allow-all`, `--yolo`, `--allow-all-paths`) ask user permission via AskUserQuestion unless already given.
- When output includes warnings or partial results, summarize them and ask how to adjust.

## Helper Script

Use `scripts/gemini-run.sh` for common operations:

```bash
# Analysis (interactive approval)
./scripts/gemini-run.sh "Analyze the codebase"

# Auto-approve tools
./scripts/gemini-run.sh -a "Fix the bug"

# Full permissions
./scripts/gemini-run.sh -y "Refactor the module"

# Resume session
./scripts/gemini-run.sh -r

# Silent mode for scripting
./scripts/gemini-run.sh -s "Generate summary"
```

Run `./scripts/gemini-run.sh --help` for all options.
