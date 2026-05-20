# Autopilot Recovery Procedures

Rare-path handlers extracted from `SKILL.md` so the happy-path flow stays compact. Each section is reached via a one-line pointer at the originating phase. None of these run in normal operation.

## Work-phase abort: replan procedure

Reached from **Phase 0** when `state.stall_reason.stalled` is `"context_overrun"` (a Work turn exceeded the context cap — `autopilot_context_cap_hook.py` prepared the handoff) or `"subagent_prompt_overrun"` (`/work`'s Subagent Dispatch Budget aborted a task whose assembled prompt exceeded 50K after one trim pass). The previous session's Work phase aborted from a hook. **The PRD is not broken — one of its tasks was scoped too big for a single Work turn.** Instead of stalling the PRD, replan it with smaller tasks and resume.

1. The aborted PRD filename is `state.prd`. Identify the aborted task from `state.task_aborts[-1]` (most recent abort): `task_id`, `cause`.
2. Read `state.replan_count` (default 0 if absent). Increment in memory.
3. **Budget floor guard:** compute `target_budget = max(40000, int(75000 / (2 ** (replan_count - 1))))`. This halves the per-task budget on each replan attempt, floored at 40K — the structural minimum for any single-file task (30K overhead + small file + PRD slice). Progression: replan 1 → 75K, replan 2 → 40K (floor), replan 3+ → 40K (floor). If `replan_count > 5` AND the same task keeps aborting, the task is genuinely too execution-heavy for a single agent turn. PAUSE:
   ```
   ── AUTOPILOT ── PRD: {prd-name} ── PAUSED ──────────────────────────
   ── {replan_count} replans, task still execution-overflowing ───────
   ── aborted task: {task_id}, cause: {cause} ─────────────────────────
   ── task may need manual scope reduction in the PRD ─────────────────
   ```
   Do NOT move the PRD anywhere. Do NOT clear state. STOP and wait for the user. The user will edit the PRD, delete tasks manually, or run `/run-autopilot status` to inspect.
4. Otherwise, prepare the replan:
   a. Build the completed-work summary AND capture the aborted-task title first (before any deletion). The data available pre-hydration is the `state.tasks[]` snapshot (`{id, name, status, model?, attempts?}` per state-schema row 127) and `state.task_aborts[-1]` (`{task_id, cause}`); `TaskList` is empty in the fresh session, and `attempts[]` does not carry commit refs (see state-schema row 129 enum). So: for the **completed-work summary**, filter `state.tasks` to `status == "completed"` and capture each entry's `name`; if the user wants commit refs in the replan context, they come from `git log` on the active branch, not from `attempts[]`. For the **aborted task**, look up `state.task_aborts[-1].task_id` in `state.tasks[]` and capture its `name`. Description is intentionally not part of the snapshot; the task name + the PRD itself give plan-tasks enough context to scope the replan. Both captures must happen before step 4b clears `state.tasks`.
   b. Query `TaskList` and `TaskUpdate(status: "deleted")` for every task regardless of status. Then clear `state.tasks` entirely (`[]`). The completed work is captured in step 4a's summary and the committed code itself; keeping completed entries in `state.tasks` alongside new plan-tasks output would collide on the fresh `TaskCreate` ids (which start at 1) and corrupt the dashboard.
   c. Write `dev/local/autopilot/replan-context.md` (overwrite if exists):
      ```markdown
      # Replan Context

      PRD: {state.prd}
      Replan attempt: {replan_count}
      Trigger: {stall_reason.stalled} on task {task_id}
      Budget: {target_budget} tokens per task

      ## Completed work (do NOT re-plan)

      - {task name from state.tasks[]} {optional: commit-ref from `git log` on active branch, if helpful}
      - ...

      ## Aborted task

      {aborted task name captured in step 4a; omit this section if step 4a found no matching entry}

      ## Directive

      Plan ONLY the remaining PRD scope (work not in "Completed work" above).
      Target ≤ {target_budget} tokens per task — the last attempt aborted at
      runtime, so split fine-grained. Budget halves each replan attempt.
      ```
   d. Update state:
      - Set `state.replan_count` to the incremented value.
      - Remove `"planning"` and `"work"` from `phases_completed` (keep `"catchup"` — the capsule is still good for the same branch).
      - `state.tasks: []`, `tasks_total: 0`, `tasks_completed: 0` (already cleared in step 4b).
      - Clear `stall_reason`.
      - `rework_task_ids: []` (defensive — a stale array would put the next Phase 3 incorrectly into rework mode against deleted task IDs).
      - Set `phase: "planning"`, `next_phase: "planning"`.
5. Print:
   ```
   ── AUTOPILOT ── PRD: {prd-name} ── REPLAN #{replan_count} (≤{target_budget} tok/task) ──
   ── trigger: {stall_reason.stalled} on {task_id} ────────────────────
   ── cleared {n} tasks ({m} completed kept in replan-context.md) ─────
   ── handing off to fresh session for planning ───────────────────────
   ```
6. Hand off: if `$_AUTOPILOT_LOOP` is set, use the canonical walk-up signal-write procedure (see "Canonical signal-write procedure" under Loop Detection in `SKILL.md`) to write `next` to the signal file at the absolute path, then STOP. Otherwise STOP and wait for the user to re-invoke `/run-autopilot`. The next session lands at Phase 2 (planning is no longer in `phases_completed`); Phase 2 will detect `replan-context.md` and pass it to `/plan-tasks`.

If `stall_reason.stalled` is anything else (or absent), return to Phase 0's Normal PRD selection.

## Crash recovery: escalation_exhausted seen at Phase 0

`escalation_exhausted` is owned inline by Phase 6 — the rework path is inside the autopilot flow, so it does its own stall move + clear before signaling. Phase 0 should never see `escalation_exhausted` in normal operation. If it does, treat it as corrupt-state crash recovery (the crash landed between Phase 6's `mv` and its `stall_reason` clear, so the PRD is already in `dev/local/prds/stalled/` but state still points at it): log a warning, clear `stall_reason`, do NOT re-run the move (Phase 6 already moved the PRD), AND reset PRD-specific fields the same way Phase 9 step 10 does for the next PRD — `phases_completed: []`, `cycle: 1`, `tasks_total: 0`, `tasks_completed: 0`, `replan_count: 0`, clear `tasks`/`task_aborts`/`autonomous_decisions`/`deferred_decisions`/`review_cycles`/`doubts`/`rework_task_ids`, preserve `batch`, set `next_phase: "catchup"` — then fall through to Phase 0's Normal PRD selection so the next PRD gets picked cleanly.

## plan-tasks stall: oversized task

Reached from **Phase 2** when `/plan-tasks` exits non-zero and writes `state.stall_reason` because a task cannot be split below the per-task budget (150K standard, or the dynamic budget from `replan-context.md` in replan mode — see `plan-tasks/SKILL.md` "Stall behavior" and "Detect replan mode").

1. Read `dev/local/autopilot/state.json`. If `stall_reason.stalled == "oversized_task"`, do NOT proceed to Phase 3.
2. **Delete any tasks `/plan-tasks` already created.** `/plan-tasks` calls `TaskCreate` before the per-task budget check, so tasks may exist in `TaskList` by the time the stall fires. Query `TaskList`, then `TaskUpdate(status: "deleted")` for every task. Same pattern as Phase 9 step 5 — prevents Phase 2's `TaskList`-skip logic from skipping planning on the next PRD.
3. Ensure `dev/local/prds/stalled/` exists (`mkdir -p dev/local/prds/stalled`).
4. `mv` the PRD from `dev/local/prds/wip/<filename>` to `dev/local/prds/stalled/<filename>` (keep the `00XXX-` prefix).
5. Clear the stall key from state: read state, delete `stall_reason`, write back. Reset PRD-specific fields the same way Phase 9 does for the next PRD: `phases_completed: []`, `cycle: 1`, `tasks_total: 0`, `tasks_completed: 0`, `replan_count: 0`, clear `tasks`/`task_aborts`/`autonomous_decisions`/`deferred_decisions`/`review_cycles`/`doubts`/`rework_task_ids`. Preserve `batch`. Set `next_phase: "catchup"`. Delete `dev/local/autopilot/replan-context.md` if it exists — otherwise the next PRD's planning would falsely enter replan mode.
6. Print:
   ```
   ── AUTOPILOT ── PRD: {prd-name} ── STALLED (oversized_task) ─────
   ── moved to dev/local/prds/stalled/ ── advancing to next PRD ────
   ```
7. If `$_AUTOPILOT_LOOP` is set, use the canonical walk-up signal-write procedure (see "Canonical signal-write procedure" under Loop Detection in `SKILL.md`) to write `next` to the signal file at the absolute path (same mechanism as Phase 9 PRD-to-PRD transition), then STOP. Otherwise jump back to Phase 0 in this same session to pick the next PRD.

## Rework escalation exhausted

Reached from **Phase 6** when a review-flagged task's last attempt was already at tier `"opus"` — the `haiku → sonnet → opus` chain has no higher tier, so the task cannot be reworked automatically.

Rewrite the attempt entry's `outcome` to `"rework_failed"`, then merge into state:

```json
"stall_reason": {"stalled": "escalation_exhausted", "task": "<id>"}
```

(The `outcome` rewrite is forensic — the stall move below clears `state.tasks` immediately after, so the `"rework_failed"` value only persists in pre-clear observers (the pidash dashboard reading state.json, any PostToolUse hook firing between the rewrite and the clear). It documents the failure mode for external observers in the brief window before reset; the durable record lives in the PRD's commit history and in `stall_reason.stalled` itself.)

Then perform the **stall move**, identical to the "plan-tasks stall: oversized task" handler above. Sub-steps run in order: the PRD `mv` (step 2) precedes the state clear (step 3). This ordering matters because a crash between the two leaves the PRD in `stalled/` with stale state still referencing it — the "Crash recovery: escalation_exhausted seen at Phase 0" section above detects this and recovers by clearing state without re-running the move.

1. `mkdir -p dev/local/prds/stalled` if missing.
2. `mv` the PRD from `dev/local/prds/wip/<filename>` to `dev/local/prds/stalled/<filename>` (keep the `00XXX-` prefix).
3. Clear `stall_reason` from state. Reset PRD-specific fields the same way Phase 9 step 10 does for the next PRD: `phases_completed: []`, `cycle: 1`, `tasks_total: 0`, `tasks_completed: 0`, `replan_count: 0`, clear `tasks`/`task_aborts`/`autonomous_decisions`/`deferred_decisions`/`review_cycles`/`doubts`/`rework_task_ids`. Preserve `batch`. Set `next_phase: "catchup"`. Delete `dev/local/autopilot/replan-context.md` if it exists (defensive — it should already be gone by the time we reach a rework path).
4. Print:
   ```
   ── AUTOPILOT ── PRD: {prd-name} ── STALLED (escalation_exhausted) ──
   ── moved to dev/local/prds/stalled/ ── advancing to next PRD ──────
   ```
5. If `$_AUTOPILOT_LOOP` is set, use the canonical walk-up signal-write procedure (see "Canonical signal-write procedure" under Loop Detection in `SKILL.md`) to write `next` to the signal file at the absolute path, then STOP. Otherwise jump back to Phase 0 in this same session to pick the next PRD.
