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

Create `dev/local/autopilot/` and subdirectories if missing. Initialize state file at PRD selection. Update state at every phase transition. Autopilot also keeps a per-PRD **decision audit log** at `dev/local/reviews/<prd-base>-audit.md`, **rendered once at Phase 9 finalize from the `state.json` decision arrays** (`autonomous_decisions`, `deferred_decisions`, `doubts`). `state.json` is the single in-run source of truth — decisions are NOT mirrored to `audit.md` incrementally per decision. Each rendered entry carries a **source** label (`autonomous`, `deferred`, or `doubt`); cycle/phase context goes in the entry body so the Phase 9 `decisions.md` projection can filter autonomous entries by label. Entry format, the Phase 9 render procedure, and the projection live in `references/audit-log-format.md`.

**Invariant:** every state mutation that advances `phase` SHOULD also set `next_phase` to the same value. The five gates are `build` | `review` | `blind` | `doubt` | `done` (plus `paused`). `build` is ONE session: selection, catchup, planning, and work all run under `phase: "build"` with no mid-build handoff. The three review surfaces (`review`, `blind`, `doubt`) each run in their own fresh session. Per-task implementor tiering inside `/work` is unchanged. The authoritative resume signal is `phase` + `phases_completed`; build sub-step skipping is by ARTIFACT (capsule freshness, tasks-exist, all-done), not by `phases_completed` membership.

### Resuming

When `/run-autopilot` is invoked and `dev/local/autopilot/state.json` exists with `batch.completed_prds`, this is a continuation after a session restart. Preserve `batch.completed_prds` (including `batch.id`) and proceed to Phase 0 to pick the next PRD.

Clean up stale signal file at start: locate the autopilot dir with the walk-up helper (`_walk_up.py --bash`) and delete `<autopilot_dir>/signal` if it exists. Do not use a bare relative path.

### Task Counts

At every state update, query `TaskList` and write current counts to the state file:
- `tasks_total` — number of tasks (pending + in_progress + completed)
- `tasks_completed` — number of tasks with status completed

This keeps the dashboard progress bar accurate.

### Hydrate TaskList from state.tasks (shared sub-step)

`TaskList` is per-session storage (`~/.claude/tasks/<session-id>/`). Every fresh autopilot session — handoff to a review surface, restart after a context-cap rotation, or any manual re-invocation — starts with an **empty** TaskList even when `state.tasks` carries the full snapshot from the prior session. Phase skipping (planning, work) and per-task model dispatch both rely on TaskList, so without rehydration the new session operates with no task tracker at all.

Run this hydration **before any phase invokes `/work` or queries TaskList for routing** — specifically: Phase 2 (before the skip-rule check), Phase 3 (before `/work`), Phase 6 (before rework `/work`), Phase 7 (after `/review-blindly`, before creating `[BLIND]` tasks), Phase 8 (before `[DOUBT]` `/work`).

**Load if empty.** Query `TaskList`. If it returns **any** tasks, no-op (already populated this session). Otherwise read `state.tasks` from `dev/local/autopilot/state.json`; if absent or empty, no-op (nothing to hydrate). Otherwise, for each entry **in declared order** (do NOT reorder), `TaskCreate(subject: name)`, passing `model` / `estimated_tokens` / `est_context_peak` / `attempts` straight through as `metadata` when present — `/work` reads `metadata.model` (PRD 00025); the rest keep the round-trip lossless. `TaskCreate` assigns ids sequentially from 1, aligning with `state.tasks[].id` by construction. Then `TaskUpdate(status: ...)` each entry to its recorded status (`in_progress` / `completed`; `pending` is the `TaskCreate` default, skip it). The `attempts` array round-trips as-is — the hydration never inspects its rows, so any per-attempt field (`implementor`, `preflight_outcome`, `self_deslop`, future fields) survives the snapshot → hydration → `TaskGet` cycle intact.

**Idempotency:** if a phase re-enters this sub-step on the same session (e.g. Phase 6 after Phase 3), the TaskList-non-empty check short-circuits. Safe to call as a precondition on every `/work` entry point.

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

Before anything else, read `dev/local/autopilot/state.json` and check `stall_reason`:

- `stall_reason.stalled` is `"subagent_prompt_overrun"` — the previous session's work aborted from a hook. The PRD is not broken; one task was scoped too big. **Follow `references/recovery.md` → "Work-phase abort: replan procedure"**, then STOP (the next session re-enters `build` at planning). This is the one surviving replan path.
- `stall_reason.stalled` is `"escalation_exhausted"` — Phase 6 owns this inline; seeing it at Phase 0 means a crash landed mid-stall-move. **Follow `references/recovery.md` → "Crash recovery: escalation_exhausted seen at Phase 0"**, then fall through to Normal PRD selection.
- `state.phase == "paused"` AND `state.cap_pause_reason` is set (the previous session's Phase 5 cap-pause behavior fired). The capped PRD is still in `dev/local/prds/wip/`; do NOT treat it as fresh PRD selection. **Follow `references/recovery.md` → "Cap-Pause Resume Handler"** — it presents the recorded unresolved findings and cycle count via the `AskUserQuestion` tool and branches on resume/abandon.
- `state.cap_rotations` has a new entry but none of the above holds — the previous session hit the Work-turn context cap and the cap hook rotated to a fresh session. The cap hook recorded the rotation (appended `cap_rotations`, reset the in-flight task to `pending`, set `next_phase: "build"`); the Stop hook then wrote the `next` signal on STOP from that `next_phase`. NOT a replan. A `cap_rotations` entry is **informational only** and needs no special handling here: fall through to Normal PRD selection, which resumes `build` by artifact (capsule fresh → skip catchup; tasks exist → skip planning; `/work` continues at the first non-completed task — the rotated task, now reset to `pending`).
- None of the above (neither a recognised `stall_reason` value nor the cap-pause condition `phase == "paused"` + `cap_pause_reason`) — continue with Normal PRD selection below.

### Normal PRD selection

1. If argument provided, find that PRD in `dev/local/prds/wip/` or `dev/local/prds/backlog/`. If found in backlog, `mv` to `wip/`.
2. Otherwise, auto-select (never ask the user):
   a. Check `dev/local/prds/wip/`:
      - 1+ found → auto-pick lowest sequence number (by `00XXX-` prefix), announce
   b. If wip is empty, check `dev/local/prds/backlog/`:
      - PRDs available → auto-pick lowest sequence number, `mv` to `wip/`
      - Empty → STOP: "No PRDs found. Create one with /create-prd."
3. Initialize `batch` in state file if not already present: `id: "<yyyymmddHHMM>"` (current timestamp), `mode: "autopilot"`, `completed_prds: []`
4. Read the first 20 lines of the selected PRD. If it begins with a `---` line, parse the YAML block between the opening `---` and the next `---`. Look for `catchup:`. Accepted values: `run`, `skip`, `force`. Anything else (other value, malformed YAML, missing frontmatter, absent `catchup:` field) → default to `run`. Write the resulting value to `state.catchup_mode`. Also look for `rework_cap:` in the same YAML block. Accepted values: positive integer (or a string that parses cleanly as a positive integer). Anything else (non-integer string, negative/zero, absent field, malformed YAML, missing frontmatter) → default to **3**. Write the resulting integer to `state.rework_cap`. On a malformed-frontmatter fallback, log a one-line warning ("autopilot: PRD frontmatter malformed; defaulting catchup_mode=run, rework_cap=3") and continue — never crash Phase 0 on a frontmatter problem. PRD frontmatter is the source of truth for catchup behavior; once Phase 0 has set `catchup_mode`, do not re-parse the PRD. Mode semantics: `run` honors the batch-cache check in Phase 1; `skip` bypasses catchup entirely; `force` ignores the batch cache and re-runs full catchup regardless of recency. The `rework_cap` value is consumed by the Phase 5 decision gate's cap check (out of scope here; that's a separate task).
5. Read the Active Work section of `dev/local/project-capsule.md` if it exists. This contains PRD progress and operational context from previous sessions. Use it to inform work in this session.
6. Initialize/update state with selected PRD, preserve `batch` field
7. Print progress:
   ```
   ── AUTOPILOT ── PRD {n}: {prd-name} ─────────────────────────────
   ```
   Where `{n}` = `len(batch.completed_prds) + 1`

## Phase 1: Catchup

**Skip if:** the batch cache is fresh (the batch-cache freshness check below holds — the capsule is already current), OR `state.catchup_mode == "skip"`. The skip is by ARTIFACT (capsule freshness), not `phases_completed` membership.

When skipped via `catchup_mode == "skip"`: do not invoke `/catchup`. Set `state.catchup_mode = "skipped"` (so subsequent re-entries also skip), keep `phase: "build"` and `next_phase: "build"`, and proceed to Phase 2.

Otherwise, decide between **full catchup** and **delta refresh** using the batch cache.

### Batch cache check

The capsule (`dev/local/project-capsule.md`) is the persisted output of catchup: invariants, architecture decisions, GitHub state, project memories. Subsequent phases and their subagents read the capsule when they need that context — not TaskList, not state.json. So between PRDs in the same batch on the same branch, the heavy gather phase of `/catchup` (full diff, blast radius, reverse deps, GitHub state) produces output that's already accurate; re-running it costs ~60-95s and ~50K tokens per PRD with no information gain.

`state.batch.catchup_completed_at` (ISO 8601) and `state.batch.catchup_head_sha` (current branch HEAD when last full catchup completed) record the cache. **Skip the full catchup and run a delta refresh** when ALL of the following hold:

1. `state.catchup_mode != "force"` — PRD frontmatter `catchup: force` overrides the cache.
2. `state.batch.catchup_completed_at` is present AND less than 4 hours old.
3. `state.batch.catchup_head_sha` matches the current `git rev-parse HEAD` on the active branch.

If any condition fails → **full catchup**: invoke `/catchup`. After completion, write `state.batch.catchup_completed_at = <now>` and `state.batch.catchup_head_sha = <current HEAD>`. These fields persist across PRDs in the batch (Phase 9 step 10 preserves them).

If all conditions hold → **delta refresh** (no `/catchup` invocation):

- Re-read all PRDs in `dev/local/prds/wip/` (the active set has changed since last catchup; new PRDs may have entered, old ones moved to `done/`).
- Update the Active Work section of `dev/local/project-capsule.md` with the current PRD list (use the same format Phase 9 step 8 uses). Leave Key Invariants, Architecture Decisions, Component Boundaries, GitHub State, Project Health, and Project Memories untouched — those reflect batch-stable knowledge.
- Print a one-line note: `── AUTOPILOT ── catchup: delta refresh (cache <Xm> old, HEAD <sha7>) ──`

After either path completes, proceed to Phase 2. Stay on `phase: "build"` and `next_phase: "build"`; do NOT add anything to `phases_completed` (build sub-steps skip by artifact, not by membership).

### Frontmatter examples

- `---\ncatchup: skip\n---` → `state.catchup_mode = "skip"`. Phase 1 records mode `skipped` and advances to planning (still `phase: "build"`).
- `---\ncatchup: force\n---` → `state.catchup_mode = "force"`. Phase 1 ignores the batch cache and runs full `/catchup`.
- PRD with no frontmatter → `state.catchup_mode = "run"`. Phase 1 honors the batch cache (delta refresh when fresh, full catchup otherwise).
- `---\ncatchup: invalid\n---` → `state.catchup_mode = "run"`, warning logged.
- `---\ncatchup\n---` (malformed YAML) → `state.catchup_mode = "run"`, warning logged.
- `---\nrework_cap: 5\n---` → `state.rework_cap = 5`. Phase 5 cap check allows 5 review cycles before pausing.
- `---\nrework_cap: abc\n---` → `state.rework_cap = 3`, warning logged. Invalid value falls back to the default.
- PRD with no `rework_cap` field → `state.rework_cap = 3` (default). Phase 5 cap check allows 3 review cycles before pausing.

## Phase 2: Planning

**First, run the "Hydrate TaskList from state.tasks" sub-step** (defined in State Management above). This is mandatory — the skip rule below depends on it. Initial planning has nothing to hydrate (no-ops on empty `state.tasks`) and replan clears `state.tasks` deliberately (also no-ops); the case the hydration covers is a resumed PRD whose prior session populated `state.tasks` and handed off (e.g., a context-cap rotation into a fresh session). Without the hydration, the skip rule below sees an empty TaskList and mistakenly re-runs `/plan-tasks`.

**Skip if:** `TaskList` returns any pending or completed tasks (tasks already exist). Evaluate this **after** the hydration step above completes. This skip is by ARTIFACT (tasks exist), not `phases_completed` membership.

### Replan mode

Before invoking `/plan-tasks`, check for `dev/local/autopilot/replan-context.md`. If present, this is a replan triggered by a Phase 0 abort handler. Pass the file to `/plan-tasks` (see `plan-tasks/SKILL.md` "Replan mode") so it scopes to remaining work and uses the tighter ≤75K per-task budget. `/plan-tasks` deletes the file after successful planning.

If `replan-context.md` is absent, run /plan-tasks normally — first-pass planning for a fresh PRD.

Invoke `/plan-tasks` with the selected PRD.

**PAUSE site - requirements clarification.** When `/plan-tasks` pauses autopilot with a requirements-ambiguity or clarification question, present it to the user and wait for the answer. Once answered, record the clarification and its resolution in `state.autonomous_decisions` (label `autonomous`) so the Phase 9 audit render captures it. Do not write `audit.md` here.

### Handle plan-tasks stall (oversized task)

`/plan-tasks` exits non-zero with `state.stall_reason.stalled == "oversized_task"` when a task cannot be split below the per-task budget. When this happens, do NOT proceed to Phase 3 — **follow `references/recovery.md` → "plan-tasks stall: oversized task"** (deletes orphan tasks, moves the PRD to `dev/local/prds/stalled/`, advances to the next PRD).

**Other outcomes from `/plan-tasks`:**

- **Exits zero**: no stall. Continue normally to the post-completion state update below.
- **Exits non-zero without `stall_reason`** (or with a `stall_reason.stalled` value other than `"oversized_task"`): treat as a sub-skill failure. PAUSE and report the error per the "Sub-skill invocation fails" entry in the Error Handling table. Do NOT proceed to Phase 3 or move the PRD.

After completion, query `TaskList` and update state: stay on `phase: "build"` and `next_phase: "build"`, write `tasks`/`tasks_total`/`tasks_completed` snapshot (see Phase 3 for format). Do NOT add anything to `phases_completed`. Flow continues DIRECTLY into Phase 3 (work) in this same session — there is no planning→work handoff.

## Phase 3: Work

**Skip if:** All tasks completed, none pending. Evaluate **after** running the hydration sub-step (below) — otherwise a fresh session sees TaskList empty and mistakenly treats "no pending" as "all done". This skip is by ARTIFACT (all tasks done), not `phases_completed` membership. When all tasks are done, the build is complete → hand off to the review session (see below).

**First, run the "Hydrate TaskList from state.tasks" sub-step** (defined in State Management above). This is the critical entry point for the post-context-cap-rotation session path.

Before invoking `/work`, query `TaskList` and write the full task snapshot to `dev/local/autopilot/state.json`:
- `tasks_total`: total count
- `tasks_completed`: completed count
- `tasks`: array of `{"id": "<task-id>", "name": "<title>", "status": "pending|in_progress|completed", ...metadata}` for EVERY task. The snapshot **must preserve every field plan-tasks or Phase 6 may have written** — at minimum: `model` (when set by plan-tasks tier classifier or Phase 6 escalation), `attempts` (the per-attempt log; see "Attempt logging" in `/work`), `estimated_tokens` and `est_context_peak` (when plan-tasks recorded a budget estimate). Stripping these on snapshot would break the hydration round-trip (subsequent sessions read them back into TaskList metadata) and lose Phase 6's tier-escalation history across the handoff. Treat the snapshot as merge-preserving over `state.tasks[i]`, not a three-field replacement.

**Include the task `id` field** — a PostToolUse hook on TaskUpdate uses it to automatically sync status changes to the dashboard. This is mandatory.

**Capture `work_start_sha` before dispatching `/work`.** Run `git rev-parse HEAD` and write the resulting SHA to `state.work_start_sha`. This bounds the commit range `work_start_sha..HEAD` that this PRD's `/work` dispatches produce — read by Phase 8 to scope the codex doubt review's diff (`<work_start_sha>..HEAD`). Capture happens **once per PRD, before `/work` runs**. In a multi-PRD batch each PRD overwrites the prior PRD's value at this step, so ranges never overlap.

**Capture `repo_root` in the same step.** Run `git rev-parse --show-toplevel` in the work repo and write the absolute path to `state.repo_root`. Usually this equals the project root, but when the work repo is nested under a non-git project root (e.g. `~/.claude/skills/run-autopilot` under `~/.claude`), the review-coverage Stop hook and the Phase 8 gate need it to run `git diff` in the right repo — without it the diff runs at the project root and fails `DIFF_ERROR` (observed 2026-06-11: the failure deleted the handoff signal and the loop reported a false "Backlog drained.").

Invoke `/work` skill. It runs until all tasks complete.

After completion, query `TaskList` again and update state: set `phase: "review"` and `next_phase: "review"`, write updated `tasks`/`tasks_total`/`tasks_completed`. Do NOT add anything to `phases_completed` here — the `build` gate leaves no membership marker; review/blind/doubt completion are the only `phases_completed` entries.

### Hand off to a fresh session for reviews

After the build completes (all tasks done), do NOT continue into Phase 4 in the same session. The review phases (4, 7, 8) each spawn multiple cloud reviewers and need a clean context window. Use the same signal-file + Stop-hook mechanism as Phase 9's PRD-to-PRD transition:

1. Update `state.next_phase` to `"review"` (the phase the next session will run). The next session resumes at this phase.
2. Print:

```
── AUTOPILOT ── PRD: {prd-name} ── Build complete ──────────────────
── AUTOPILOT ── handing off to fresh session for reviews ───────────
```

3. **STOP.** Do NOT invoke `/review-work-completion`, `/review-blindly`, or `/review-with-doubt` in this session, even if context budget appears sufficient.

The Stop hook owns the signal: it reads `next_phase: "review"` from `state.json` and — when `$_AUTOPILOT_LOOP` is set — writes `next` to the signal file itself, then auto-exits. The shell loop wrapper (`while true; do claude "/run-autopilot"; ... done`) starts a fresh session and re-invokes `/run-autopilot`. The new session reads `dev/local/autopilot/state.json` (`phase: "review"`), resumes at Phase 4, and re-enters `build` only if an artifact is missing (capsule stale, no tasks, or tasks pending). Outside the loop (`$_AUTOPILOT_LOOP` unset) the hook writes nothing — the session stays interactive and the same resume logic applies on the next manual invocation.

## Phase 4: Review

**Skip the entire review-rework loop if:** `"review"` is in `phases_completed` — the loop already converged in a prior session and handed off (see "Hand off to a fresh session before blind review" in Phase 5). Skip Phases 4, 5, and 6, and resume directly at Phase 7.

**Skip this cycle's review if:** A review file exists in `dev/local/reviews/` for the current cycle (filename pattern `{prd-name}-review-{cycle}.md`).

Invoke `/review-work-completion` skill.

After completion, stay on `phase: "review"` and `next_phase: "review"` (the decision gate is part of the review surface).

## Phase 5: Decision Gate

### Cap check — evaluate after reading review, before rework dispatch

The cap is a gate on REWORK, not on Phase 5 itself. **First, read the review output** (see "Read the review output" further below). If it converged (no unresolved findings remain), the cap is irrelevant — proceed directly to Outcomes "No issues found" → Phase 7 hand-off. The PRD success metric "passes review within three cycles is completely unaffected" requires this: a clean cycle-3 convergence at cap=3 must reach Phase 7, not cap-pause.

Otherwise (unresolved findings remain), before evaluating the Safety Checks table below, check whether the review-rework cycle cap has been reached.

Read `state.cycle` (starts at 1; the number of the review cycle just completed) and `state.rework_cap` (the effective cap, set by Phase 0 from PRD frontmatter — default 3; see Phase 0 step 4).

**Rework is allowed while `cycle < cap`; when `cycle >= cap` AND rework would otherwise be dispatched, the gate pauses instead of reworking.**

Worked example, cap 3:

- cycle 1 review fails → `1 < 3` → rework → cycle 2.
- cycle 2 fails → `2 < 3` → rework → cycle 3.
- cycle 3 fails → `3 >= 3` → **pause, no 4th rework**.
- cycle 3 converges (0 findings) → cap irrelevant → Phase 7 hand-off (no pause).

Cap 5 yields five review cycles before the pause (cycles 1-4 → rework, cycle 5 → pause).

When the cap is hit AND the review did not converge (`state.cycle >= state.rework_cap` AND unresolved findings remain), perform the **Cap-pause behavior** (see below) and STOP — do NOT continue into the rest of Phase 5 (no Classification, no Outcomes, no signal write). When the cap is NOT hit (or the review converged with no findings), continue with the normal Outcomes flow below.

### Cap-pause behavior

Executed only when the Cap check above fired (`state.cycle >= state.rework_cap` AND the review did not converge). This sub-section is the ONLY writer of the `cap_pause_reason` state field; it is a separate top-level field from `stall_reason` (which has different shapes — `oversized_task`, `subagent_prompt_overrun`, `escalation_exhausted` — and a different lifecycle).

1. **Collect unresolved findings.** Read the current review-cycle output (the same review file Phase 4 produced) and gather every finding that has not yet been resolved by an earlier cycle. Format each finding minimally — at least `{"issue": <description>, "severity": <"critical"|"high"|"medium"|"low">, "consensus": <"N/M">}` — additional fields are allowed.

2. **Write `cap_pause_reason` to `state.json`.** Merge (do NOT replace siblings) the field:
   ```json
   "cap_pause_reason": {
     "cycle": <state.cycle>,
     "cap": <state.rework_cap>,
     "unresolved_findings": [ ... ]
   }
   ```

3. **Set `state.phase` and `state.next_phase`.** Both become `"paused"`. The Phase 0 Cap-Pause Resume Handler (a separate task) is what clears these on resume.

4. **Best-effort dashboard hint (optional).** MAY set `state.needs_attention = true`. This is a hint only — `needs_attention` is dashboard-only state cleared by the `clear-pidash-attention.py` PostToolUse hook on the next tool call, so it does NOT survive and MUST NOT be relied on as the pause indicator. The authoritative cap-pause signal is `phase == "paused"` PLUS `cap_pause_reason` being set (NOT `needs_attention`).

5. **No signal is written — by design.** Step 3 set `state.phase = "paused"`, and the Stop hook's decision table maps `phase == "paused"` → no signal (cap-pause and PAUSE sites stay interactive). So the hook suppresses the loop signal on its own; the shell wrapper sees no signal and exits its loop cleanly, and the user re-invokes `/run-autopilot` to handle the pause. The model writes nothing to the signal file.

6. **Print the cap-pause banner:**
   ```
   ── AUTOPILOT ── PRD: {prd-name} ── CAP PAUSE (cycle {n}/{cap}) ─────
   ── {k} unresolved findings — see state.json cap_pause_reason ───────
   ── re-invoke /run-autopilot to resume or abandon ───────────────────
   ```
   Substitute `{prd-name}` from `state.prd` (strip the `.md` extension), `{n}` from `state.cycle`, `{cap}` from `state.rework_cap`, and `{k}` from `len(unresolved_findings)`.

7. **STOP.** Do NOT proceed to Phase 6. Do NOT continue into Classification, Outcomes, or the hand-off-to-blind sub-section. The paused `state.json` is the durable signal that this PRD is awaiting user action; the Phase 0 Cap-Pause Resume Handler picks it up on the next `/run-autopilot` invocation.

Read the review output. Categorize each finding using `references/decision-framework.md`.

### Safety Checks — evaluate BEFORE classifying individual issues:

| Condition | Action |
|-----------|--------|
| >10 follow-up tasks from review | PAUSE: scope alarm — ask user before proceeding |
| Issue count not decreasing vs previous cycle | LOG and continue — a steady cycle is not a failure; the Phase 5 rework cap is the backstop |
| Same issue reappearing after previous fix | Route to research-then-decide Protocol B |
| A reviewer or sub-skill errored transiently during this review cycle | LOG and continue using the reviewers/sub-skills that succeeded (graceful degradation - e.g. a quota-exhausted reviewer is skipped, per the review skill). PAUSE only if the cycle cannot complete at all (no reviewer produced parseable output). A single transient error must not break an unattended run. |

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
- Decision blocks subsequent tasks (e.g. API shape needed before frontend can proceed)
- Data model choice that all remaining work depends on

Log every decision in the state file (`autonomous_decisions` or `deferred_decisions`); note the review cycle (`state.cycle`) in the entry's Decision text. The Phase 9 audit render reads these arrays — do not write `audit.md` here.

### Outcomes:

- **All auto-fixable, no deferrals, no blockers** → proceed to Phase 6
- **Has deferrals but no blockers** → log deferred items to `dev/local/autopilot/deferred/{batch_id}-deferred.json`, proceed to Phase 6 with auto-fixable items only
- **Has blocking escalation** → PAUSE. Present only the blocking issue(s) to user. Wait for decision. After user responds, proceed to Phase 6.
- **No issues found** → the review-rework loop has converged. Hand off to a fresh session for Phase 7 (see "Hand off to a fresh session before blind review" below).

### Hand off to a fresh session before blind review

When the flow is about to enter Phase 7 — the review-rework loop has converged (the "No issues found" outcome above) or exhausted its cycles — do NOT continue into Phase 7 in this session. Phase 7 spawns a blind reviewer and must start with a clean context window, uncluttered by this session's review findings and rework. Use the same signal-file + Stop-hook mechanism as the Phase 3 hand-off:

1. Add `"review"` to `phases_completed` — the marker Phase 4 reads to skip the whole review-rework loop on resume.
2. Set `phase` and `next_phase` to `"blind"`. The next session resumes here in a fresh session.
3. Print:

```
── AUTOPILOT ── PRD: {prd-name} ── review-rework loop complete ─────
── AUTOPILOT ── handing off to fresh session for blind review ──────
```

4. **STOP.** Do NOT invoke `/review-blindly` or `/review-with-doubt` in this session.

The Stop hook reads `next_phase: "blind"` from `state.json` and — when `$_AUTOPILOT_LOOP` is set — writes `next` to the signal file itself, then auto-exits. The fresh session reads `dev/local/autopilot/state.json` (with `"review"` in `phases_completed`), skips Phases 4-6 via the loop-level skip in Phase 4, and resumes at Phase 7. Outside the loop the hook writes nothing and the same resume logic applies on the next manual invocation.

## Phase 6: Rework

**Session model:** Phase 6 runs in the same session as Phase 4 (the `review` surface). The per-task tier escalation in `/work` step 3 (dispatching each task as a separate Agent call at `metadata.model`) means the actual rework implementation runs at the escalated tier (haiku/sonnet/opus) regardless of the outer session. No separate rework handoff is needed: the review session handles review quality; per-task dispatch handles implementation correctness.

Two task kinds enter this phase:

- **Review-flagged original-plan tasks** (`[C{cycle}]` prefix): a task `/work` already attempted that the review phase wants re-done. These are retries — escalate the model tier per the rule below.
- **Decision gate follow-ups** (`[D{cycle}]` prefix): brand-new tasks created from decision gate resolutions. These are first-pass work, not retries — they default to `sonnet` (no escalation applies). Apply the `/plan-tasks` Tier classifier here too if you have the inputs (PRD slice, files-touched estimate); otherwise default `sonnet`.

Both prefixes use the current cycle number. Both kinds dispatch through the same rework-mode `/work` invocation — see "Dispatch rework" below for how each gets its tier set and queued.

### Hydrate before any TaskUpdate (PRD 00025)

**Run the "Hydrate TaskList from state.tasks" sub-step** (defined in State Management above) BEFORE the "Escalate review-flagged tasks by tier" section's `TaskUpdate` calls. The rework session almost always inherits an empty TaskList from the post-Phase-3 handoff — running escalation TaskUpdate calls against an empty tracker either errors on unknown IDs or silently no-ops, losing the status→pending transition and dashboard visibility. Hydration is the first action of Phase 6, no exceptions.

### Escalate review-flagged tasks by tier (PRD 00025)

**Escalation caveat — diagnose the failure before escalating.** The tier chain
`haiku → sonnet → opus` assumes a review failure means the model wasn't capable
enough. That is often wrong. A review failure caused by a **spec-transmission
gap** — the implementer built a self-consistent *wrong* thing because the task
description never carried the PRD's exact contract (field names, enum values,
hook kind, thresholds) — is not a capability failure. Escalating the tier costs
more and does not address the cause: a stronger model fed the same thin task
description can fail the same way. Before escalating, look at the cycle's review
findings. If they are predominantly spec-misread (wrong schema, wrong API,
missing feature, wrong artifact kind) rather than implementation-quality bugs
(edge cases, perf, logic errors), the real fix is a **corrected task
description** — and the review's follow-up tasks should already carry the exact
contract verbatim. In that case keep the **same tier**; do not escalate. Record
the decision and rationale in `autonomous_decisions` (the Phase 9 audit render reads it). Escalate the tier only
when the prior attempt genuinely struggled on a correctly-specified task. (Root
cause of the original gap: `plan-tasks` must copy the PRD's contract and
acceptance criteria verbatim into each task — see `plan-tasks/SKILL.md` step 4.)

For each review-flagged original-plan task in the current cycle's review output:

1. Look up `state.tasks[i].attempts[-1]` — the last `/work` pass's entry, written by `/work` Attempt logging.
2. If `state.tasks[i].attempts` is empty or absent (legacy-plan task with no attempt log — covered by step 3's "no prior attempt" case and the closing paragraph after step 5), skip this step entirely and proceed to step 3's next-tier computation. Otherwise, rewrite that entry's `outcome` to `"review_flagged"` (it was `"completed"` when `/work` exited; review just flagged it).
3. Compute the next tier in the chain `haiku → sonnet → opus`:
   - **no prior attempt** (`state.tasks[i].attempts` empty or absent — covers both pre-PRD-00025 legacy plans and PRD-00025 tasks that crashed before the first attempt log wrote) → treat as `"sonnet"`; next is `"opus"`. **Metric caveat**: when this branch fires for a PRD-00025 task whose actual pass ran `haiku`, it inflates the apparent sonnet→opus escalation rate vs the PRD's ≤2% target. The branch is rare (crash before first attempt-log write) and the conservative jump-to-opus is the right correctness choice; just don't read sonnet→opus telemetry without accounting for it.
   - last attempt at `"haiku"` → next is `"sonnet"`
   - last attempt at `"sonnet"` → next is `"opus"`
   - last attempt at `"opus"` → **escalation exhausted**: the `haiku → sonnet → opus` chain has no higher tier, so the task cannot be reworked automatically. Do NOT continue to step 4 — **follow `references/recovery.md` → "Rework escalation exhausted"** (rewrites the last attempt's `outcome` to `"rework_failed"`, moves the PRD to `dev/local/prds/stalled/`, advances to the next PRD).
4. Otherwise (chain not exhausted), persist the escalated tier in BOTH places so `/work` and the state snapshot stay in sync, then queue the task for rework:
   - `TaskUpdate(taskId="<id>", metadata={"model": "<next_tier>"})` — canonical source `/work` reads via `TaskGet` (see `work/SKILL.md` "Per-task model dispatch").
   - Write the same value to `state.tasks[i].model` — the snapshot the dashboard and the next review cycle read.
   - Append the task ID to `state.rework_task_ids` (create the array if absent).
5. Reset `state.tasks[i].status` back to `"pending"` via `TaskUpdate(taskId, status="pending")` so `/work` will iterate it again. **Reverse status transitions (`completed` → `pending`) are supported** — the hydration sub-step (State Management above) relies on the same mechanism to restore `completed` status on a fresh session, and the PostToolUse status-sync hook treats whatever `TaskUpdate` writes as the new ground truth.

The "no prior attempt" case in step 3 covers both pre-PRD-00025 legacy plans (which lack `metadata.model` and `attempts[]` entirely) and PRD-00025 tasks that crash before the first attempt log writes (rare but possible). Both are treated as `"sonnet"` for the next-tier computation, so first escalation goes to `"opus"`.

### Dispatch rework

Build the rework batch from two sources:

1. **Review-flagged `[C{cycle}]` tasks** — `state.rework_task_ids` already contains their IDs (appended in step 4 above), and their `metadata.model` + `state.tasks[i].model` already carry the escalated tier.
2. **Decision gate `[D{cycle}]` follow-ups** — for each new task created from a decision gate resolution:
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

**Skip if:** `"blind"` in `phases_completed` in state file.

Spec-only verification by a reviewer with no implementation context. Invoke `/review-blindly` with only the PRD content - no file lists, implementation notes, or review history.

After the review:

1. **No Critical/Important findings** → update state: add `"blind"` to `phases_completed`, set `phase: "doubt"` and `next_phase: "doubt"`. Then hand off to a fresh session for Phase 8 (see "Hand off to a fresh session for doubt review" below).
2. **Critical or Important findings** → **first run the "Hydrate TaskList from state.tasks" sub-step** (the blind review session is fresh; TaskList is empty). Then create tasks tagged `[BLIND]` (each `TaskCreate` gets a new id appended to the hydrated list) and insert a merge-preserving snapshot for each new `[BLIND]` task into `state.tasks` (carrying `{id, name, status}`; the tier classifier does not run on [BLIND] tasks — they default to the running session's model unless you opt to set `metadata.model` explicitly). Invoke `/work`. After fixes complete, update state the same way as outcome 1: add `"blind"` to `phases_completed`, set `phase: "doubt"` and `next_phase: "doubt"`. **Also update task counts (`tasks_total`/`tasks_completed`) only — do NOT rewrite `state.tasks` here; `/work` already wrote `attempts[]` entries directly to `state.tasks` for the `[BLIND]` tasks, and a bare TaskList snapshot would strip them** (same rationale as Phase 6 step 3 and Phase 8 step 5). Then hand off to a fresh session for Phase 8 (see "Hand off to a fresh session for doubt review" below). Do not loop back to Phase 4.
3. **Zero issues with no file references** → suspicious result (reviewer may not have found the code). Log a warning, then update state the same way as outcome 1 (add `"blind"` to `phases_completed`, set `phase` and `next_phase` to `"doubt"`) and hand off to a fresh session for Phase 8 (see "Hand off to a fresh session for doubt review" below).

Minor findings: defer to batch end (append to `deferred_decisions` in state).

This phase runs once per PRD.

### Hand off to a fresh session for doubt review

After Phase 7 completes (either outcome above — `"blind"` is now in `phases_completed` and `next_phase` is `"doubt"`), do NOT continue into Phase 8 in this session. The doubt review needs a clean context window. Same mechanism as the Phase 3 and Phase 5 hand-offs:

1. Confirm `"blind"` is in `phases_completed` and `phase`/`next_phase` are `"doubt"` (set by the outcome handlers above).
2. Print:

```
── AUTOPILOT ── PRD: {prd-name} ── Phase 7 (Blind Review) complete ─
── AUTOPILOT ── handing off to fresh session for doubt review ──────
```

3. **STOP.** Do NOT invoke `/review-with-doubt` in this session.

The Stop hook reads `next_phase: "doubt"` from `state.json` and — when `$_AUTOPILOT_LOOP` is set — writes `next` to the signal file itself, then auto-exits. The fresh session reads `dev/local/autopilot/state.json` (`"blind"` in `phases_completed`), skips Phases 4-7 via their skip conditions, and resumes at Phase 8. Outside the loop the hook writes nothing and the same resume logic applies on the next manual invocation.

## Phase 8: Doubt Review

**Skip if:** `"doubt"` in `phases_completed` in state file.

**Apply the doubt review rubric.** This phase applies the numbered rubric at `references/doubt-review-rubric.md` (rules R1-R5). The doubt review output MUST record `R{n}: pass|fail` for every rule — one rule per line, no other text on the line, no rationale. A rule the reviewer cannot evaluate counts as `fail`; never omit the line. Rule IDs are stable; do not renumber.

**Run codex as the primary doubt reviewer, with a Claude fallback.** codex is strong at skeptical review, so this phase runs it — but a codex outage must never skip a mandated review, so it falls back to Claude. Procedure (sequential Bash calls — never a bare relative path):

1. Resolve the autopilot dir: `python3 ~/.claude/skills/run-autopilot/scripts/_walk_up.py --bash`.
2. Build a self-contained prompt: read `prompts/doubt-review.md`, append the PRD content, the diff range (`<state.work_start_sha>..HEAD`), and the changed-file list (so codex can fill the coverage block's `files`/`features` dimensions), and write the combined prompt to `dev/local/autopilot/doubt-prompt.md` (Write tool, absolute path).
3. Run codex: `python3 ~/.claude/skills/run-autopilot/scripts/codex_review_run.py <autopilot_dir>/doubt-prompt.md`.

Branch on its exit code:
- **exit 0** → read the review from `<autopilot_dir>/codex-review-output.md`. This is the doubt review output: FIX/VERIFY/KNOWN findings, the `R{n}: pass|fail` block, and the `---review-coverage---` block.
- **exit 3 (codex unavailable) or exit 4 (codex ran but failed, e.g. usage-limit/quota)** → print the loud banner, then run the Claude fallback:
  ```
  ── AUTOPILOT ── codex unavailable for doubt review; running on Claude ──
  ```
  Invoke `/review-with-doubt` with the `references/doubt-review-rubric.md` content inlined as additional context (it runs in a subagent that needs a self-contained prompt), and instruct it to apply the same **de-slop lens** the codex prompt uses (flag over-engineering, dead code, single-caller abstractions, and AI-slop in the diff). Require the identical output: FIX/VERIFY/KNOWN, the `R{n}: pass|fail` block, and the `---review-coverage---` block.

**Coverage block (both paths).** The output MUST include a `---review-coverage---` block with `files`, `features`, and `rubric` filled and `tests` left as `pending: filled by consolidation`. The exact format is defined in `skills/review-work-completion/references/review-coverage-format.md`. PRD 00038's `review_coverage.py` parses this block downstream; a missing or malformed block fails the Phase 8 verdict.

**Run the coverage gate.** After the doubt review output is obtained (from either the codex path or the Claude fallback), run the gate before processing any findings:

1. Identify the doubt review output file: `<autopilot_dir>/codex-review-output.md` on the codex path. On the Claude fallback path, if the output is not already on disk, write it to `dev/local/reviews/.doubt-reviewer-block.md` first.
2. Resolve `<prd-base>` = `state.prd` without its `.md` extension.
3. Invoke the gate (do NOT pass `--rubric` — `SURFACE_RUBRIC_DEFAULTS` resolves `doubt` automatically):
   ```bash
   python3 ~/.claude/skills/review-work-completion/scripts/review_coverage.py \
     --surface doubt \
     --prd dev/local/prds/wip/<state.prd> \
     --diff-range <state.work_start_sha>..HEAD \
     --reviewer-block <doubt-output-file> \
     --run-tests \
     --write-aggregate dev/local/reviews/.doubt-aggregate.md \
     --repo <state.repo_root>
   ```
   `--repo` must be `state.repo_root` when set (work repo nested under a non-git
   project root); omit it only when the project root itself is the git repo.
   `--run-tests` makes the gate run the changed test files (`test_*.py` / `*_test.py`
   in the diff range) once and fill the aggregate's `tests` dimension with real
   pass/fail/skip counts; the doubt reviewer leaves `tests` as the `pending`
   sentinel. A code diff whose tests dimension stays unfilled fails `EMPTY_TESTS`.
4. If the gate exits non-zero: the doubt review FAILS — surface the gap kind printed on stderr (`MISSING_REVIEW_BLOCK`, `MALFORMED_BLOCK`, `MISSING_FILES`, `EMPTY_TESTS`, `UNMAPPED_FEATURE`, `MISSING_RUBRIC_RULE`, `MISSING_PRD`, or `DIFF_ERROR` — the last means the gate could not run `git diff` at all; fix `--repo`/`state.repo_root` instead of treating it as a coverage gap) and its detail; do NOT continue to findings classification.
5. On exit 0: write `dev/local/reviews/<prd>-doubt-review.md` (where `<prd>` = `<prd-base>`) containing the doubt findings (FIX / VERIFY / KNOWN) followed by the aggregate coverage block from `dev/local/reviews/.doubt-aggregate.md`. (This filename is intentionally distinct from the `-review-NN.md` pattern — no collision with the Phase 4 cycle-skip glob. The autopilot Phase 2 Stop hook re-checks this file's aggregate block when `state.phase == "done"`.)

The doubt review produces findings in three categories: **FIX** (fixable now), **VERIFY** (needs checking), and **KNOWN** (real limitation, out of scope).

**Before processing any FIX/VERIFY items, run the "Hydrate TaskList from state.tasks" sub-step** (defined in State Management). This guarantees subsequent `[DOUBT]` `TaskCreate` calls get ids appended after the hydrated original-plan tasks (rather than overwriting id 1 in an empty tracker).

Process each:

### Handling FIX items

1. Create a task tagged `[DOUBT]` for each FIX item.
2. Add an entry to `doubts` in state: `{"description": "...", "category": "fix", "status": "pending"}`.

### Handling VERIFY items

VERIFY items are resolved during the review itself (the doubt skill runs checks and reclassifies as FIX or dismissed). If any survive unresolved:
1. Treat as FIX — create a `[DOUBT]` task.
2. Add to `doubts` in state with `"category": "verify"`.

### Handling KNOWN items

KNOWN items cannot be fixed in this scope. They flow to batch-end review for the user to decide.
1. Add to `doubts` in state: `{"description": "...", "category": "known", "justification": "...", "status": "pending"}`.
2. Do NOT create tasks for KNOWN items — they are deferred, not actionable here.

### Execution

After classifying all items:

1. If no FIX or VERIFY tasks → proceed to Phase 9. KNOWN items (if any) will be surfaced at batch end.
2. If >5 FIX/VERIFY tasks → defer all to batch end (append each to `deferred_decisions` in state as `{"type": "doubt-overflow", "description": "...", "category": "fix|verify", "status": "pending"}`). Log warning but do NOT PAUSE. Proceed to Phase 9.
3. If ≤5 FIX/VERIFY tasks → invoke `/work` on `[DOUBT]`-tagged tasks immediately — no decision gate, no rework loop. (Hydration already ran at the top of the phase.)
4. After work completes, mark each resolved doubt entry's `status` as `"resolved"` in state.
5. Record per-rule verdicts. Read the `R{n}: pass|fail` block from the doubt review output and append it to `state.doubts_rubric_verdicts` as an array of `{"rule_id": "R{n}", "verdict": "pass"|"fail"}` objects. Every rubric rule must have an entry. The downstream coverage parser (PRD 00038's `review_coverage.py`) reads these verdicts from the raw doubt review output; this state field is the autopilot-internal record so the batch report can summarize them in Phase 9.
6. Update state: add `"doubt"` to `phases_completed`, set `phase: "done"` and `next_phase: "done"`, update task counts (`tasks_total`/`tasks_completed` only — do NOT rewrite `state.tasks` here; same rationale as Phase 6 step 3, `/work` wrote `attempts[]` to `state.tasks` for `[DOUBT]` tasks).

KNOWN items keep `"status": "pending"` — Phase 9 step 6 collects these into the batch deferred log for batch-end review.

This phase runs once per PRD. It does not loop back to Phase 4.

## Phase 9: Completion

1. **Commit history is left as-is.** Autopilot does NOT rewrite the PRD's commit history. The former cherry-pick regroup engine never pushed — it only churned local history the user re-reviewed before pushing anyway — so it was pure risk (conflict aborts, backup branches) for no shipped benefit. The user squashes/groups commits manually before pushing.

2. Update state: set `phase: "done"` and `next_phase: "done"`
3. Move PRD from `wip/` to `done/` (use `mv`, keep `00XXX-` prefix)
4. Append completed PRD to `batch.completed_prds` in state file
5. Delete all tasks from the completed PRD: query `TaskList`, mark every task as `deleted` via `TaskUpdate`. This prevents stale tasks from triggering Phase 2's skip logic on the next PRD.
6. Append items to `dev/local/autopilot/deferred/{batch_id}-deferred.json` (create if missing). Collect from the current state file:
   - `deferred_decisions` with status `"pending"` or `"deferred"` -> type `"deferred_decision"` (preserve original `type` field if present, e.g. `"doubt-overflow"`)
   - `doubts` with status `"pending"` -> type `"doubt"`
   - `autonomous_decisions` with `research` field -> type `"autonomous_research"` (for user awareness at batch end)
   Each entry gets tagged with `prd` (filename) and `cycle`. Preserve the full `research` field when present - this is the only copy that survives state reset. Skip this step if nothing to write.
6a. **Render this PRD's audit file** `dev/local/reviews/<prd-base>-audit.md` (`<prd-base>` = PRD filename without `.md`) ONCE from the state decision arrays — this is the ONLY writer of `audit.md`. Write in a single pass (Write tool): a header (PRD, started/completed timestamps, counts `autonomous N | deferred N | doubts N`), then one entry per item in `state.autonomous_decisions` (label `autonomous`), `state.deferred_decisions` (`deferred`), and `state.doubts` (`doubt`), using the entry format in `references/audit-log-format.md`. When all three arrays are empty, write the header plus a single `no decisions recorded` line.

7. Append PRD summary to `dev/local/autopilot/reports/{batch_id}-report.md` (create with header if missing). See `references/batch-report-format.md` for format.
7b. Project autonomous decisions into `dev/local/decisions.md` when that opt-in file exists (skip when absent; `audit.md` is written either way). Follow the **"decisions.md Projection"** procedure in `references/audit-log-format.md` — it covers the qualify criterion (label `autonomous` + non-trivial), the row format, dedupe, and the single-source rule.
8. Update the Active Work section of `dev/local/project-capsule.md` with batch progress. Use the Edit tool to replace the Active Work section content:
   ```markdown
   ## Active Work

   ### Batch {batch_id}
   - [x] {completed PRD name} ({n} cycles)
   - [x] ...for each completed PRD in batch
   - [ ] {PRD name} - for each PRD still in wip/ or backlog/

   Observations: {any operational gotchas useful for next iteration}
   ```
   If the capsule doesn't exist yet (catchup was skipped), create a minimal one with just the Active Work section.
9. Print per-PRD summary:

```
── AUTOPILOT ── PRD: {prd-name} ── DONE ── {n} cycles ─────────────

Summary:
- Cycles: {n}
- Autonomous decisions: {count}
- Escalated decisions: {count}
- Follow-up tasks fixed: {count}
```

### Continuation

10. Check: any PRDs remaining in `dev/local/prds/wip/*.md` or `dev/local/prds/backlog/*.md`?
   - **Yes** → reset state for next PRD: set `phases_completed` to `[]`, `cycle` to `1`, `tasks_total: 0`, `tasks_completed: 0`, clear tasks/task_aborts/`cap_rotations`/autonomous_decisions/deferred_decisions/review_cycles/doubts/`doubts_rubric_verdicts`/`rework_task_ids`/`work_start_sha`/`repo_root` (the next PRD starts a fresh plan, not a rework dispatch; `cap_rotations`, `work_start_sha`, `repo_root`, and `doubts_rubric_verdicts` are per-PRD scratch — Phase 3 of the next PRD overwrites `work_start_sha` and `repo_root`, Phase 8 overwrites `doubts_rubric_verdicts`, but clearing here prevents stale values from surviving if the next PRD aborts before reaching those phases), set `replan_count: 0` (it tracked the current PRD's replans; the next PRD starts fresh). Delete `dev/local/autopilot/replan-context.md` if it exists (defensive — plan-tasks deletes it on success, but a malformed prior session may have left it). **Preserve `batch` field in full, including `batch.catchup_completed_at` and `batch.catchup_head_sha`** — Phase 1 of the next PRD reads these to decide between full catchup and delta refresh (see Phase 1 "Batch cache check"). Set `phase: "build"` and `next_phase: "build"` (the next PRD starts the build gate at catchup). The Stop hook reads `next_phase: "build"` and — when `$_AUTOPILOT_LOOP` is set — writes `next` to the signal file itself, then auto-exits; outside the loop it writes nothing and the user re-invokes `/run-autopilot` manually for the next PRD. Print:
     ```
     ── AUTOPILOT ── {prd-name} done ── next PRD in new session ────────
     ```
     Then **STOP**.
   - **No** → print batch summary. Set `state.phase = "paused"` and do NOT delete `state.json` — batch-end review is an interactive pause, so the Stop hook suppresses the loop signal (`phase == "paused"` → no signal) while you collect user decisions, and it needs `state.json` present to emit the final `done`. The session stays interactive for batch-end review.
     ```
     ── AUTOPILOT ── COMPLETE ───────────────────────────────────────────

     Completed {n} PRDs:
       1. {prd-name} ({cycles} cycles)
       2. {prd-name} ({cycles} cycles)
       ...
     ```

     ### Batch-End Review

     Before exiting, collect ALL pending items from across the batch and present them to the user. This is mandatory if any items exist - never auto-exit with unreviewed items.

     **Source:** `dev/local/autopilot/deferred/{batch_id}-deferred.json` (single source of truth - all items were written here at Phase 9 step 6 of each PRD). Contains four item types:
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

     After all PRD chunks are reviewed (or user says stop), delete the deferred JSON. Set `state.phase = "done"` and `state.next_phase = ""` (empty; nothing more to run), then STOP. The Stop hook reads `next_phase: ""` (with `phase` no longer `"paused"`), writes `done` to the signal file, deletes `state.json` so the next batch starts from a clean slate, and auto-exits; the shell loop sees `done` and stops. Outside the loop (`$_AUTOPILOT_LOOP` unset) the hook writes nothing — leave the session interactive.
     If the deferred JSON doesn't exist or is empty, set `state.phase = "done"` and `state.next_phase = ""` and STOP immediately — the hook emits `done` and cleans up the same way.

## Session Loop

Autopilot supports automatic session cycling via a signal file + Stop hook. This enables unattended PRD-to-PRD transitions while keeping sessions interactive.

**Signal file:** `dev/local/autopilot/signal` — written by the Stop hook (`scripts/autopilot_stop_hook.py`) from `state.json`, never by the model. Possible values:

- `next` — emitted when `state.next_phase` is a non-empty gate (`review`/`blind`/`doubt`/`build`) and work remains: the build→review hand-off, the review→blind and blind→doubt hand-offs, Phase 9 step 10 when more PRDs remain, AND a Work-turn context-cap overrun, where `autopilot_context_cap_hook.py` records the rotation (appends to `state.cap_rotations`, resets the in-flight task to `pending`, sets `next_phase: "build"`); the Stop hook writes `next` on STOP. The fresh session resumes `build` by artifact — capsule fresh → skip catchup, tasks exist → skip planning, `/work` continues at the first non-completed task (the rotated task, now reset to `pending`); NO replan. Shell wrapper continues the loop.
- `done` — emitted when batch-end review sets `state.next_phase: ""` (empty). The hook also deletes `state.json` so the next batch starts clean. Shell wrapper exits the loop.
- `task_aborted` — emitted when `state.stall_reason.stalled == "subagent_prompt_overrun"` (set by `/work`'s Subagent Dispatch Budget when an assembled subagent prompt exceeded 50K after one trim pass; `/work` also appends to `state.task_aborts`). This is the one surviving replan path. Shell wrapper continues the loop; Phase 0 of the next session replans the PRD in place (PRD stays in `wip/`; see Phase 0 step 1's replan procedure).

The model's only job at a hand-off is to write `state.next_phase` (and `phase`/`stall_reason`) accurately, print the banner, and STOP. The Stop hook reads those fields and writes the matching signal itself — gated on `$_AUTOPILOT_LOOP` (set by `autoclaude`); outside the loop it writes nothing.

### Loop Detection

The shell wrapper (the `autoclaude` function in `~/.config/bash/plugins/development.plugin.bash`) exports `_AUTOPILOT_LOOP=$$` before invoking `claude`. The Stop hook reads this env var directly and only writes the signal (and only SIGINTs to auto-exit) when it is set — outside the loop the hook is inert, so an interactive `/run-autopilot` is never auto-exited or signaled.

The model does NOT write the signal and does NOT check `_AUTOPILOT_LOOP` at hand-off sites. Each hand-off is three actions: update `state.json` (set `next_phase`, plus `phase`/`stall_reason` where relevant), print the banner, and STOP. The Stop hook (`scripts/autopilot_stop_hook.py`) walks up from cwd to the autopilot dir, reads `state.json`, computes the signal from its decision table (`phase == "paused"` → none; `stall_reason.stalled == "subagent_prompt_overrun"` → `task_aborted`; `next_phase == ""` → `done`; non-empty `next_phase` → `next`; absent/corrupt state → none, fail open), writes it to the absolute signal path, and auto-exits. Because the hook derives the path from the walk-up helper itself, a changed cwd during the work phase no longer matters.

**Shell wrapper:**

```bash
while true; do
  claude "/run-autopilot"
  signal=$(cat dev/local/autopilot/signal 2>/dev/null)
  rm -f dev/local/autopilot/signal
  case "$signal" in
    next)         echo "Starting next PRD..." ;;
    task_aborted) echo "Work task hit subagent-prompt overrun; PRD will be replanned. Continuing..." ;;
    done)         echo "Backlog drained."; break ;;
    *)            echo "No/unknown signal: session died, paused, or a gate blocked the handoff. NOT drained." >&2; break ;;
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

### De-slop is part of the doubt review (Phase 8)

There is no separate between-session de-slop pass. The standalone codex pass that
once ran from the `autoclaude` wrapper after every commit was removed: it was an
unconditional external call that fell silently dead when codex hit its usage
limit. De-slopping now happens **inside Phase 8** — codex conducts the doubt
review with an added de-slop lens (see Phase 8). The codex runner is
`scripts/codex_review_run.py` (it returns exit 3 when codex is unavailable and 4
when codex ran but failed, so Phase 8 can fall back to a Claude review rather
than silently skip). If you are checking how de-slop is wired, look at Phase 8,
not the `autoclaude` function.

## Shell Command Rules

- **Never chain commands** with `&&`, `|`, or `;` in a single Bash call. Use separate Bash tool calls instead.
- **Never use redirections** like `2>/dev/null`. Handle missing files by checking existence or catching errors in the tool result.
- Use `Glob` or `Read` instead of `ls` where possible (e.g. to check if files exist or list directory contents).
- Use `mkdir -p` in its own Bash call when creating directories.

## Error Handling

| Situation | Action |
|-----------|--------|
| Sub-skill invocation fails outright (no usable result; the phase cannot proceed) | PAUSE, report which skill failed and error. A transient reviewer/sub-skill error *during the Phase 4-6 review-rework cycle* is the Phase 5 Safety Checks row's domain instead (graceful degradation, not a PAUSE). |
| No PRDs anywhere | STOP with message about /create-prd |
| State file corrupted | Delete it, restart from Phase 0 |
| Review produces no parseable output | PAUSE, report — don't retry |
| All three reviewers fail | PAUSE, report — partial results usable if user confirms |
| `dev/local/` doesn't exist | Create it |
| Task tools unavailable | STOP, report — can't operate without tasks |

**Turn-ending PAUSE rows must set `state.phase = "paused"` (and `state.next_phase = "paused"`) before stopping.** Otherwise the Stop hook — seeing `$_AUTOPILOT_LOOP` set and a non-empty `next_phase` with work pending — would write `next` and relaunch the failed phase instead of leaving the session interactive for you to intervene. `phase == "paused"` is the hook's suppression key (decision table: `phase == "paused"` → no signal). This applies to "Sub-skill invocation fails outright", "Review produces no parseable output", and "All three reviewers fail". Exceptions that need no `phase` change: "State file corrupted" (deleting state makes the hook fail open with no signal) and "No PRDs anywhere" (a clean terminal — the hook emits `done` if `next_phase` is `""`, otherwise nothing). PAUSE sites that ask via `AskUserQuestion` mid-turn (Phase 2 clarification, Phase 5 blocking escalation and scope alarm) do NOT end the turn, so the hook never fires there and they need no `phase` change.

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
- `references/recovery.md` — rare-path handlers: Work-phase abort/replan, plan-tasks stall, escalation-exhausted
- `references/dashboard-format.md` — live dashboard via pidash
- `references/batch-report-format.md` — batch audit report format
