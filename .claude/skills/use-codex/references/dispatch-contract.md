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

- Attended sessions: after every run-script command, use `AskUserQuestion` to confirm next steps.
- Unattended sessions (`CLAUDE_UNATTENDED=1`): never call `AskUserQuestion`; take the documented default, log it as `defaulted:<decision>` in the run report, and follow `/Users/bob/.claude/skills/run-autopilot/references/unattended-contract.md`.
- By default each run is independent - a follow-up task is a new run with a new prompt, so restate the relevant context. Where the backend supports resuming, the resumed session carries the original run's model and context over (see each SKILL.md for its resume flags).
- Restate the permission mode when proposing follow-up actions (attended sessions).

## Error Handling

- Stop and report failures whenever a run-script command exits non-zero. Attended: request direction before retrying. Unattended (`CLAUDE_UNATTENDED=1`): retry at most 2 times, then mark the step FAILED with the captured stderr, per the unattended contract cited above.
- Before using high-impact permission flags (`-y`/`--yolo` and backend equivalents) ask user permission via AskUserQuestion unless already given; unattended, use them only where the calling skill's documented defaults already grant them.
- When output includes warnings or partial results, summarize them and ask how to adjust (attended) or log them in the run report and proceed (unattended).

### Error taxonomy

A non-zero exit is not one failure — recognize the class and act per its row before retrying (the retry bounds above still apply: attended asks, unattended retries ≤2 then FAILED). Each row names an observable recognition signal and an observable outcome; a caller that hits this case answers "what do I do when the CLI fails this way" from the table, not from memory.

| Class | Recognize by | Action |
|-------|--------------|--------|
| **Auth expired** | stderr names auth/login/credentials/token — `not logged in`, `authentication failed`, `401`, `re-authenticate` | Do NOT retry blindly (a retry re-fails identically). Mark the step **FAILED** and print the re-auth hint (the backend's login command — e.g. `codex login`, `gemini`/`copilot` auth). Unattended cannot re-auth, so it stops here rather than burning retries. |
| **Quota / rate exhausted** | stderr names quota/rate/usage — `monthly quota exceeded`, `rate limit`, `429`, `usage limit`. DISTINCT from auth: the credential is valid, the budget is spent | Mark **FAILED** — retrying spends nothing and fixes nothing. When the CLI reports a reset time, **quote it in the run report** so the caller knows when a retry could succeed. (A Carl/copilot `monthly quota exceeded` is this class — a runtime skip, not a prerequisite failure.) |
| **CLI died mid-run** | non-zero exit with a truncated/partial `-o` file (crash, OOM-kill, SIGKILL) | **Salvage** what landed in the `-o` file, mark it **PARTIAL** in the run report, and treat the run as FAILED-with-partial — never present a truncated result as the full answer. |
| **Empty output despite rc 0** | helper exited 0 but the `-o` file is empty (0 bytes) or whitespace-only | Treat as **FAILED**, not success (a silent empty result reads as a passed review that never happened). **Quote the run's stderr** in the report — the real cause is usually there. |

**Codex exit-4 salvage (codex backend).** `codex-run.sh` exit 4 (codex ran but the wrapper flagged failure, e.g. quota) has a documented FALSE-POSITIVE mode: the quota/error markers can match codex's own command-line args or gateguard ERROR noise while codex actually finished, and the `-o` file may be unwritten even though the work completed. Before treating exit 4 as the Quota class above, check the wrapper's `codex-review-last.jsonl` sidecar (its last-run JSONL): if it holds a COMPLETE result (the expected findings/verdict content), **salvage it and treat the run as succeeded**. Only when nothing salvageable is in the sidecar → FAILED. Encoded here so every codex caller inherits it, not just `review-work-completion` (which carries the review-specific `R{n}:`-verdict variant). Memory: `project_codex_review_run_exit4_false_positive`.
