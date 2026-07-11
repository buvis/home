# Autopilot Recovery Procedures

Rare-path handlers extracted from the autopilot skill (core `SKILL.md` + the `phase-*.md` gate files) so the happy-path flow stays compact. Each section is reached via a one-line pointer at the originating phase. None of these run in normal operation.

## Loop-mode stall procedure (PRD 00017)

The uniform "a single PRD may stall; the batch never stops to ask a question"
procedure. Every loop-mode failure site references THIS section instead of
pausing. Interactive (non-loop) sites keep their PAUSE semantics.

1. **Move the PRD** from `dev/local/prds/wip/<filename>` to
   `dev/local/prds/stalled/<filename>` (keep the `00XXX-` prefix), after
   `mkdir -p dev/local/prds/stalled`. **Verify the move** (file exists at the
   destination). If the `mv` fails, retry ONCE after re-running `mkdir -p`;
   if it still fails, this is the one legitimate loud stop — notify ⚠️ and
   halt (set `state.phase = "paused"`, `state.pause_reason = {"site":
   "mv_verify", "detail": ...}`); a filesystem that refuses moves cannot be
   safely continued past.
2. **Record the stall** in the batch deferred JSON
   (`dev/local/autopilot/deferred/{batch_id}-deferred.json`, create if
   missing): append `{"type": "stall", "site": "<slug>", "detail":
   "<one-line human string>", "prd": "<filename>"}`.
   **This record is distinct from `state.stall_reason`** — that field is the
   wrapper's replan signal (`subagent_prompt_overrun`, branch 2 of the
   Session Loop decision table). The stall procedure NEVER writes
   `state.stall_reason`.
3. **Reset per-PRD state** exactly as the "plan-tasks stall" handler's step 5
   does (clear the per-PRD fields, preserve `batch`, set `phase: "build"`,
   `next_phase: "build"`).
4. **Print the banner** and continue the batch:
   ```
   ── AUTOPILOT ── PRD: {prd-name} ── STALLED ({site}) ────────────────
   ── moved to dev/local/prds/stalled/ ── advancing to next PRD ──────
   ```
5. **Continue**: end the turn (the wrapper relaunches on `next_phase:
   "build"`), or jump to Phase 0 in-session when interactive. Batch-end
   review lists every stall first, with resume instructions ("move back to
   wip/ and re-run").

## Cap rotation

Reached from **Phase 0** when `state.cap_rotations` gained an entry but no `stall_reason` is set. A Work turn during `build` exceeded the context cap; `autopilot_context_cap_hook.py` appended `{task_id, cycle}` to `state.cap_rotations`, reset the in-flight task's status to `pending`, and set `next_phase: "build"` — a ROTATION, not a replan. The session then ends its turn and the loop wrapper relaunches on the non-empty `next_phase`. There is nothing to do here: the rotation is lossless and needs no handler.

The fresh session resumes `build` by artifact: capsule fresh → skip catchup; `state.tasks` non-empty → skip planning; `/work` continues at the first non-completed task. Because the in-flight task was reset to `pending`, it is that first non-completed task: its uncommitted partial attempt is discarded and re-attempted. Only the in-flight task's status changes (`in_progress → pending`); other `state.tasks` and `phases_completed` are untouched; `replan_count` is unchanged; no `replan-context.md` is written.

**Livelock guard (in the cap hook).** If the last `cap_rotations` entry already names the in-flight task, a second consecutive fire on the same task means the task is genuinely oversized. The hook does NOT append another rotation; instead it records `stall_reason.stalled == "oversized_task"` and instructs the oversized-task stall — handled by the "plan-tasks stall: oversized task" procedure below (move the PRD to `dev/local/prds/stalled/`, advance to the next PRD). One oversized task costs at most two rotations before a loud stall.

## Work-phase abort: replan procedure

Reached from **Phase 0** when `state.stall_reason.stalled` is `"subagent_prompt_overrun"` (`/work`'s Subagent Dispatch Budget aborted a task whose assembled prompt exceeded 50K after one trim pass). This is the ONE surviving replan path — the context-cap response is rotation (see "Cap rotation" above), not replan. The previous session's work aborted from a hook. **The PRD is not broken — one of its tasks produced an oversized subagent prompt.** Instead of stalling the PRD, replan it with smaller tasks and resume.

1. The aborted PRD filename is `state.prd`. Identify the aborted task from `state.task_aborts[-1]` (most recent abort): `task_id`, `cause`.
2. Read `state.replan_count` (default 0 if absent). Increment in memory.
3. **Budget floor guard:** compute `target_budget = max(40000, int(75000 / (2 ** (replan_count - 1))))`. This halves the per-task budget on each replan attempt, floored at 40K — the structural minimum for any single-file task (30K overhead + small file + PRD slice). Progression: replan 1 → 75K, replan 2 → 40K (floor), replan 3+ → 40K (floor). If `replan_count > 5` AND the same task keeps aborting, the task is genuinely too execution-heavy for a single agent turn. **In loop mode (`$_AUTOPILOT_LOOP` set): do NOT pause — the five replans were the retries; follow the "Loop-mode stall procedure" above with `site: "replan_exhausted"` and continue the batch.** Interactively, PAUSE:
   ```
   ── AUTOPILOT ── PRD: {prd-name} ── PAUSED ──────────────────────────
   ── {replan_count} replans, task still execution-overflowing ───────
   ── aborted task: {task_id}, cause: {cause} ─────────────────────────
   ── task may need manual scope reduction in the PRD ─────────────────
   ```
   Set `state.phase = "paused"` and `state.next_phase = "paused"`, and write `state.pause_reason = {"site": "replan_exhausted", "detail": "{replan_count} replans, task {task_id} still execution-overflowing"}`. Do NOT move the PRD anywhere. Do NOT clear state. STOP and wait for the user. The user will edit the PRD, delete tasks manually, or run `/run-autopilot status` to inspect. (Setting `phase`/`next_phase`/`pause_reason` here is what makes the Stop hook halt at this PAUSE — without them, `stall_reason.stalled == "subagent_prompt_overrun"` is still set, and Phase 0 would otherwise emit `task_aborted` and re-enter the replan loop.)
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
      - Leave `phases_completed` as-is — build sub-steps are not tracked there (it should be empty during build); the capsule stays valid for the same branch.
      - `state.tasks: []`, `tasks_total: 0`, `tasks_completed: 0` (already cleared in step 4b).
      - Clear `stall_reason`.
      - Clear `pause_reason` and `cap_pause_reason`, if present (defensive — a stale pause marker from an earlier PAUSE should not survive into the replanned build).
      - `rework_task_ids: []` (defensive — a stale array would put the next Phase 3 incorrectly into rework mode against deleted task IDs).
      - Set `phase: "build"`, `next_phase: "build"`.
5. Print:
   ```
   ── AUTOPILOT ── PRD: {prd-name} ── REPLAN #{replan_count} (≤{target_budget} tok/task) ──
   ── trigger: {stall_reason.stalled} on {task_id} ────────────────────
   ── cleared {n} tasks ({m} completed kept in replan-context.md) ─────
   ── handing off to fresh session for planning ───────────────────────
   ```
6. Hand off: end the turn. In loop mode the wrapper reads the non-empty `next_phase: "build"` and relaunches; otherwise the user re-invokes `/run-autopilot`. The next session re-enters `build`; with `state.tasks` cleared, Phase 2's tasks-exist skip does not fire, so it plans, detects `replan-context.md`, and passes it to `/plan-tasks`.

If `stall_reason.stalled` is anything else (or absent), return to Phase 0's Normal PRD selection.

## Crash recovery: escalation_exhausted seen at Phase 0

`escalation_exhausted` is owned inline by Phase 6 — the rework path is inside the autopilot flow, so it does its own stall move + clear before signaling. Phase 0 should never see `escalation_exhausted` in normal operation. If it does, treat it as corrupt-state crash recovery (the crash landed between Phase 6's `mv` and its `stall_reason` clear, so the PRD is already in `dev/local/prds/stalled/` but state still points at it): log a warning, clear `stall_reason`, do NOT re-run the move (Phase 6 already moved the PRD), AND reset PRD-specific fields the same way Phase 9 step 10 does for the next PRD — `phases_completed: []`, `cycle: 1`, `tasks_total: 0`, `tasks_completed: 0`, `replan_count: 0`, clear `tasks`/`task_aborts`/`cap_rotations`/`autonomous_decisions`/`deferred_decisions`/`review_cycles`/`doubts`/`doubts_rubric_verdicts`/`rework_task_ids`/`work_start_sha`/`design_doc`/`design_gate`/`design_mode`/`pause_reason`/`cap_pause_reason`, preserve `batch`, set `next_phase: "build"` — then fall through to Phase 0's Normal PRD selection so the next PRD gets picked cleanly.

## plan-tasks stall: oversized task

Reached from **Phase 2** when `/plan-tasks` exits non-zero and writes `state.stall_reason` because a task cannot be split below the per-task budget (150K standard, or the dynamic budget from `replan-context.md` in replan mode — see `plan-tasks/SKILL.md` "Stall behavior" and "Detect replan mode").

1. Read `dev/local/autopilot/state.json`. If `stall_reason.stalled == "oversized_task"`, do NOT proceed to Phase 3.
2. **Delete any tasks `/plan-tasks` already created.** `/plan-tasks` calls `TaskCreate` before the per-task budget check, so tasks may exist in `TaskList` by the time the stall fires. Query `TaskList`, then `TaskUpdate(status: "deleted")` for every task. Same pattern as Phase 9 step 5 — prevents Phase 2's `TaskList`-skip logic from skipping planning on the next PRD.
3. Ensure `dev/local/prds/stalled/` exists (`mkdir -p dev/local/prds/stalled`).
4. `mv` the PRD from `dev/local/prds/wip/<filename>` to `dev/local/prds/stalled/<filename>` (keep the `00XXX-` prefix). After the `mv`, **verify the move**: confirm the PRD now exists in `dev/local/prds/stalled/`. If it does not, the move failed — set `state.phase = "paused"` and `state.next_phase = "paused"`, write `state.pause_reason = {"site": "mv_verify", "detail": "<source, destination, mv error>"}`, then PAUSE naming the source, the destination, and the `mv` error, and do not continue (do not clear state or advance to the next PRD).
5. Clear the stall key from state: read state, delete `stall_reason`, write back. Reset PRD-specific fields the same way Phase 9 step 10 does for the next PRD: `phases_completed: []`, `cycle: 1`, `tasks_total: 0`, `tasks_completed: 0`, `replan_count: 0`, clear `tasks`/`task_aborts`/`cap_rotations`/`autonomous_decisions`/`deferred_decisions`/`review_cycles`/`doubts`/`doubts_rubric_verdicts`/`rework_task_ids`/`work_start_sha`/`design_doc`/`design_gate`/`design_mode`/`pause_reason`/`cap_pause_reason`. Preserve `batch`. Set `next_phase: "build"`. Delete `dev/local/autopilot/replan-context.md` if it exists — otherwise the next PRD's planning would falsely enter replan mode.
6. Print:
   ```
   ── AUTOPILOT ── PRD: {prd-name} ── STALLED (oversized_task) ─────
   ── moved to dev/local/prds/stalled/ ── advancing to next PRD ────
   ```
7. If `$_AUTOPILOT_LOOP` is set, end the turn — the wrapper reads `next_phase: "build"` and relaunches (same mechanism as the Phase 9 PRD-to-PRD transition). Otherwise jump back to Phase 0 in this same session to pick the next PRD.

## Rework escalation exhausted

Reached from **Phase 6** when a review-flagged task's last attempt was already at tier `"opus"` — the `haiku → sonnet → opus` chain has no higher tier, so the task cannot be reworked automatically.

Rewrite the attempt entry's `outcome` to `"rework_failed"`, then merge into state:

```json
"stall_reason": {"stalled": "escalation_exhausted", "task": "<id>"}
```

(The `outcome` rewrite is forensic — the stall move below clears `state.tasks` immediately after, so the `"rework_failed"` value only persists in pre-clear observers (the pidash dashboard reading state.json, any PostToolUse hook firing between the rewrite and the clear). It documents the failure mode for external observers in the brief window before reset; the durable record lives in the PRD's commit history and in `stall_reason.stalled` itself.)

Then perform the **stall move**, identical to the "plan-tasks stall: oversized task" handler above. Sub-steps run in order: the PRD `mv` (step 2) precedes the state clear (step 3). This ordering matters because a crash between the two leaves the PRD in `stalled/` with stale state still referencing it — the "Crash recovery: escalation_exhausted seen at Phase 0" section above detects this and recovers by clearing state without re-running the move.

1. `mkdir -p dev/local/prds/stalled` if missing.
2. `mv` the PRD from `dev/local/prds/wip/<filename>` to `dev/local/prds/stalled/<filename>` (keep the `00XXX-` prefix). After the `mv`, **verify the move**: confirm the PRD now exists in `dev/local/prds/stalled/`. If it does not, the move failed — set `state.phase = "paused"` and `state.next_phase = "paused"`, write `state.pause_reason = {"site": "mv_verify", "detail": "<source, destination, mv error>"}`, then PAUSE naming the source, the destination, and the `mv` error, and do not continue (do not clear state or advance to the next PRD).
3. Clear `stall_reason` from state. Reset PRD-specific fields the same way Phase 9 step 10 does for the next PRD: `phases_completed: []`, `cycle: 1`, `tasks_total: 0`, `tasks_completed: 0`, `replan_count: 0`, clear `tasks`/`task_aborts`/`cap_rotations`/`autonomous_decisions`/`deferred_decisions`/`review_cycles`/`doubts`/`doubts_rubric_verdicts`/`rework_task_ids`/`work_start_sha`/`design_doc`/`design_gate`/`design_mode`/`pause_reason`/`cap_pause_reason`. Preserve `batch`. Set `next_phase: "build"`. Delete `dev/local/autopilot/replan-context.md` if it exists (defensive — it should already be gone by the time we reach a rework path).
4. Print:
   ```
   ── AUTOPILOT ── PRD: {prd-name} ── STALLED (escalation_exhausted) ──
   ── moved to dev/local/prds/stalled/ ── advancing to next PRD ──────
   ```
5. If `$_AUTOPILOT_LOOP` is set, end the turn — the wrapper reads `next_phase: "build"` and relaunches. Otherwise jump back to Phase 0 in this same session to pick the next PRD.

## Cap-Pause Resume Handler

Reached from **Phase 0** when `state.phase == "paused"` AND `state.cap_pause_reason` is set — Phase 5's cap-pause behavior fired in a prior INTERACTIVE session because the review-rework cap was hit (`state.cycle >= state.rework_cap`). (Loop-mode runs never cap-pause — PRD 00017: they defer ≤high findings and stall on unresolved CRITICALs instead; this handler serves interactive runs only.) The PRD is still in `dev/local/prds/wip/` and was not advanced. This handler presents the recorded findings to the user and branches on resume or abandon. It is the ONLY consumer of `cap_pause_reason`; it MUST clear the field on resume.

1. **Read the cap-pause state.** From `state.json`: `state.cycle`, `state.rework_cap`, `state.cap_pause_reason.unresolved_findings` (the list of findings Phase 5 collected), and the PRD filename in `state.prd`.

2. **Present the findings to the user.** Use the `AskUserQuestion` tool (the same direct-input mechanism other handlers use for resume/abandon decisions). Show:
   - The PRD name (strip the `.md` extension).
   - The cycle / cap (`{cycle}/{cap}`).
   - Every entry from `cap_pause_reason.unresolved_findings` — each entry's issue, severity, and consensus.
   Offer two choices:
   - **Resume** (optionally with a raised cap).
   - **Abandon** (leave the PRD in place for manual handling).

3. **On "resume":**
   a. Clear `cap_pause_reason` from `state.json` (delete the key entirely; merge-preserving on all other fields).
   b. Set `state.phase = "review"` and `state.next_phase = "review"` (the resume continues at Phase 4, which the fresh session reaches via the existing review-phase skip rules).
   c. If the user selected a raised cap, write the new integer to `state.rework_cap`. Otherwise leave `state.rework_cap` unchanged.
   d. **Do NOT move the PRD.** It is in `dev/local/prds/wip/` and stays there.
   e. **Do NOT replan tasks.** The existing `state.tasks` and TaskList state is preserved; the resume picks up at the next review cycle.
   f. **Hand off to a fresh session for Phase 4.** End the turn — the same end-turn hand-off as Phase 3. In loop mode the wrapper relaunches on the non-empty `next_phase: "review"`; interactively the user re-invokes `/run-autopilot` manually.
   g. Print:
      ```
      ── AUTOPILOT ── PRD: {prd-name} ── RESUMING from cap pause ──────
      ── cap: {cap} ── continuing at Phase 4 (review) in fresh session
      ```
   h. STOP.

4. **On "abandon":**
   a. Do NOT clear `cap_pause_reason`. Do NOT change `state.phase` / `state.next_phase`. Do NOT move the PRD. The paused state survives by design — the user wants autopilot to stay out of the way.
   b. Print:
      ```
      ── AUTOPILOT ── PRD: {prd-name} ── ABANDONED at cap pause ──────
      ── PRD left in dev/local/prds/wip/ for manual handling ─────────
      ── re-invoke /run-autopilot to revisit, or move/delete the PRD manually
      ```
   c. No state advance happens — the wrapper stops on the paused state, so there is no automatic re-entry.
   d. STOP.
   e. **Re-entry behavior.** Because the abandon branch leaves `cap_pause_reason` set, a future manual `/run-autopilot` invocation will re-trigger this handler with the same findings — it does NOT loop autonomously (no signal is written, so the shell wrapper exited; only an explicit user re-invocation re-enters). To exit the cap-pause loop permanently the user must EITHER pick "resume" (clears `cap_pause_reason` per step 3) OR manually edit `state.json` / move the PRD out of `dev/local/prds/wip/`.

5. The cap-paused PRD is NEVER re-selected as new work by Phase 0's Normal PRD selection — the handler check fires BEFORE Normal PRD selection (see `references/phase-build.md` Phase 0 "Handle Work-phase abort" sub-section) and short-circuits the flow.

6. The handler clears the cap-pause event only on "resume" (step 3 deletes `cap_pause_reason`). On "abandon" the event persists — see step 4.e for the re-entry contract.
