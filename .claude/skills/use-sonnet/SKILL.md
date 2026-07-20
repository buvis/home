---
name: use-sonnet
description: Use when running Anthropic Claude Sonnet via the native claude CLI (headless) for code analysis, refactoring, or editing. Triggers on "run sonnet", "sonnet analyze", "ask sonnet".
---

# Sonnet Skill Guide

Sonnet is accessed via the native `claude` CLI (headless `-p`). The helper script defaults to the `sonnet` alias (latest base Sonnet) and exposes `-m/--model` for explicit overrides. This uses your Claude quota, not Copilot credits - never route Sonnet (or any model Claude already provides) through `copilot`.

## Dependencies

- Files read from other skill dirs:
  `~/.claude/skills/use-codex/references/dispatch-contract.md` - mandatory,
  applies verbatim (see below)
  - `~/.claude/skills/run-autopilot/scripts/detect_usage_limit.py` - optional,
    for a deterministic reset-epoch parse of a usage-limit banner (see
    "Usage-limit banner" below)
- CLIs: `claude` (native, headless `-p`); `mise` for resolution

## Dispatch Contract (shared)

Background dispatch and waiting (TaskOutput-only waiting), following up, error handling, and the always-use-`-f` prompt rule are defined once in `/Users/bob/.claude/skills/use-codex/references/dispatch-contract.md`. Read it before dispatching; it applies verbatim to this skill.

## Usage-limit banner (claude backend only)

`claude -p` is the one backend that can hit the **Claude usage limit** mid-run: instead of a normal result it returns a banner like `You've hit your session limit · resets 8:10pm (Europe/Prague)` (also `weekly`/`usage` limit; a stream-json run additionally carries a rejected `rate_limit_event` with a machine-readable `resetsAt` epoch). This is neither a task failure nor retryable — the quota is spent until the reset.

**Detect** it by scanning the run's output / `-o` file for the same markers `detect_usage_limit.py` uses: `hit your (session|usage|weekly) limit` or `usage limit reached`, and `resets <HH[:MM]> <am|pm> (<tz>)` for the reset time. For a deterministic reset epoch, run `python3 ~/.claude/skills/run-autopilot/scripts/detect_usage_limit.py --log <the -o output file>` — exit 0 prints the reset epoch (it parses both the prose banner and a stream-json `resetsAt`); exit 1 means no live limit.

**On a hit:** mark the run **FAILED**, report the reset time in the run report (`usage limit; resets <time>`), and do NOT retry before the reset — a retry re-fails identically. Under autopilot the `autoclaude` wrapper already sleeps-until-reset at the loop boundary; a standalone `use-sonnet` run cannot wait, so it stops and surfaces the reset for the user.

## Model Policy

- **Default:** `sonnet` (latest base Sonnet). Use unless the user asks for a different model.
- **`-m/--model` override:** pass a `claude` alias (`opus`, `haiku`) or a full model id (`claude-sonnet-5`). Opus costs more of your Claude quota - confirm with the user before defaulting to it for routine work.

## Running a Task

1. Select the permission mode required for the task; default to no special flags (interactive approval) unless edits are necessary.
2. Assemble the command with appropriate options:
   - `-m, --model MODEL` to override the default (`sonnet`); ask the user first if the override is a costlier tier (e.g. `opus`)
   - `-f, --file FILE` to read the prompt from a file (preferred - avoids shell escaping)
   - `-i, --interactive <prompt>` for interactive mode with initial prompt
   - `-a, --allow-edits` to auto-approve file edits only (maps to `--permission-mode acceptEdits`; Bash and other tools stay gated, so an unattended agentic child can stall on a prompt)
   - `-y, --yolo` for full permissions (`--permission-mode bypassPermissions`); REQUIRED for unattended agentic dispatches that must run commands. Note: a `-y` child runs with no warden or hook filtering
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
| Auto-approve edits only | `-a -f prompt.txt` |
| Full auto, unattended agentic (edits + commands) | `-y -f prompt.txt` |
| Allow specific directory | `-d <DIR> -f prompt.txt` |
| Resume recent session | `--continue` |
| Resume specific session | `--resume [sessionId]` |
| Scripting (clean output) | `-s -f prompt.txt` |

## Helper Script

```bash
# Write prompt to temp file (see the shared dispatch contract), then run
~/.claude/skills/use-sonnet/scripts/sonnet-run.sh -f /tmp/sonnet-prompt.txt

# With auto-approve edits (Bash still gated)
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
