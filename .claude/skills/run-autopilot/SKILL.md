---
name: run-autopilot
description: Run full PRD lifecycle autonomously - catchup, planning, work, review, rework. Triggers on "autopilot", "run autopilot", "autopilot status", "drain backlog", "execute PRD end to end".
argument-hint: "[<prd-filename> | status]"
---

# Autopilot

Orchestrate the full PRD lifecycle: catchup → plan-tasks → work → review → rework loop → doubt review → done.

Makes autonomous decisions backed by research (dependencies, recurring issues, API/schema changes when PRD-driven) and pauses only for critical security, requirements ambiguity, or blocking decisions.

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

### Resuming

When `/run-autopilot` is invoked and `dev/local/autopilot/state.json` exists with `batch.completed_prds`, this is a continuation after a session restart. Preserve `batch.completed_prds` (including `batch.id`) and proceed to Phase 0 to pick the next PRD.

Clean up stale signal file at start: delete `dev/local/autopilot/signal` if it exists.

### Task Counts

At every state update, query `TaskList` and write current counts to the state file:
- `tasks_total` — number of tasks (pending + in_progress + completed)
- `tasks_completed` — number of tasks with status completed

This keeps the dashboard progress bar accurate.

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

1. If argument provided, find that PRD in `dev/local/prds/wip/` or `dev/local/prds/backlog/`. If found in backlog, `mv` to `wip/`.
2. Otherwise, auto-select:
   a. Check `dev/local/prds/wip/`:
      - 1 found → auto-select, announce
      - 2+ found → ask user which one
   b. If wip is empty, check `dev/local/prds/backlog/`:
      - PRDs available → auto-pick lowest sequence number, `mv` to `wip/`
      - Empty → STOP: "No PRDs found. Create one with /create-prd."
3. Initialize `batch` in state file if not already present: `id: "<yyyymmddHHMM>"` (current timestamp), `mode: "autopilot"`, `completed_prds: []`
4. Read the Active Work section of `dev/local/project-capsule.md` if it exists. This contains PRD progress and operational context from previous sessions. Use it to inform work in this session.
5. Initialize/update state with selected PRD, preserve `batch` field
6. Print progress:
   ```
   ── AUTOPILOT ── PRD {n}: {prd-name} ─────────────────────────────
   ```
   Where `{n}` = `len(batch.completed_prds) + 1`

## Phase 1: Catchup

**Skip if:** `"catchup"` in `phases_completed` in state file.

Invoke `/catchup` skill.

After completion, update state: add `"catchup"` to `phases_completed`, set `phase: "planning"`.

## Phase 2: Planning

**Skip if:** `TaskList` returns any pending or completed tasks (tasks already exist).

Invoke `/plan-tasks` with the selected PRD.

After completion, query `TaskList` and update state: add `"planning"` to `phases_completed`, set `phase: "work"`, write `tasks`/`tasks_total`/`tasks_completed` snapshot (see Phase 3 for format).

## Phase 3: Work

**Skip if:** All tasks completed, none pending.

Before invoking `/work`, query `TaskList` and write the full task snapshot to `dev/local/autopilot/state.json`:
- `tasks_total`: total count
- `tasks_completed`: completed count
- `tasks`: array of `{"id": "<task-id>", "name": "<title>", "status": "pending|in_progress|completed"}` for EVERY task

**Include the task `id` field** — a PostToolUse hook on TaskUpdate uses it to automatically sync status changes to the dashboard. This is mandatory.

Invoke `/work` skill. It runs until all tasks complete.

After completion, query `TaskList` again and update state: add `"work"` to `phases_completed`, set `phase: "review"`, write updated `tasks`/`tasks_total`/`tasks_completed`.

## Phase 4: Review

**Skip if:** Review file exists in `dev/local/reviews/` for current cycle (check filename pattern `{prd-name}-review-{cycle}.md`).

Invoke `/review-work-completion` skill.

After completion, update state: set `phase: "decision-gate"`.

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
- **No issues found** → proceed to Phase 7 (Doubt Review)

## Phase 6: Rework

Tag follow-up tasks from review findings with `[C{cycle}]` prefix and tasks from decision-gate resolutions with `[D{cycle}]` prefix. Both use the current cycle number.

Before invoking `/work`, update state with current task counts.

Invoke `/work` on follow-up tasks (auto-fixable ones + user-approved ones only).

The work skill may parallelize independent rework tasks when `superpowers:dispatching-parallel-agents` is available (see work skill's "Parallel dispatch for independent rework fixes").

Increment cycle counter. Update state: set `phase: "review"`, update task counts. Loop back to Phase 4.

## Phase 7: Doubt Review

**Skip if:** `"doubt-review"` in `phases_completed` in state file.

Final sanity check before completion. Invoke `/review-with-doubt`.

After the review produces findings:

1. For each concrete weakness, missing test, edge case, or flaw identified:
   - Create a task tagged with `[DOUBT]` prefix
   - Add an entry to `doubts` in the state file: `{"description": "...", "severity": "low|medium|high|critical", "status": "pending"}`
2. If no actionable findings (confidence >= 8, no concrete issues) → skip to Phase 8
3. If >5 doubt tasks created → PAUSE: "Doubt review flagged {n} issues after review cycle passed. Review the list before proceeding."
4. Otherwise, invoke `/work` on the `[DOUBT]`-tagged tasks immediately — no decision gate, no rework loop
5. After work completes, mark each doubt entry's `status` as `"resolved"` in the state file
6. Update state: add `"doubt-review"` to `phases_completed`, set `phase: "done"`, update task counts

This phase runs once per PRD. It does not loop back to Phase 4.

## Phase 8: Completion

1. Update state: set `phase: "done"`
2. Move PRD from `wip/` to `done/` (use `mv`, keep `00XXX-` prefix)
3. Append completed PRD to `batch.completed_prds` in state file
4. Delete all tasks from the completed PRD: query `TaskList`, mark every task as `deleted` via `TaskUpdate`. This prevents stale tasks from triggering Phase 2's skip logic on the next PRD.
5. Append items to `dev/local/autopilot/deferred/{batch_id}-deferred.json` (create if missing). Collect from the current state file:
   - `deferred_decisions` with status `"pending"` or `"deferred"` -> type `"deferred_decision"`
   - `doubts` with status `"pending"` -> type `"doubt"`
   - `autonomous_decisions` with `research` field -> type `"autonomous_research"` (for user awareness at batch end)
   Each entry gets tagged with `prd` (filename) and `cycle`. Preserve the full `research` field when present - this is the only copy that survives state reset. Skip this step if nothing to write.
6. Append PRD summary to `dev/local/autopilot/reports/{batch_id}-report.md` (create with header if missing). See `references/batch-report-format.md` for format.
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
8. Print per-PRD summary:

```
── AUTOPILOT ── PRD: {prd-name} ── DONE ── {n} cycles ─────────────

Summary:
- Cycles: {n}
- Autonomous decisions: {count}
- Escalated decisions: {count}
- Follow-up tasks fixed: {count}
```

### Continuation

9. Check: any PRDs remaining in `dev/local/prds/wip/*.md` or `dev/local/prds/backlog/*.md`?
   - **Yes** → reset state for next PRD: set `phases_completed` to `[]`, `cycle` to `1`, clear tasks/decisions/review_cycles/doubts. Preserve `batch` field. Write `next` to `dev/local/autopilot/signal`. Print:
     ```
     ── AUTOPILOT ── {prd-name} done ── next PRD in new session ────────
     ```
     Then **STOP**. The stop hook auto-exits the session. The shell loop starts a fresh session.
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

     **Source:** `dev/local/autopilot/deferred/{batch_id}-deferred.json` (single source of truth - all items were written here at Phase 8 step 5 of each PRD). Contains three item types:
     - `deferred_decision` - issues that failed research or were deferred for other reasons
     - `doubt` - unresolved findings from doubt review
     - `autonomous_research` - research-backed decisions made autonomously (for user awareness)

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

     After all PRD chunks are reviewed (or user says stop), delete the deferred JSON and write `done` to `dev/local/autopilot/signal`.
     If the deferred JSON doesn't exist or is empty, write `done` to `dev/local/autopilot/signal` immediately.
     The stop hook auto-exits the session. The shell loop sees `done` and stops.

## Session Loop

Autopilot supports automatic session cycling via a signal file + Stop hook. This enables unattended PRD-to-PRD transitions while keeping sessions interactive.

**Signal file:** `dev/local/autopilot/signal` — written at Phase 8 completion with `next` (more PRDs) or `done` (backlog empty).

**Shell wrapper:**

```bash
while true; do
  claude "/run-autopilot"
  signal=$(cat dev/local/autopilot/signal 2>/dev/null)
  rm -f dev/local/autopilot/signal
  if [ "$signal" != "next" ]; then
    echo "Backlog drained."
    break
  fi
  echo "Starting next PRD..."
done
```

**Required:** A Stop hook that auto-exits when the signal file exists. See `scripts/autopilot-stop-hook.sh`. Configure in `settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "command": "~/.claude/skills/run-autopilot/scripts/autopilot-stop-hook.sh"
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

### Used by the Work skill (Phases 3, 6, 7)

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

Per-task review (step 5.7) and PRD-level review (Phase 4) are complementary, not redundant. Per-task catches issues early before they compound across tasks. Phase 4 catches cross-task coherence, requirement coverage, and integration issues. Both are needed.

## Reference Files

- `references/state-schema.md` — state file JSON schema and skip logic
- `references/decision-framework.md` — auto-fix vs escalate classification rules
- `references/dashboard-format.md` — live dashboard via pidash
- `references/batch-report-format.md` — batch audit report format
