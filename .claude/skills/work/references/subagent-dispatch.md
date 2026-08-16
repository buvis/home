# Subagent Dispatch

How to safely make an Agent call from `/work`. Two rules apply to **every**
Agent dispatch (Tess, Ivan, Devon, or the code reviewer): the Dispatch Budget and
the Watchdog. Read this file before your first Agent dispatch in a session.
Bare step numbers below (`step 4`, `step 4.2`, `step 2`, `step 6`) refer to
`SKILL.md`'s Workflow sections.

## Subagent Dispatch Budget

Every prompt passed to the Agent tool (Tess the test author, Ivan the implementor, Devon the adversary, or code reviewer) must be **≤ 50 000 bytes**.

PostToolUse hooks do not fire inside subagents (see `SKILL.md` "CRITICAL: One Task at a Time"), so the runtime context cap from PRD 00024 cannot abort a subagent that grows past 200K. The bound must be enforced at dispatch time, before the Agent call.

**Procedure before every Agent dispatch:**

1. Render the prompt from its persona with `scripts/render_prompt.py`, per the call shape `SKILL.md` gives for that dispatch (Tess 2.7, Ivan 3 / 5.5 / 7, Pat 5.7). The orchestrator does **not** assemble the prompt string itself: the persona files carry every fixed block, and `SKILL.md` § Passing values to render_prompt.py decides which flag each value takes.
2. Measure: the byte count `render_prompt.py` prints on stdout **is** the measurement. There is no separate `wc -c` step and no scratch copy to measure — the render already wrote the file to its `--out` path (`dev/local/tmp/dispatch-<persona>-<task-id>.txt`, a per-task filename, since a fixed name collides when independent rework tasks dispatch in parallel).
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
        `model` from `state.tasks[i].model`,
        `review_cycle: null` (Phase 3) or current `state.cycle` (rework).
     5. Report cause `subagent_prompt_overrun` and stop work on this task.
4. The abort-instruction line is **baked into the persona files**, so there is nothing to prepend:
   ```
   Abort and report if you read more than 100K of total input. Return the partial result and an abort_reason: context_overrun field.
   ```
   `agents/ivan.md` and `references/tess-prompt.md` both carry it verbatim, and a render therefore cannot omit it. Trimming at step 3 removes context, never this line. If you add a new persona to the dispatch set, put the line in the persona file rather than re-introducing a prepend step here — a prepend that some call sites remember and others forget is exactly how Tess lost this guard once.

**Rationale:** soft enforcement — the subagent honors the instruction — but `/plan-tasks`'s 150K per-task budget bounds how much context `/work` can plausibly hand off anyway. Combined, the 50K dispatch cap, the 100K subagent-internal cap, and the 150K per-task cap keep subagent contexts well under any work-tier model's window (200K for the base tiers; the `claude-fable-5[1m]` default carries 1M).

## Subagent Watchdog

Every Agent dispatch in this skill (Tess, Ivan, Devon, or the code reviewer) must be wrapped in a watchdog. A dispatched subagent can crash, lose its result, or hang silently — and a foreground `Agent` call then blocks this session **indefinitely** with no signal. Observed failure: a dead subagent left the parent session blocked for 1.5 hours until the user manually intervened.

**Dispatch protocol — applies to every Agent call:**

1. Dispatch with `run_in_background: true` (plus `model` per `SKILL.md` "Per-task model dispatch"). Record the dispatch wall-clock time. Arm the watchdog as a `Monitor` timer (`sleep 900; echo "WATCHDOG: ..."`) — **15 minutes is a check-in, not a kill deadline**.
2. When the agent's completion notification arrives first, `TaskStop` the watchdog timer immediately (a stale timer fires later and reads as a hang that is not there), retrieve the result, and continue to `SKILL.md` step 4.
3. **When the timer fires first, probe for progress before any kill** — two cheap read-only checks:
   - `git status --porcelain` (the repo's own git context): have the task's AUTHORIZED surfaces changed since dispatch?
   - `ls -la` on the dispatch's `<task-id>.output` file: is its mtime/size still advancing? (Never Read that file — it is the full subagent transcript and will overflow context.)
   Branch on the evidence:
   - **Progress on either probe** → the agent is working, not hung. Re-arm the timer (10-15 min) and keep waiting. Hard cap: **45 minutes wall-clock per dispatch**, after which treat it as hung regardless of probes.
   - **No progress on BOTH probes across two consecutive checks** (or the 45-min cap) → `TaskStop` the agent. If `TaskStop` reports the task **already completed**, the "hang" was a late completion notification — treat it as a normal completion, not a failure. Otherwise handle it as the **Result lost / hung** row of `SKILL.md`'s Handle result table (step 4) → the infrastructure-failure circuit breaker (step 4.2). Do **not** treat a hung agent as a content **Timeout**: it produced no usable work, so splitting the task (the Timeout remedy) would split nothing.
4. **After ANY kill, inspect before re-dispatching.** Run `git status` over the authorized surfaces:
   - **Work looks complete** → the kill landed at the agent's verification/reporting tail (the common case — measured 2026-07-31: 5 kills in one session, 0 true hangs; 3 had complete work on disk). Verify the work INDEPENDENTLY (run the task's own verify commands yourself); green → accept it as a normal completion. The report footers are lost with the agent, so reconstruct `FILES_TOUCHED:` from the tree and record the missing `ASSUMPTIONS:` footer in the assumptions ledger.
   - **Work is partial** → the step-4.2 re-dispatch must be a CONTINUATION brief that names the completed surfaces (verified by you) so the fresh agent does not redo or clobber them.

**Right-size multi-surface briefs — the main driver of slow dispatches.** A dispatch touching 3+ files, or any file over ~400 lines, must carry a READING BUDGET in its brief: exact `rg`/Read line anchors per surface, an ordered per-surface work plan, and per-surface verification so partial progress survives a kill. Measured 2026-07-31: an anchored continuation finished in one window a job whose unanchored first dispatch had produced zero edits in 18 minutes of reading.

A background dispatch does **not** relax the one-task-at-a-time rule: dispatch one agent, wait for it (or its watchdog), then proceed. Never have two plan-task agents in flight at once. The watchdog converts a silent infinite block into a detectable failure that the Handle result table routes to the circuit breaker.

**Helper-script dispatches** (`use-codex`/`use-gemini`/`use-qwen` helper scripts, which run as background Bash tasks) follow the same protocol: dispatch with `run_in_background: true`, then wait with `TaskOutput(task_id, block=true, timeout=600000)` (600000 ms = 10 min, the max per call) — it returns on completion or at the deadline; on a still-running return, re-issue the wait once, then treat a second timeout as a hang. Never hand-roll a `while`/`if`/`wc -c` stability loop in `Monitor` or `Bash` to detect completion: its shell control flow cannot be statically analyzed by Warden, so it prompts for approval and stalls an unattended autopilot run.

**qwen helper-script deadline.** qwen dispatches use the **10 min × 2 `TaskOutput`** wait pattern above — the same as `use-codex` and `use-gemini` — NOT the 15-min `Monitor` watchdog (which applies to Agent dispatches like Tess / Ivan / Devon / reviewer). The `pi` invocation that `qwen-run.sh` wraps is a Bash helper-script dispatch, so the helper-script deadline applies. Local-inference latency on a 30B-parameter qwen model can routinely exceed several minutes; the 10-min × 2 budget accommodates that without conflating it with the Agent watchdog.

**Three deadlines exist, by mechanism — keep them distinct:**

- **15 min check-in, progress-probed extensions, 45 min hard cap** — `Monitor` watchdog on Tess/Ivan/Devon/reviewer dispatches (this section). Honest single-task dispatch runtimes measured 2026-07-31 ranged 2-30 min (median ~12; multi-surface tasks 19-30), so a fixed 15-min kill destroys nearly-finished work.
- **10 min × 2** — `TaskOutput` waits on `use-codex`/`use-gemini` helper-script Bash dispatches (paragraph above).
- **20 min** — `Monitor` waits on backgrounded `cargo` full-suite runs (see `SKILL.md` "CRITICAL: Never Ask the User to Run Commands").

They differ because the work differs — a full Rust test suite legitimately runs longer than a single-task subagent. Do not unify them into one number.
