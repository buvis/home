# Subagent Dispatch

How to safely make an Agent call from `/work`. Two rules apply to **every**
Agent dispatch (Tess, Ivan, Devon, or the code reviewer): the Dispatch Budget and
the Watchdog. Read this file before your first Agent dispatch in a session.
Bare step numbers below (`step 4`, `step 4.2`, `step 2`, `step 6`) refer to
`SKILL.md`'s Workflow sections.

## Dispatch-log append

At every terminal outcome of a dispatch, append one entry to `dev/local/autopilot/dispatch-log.jsonl` by running:

```bash
python3 ~/.claude/skills/run-autopilot/scripts/log_dispatch.py \
  --prd <prd> --task-id <id> --task-name <name> \
  --dispatch-type <tess|ivan|devon|reviewer|codex|gemini|qwen> \
  --model <model> --outcome <outcome> \
  --duration-s <seconds> --attempt <n>
```

`ts` is computed by the helper. `duration_s` = now minus the watchdog's already-recorded dispatch wall-clock start time (recorded in step 1 of the Subagent Watchdog below). The helper is gated on `$_AUTOPILOT_LOOP` (no-op outside an autopilot run) and always exits 0 — this is fire-and-forget; never gate control flow on it.

**Outcome mapping:**

| Terminal outcome | `outcome` value |
|-----------------|----------------|
| Monitor reports agent finished within deadline | `completed` |
| 15-min Monitor deadline elapsed, agent hung (first or second) | `hung` |
| Handle-result: Timeout row | `timeout` |
| Handle-result: Context exceeded row | `context_overrun` |
| Handle-result: Error row | `error` |
| Handle-result: Result lost / hung row (routes to circuit breaker) | `hung` |
| Circuit-breaker step 4.2 second infra failure | `infra_failure` |
| Dispatch Budget abort (prompt still oversized after trim) | `subagent_prompt_overrun` |
| Helper-script (codex/gemini) completed | `completed` |
| Helper-script (codex/gemini) timed out | `timeout` |
| Helper-script (codex/gemini) hung after second wait | `hung` |
| Helper-script (qwen) completed | `completed` |
| Helper-script (qwen) timed out | `timeout` |
| Helper-script (qwen) hung after second wait | `hung` |

**Additive rule:** the log-append does NOT replace `state.task_aborts[]` or `state.tasks[].attempts[]` writes — both continue exactly as before. This is an additional record only.

## Subagent Dispatch Budget

Every prompt passed to the Agent tool (Tess the test author, Ivan the implementor, Devon the adversary, or code reviewer) must be **≤ 50 000 bytes**.

PostToolUse hooks do not fire inside subagents (see `SKILL.md` "CRITICAL: One Task at a Time"), so the runtime context cap from PRD 00024 cannot abort a subagent that grows past 200K. The bound must be enforced at dispatch time, before the Agent call.

**Procedure before every Agent dispatch:**

1. Assemble the prompt string (task description + relevant file paths + test patterns + code-quality rules block + abort instruction).
2. Measure: write the assembled prompt to `/tmp/dispatch-prompt-<task-id>.txt` (per-task filename — a fixed name collides when independent rework tasks dispatch in parallel), then check size with `wc -c /tmp/dispatch-prompt-<task-id>.txt` (pass the path as an argument — no `<` redirect). **Absolute path required** — relative `tmp/...` or `../../tmp/...` paths trip auto-mode's classifier and stall an unattended autopilot run on a permission prompt, even though `/tmp/**` is in `permissions.allow`. The autoMode allowlist matches the *literal* path the tool was invoked with.
3. If the prompt exceeds 50 000 bytes:
   - Trim by removing the lowest-priority context first (large example files, full architecture docs). Re-measure.
   - If still oversized after one trim pass, abort the task. Wire the abort
     through the same handoff the runtime context-cap hook uses, so
     `/run-autopilot` Phase 0 of the next session replans the PRD in place
     (PRD stays in `wip/`; see Phase 0 step 1's replan procedure — parallel
     to `context_overrun`):
     1. Append to `state.task_aborts[]`:
        ```json
        {"task_id": "<id>", "turn": -1, "total_input_tokens": <prompt-bytes/4>, "cause": "subagent_prompt_overrun"}
        ```
     2. Set `state.stall_reason`:
        ```json
        {"stalled": "subagent_prompt_overrun", "task": "<id>", "prompt_bytes": <prompt-bytes>}
        ```
        In the same state write, set `state.next_phase` to `"planning"` —
        the relaunch is a replan (planning) session and `autoclaude` picks
        the launch model from `next_phase`; leaving it at `"work"` would
        launch the replan on the work-tier model.
     3. **Only if `$_AUTOPILOT_LOOP` is set** (per `/run-autopilot` "Loop
        Detection" — manual sessions have no shell wrapper to restart on
        SIGINT), write `task_aborted` to the autopilot signal file. Use
        walk-up discipline to find the autopilot dir from cwd, then write
        to `<autopilot_dir>/signal`. Skip the signal write when
        `$_AUTOPILOT_LOOP` is unset; the next manual `/run-autopilot`
        invocation will resume via `state.stall_reason`.
     4. Append an attempt-log entry per `references/attempt-logging.md`:
        `outcome: "aborted"`, `cause: "subagent_prompt_overrun"`,
        `model` from `task.metadata.model`,
        `review_cycle: null` (Phase 3) or current `state.cycle` (rework).
     5. **Dispatch-log append** (see "Dispatch-log append" above): `outcome: "subagent_prompt_overrun"`, `duration_s` = now minus dispatch wall-clock start (0 if no dispatch occurred yet), `dispatch_type` = the type that was about to be dispatched.
     6. Report cause `subagent_prompt_overrun` and stop work on this task.
4. Prepend the abort-instruction line verbatim to the prompt:
   ```
   Abort and report if you read more than 100K of total input. Return the partial result and an abort_reason: context_overrun field.
   ```

**Rationale:** soft enforcement — the subagent honors the instruction — but `/plan-tasks`'s 150K per-task budget bounds how much context `/work` can plausibly hand off anyway. Combined, the 50K dispatch cap, the 100K subagent-internal cap, and the 150K per-task cap keep subagent contexts well under Sonnet 4.6's 200K standard-tier ceiling.

## Subagent Watchdog

Every Agent dispatch in this skill (Tess, Ivan, Devon, or the code reviewer) must be wrapped in a watchdog. A dispatched subagent can crash, lose its result, or hang silently — and a foreground `Agent` call then blocks this session **indefinitely** with no signal. Observed failure: a dead subagent left the parent session blocked for 1.5 hours until the user manually intervened.

**Dispatch protocol — applies to every Agent call:**

1. Dispatch with `run_in_background: true` (plus `model` per `SKILL.md` "Per-task model dispatch"). Record the dispatch wall-clock time.
2. Wait for the background agent using the `Monitor` tool with a **15-minute** timeout. The harness re-invokes you when a background agent finishes — do not poll in a tight loop.
3. If `Monitor` reports the agent completed within the deadline, retrieve its result (`TaskOutput`) and continue to the result handling in `SKILL.md` step 4. **Dispatch-log append** (see "Dispatch-log append" above): `outcome: "completed"`, `duration_s` = now minus the start time recorded in step 1.
4. If the 15-minute deadline elapses with no completion, the agent is **presumed hung**: call `TaskStop` on it, then handle it as the **Result lost / hung** row of `SKILL.md`'s Handle result table (step 4) — which routes to the infrastructure-failure circuit breaker (step 4.2). Do **not** treat a hung agent as a content **Timeout**: it produced no usable work, so splitting the task (the Timeout remedy) would split nothing. **Dispatch-log append** (see "Dispatch-log append" above): `outcome: "hung"`, `duration_s` = now minus the start time recorded in step 1. This fires on the FIRST hang — the dispatch log closes the gap where a first-hang produced no record.

A background dispatch does **not** relax the one-task-at-a-time rule: dispatch one agent, wait for it (or its watchdog), then proceed. Never have two plan-task agents in flight at once. The watchdog converts a silent infinite block into a detectable failure that the Handle result table routes to the circuit breaker.

**Helper-script dispatches** (`use-codex`/`use-gemini`/`use-qwen` helper scripts, which run as background Bash tasks) follow the same protocol: dispatch with `run_in_background: true`, then wait with `TaskOutput(task_id, block=true, timeout=600000)` (600000 ms = 10 min, the max per call) — it returns on completion or at the deadline; on a still-running return, re-issue the wait once, then treat a second timeout as a hang. Never hand-roll a `while`/`if`/`wc -c` stability loop in `Monitor` or `Bash` to detect completion: its shell control flow cannot be statically analyzed by Warden, so it prompts for approval and stalls an unattended autopilot run. At each terminal state, **dispatch-log append** (see "Dispatch-log append" above) with `dispatch_type: "codex"`, `"gemini"`, or `"qwen"` and the matching outcome: `completed` on success, `timeout` on first-wait deadline, `hung` on second-wait deadline.

**qwen helper-script deadline.** qwen dispatches use the **10 min × 2 `TaskOutput`** wait pattern above — the same as `use-codex` and `use-gemini` — NOT the 15-min `Monitor` watchdog (which applies to Agent dispatches like Tess / Ivan / Devon / reviewer). The `pi` invocation that `qwen-run.sh` wraps is a Bash helper-script dispatch, so the helper-script deadline applies. Local-inference latency on a 30B-parameter qwen model can routinely exceed several minutes; the 10-min × 2 budget accommodates that without conflating it with the Agent watchdog.

**Three deadlines exist, by mechanism — keep them distinct:**

- **15 min** — `Monitor` watchdog on Tess/Ivan/Devon/reviewer dispatches (this section).
- **10 min × 2** — `TaskOutput` waits on `use-codex`/`use-gemini` helper-script Bash dispatches (paragraph above).
- **20 min** — `Monitor` waits on backgrounded `cargo` full-suite runs (see `SKILL.md` "CRITICAL: Never Ask the User to Run Commands").

They differ because the work differs — a full Rust test suite legitimately runs longer than a single-task subagent. Do not unify them into one number.
