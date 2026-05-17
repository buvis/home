---
name: run-autopilot
description: Use when running a PRD end-to-end autonomously through catchup, plan, work, review, rework, blind review, and doubt review. Triggers on "autopilot", "run autopilot", "autopilot status", "drain backlog", "execute PRD end to end".
argument-hint: "[<prd-filename> | status]"
---

# Autopilot

Orchestrate the full PRD lifecycle: catchup → plan-tasks → work → review → rework loop → blind review → doubt review → done.

Makes autonomous decisions backed by research (dependencies, recurring issues, API/schema changes when PRD-driven) and pauses only for critical security, requirements ambiguity, or blocking decisions.

## Execution Model

**Run all phases in sequence without stopping.** After each phase completes, immediately update state and proceed to the next phase. Do not pause between phases, do not summarize progress, do not wait for user input - unless the phase explicitly says PAUSE or STOP. Completing a sub-skill invocation (`/catchup`, `/plan-tasks`, `/work`, `/review-work-completion`, etc.) is NOT a stopping point. It is an intermediate step. Continue.

## Entry Points

- `/run-autopilot` — auto-select PRD (wip first, then backlog), run full cycle
- `/run-autopilot <prd-filename>` — full cycle with specific PRD
- `/run-autopilot status` — print current dashboard, no action

If invoked with `status`, read `dev/local/autopilot/state.json`, print phase/cycle/task summary, and stop.

## State Management

All autopilot artifacts live under `dev/local/autopilot/`, organized by type:

```
dev/local/autopilot/
  state.json                              # current cycle state
  signal                                  # transient, used by stop hook
  reports/{batch_id}-report.md            # batch audit report
  deferred/{batch_id}-deferred.json       # unresolved items across PRDs
```

State file: `dev/local/autopilot/state.json` — see `references/state-schema.md` for schema.

Create `dev/local/autopilot/` and subdirectories if missing. Initialize state file at PRD selection. Update state at every phase transition.

**Invariant:** every state mutation that advances `phase` MUST also set `next_phase` to the same value. `autoclaude` reads `next_phase` to pick `--model` for the next launch (Work → Sonnet 4.6; everything else → Opus 4.7). If the two ever diverge, the next session may land on the wrong model. Empty `next_phase` (e.g. backlog drained) means "no preference; autoclaude defaults to Opus."

### Resuming

When `/run-autopilot` is invoked and `dev/local/autopilot/state.json` exists with `batch.completed_prds`, this is a continuation after a session restart. Preserve `batch.completed_prds` (including `batch.id`) and proceed to Phase 0 to pick the next PRD.

Clean up stale signal file at start: locate the autopilot dir with the canonical walk-up helper (`_walk_up.py --bash`, see "Canonical signal-write procedure" in Loop Detection) and delete `<autopilot_dir>/signal` if it exists. Do not use a bare relative path.

### Task Counts

At every state update, query `TaskList` and write current counts to the state file:
- `tasks_total` — number of tasks (pending + in_progress + completed)
- `tasks_completed` — number of tasks with status completed

This keeps the dashboard progress bar accurate.

### Hydrate TaskList from state.tasks (shared sub-step)

`TaskList` is per-session storage (`~/.claude/tasks/<session-id>/`). Every fresh autopilot session — handoff from Phase 3, restart after a context-cap abort, or any manual re-invocation — starts with an **empty** TaskList even when `state.tasks` carries the full snapshot from the prior session. Phase skipping (planning, work) and per-task model dispatch both rely on TaskList, so without rehydration the new session operates with no task tracker at all.

Run this hydration **before any phase invokes `/work` or queries TaskList for routing** — specifically: Phase 2 (before the skip-rule check), Phase 3 (before `/work`), Phase 6 (before rework `/work`), Phase 7 (after `/review-blindly`, before creating `[BLIND]` tasks), Phase 8 (before `[DOUBT]` `/work`).

**Procedure:**

1. Query `TaskList`. If it returns **any** tasks, no-op (already populated for this session).
2. Read `state.tasks` from `dev/local/autopilot/state.json`. If absent or empty, no-op (nothing to hydrate).
3. For each entry in `state.tasks` **in declared order** (do NOT reorder):
   - `TaskCreate` with `subject: name`. `TaskCreate` assigns ids sequentially starting at 1, so the new ids align with `state.tasks[].id` numbering by construction.
   - If the entry carries `model` / `estimated_tokens` / `est_context_peak` / `attempts`, pass them through as `metadata` on `TaskCreate`. `/work`'s per-task model dispatch consumes `metadata.model` only (PRD 00025); the other three are preserved so the TaskList round-trip stays lossless across sessions — future tooling and dashboards can read them via `TaskGet` without re-deriving from `state.tasks`.
4. After all `TaskCreate` calls succeed, walk `state.tasks` again and `TaskUpdate(status: ...)` to match the recorded status (`pending` / `in_progress` / `completed`). Skip entries where status is already `pending` (the TaskCreate default).
5. Verify hydration integrity against `TaskList`:
   - **Count check**: the number of tasks in `TaskList` must equal `len(state.tasks)`. If not, abort with a state error.
   - **ID-alignment check**: for each entry in `state.tasks`, verify its `id` appears in the `TaskList` result. The sequential-id assumption (`state.tasks[0].id == "1"`, etc.) breaks when `state.tasks` contains non-sequential IDs from manual edits, deletions, or `[C{n}]`/`[D{n}]` suffixes. Count-only verification would silently let a misaligned hydration proceed, causing `/work` to dispatch against wrong task IDs.
   - If either check fails, abort with a clear error message naming the mismatched IDs. Do NOT silently continue.

**Idempotency:** if a phase re-enters this sub-step on the same session (e.g. Phase 6 after Phase 3), step 1 short-circuits. Safe to call as a precondition on every `/work` entry point.

### Live Dashboard

The user can run `pidash` (from buvis-gems) in a separate terminal pane to watch progress in real time. It watches `dev/local/autopilot/state.json` automatically — no action needed from autopilot beyond keeping the state file updated.

### Phase Banners

Print a banner at each phase transition:

```
── AUTOPILOT ── PRD: {prd-name} ── Phase: {PHASE} ──────────────────
── AUTOPILOT ── PRD: {prd-name} ── Phase: REVIEW ── Cycle {n} ─────
── AUTOPILOT ── PAUSED ── {n} issue(s) need your decision ──────────
── AUTOPILOT ── PRD: {prd-name} ── DONE ── {n} cycles ─────────────
```

## Phase 0: PRD Selection

### Handle Work-phase abort (from a prior session)

Before anything else, read `dev/local/autopilot/state.json`. If
`stall_reason.stalled` is `"context_overrun"` (Work turn exceeded
180K — `autopilot_context_cap_hook.py` prepared the handoff) or
`"subagent_prompt_overrun"` (`/work` Subagent Dispatch Budget aborted a
task whose assembled prompt exceeded 50K after one trim pass), the
previous session's Work phase aborted from a hook. **The PRD is not
broken — one of its tasks was scoped too big for a single Work turn.**
Instead of stalling the PRD, replan it with smaller tasks and resume.

(`escalation_exhausted` is owned inline by Phase 6 — the rework path is
inside the autopilot flow, so it does its own stall move + clear before
signaling. Phase 0 should never see `escalation_exhausted` in normal
operation. If it does, treat it as corrupt-state crash recovery (the
crash landed between Phase 6's `mv` and its `stall_reason` clear, so
the PRD is already in `dev/local/prds/stalled/` but state still points
at it): log a warning, clear `stall_reason`, do NOT re-run the move
(Phase 6 already moved the PRD), AND reset PRD-specific fields the same
way Phase 9 step 9 does for the next PRD — `phases_completed: []`,
`cycle: 1`, `tasks_total: 0`, `tasks_completed: 0`, `replan_count: 0`,
clear `tasks`/`task_aborts`/`autonomous_decisions`/`deferred_decisions`/`review_cycles`/`doubts`/`rework_task_ids`,
preserve `batch`, set `next_phase: "catchup"` — then fall through to
normal PRD selection so the next PRD gets picked cleanly.)

#### Replan procedure

1. The aborted PRD filename is `state.prd`. Identify the aborted task from `state.task_aborts[-1]` (most recent abort): `task_id`, `cause`.
2. Read `state.replan_count` (default 0 if absent). Increment in memory.
3. **Loop guard:** if the incremented value is `> 2` → PAUSE. Print:
   ```
   ── AUTOPILOT ── PRD: {prd-name} ── PAUSED ──────────────────────────
   ── replanned twice and still aborting; scope likely wrong ─────────
   ── aborted task: {task_id}, cause: {cause} ─────────────────────────
   ── inspect dev/local/autopilot/state.json and decide how to proceed
   ```
   Do NOT move the PRD anywhere. Do NOT clear state. STOP and wait for the user. The user will edit the PRD, delete tasks manually, or run `/run-autopilot status` to inspect.
4. Otherwise, prepare the replan:
   a. Build the completed-work summary AND capture the aborted-task title first (before any deletion). The data available pre-hydration is the `state.tasks[]` snapshot (`{id, name, status, model?, attempts?}` per state-schema row 127) and `state.task_aborts[-1]` (`{task_id, cause}`); `TaskList` is empty in the fresh session, and `attempts[]` does not carry commit refs (see state-schema row 129 enum). So: for the **completed-work summary**, filter `state.tasks` to `status == "completed"` and capture each entry's `name`; if the user wants commit refs in the replan context, they come from `git log` on the active branch, not from `attempts[]`. For the **aborted task**, look up `state.task_aborts[-1].task_id` in `state.tasks[]` and capture its `name`. Description is intentionally not part of the snapshot; the task name + the PRD itself give plan-tasks enough context to scope the replan. Both captures must happen before step 4b clears `state.tasks`.
   b. Query `TaskList` and `TaskUpdate(status: "deleted")` for every task regardless of status. Then clear `state.tasks` entirely (`[]`). The completed work is captured in step 4a's summary and the committed code itself; keeping completed entries in `state.tasks` alongside new plan-tasks output would collide on the fresh `TaskCreate` ids (which start at 1) and corrupt the dashboard.
   c. Write `dev/local/autopilot/replan-context.md` (overwrite if exists):
      ```markdown
      # Replan Context

      PRD: {state.prd}
      Replan attempt: {replan_count} of 2
      Trigger: {stall_reason.stalled} on task {task_id}

      ## Completed work (do NOT re-plan)

      - {task name from state.tasks[]} {optional: commit-ref from `git log` on active branch, if helpful}
      - ...

      ## Aborted task

      {aborted task name captured in step 4a; omit this section if step 4a found no matching entry}

      ## Directive

      Plan ONLY the remaining PRD scope (work not in "Completed work" above).
      Target ≤ 75 000 tokens per task (half the standard 150K budget) — the
      last attempt aborted at runtime, so split fine-grained.
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
   ── AUTOPILOT ── PRD: {prd-name} ── REPLAN ({replan_count}/2) ───────
   ── trigger: {stall_reason.stalled} on {task_id} ────────────────────
   ── cleared {n} tasks ({m} completed kept in replan-context.md) ─────
   ── handing off to fresh session for planning ───────────────────────
   ```
6. Hand off: if `$_AUTOPILOT_LOOP` is set, use the canonical walk-up signal-write procedure (see "Canonical signal-write procedure" in Loop Detection) to write `next` to the signal file at the absolute path, then STOP. Otherwise STOP and wait for the user to re-invoke `/run-autopilot`. The next session lands at Phase 2 (planning is no longer in `phases_completed`); Phase 2 will detect `replan-context.md` and pass it to `/plan-tasks`.

If `stall_reason.stalled` is anything else (or absent), continue with
normal PRD selection below.

### Normal PRD selection

1. If argument provided, find that PRD in `dev/local/prds/wip/` or `dev/local/prds/backlog/`. If found in backlog, `mv` to `wip/`.
2. Otherwise, auto-select (never ask the user):
   a. Check `dev/local/prds/wip/`:
      - 1+ found → auto-pick lowest sequence number (by `00XXX-` prefix), announce
   b. If wip is empty, check `dev/local/prds/backlog/`:
      - PRDs available → auto-pick lowest sequence number, `mv` to `wip/`
      - Empty → STOP: "No PRDs found. Create one with /create-prd."
3. Initialize `batch` in state file if not already present: `id: "<yyyymmddHHMM>"` (current timestamp), `mode: "autopilot"`, `completed_prds: []`
4. Read the first 20 lines of the selected PRD. If it begins with a `---` line, parse the YAML block between the opening `---` and the next `---`. Look for `catchup:`. Accepted values: `run`, `skip`, `force`. Anything else (other value, malformed YAML, missing frontmatter, absent `catchup:` field) → default to `run`. Write the resulting value to `state.catchup_mode`. On a malformed-frontmatter fallback, log a one-line warning ("autopilot: PRD frontmatter malformed; defaulting catchup_mode=run") and continue — never crash Phase 0 on a frontmatter problem. PRD frontmatter is the source of truth for catchup behavior; once Phase 0 has set `catchup_mode`, do not re-parse the PRD. Mode semantics: `run` honors the batch-cache check in Phase 1; `skip` bypasses catchup entirely; `force` ignores the batch cache and re-runs full catchup regardless of recency.
5. Read the Active Work section of `dev/local/project-capsule.md` if it exists. This contains PRD progress and operational context from previous sessions. Use it to inform work in this session.
6. Initialize/update state with selected PRD, preserve `batch` field
7. Print progress:
   ```
   ── AUTOPILOT ── PRD {n}: {prd-name} ─────────────────────────────
   ```
   Where `{n}` = `len(batch.completed_prds) + 1`

## Phase 1: Catchup

**Skip if:** `"catchup"` in `phases_completed` in state file, OR `state.catchup_mode == "skip"`.

When skipped via `catchup_mode == "skip"`: do not invoke `/catchup`. Add `"catchup"` to `phases_completed`, set `state.catchup_mode = "skipped"` (so subsequent re-entries also skip), set `phase: "planning"` and `next_phase: "planning"`, and proceed to Phase 2.

Otherwise, decide between **full catchup** and **delta refresh** using the batch cache.

### Batch cache check

The capsule (`dev/local/project-capsule.md`) is the persisted output of catchup: invariants, architecture decisions, GitHub state, project memories. Subsequent phases and their subagents read the capsule when they need that context — not TaskList, not state.json. So between PRDs in the same batch on the same branch, the heavy gather phase of `/catchup` (full diff, blast radius, reverse deps, GitHub state) produces output that's already accurate; re-running it costs ~60-95s and ~50K tokens per PRD with no information gain.

`state.batch.catchup_completed_at` (ISO 8601) and `state.batch.catchup_head_sha` (current branch HEAD when last full catchup completed) record the cache. **Skip the full catchup and run a delta refresh** when ALL of the following hold:

1. `state.catchup_mode != "force"` — PRD frontmatter `catchup: force` overrides the cache.
2. `state.batch.catchup_completed_at` is present AND less than 4 hours old.
3. `state.batch.catchup_head_sha` matches the current `git rev-parse HEAD` on the active branch.

If any condition fails → **full catchup**: invoke `/catchup`. After completion, write `state.batch.catchup_completed_at = <now>` and `state.batch.catchup_head_sha = <current HEAD>`. These fields persist across PRDs in the batch (Phase 9 step 9 preserves them).

If all conditions hold → **delta refresh** (no `/catchup` invocation):

- Re-read all PRDs in `dev/local/prds/wip/` (the active set has changed since last catchup; new PRDs may have entered, old ones moved to `done/`).
- Update the Active Work section of `dev/local/project-capsule.md` with the current PRD list (use the same format Phase 9 step 7 uses). Leave Key Invariants, Architecture Decisions, Component Boundaries, GitHub State, Project Health, and Project Memories untouched — those reflect batch-stable knowledge.
- Print a one-line note: `── AUTOPILOT ── catchup: delta refresh (cache <Xm> old, HEAD <sha7>) ──`

After either path completes, update state: add `"catchup"` to `phases_completed`, set `phase: "planning"` and `next_phase: "planning"`.

### Frontmatter examples

- `---\ncatchup: skip\n---` → `state.catchup_mode = "skip"`. Phase 1 records mode `skipped`, adds `"catchup"` to `phases_completed`, advances to planning.
- `---\ncatchup: force\n---` → `state.catchup_mode = "force"`. Phase 1 ignores the batch cache and runs full `/catchup`.
- PRD with no frontmatter → `state.catchup_mode = "run"`. Phase 1 honors the batch cache (delta refresh when fresh, full catchup otherwise).
- `---\ncatchup: invalid\n---` → `state.catchup_mode = "run"`, warning logged.
- `---\ncatchup\n---` (malformed YAML) → `state.catchup_mode = "run"`, warning logged.

## Phase 2: Planning

**First, run the "Hydrate TaskList from state.tasks" sub-step** (defined in State Management above). This is mandatory — the skip rule below depends on it. Initial planning has nothing to hydrate (no-ops on empty `state.tasks`) and replan clears `state.tasks` deliberately (also no-ops); the case the hydration covers is a resumed PRD whose prior session populated `state.tasks` and handed off (e.g., the post-Phase-3 handoff). Without the hydration, the skip rule below sees an empty TaskList and mistakenly re-runs `/plan-tasks`.

**Skip if:** `TaskList` returns any pending or completed tasks (tasks already exist). Evaluate this **after** the hydration step above completes.

### Replan mode

Before invoking `/plan-tasks`, check for `dev/local/autopilot/replan-context.md`. If present, this is a replan triggered by a Phase 0 abort handler. Pass the file to `/plan-tasks` (see `plan-tasks/SKILL.md` "Replan mode") so it scopes to remaining work and uses the tighter ≤75K per-task budget. `/plan-tasks` deletes the file after successful planning.

If `replan-context.md` is absent, run /plan-tasks normally — first-pass planning for a fresh PRD.

Invoke `/plan-tasks` with the selected PRD.

### Handle plan-tasks stall (oversized task)

`/plan-tasks` exits non-zero and writes `state.stall_reason` when a task cannot be split below the per-task budget (150K standard, 75K in replan mode — see `plan-tasks/SKILL.md` "Stall behavior" and "Detect replan mode"). When this happens:

1. Read `dev/local/autopilot/state.json`. If `stall_reason.stalled == "oversized_task"`, do NOT proceed to Phase 3.
2. **Delete any tasks `/plan-tasks` already created.** `/plan-tasks` calls `TaskCreate` before the per-task budget check, so tasks may exist in `TaskList` by the time the stall fires. Query `TaskList`, then `TaskUpdate(status: "deleted")` for every task. Same pattern as Phase 9 step 4 — prevents Phase 2's `TaskList`-skip logic from skipping planning on the next PRD.
3. Ensure `dev/local/prds/stalled/` exists (`mkdir -p dev/local/prds/stalled`).
4. `mv` the PRD from `dev/local/prds/wip/<filename>` to `dev/local/prds/stalled/<filename>` (keep the `00XXX-` prefix).
5. Clear the stall key from state: read state, delete `stall_reason`, write back. Reset PRD-specific fields the same way Phase 9 does for the next PRD: `phases_completed: []`, `cycle: 1`, `tasks_total: 0`, `tasks_completed: 0`, `replan_count: 0`, clear `tasks`/`task_aborts`/`autonomous_decisions`/`deferred_decisions`/`review_cycles`/`doubts`/`rework_task_ids`. Preserve `batch`. Set `next_phase: "catchup"`. Delete `dev/local/autopilot/replan-context.md` if it exists — otherwise the next PRD's planning would falsely enter replan mode.
6. Print:
   ```
   ── AUTOPILOT ── PRD: {prd-name} ── STALLED (oversized_task) ─────
   ── moved to dev/local/prds/stalled/ ── advancing to next PRD ────
   ```
7. If `$_AUTOPILOT_LOOP` is set, use the canonical walk-up signal-write procedure (see "Canonical signal-write procedure" in Loop Detection) to write `next` to the signal file at the absolute path (same mechanism as Phase 9 PRD-to-PRD transition), then STOP. Otherwise jump back to Phase 0 in this same session to pick the next PRD.

**Other outcomes from `/plan-tasks`:**

- **Exits zero**: no stall. Continue normally to the post-completion state update below.
- **Exits non-zero without `stall_reason`** (or with a `stall_reason.stalled` value other than `"oversized_task"`): treat as a sub-skill failure. PAUSE and report the error per the "Sub-skill invocation fails" entry in the Error Handling table. Do NOT proceed to Phase 3 or move the PRD.

After completion, query `TaskList` and update state: add `"planning"` to `phases_completed`, set `phase: "work"` and `next_phase: "work"`, write `tasks`/`tasks_total`/`tasks_completed` snapshot (see Phase 3 for format).

## Phase 3: Work

**Skip if:** All tasks completed, none pending. Evaluate **after** running the hydration sub-step (below) — otherwise a fresh session sees TaskList empty and mistakenly treats "no pending" as "all done".

**First, run the "Hydrate TaskList from state.tasks" sub-step** (defined in State Management above). This is the critical entry point for the post-handoff and post-context-cap session paths.

Before invoking `/work`, query `TaskList` and write the full task snapshot to `dev/local/autopilot/state.json`:
- `tasks_total`: total count
- `tasks_completed`: completed count
- `tasks`: array of `{"id": "<task-id>", "name": "<title>", "status": "pending|in_progress|completed", ...metadata}` for EVERY task. The snapshot **must preserve every field plan-tasks or Phase 6 may have written** — at minimum: `model` (when set by plan-tasks tier classifier or Phase 6 escalation), `attempts` (the per-attempt log; see "Attempt logging" in `/work`), `estimated_tokens` and `est_context_peak` (when plan-tasks recorded a budget estimate). Stripping these on snapshot would break the hydration round-trip (subsequent sessions read them back into TaskList metadata) and lose Phase 6's tier-escalation history across the handoff. Treat the snapshot as merge-preserving over `state.tasks[i]`, not a three-field replacement.

**Include the task `id` field** — a PostToolUse hook on TaskUpdate uses it to automatically sync status changes to the dashboard. This is mandatory.

Invoke `/work` skill. It runs until all tasks complete.

After completion, query `TaskList` again and update state: add `"work"` to `phases_completed`, set `phase: "review"` and `next_phase: "review"`, write updated `tasks`/`tasks_total`/`tasks_completed`.

### Hand off to a fresh session for reviews

After Phase 3 completes, do NOT continue into Phase 4 in the same session. The review phases (4, 7, 8) each spawn multiple cloud reviewers and need a clean context window. Use the same signal-file + Stop-hook mechanism as Phase 9's PRD-to-PRD transition:

1. Update `state.next_phase` to `"review"` (the phase the next session will run). This is what `autoclaude` reads to pick the model for the next launch (Opus for review).
2. Write the signal only when running inside the loop (see "Loop Detection" under Session Loop): if `$_AUTOPILOT_LOOP` is set, use the canonical walk-up signal-write procedure (see "Canonical signal-write procedure" in Loop Detection) to write `next` to the signal file at the absolute path. Never use a bare relative `dev/local/autopilot/signal` — the cwd may have changed during the work phase. If unset, skip the signal write — the session will stay interactive and the user will re-invoke `/run-autopilot` manually.
3. Print:

```
── AUTOPILOT ── PRD: {prd-name} ── Phase 3 (Work) complete ─────────
── AUTOPILOT ── handing off to fresh session for reviews ───────────
```

4. **STOP.** Do NOT invoke `/review-work-completion`, `/review-blindly`, or `/review-with-doubt` in this session, even if context budget appears sufficient.

When the signal was written, the Stop hook auto-exits and the shell loop wrapper (`while true; do claude "/run-autopilot"; ... done`) starts a fresh session and re-invokes `/run-autopilot`. The new session reads `dev/local/autopilot/state.json` (with `phases_completed=["catchup", "planning", "work"]`), skips Phases 1-3 via their skip conditions, and resumes at Phase 4. When no signal was written, the same resume logic applies on the next manual invocation.

## Phase 4: Review

**Skip if:** Review file exists in `dev/local/reviews/` for current cycle (check filename pattern `{prd-name}-review-{cycle}.md`).

Invoke `/review-work-completion` skill.

After completion, update state: set `phase: "decision-gate"` and `next_phase: "decision-gate"`.

## Phase 5: Decision Gate

Read the review output. Categorize each finding using `references/decision-framework.md`.

### Safety Checks — evaluate BEFORE classifying individual issues:

| Condition | Action |
|-----------|--------|
| Cycle 3 reached | PAUSE: escalate ALL remaining issues regardless of severity |
| >10 follow-up tasks from review | PAUSE: scope alarm — ask user before proceeding |
| Issue count not decreasing vs previous cycle | PAUSE: escalate immediately — fixes aren't working |
| Same issue reappearing after previous fix | Route to research-then-decide Protocol B |
| A sub-skill errored during this cycle | PAUSE: report error, don't retry automatically |

### Classification (per finding):

**Auto-fix** (proceed without asking):
- Low severity, any consensus
- Medium severity, clear mechanical fix
- Medium severity, 1/3 consensus
- Any severity where fix is additive only (adds code/tests, doesn't modify signatures/types/schemas)

**Research-then-decide** (run protocol, then auto-fix or defer):
- New dependency needed -> Protocol A from `references/decision-framework.md`
- Recurring issue (appeared in previous cycle) -> Protocol B
- High + data model change -> Protocol C
- High + touches public API -> Protocol D

Execute the research protocol. If verdict is "proceed", treat as auto-fix. If verdict is "escalate", defer to batch end. Log with full `research` field in either case.

**Defer to batch end** (log, don't PAUSE):
- Critical severity, always
- Requirements ambiguity (PRD says X, code does Y)
- Research-failed items (verdict "escalate" from research protocols)

**PAUSE** (present to user, block progress):
- >10 follow-up tasks from review (scope alarm)
- Cycle 3 reached (hard stop)
- Decision blocks subsequent tasks (e.g. API shape needed before frontend can proceed)
- Data model choice that all remaining work depends on

Log every decision in state file (`autonomous_decisions` or `deferred_decisions`).

### Outcomes:

- **All auto-fixable, no deferrals, no blockers** → proceed to Phase 6
- **Has deferrals but no blockers** → log deferred items to `dev/local/autopilot/deferred/{batch_id}-deferred.json`, proceed to Phase 6 with auto-fixable items only
- **Has blocking escalation** → PAUSE. Present only the blocking issue(s) to user. Wait for decision. After user responds, proceed to Phase 6.
- **No issues found** → proceed to Phase 7 (Blind Review)

## Phase 6: Rework

**Session model:** Phase 6 runs in the same session as Phase 4 (review). That session uses Opus 4.7 (per `autoclaude`'s `next_phase = "review"` → Opus mapping). The per-task tier escalation in `/work` step 3 (dispatching each task as a separate Agent call at `metadata.model`) means the actual rework implementation runs at the escalated tier (haiku/sonnet/opus) regardless of the outer session. No separate rework handoff is needed: the session model handles review quality; per-task dispatch handles implementation correctness. This resolves PRD 00024 cycle-1 item 1.

Two task kinds enter this phase:

- **Review-flagged original-plan tasks** (`[C{cycle}]` prefix): a task `/work` already attempted that the review phase wants re-done. These are retries — escalate the model tier per the rule below.
- **Decision-gate follow-ups** (`[D{cycle}]` prefix): brand-new tasks created from decision-gate resolutions. These are first-pass work, not retries — they default to `sonnet` (no escalation applies). Apply the `/plan-tasks` Tier classifier here too if you have the inputs (PRD slice, files-touched estimate); otherwise default `sonnet`.

Both prefixes use the current cycle number. Both kinds dispatch through the same rework-mode `/work` invocation — see "Dispatch rework" below for how each gets its tier set and queued.

### Hydrate before any TaskUpdate (PRD 00025)

**Run the "Hydrate TaskList from state.tasks" sub-step** (defined in State Management above) BEFORE the "Escalate review-flagged tasks by tier" section's `TaskUpdate` calls. The rework session almost always inherits an empty TaskList from the post-Phase-3 handoff — running escalation TaskUpdate calls against an empty tracker either errors on unknown IDs or silently no-ops, losing the status→pending transition and dashboard visibility. Hydration is the first action of Phase 6, no exceptions.

### Escalate review-flagged tasks by tier (PRD 00025)

For each review-flagged original-plan task in the current cycle's review output:

1. Look up `state.tasks[i].attempts[-1]` — the last `/work` pass's entry, written by `/work` Attempt logging.
2. If `state.tasks[i].attempts` is empty or absent (legacy-plan task with no attempt log — covered by step 3's "no prior attempt" case and the closing paragraph after step 5), skip this step entirely and proceed to step 3's next-tier computation. Otherwise, rewrite that entry's `outcome` to `"review_flagged"` (it was `"completed"` when `/work` exited; review just flagged it).
3. Compute the next tier in the chain `haiku → sonnet → opus`:
   - **no prior attempt** (`state.tasks[i].attempts` empty or absent — covers both pre-PRD-00025 legacy plans and PRD-00025 tasks that crashed before the first attempt log wrote) → treat as `"sonnet"`; next is `"opus"`. **Metric caveat**: when this branch fires for a PRD-00025 task whose actual pass ran `haiku`, it inflates the apparent sonnet→opus escalation rate vs the PRD's ≤2% target. The branch is rare (crash before first attempt-log write) and the conservative jump-to-opus is the right correctness choice; just don't read sonnet→opus telemetry without accounting for it.
   - last attempt at `"haiku"` → next is `"sonnet"`
   - last attempt at `"sonnet"` → next is `"opus"`
   - last attempt at `"opus"` → **escalation exhausted**: rewrite the entry's `outcome` to `"rework_failed"`, then merge into state:
     ```json
     "stall_reason": {"stalled": "escalation_exhausted", "task": "<id>"}
     ```
     (The `outcome` rewrite is forensic — sub-step 3 below clears `state.tasks` immediately after the stall move, so the `"rework_failed"` value only persists in pre-clear observers (the pidash dashboard reading state.json, any PostToolUse hook firing between the rewrite and the clear). It documents the failure mode for external observers in the brief window before reset; the durable record lives in the PRD's commit history and in `stall_reason.stalled` itself.)
     Then perform the **stall move**, identical to Phase 2's `oversized_task` handler. Sub-steps run in order: the PRD `mv` (step 2) precedes the state clear (step 3). This ordering matters because a crash between the two leaves the PRD in `stalled/` with stale state still referencing it — Phase 0's `escalation_exhausted` crash-recovery branch (under "Handle Work-phase abort") detects this and recovers by clearing state without re-running the move.
     1. `mkdir -p dev/local/prds/stalled` if missing.
     2. `mv` the PRD from `dev/local/prds/wip/<filename>` to `dev/local/prds/stalled/<filename>` (keep the `00XXX-` prefix).
     3. Clear `stall_reason` from state. Reset PRD-specific fields the same way Phase 9 step 9 does for the next PRD: `phases_completed: []`, `cycle: 1`, `tasks_total: 0`, `tasks_completed: 0`, `replan_count: 0`, clear `tasks`/`task_aborts`/`autonomous_decisions`/`deferred_decisions`/`review_cycles`/`doubts`/`rework_task_ids`. Preserve `batch`. Set `next_phase: "catchup"`. Delete `dev/local/autopilot/replan-context.md` if it exists (defensive — it should already be gone by the time we reach a rework path).
     4. Print:
        ```
        ── AUTOPILOT ── PRD: {prd-name} ── STALLED (escalation_exhausted) ──
        ── moved to dev/local/prds/stalled/ ── advancing to next PRD ──────
        ```
     5. If `$_AUTOPILOT_LOOP` is set, use the canonical walk-up signal-write procedure (see "Canonical signal-write procedure" in Loop Detection) to write `next` to the signal file at the absolute path, then STOP. Otherwise jump back to Phase 0 in this same session to pick the next PRD.
4. Otherwise (chain not exhausted), persist the escalated tier in BOTH places so `/work` and the state snapshot stay in sync, then queue the task for rework:
   - `TaskUpdate(taskId="<id>", metadata={"model": "<next_tier>"})` — canonical source `/work` reads via `TaskGet` (see `work/SKILL.md` "Per-task model dispatch").
   - Write the same value to `state.tasks[i].model` — the snapshot the dashboard and the next review cycle read.
   - Append the task ID to `state.rework_task_ids` (create the array if absent).
5. Reset `state.tasks[i].status` back to `"pending"` via `TaskUpdate(taskId, status="pending")` so `/work` will iterate it again. **Reverse status transitions (`completed` → `pending`) are supported** — the hydration sub-step (State Management above) relies on the same mechanism to restore `completed` status on a fresh session, and the PostToolUse status-sync hook treats whatever `TaskUpdate` writes as the new ground truth.

The "no prior attempt" case in step 3 covers both pre-PRD-00025 legacy plans (which lack `metadata.model` and `attempts[]` entirely) and PRD-00025 tasks that crash before the first attempt log writes (rare but possible). Both are treated as `"sonnet"` for the next-tier computation, so first escalation goes to `"opus"`.

### Dispatch rework

Build the rework batch from two sources:

1. **Review-flagged `[C{cycle}]` tasks** — `state.rework_task_ids` already contains their IDs (appended in step 4 above), and their `metadata.model` + `state.tasks[i].model` already carry the escalated tier.
2. **Decision-gate `[D{cycle}]` follow-ups** — for each new task created from a decision-gate resolution:
   - Compute the tier: start with the `/plan-tasks` Tier classifier output if the inputs are available (PRD slice, files-touched estimate); otherwise default to `sonnet`. Then apply the **PRD `default_model` floor** the same way `/plan-tasks` step 4.7 does: `final_tier = max(tier, default_model)` — a PRD with `default_model: opus` must produce `opus` for every `[D]` follow-up, never a lower tier. **Reading `default_model` at Phase 6 runtime:** re-parse the PRD frontmatter from `dev/local/prds/wip/<state.prd>` using the same YAML-tolerant parse Phase 0 step 4 applies for `catchup:`. Look for `default_model:`. Accepted values: `haiku`, `sonnet`, `opus`. Behavior matches `/plan-tasks` step 4.7 exactly: absent frontmatter or unset `default_model:` → no override (silent; classifier output passes through); malformed YAML or invalid value → no override AND log a one-line warning, then classifier output passes through; valid value → apply `final_tier = max(tier, default_model)`. `default_model` is intentionally NOT persisted to state — the PRD frontmatter is the single source of truth.
   - `TaskCreate(metadata={"model": final_tier, ...})`.
   - Append the new task's ID to `state.rework_task_ids` AND insert a merge-preserving snapshot into `state.tasks[]` carrying `{id, name, status, model}` plus any classifier-produced fields (`estimated_tokens`, `est_context_peak`) — same merge-preserving rule Phase 3 establishes for the original-plan snapshot. The dashboard sees the new task and `/work` rework mode iterates it.

Hydration already ran at the top of Phase 6 (see "Hydrate before any TaskUpdate" above) — the rework session inherits a populated TaskList by this point, so the `TaskUpdate` and `TaskCreate` calls operate on real tasks.

After both sources are merged into `rework_task_ids`, update state with current task counts. Invoke `/work` — it reads `state.rework_task_ids` and enters **rework mode** (see `work/SKILL.md` "Rework-mode task filter"), processing only the listed IDs at the tier each task carries in `metadata.model`; non-listed completed tasks are skipped.

The work skill may parallelize independent rework tasks when `superpowers:dispatching-parallel-agents` is available (see work skill's "Parallel dispatch for independent rework fixes").

### After /work returns

1. Clear `state.rework_task_ids` (set to `[]`).
2. Increment cycle counter.
3. Update state: set `phase: "review"` and `next_phase: "review"`, update task counts (`tasks_total`/`tasks_completed` only — do NOT rewrite `state.tasks` here; `/work` already wrote `attempts[]` entries directly to `state.tasks` during rework, and a bare TaskList snapshot would strip them).
4. Loop back to Phase 4.

Cross-references: `references/state-schema.md` (`rework_task_ids`, `tasks[].model`, `tasks[].attempts`, `stall_reason` shapes); `work/SKILL.md` Per-task model dispatch, Attempt logging, Rework-mode task filter.

## Phase 7: Blind Review

**Skip if:** `"blind-review"` in `phases_completed` in state file.

Spec-only verification by a reviewer with no implementation context. Invoke `/review-blindly` with only the PRD content - no file lists, implementation notes, or review history.

After the review:

1. **No Critical/Important findings** → update state: add `"blind-review"` to `phases_completed`, set `phase: "doubt-review"` and `next_phase: "doubt-review"`. Proceed to Phase 8.
2. **Critical or Important findings** → **first run the "Hydrate TaskList from state.tasks" sub-step** (the blind-review session is fresh; TaskList is empty). Then create tasks tagged `[BLIND]` (each `TaskCreate` gets a new id appended to the hydrated list) and insert a merge-preserving snapshot for each new `[BLIND]` task into `state.tasks` (carrying `{id, name, status}`; the tier classifier does not run on [BLIND] tasks — they default to the running session's model unless you opt to set `metadata.model` explicitly). Invoke `/work`. After fixes complete, update state the same way as outcome 1: add `"blind-review"` to `phases_completed`, set `phase: "doubt-review"` and `next_phase: "doubt-review"`. **Also update task counts (`tasks_total`/`tasks_completed`) only — do NOT rewrite `state.tasks` here; `/work` already wrote `attempts[]` entries directly to `state.tasks` for the `[BLIND]` tasks, and a bare TaskList snapshot would strip them** (same rationale as Phase 6 step 3 and Phase 8 step 5). Then proceed to Phase 8. Do not loop back to Phase 4.
3. **Zero issues with no file references** → suspicious result (reviewer may not have found the code). Log a warning but proceed.

Minor findings: defer to batch end (append to `deferred_decisions` in state).

This phase runs once per PRD.

## Phase 8: Doubt Review

**Skip if:** `"doubt-review"` in `phases_completed` in state file.

Final sanity check before completion. Invoke `/review-with-doubt`.

The doubt review produces findings in three categories: **FIX** (fixable now), **VERIFY** (needs checking), and **KNOWN** (real limitation, out of scope).

**Before processing any FIX/VERIFY items, run the "Hydrate TaskList from state.tasks" sub-step** (defined in State Management). This guarantees subsequent `[DOUBT]` `TaskCreate` calls get ids appended after the hydrated original-plan tasks (rather than overwriting id 1 in an empty tracker).

Process each:

### Handling FIX items

1. Create a task tagged `[DOUBT]` for each FIX item.
2. Add an entry to `doubts` in state: `{"description": "...", "category": "fix", "status": "pending"}`

### Handling VERIFY items

VERIFY items are resolved during the review itself (the doubt skill runs checks and reclassifies as FIX or dismissed). If any survive unresolved:
1. Treat as FIX — create a `[DOUBT]` task.
2. Add to `doubts` in state with `"category": "verify"`.

### Handling KNOWN items

KNOWN items cannot be fixed in this scope. They flow to batch-end review for the user to decide.
1. Add to `doubts` in state: `{"description": "...", "category": "known", "justification": "...", "status": "pending"}`
2. Do NOT create tasks for KNOWN items — they are deferred, not actionable here.

### Execution

After classifying all items:

1. If no FIX or VERIFY tasks → proceed to Phase 9. KNOWN items (if any) will be surfaced at batch end.
2. If >5 FIX/VERIFY tasks → defer all to batch end (append each to `deferred_decisions` in state as `{"type": "doubt-overflow", "description": "...", "category": "fix|verify", "status": "pending"}`). Log warning but do NOT PAUSE. Proceed to Phase 9.
3. If ≤5 FIX/VERIFY tasks → invoke `/work` on `[DOUBT]`-tagged tasks immediately — no decision gate, no rework loop. (Hydration already ran at the top of the phase.)
4. After work completes, mark each resolved doubt entry's `status` as `"resolved"` in state.
5. Update state: add `"doubt-review"` to `phases_completed`, set `phase: "done"` and `next_phase: "done"`, update task counts (`tasks_total`/`tasks_completed` only — do NOT rewrite `state.tasks` here; same rationale as Phase 6 step 3, `/work` wrote `attempts[]` to `state.tasks` for `[DOUBT]` tasks).

KNOWN items keep `"status": "pending"` — Phase 9 step 5 collects these into the batch deferred log for batch-end review.

This phase runs once per PRD. It does not loop back to Phase 4.

## Phase 9: Completion

1. Update state: set `phase: "done"` and `next_phase: "done"`
2. Move PRD from `wip/` to `done/` (use `mv`, keep `00XXX-` prefix)
3. Append completed PRD to `batch.completed_prds` in state file
4. Delete all tasks from the completed PRD: query `TaskList`, mark every task as `deleted` via `TaskUpdate`. This prevents stale tasks from triggering Phase 2's skip logic on the next PRD.
5. Append items to `dev/local/autopilot/deferred/{batch_id}-deferred.json` (create if missing). Collect from the current state file:
   - `deferred_decisions` with status `"pending"` or `"deferred"` -> type `"deferred_decision"` (preserve original `type` field if present, e.g. `"doubt-overflow"`)
   - `doubts` with status `"pending"` -> type `"doubt"`
   - `autonomous_decisions` with `research` field -> type `"autonomous_research"` (for user awareness at batch end)
   Each entry gets tagged with `prd` (filename) and `cycle`. Preserve the full `research` field when present - this is the only copy that survives state reset. Skip this step if nothing to write.
6. Append PRD summary to `dev/local/autopilot/reports/{batch_id}-report.md` (create with header if missing). See `references/batch-report-format.md` for format.
6b. Append autonomous decisions to `dev/local/decisions.md` if that file exists (skip if absent - user opts in by creating it). For each non-trivial entry in `autonomous_decisions` from the state file, append one row:
    ```
    | {YYYY-MM-DD} | {decision summary} | {rationale or research evidence} | batch-{batch_id} PRD {prd-number} |
    ```
    Dedupe: grep the decision summary before appending; skip if already present.
7. Update the Active Work section of `dev/local/project-capsule.md` with batch progress. Use the Edit tool to replace the Active Work section content:
   ```markdown
   ## Active Work

   ### Batch {batch_id}
   - [x] {completed PRD name} ({n} cycles)
   - [x] ...for each completed PRD in batch
   - [ ] {PRD name} - for each PRD still in wip/ or backlog/

   Observations: {any operational gotchas useful for next iteration}
   ```
   If the capsule doesn't exist yet (catchup was skipped), create a minimal one with just the Active Work section.
8. Print per-PRD summary. Run the tier-escalation aggregator first:
   ```bash
   python3 ~/.claude/skills/run-autopilot/scripts/tier_escalation_metrics.py
   ```
   Then print:

```
── AUTOPILOT ── PRD: {prd-name} ── DONE ── {n} cycles ─────────────

Summary:
- Cycles: {n}
- Autonomous decisions: {count}
- Escalated decisions: {count}
- Follow-up tasks fixed: {count}
- {tier_escalation_metrics output, indented two spaces}
```

   If the script exits non-zero or produces no output (no attempt data yet), omit the tier-escalation line — do not fail Phase 9.

### Continuation

9. Check: any PRDs remaining in `dev/local/prds/wip/*.md` or `dev/local/prds/backlog/*.md`?
   - **Yes** → reset state for next PRD: set `phases_completed` to `[]`, `cycle` to `1`, `tasks_total: 0`, `tasks_completed: 0`, clear tasks/task_aborts/autonomous_decisions/deferred_decisions/review_cycles/doubts/`rework_task_ids` (the next PRD starts a fresh plan, not a rework dispatch), set `replan_count: 0` (it tracked the current PRD's replans; the next PRD starts fresh). Delete `dev/local/autopilot/replan-context.md` if it exists (defensive — plan-tasks deletes it on success, but a malformed prior session may have left it). **Preserve `batch` field in full, including `batch.catchup_completed_at` and `batch.catchup_head_sha`** — Phase 1 of the next PRD reads these to decide between full catchup and delta refresh (see Phase 1 "Batch cache check"). Set `next_phase: "catchup"` (the next PRD starts at catchup; Opus tier). If `$_AUTOPILOT_LOOP` is set, use the canonical walk-up signal-write procedure (see Loop Detection) to write `next` to the signal file at the absolute path (never a bare relative path). If unset, skip the signal write — the session stays interactive and the user re-invokes `/run-autopilot` manually for the next PRD. Print:
     ```
     ── AUTOPILOT ── {prd-name} done ── next PRD in new session ────────
     ```
     Then **STOP**.
   - **No** → print batch summary, delete state file. Do NOT write `dev/local/autopilot/signal` - the session stays interactive for batch-end review.
     ```
     ── AUTOPILOT ── COMPLETE ───────────────────────────────────────────

     Completed {n} PRDs:
       1. {prd-name} ({cycles} cycles)
       2. {prd-name} ({cycles} cycles)
       ...
     ```

     ### Batch-End Review

     Before exiting, collect ALL pending items from across the batch and present them to the user. This is mandatory if any items exist - never auto-exit with unreviewed items.

     **Source:** `dev/local/autopilot/deferred/{batch_id}-deferred.json` (single source of truth - all items were written here at Phase 9 step 5 of each PRD). Contains four item types:
     - `deferred_decision` - issues that failed research or were deferred for other reasons
     - `doubt` - unresolved findings from doubt review
     - `doubt-overflow` - FIX/VERIFY items deferred when doubt review found >5 issues (present under UNRESOLVED DOUBTS)
     - `autonomous_research` - research-backed decisions made autonomously (for user awareness)

     **Auto-fix trivial items first.** Before presenting items to the user, scan for trivial fixes that are clearly additive-only: docstring/comment improvements, test helper fixes (missing kwargs, style), formatting. Fix these silently, commit, and remove from the deferred list. Only present items that genuinely need a user decision.

     **Presentation format - chunked by PRD:**

     Present items grouped by PRD, one PRD at a time. For each PRD chunk:

     ```
     ── BATCH REVIEW ── PRD: {prd-name} ── {n} items ──────────────────

     DEFERRED DECISIONS ({count}):

     1. {severity emoji} {issue description}
        Cycle: {n} | Consensus: {consensus}
        Context: {why this was deferred - include research evidence if available}
        File: {path}
        Options: fix now / create issue / ignore

     2. ...

     UNRESOLVED DOUBTS ({count}):

     1. {severity emoji} {doubt description}
        Context: {what the doubt review found and why it matters}
        Options: fix now / create issue / ignore

     AUTONOMOUS RESEARCH DECISIONS ({count} - for awareness):

     1. {severity emoji} {issue description} -> {action taken}
        Research: {evidence_summary from research field}
        (No action needed unless you disagree)
     ```

     Wait for user decisions on each PRD chunk before showing the next. For "fix now" items, execute the fix before continuing. For "create issue", create a GitHub issue with the context shown.

     After all PRD chunks are reviewed (or user says stop), delete the deferred JSON. Set `next_phase: ""` (empty; nothing more to run). If `$_AUTOPILOT_LOOP` is set, use the canonical walk-up signal-write procedure (see "Canonical signal-write procedure" in Loop Detection) to write `done` to the signal file at the absolute path (the stop hook auto-exits and the shell loop sees `done` and stops). If unset, skip the signal write — leave the session interactive.
     If the deferred JSON doesn't exist or is empty, do the same signal-write-if-in-loop step immediately.

## Session Loop

Autopilot supports automatic session cycling via a signal file + Stop hook. This enables unattended PRD-to-PRD transitions while keeping sessions interactive.

**Signal file:** `dev/local/autopilot/signal` — possible values:

- `next` — written at Phase 3 hand-off and Phase 9 step 9 when more PRDs remain. Shell wrapper continues the loop.
- `done` — written at the end of batch-end review. Shell wrapper exits the loop.
- `task_aborted` — written by the model in two cases: (a) when `autopilot_context_cap_hook.py` fires on a 180K Work-turn overrun (the hook prepares `state.stall_reason = {"stalled": "context_overrun", ...}`); or (b) when `/work` Subagent Dispatch Budget aborts a task whose assembled subagent prompt exceeded 50K after one trim pass (`/work` prepares `state.stall_reason = {"stalled": "subagent_prompt_overrun", ...}`). In both cases the writer appends to `state.task_aborts` before instructing the model to write the signal. Shell wrapper continues the loop; Phase 0 of the next session replans the PRD in place (PRD stays in `wip/`; see Phase 0 step 1's replan procedure).

Every signal write is paired with a `state.next_phase` write that happens immediately before — `autoclaude` reads `next_phase` to pick `--model` for the next launch.

### Loop Detection

The shell wrapper (the `autoclaude` function in `~/.config/bash/plugins/development.plugin.bash`) exports `_AUTOPILOT_LOOP=$$` before invoking `claude`. The skill MUST only write `dev/local/autopilot/signal` when this env var is set — writing it without a loop wrapper present causes the Stop hook to SIGINT the session with no restart, which surprises the user.

Check before every signal write with a Bash call such as `echo "${_AUTOPILOT_LOOP-}"` (always exits 0; prints empty when unset) and treat empty output as "not in loop, skip signal". Do NOT use `printenv _AUTOPILOT_LOOP` — it exits 1 when the variable is unset, which the Bash tool surfaces as an error. When skipping the signal, still print the handoff banner and STOP — the session simply stays interactive and the user re-invokes `/run-autopilot` (the next session resumes via `state.json` skip conditions).

**Canonical signal-write procedure:** Always derive the signal path using the walk-up helper so the write lands in the correct absolute location even if the model's cwd has changed (e.g., after Bash `cd` calls during a work task). Use two sequential Bash calls:

```bash
# Step 1: resolve the autopilot dir
python3 ~/.claude/skills/run-autopilot/scripts/_walk_up.py --bash
# → prints the resolved absolute path, e.g. /Users/bob/.claude/dev/local/autopilot

# Step 2: write signal using the resolved path (substitute the path from step 1)
python3 -c "open('/resolved/path/from/step-1/signal', 'w').write('next')"
```

Or equivalently use the Write tool with the absolute path returned by step 1. All "write signal" instructions in Phase 3, Phase 9, Phase 0, Phase 2, and Phase 6 must follow this procedure.

**Shell wrapper:**

```bash
while true; do
  claude "/run-autopilot"
  signal=$(cat dev/local/autopilot/signal 2>/dev/null)
  rm -f dev/local/autopilot/signal
  case "$signal" in
    next)         echo "Starting next PRD..." ;;
    task_aborted) echo "Work task hit context cap; PRD will be replanned. Continuing..." ;;
    *)            echo "Backlog drained."; break ;;
  esac
done
```

(The real `autoclaude` function is more involved — it exports `_AUTOPILOT_LOOP`, traps signals, and cleans up orphaned children — but the loop contract is the same.)

**Required:** A Stop hook that auto-exits when the signal file exists. See `scripts/autopilot_stop_hook.py`. Configure in `settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "command": "~/.claude/skills/run-autopilot/scripts/autopilot_stop_hook.py"
      }
    ]
  }
}
```

Without the hook, sessions remain interactive but require manual exit (Ctrl+D) between PRDs. The shell loop still handles restart.

## Shell Command Rules

- **Never chain commands** with `&&`, `|`, or `;` in a single Bash call. Use separate Bash tool calls instead.
- **Never use redirections** like `2>/dev/null`. Handle missing files by checking existence or catching errors in the tool result.
- Use `Glob` or `Read` instead of `ls` where possible (e.g. to check if files exist or list directory contents).
- Use `mkdir -p` in its own Bash call when creating directories.

## Error Handling

| Situation | Action |
|-----------|--------|
| Sub-skill invocation fails | PAUSE, report which skill failed and error |
| No PRDs anywhere | STOP with message about /create-prd |
| State file corrupted | Delete it, restart from Phase 0 |
| Review produces no parseable output | PAUSE, report — don't retry |
| All three reviewers fail | PAUSE, report — partial results usable if user confirms |
| `dev/local/` doesn't exist | Create it |
| Task tools unavailable | STOP, report — can't operate without tasks |

## Superpowers Integration

Autopilot depends on superpowers for quality gates. All integrations are conditional - autopilot works without them, but quality improves with them.

### Used by the Work skill (Phases 3, 6, 7, 8)

| Superpower | Step | Purpose |
|-----------|------|---------|
| `test-driven-development` | 2.7 | Write failing tests before implementation |
| `systematic-debugging` | 4.5 | Root-cause analysis on errors |
| `verification-before-completion` | 5.5 | Run test suite before marking done |
| `requesting-code-review` | 5.7 | Per-task code review after commit |
| `receiving-code-review` | 5.7 | Evaluate review feedback before acting on it |

### Used in Phase 6 (Rework)

| Superpower | Condition | Purpose |
|-----------|-----------|---------|
| `dispatching-parallel-agents` | 2+ independent rework tasks | Parallelize isolated review fixes |

### Not used (rationale)

| Superpower | Reason |
|-----------|--------|
| `brainstorming` | Interactive; happens before PRD exists |
| `writing-plans` | PRD is the plan; plan-tasks decomposes into tasks |
| `executing-plans` | Work skill manages per-task dispatch already |
| `subagent-driven-development` | Work skill's loop serves same purpose |
| `finishing-a-development-branch` | Autopilot works on current branch, not worktrees |
| `using-git-worktrees` | Separate architectural concern |
| `using-superpowers` | Session-start meta-skill; autopilot is autonomous, not conversational |
| `writing-skills` | Meta-skill for creating skills, not a workflow gate |

### Note on review layering

Per-task review (step 5.7), PRD-level review (Phase 4), and blind review (Phase 7) are complementary, not redundant. Per-task catches issues early before they compound. Phase 4 catches cross-task coherence and integration issues. Phase 7 catches spec drift and gaps that implementation-aware reviewers miss by giving a fresh agent only the spec. All three are needed.

## Reference Files

- `references/state-schema.md` — state file JSON schema and skip logic
- `references/decision-framework.md` — auto-fix vs escalate classification rules
- `references/dashboard-format.md` — live dashboard via pidash
- `references/batch-report-format.md` — batch audit report format
