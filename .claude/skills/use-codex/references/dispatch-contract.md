# Use-Model Dispatch Contract

Canonical shared contract for the four dispatch skills: `use-codex`, `use-gemini`, `use-qwen`, `use-sonnet`. Each skill's SKILL.md keeps only backend-specific content (model/multiplier policy, flag quick-reference, prerequisites) and points here for everything below. When wording here and in a SKILL.md disagree, this file wins.

Every skill dispatches through its helper: `~/.claude/skills/use-<backend>/scripts/<backend>-run.sh` (backend: codex, gemini, qwen, sonnet).

## Prompt Delivery

**IMPORTANT**: Always use `-f` with a temp file for prompts to avoid shell escaping issues.

```bash
# Write prompt to temp file, then run
echo 'Your prompt here (can contain "quotes", parens(), etc.)' > /tmp/model-prompt.txt
~/.claude/skills/use-<backend>/scripts/<backend>-run.sh -f /tmp/model-prompt.txt
```

Prompts pass via argument or `-f` file, never stdin.

## Child Stdin Policy

Every headless child CLI invocation (the `-p`/`--print`/`codex exec` dispatch paths, plus preflight probes and the `mise env` PATH lookup) redirects the child's stdin with `< /dev/null`, so an unattended background dispatch can never hang on a child reading the inherited stdin (the PRD 00040 hang class). Documented exception: interactive (`-i`), bare `-r`/`--resume`, and `-c`/`--continue` invocations keep stdin - they legitimately need the TTY. Never dispatch those modes unattended.

## Error Stream Convention

Usage and preflight errors (missing prompt, missing prompt file, backend CLI not found) print to stderr and exit non-zero. stdout is reserved for model output and the tee'd `-o` run log.

## Background Dispatch and Waiting

A run-script call can run for many minutes. When you need to do other work while it runs, or you are inside an autopilot run:

1. Dispatch the helper script with `run_in_background: true`. The dispatch tool result returns the task's output file path.
2. Wait with the `TaskOutput` tool: `TaskOutput(task_id, block=true, timeout=600000)` (600000 ms = 10 min is the max per call). It returns when the task completes or at the deadline. It is the watchdog.
3. On completion, `Read` the output file. On a timeout return, treat it as an infrastructure hang (see Error Handling); do not silently re-dispatch.

**Never hand-roll a polling loop.** Do not pass a `while`/`if`/`wc -c` stability loop to `Monitor` or `Bash` to detect completion. Such commands contain shell control flow that Warden cannot statically analyze, so they prompt for approval, which stalls an unattended autopilot run. The harness already notifies you when a background task finishes; `TaskOutput` is the only wait primitive you need.

## Following Up

- After every run-script command, use `AskUserQuestion` to confirm next steps.
- By default each run is independent - a follow-up task is a new run with a new prompt, so restate the relevant context. Where the backend supports resuming, the resumed session carries the original run's model and context over (see each SKILL.md for its resume flags).
- Restate the permission mode when proposing follow-up actions.

## Error Handling

- Stop and report failures whenever a run-script command exits non-zero; request direction before retrying.
- Before using high-impact permission flags (`-y`/`--yolo` and backend equivalents) ask user permission via AskUserQuestion unless already given.
- When output includes warnings or partial results, summarize them and ask how to adjust.
