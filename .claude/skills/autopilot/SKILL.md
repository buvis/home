---
name: autopilot
description: Orchestrate full PRD lifecycle autonomously — catchup, planning, work, review, and rework loops. Chains existing skills, tracks state, makes safe decisions autonomously, pauses only when human judgment is needed. Use when ready to execute a PRD end-to-end. Triggers on "autopilot", "run autopilot", "autopilot status", "auto pilot", "run the full cycle", "execute PRD end to end".
---

# Autopilot

Orchestrate the full PRD lifecycle: catchup → plan-tasks → work → review → rework loop → done.

Makes safe autonomous decisions (style fixes, missing tests) and pauses for dangerous ones (security, API changes, ambiguity).

## Entry Points

- `/autopilot` — full cycle, auto-detect PRD
- `/autopilot <prd-filename>` — full cycle with specific PRD
- `/autopilot status` — print current dashboard, no action

If invoked with `status`, read `.local/prd-cycle.json`, print phase/cycle/task summary, and stop.

## State Management

State file: `.local/prd-cycle.json` — see `references/state-schema.md` for schema.

Create `.local/` if missing. Initialize state file at PRD selection. Update state at every phase transition.

### Task Counts

At every state update, query `TaskList` and write current counts to the state file:
- `tasks_total` — number of tasks (pending + in_progress + completed)
- `tasks_completed` — number of tasks with status completed

This keeps the dashboard progress bar accurate.

### Live Dashboard

The user can run `pidash` (from buvis-gems) in a separate terminal pane to watch progress in real time. It watches `.local/prd-cycle.json` automatically — no action needed from autopilot beyond keeping the state file updated.

### Phase Banners

Print a banner at each phase transition:

```
── AUTOPILOT ── PRD: {prd-name} ── Phase: {PHASE} ──────────────────
── AUTOPILOT ── PRD: {prd-name} ── Phase: REVIEW ── Cycle {n} ─────
── AUTOPILOT ── PAUSED ── {n} issue(s) need your decision ──────────
── AUTOPILOT ── PRD: {prd-name} ── DONE ── {n} cycles ─────────────
```

## Phase 0: PRD Selection

1. If argument provided, find that PRD in `.local/prds/wip/` or `.local/prds/backlog/`
2. Otherwise check `.local/prds/wip/`:
   - 1 found → auto-select, announce
   - 2+ found → ask user which one
   - 0 found → check `.local/prds/backlog/`:
     - PRDs available → present numbered list, user picks, `mv` to `wip/`
     - Empty → STOP: "No PRDs found. Create one with /save-plan."
3. Initialize state file with selected PRD — always overwrite any existing `.local/prd-cycle.json` (previous run's state is stale)

## Phase 1: Catchup

**Skip if:** `"catchup"` in `phases_completed` in state file.

Invoke `/catchup` skill.

After completion, update state: add `"catchup"` to `phases_completed`, set `phase: "planning"`.

## Phase 2: Planning

**Skip if:** `TaskList` returns any pending or completed tasks (tasks already exist).

Invoke `/plan-tasks` with the selected PRD.

After completion, update state: add `"planning"` to `phases_completed`, set `phase: "work"`.

## Phase 3: Work

**Skip if:** All tasks completed, none pending.

Before invoking `/work`, update state with current task counts (query `TaskList`).

Invoke `/work` skill. It runs until all tasks complete.

After completion, update state: add `"work"` to `phases_completed`, set `phase: "review"`, update task counts.

## Phase 4: Review

**Skip if:** Review file exists in `.local/reviews/` for current cycle (check filename pattern `{prd-name}-review-{cycle}.md`).

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
| Same issue reappearing after previous fix | Escalate that specific issue — fix didn't stick |
| A sub-skill errored during this cycle | PAUSE: report error, don't retry automatically |

### Classification (per finding):

**Auto-fix** (proceed without asking):
- Low severity, any consensus
- Medium severity, clear mechanical fix
- Medium severity, 1/3 consensus
- Any severity where fix is additive only (adds code/tests, doesn't modify signatures/types/schemas)

**Escalate** (PAUSE, present to user):
- Critical severity, always
- High + touches public API
- High + data model change
- Requirements ambiguity (PRD says X, code does Y)
- New dependency needed
- Recurring issue (appeared in previous cycle)

Log every decision in state file (`autonomous_decisions` or `deferred_decisions`).

### Outcomes:

- **All auto-fixable, no escalations** → proceed to Phase 6
- **Any escalation needed** → PAUSE. Present escalated issues to user per format in `references/decision-framework.md`. Wait for user decisions. After user responds, update `deferred_decisions` statuses and proceed to Phase 6 with resolved items.
- **No issues found** → proceed to Phase 7

## Phase 6: Rework

Tag follow-up tasks with `[C{cycle}]` prefix to distinguish from original tasks.

Before invoking `/work`, update state with current task counts.

Invoke `/work` on follow-up tasks (auto-fixable ones + user-approved ones only).

Increment cycle counter. Update state: set `phase: "review"`, update task counts. Loop back to Phase 4.

## Phase 7: Completion

1. Update state: set `phase: "done"`
2. Move PRD from `wip/` to `done/` (use `mv`, keep `00XXX-` prefix)
3. Print final summary:

```
── AUTOPILOT ── PRD: {prd-name} ── DONE ── {n} cycles ─────────────

Summary:
- Cycles: {n}
- Autonomous decisions: {count}
- Escalated decisions: {count}
- Follow-up tasks fixed: {count}
```

## Shell Command Rules

- **Never chain commands** with `&&`, `|`, or `;` in a single Bash call. Use separate Bash tool calls instead.
- **Never use redirections** like `2>/dev/null`. Handle missing files by checking existence or catching errors in the tool result.
- Use `Glob` or `Read` instead of `ls` where possible (e.g. to check if files exist or list directory contents).
- Use `mkdir -p` in its own Bash call when creating directories.

## Error Handling

| Situation | Action |
|-----------|--------|
| Sub-skill invocation fails | PAUSE, report which skill failed and error |
| No PRDs anywhere | STOP with message about /save-plan |
| State file corrupted | Delete it, restart from Phase 0 |
| Review produces no parseable output | PAUSE, report — don't retry |
| All three reviewers fail | PAUSE, report — partial results usable if user confirms |
| `.local/` doesn't exist | Create it |
| Task tools unavailable | STOP, report — can't operate without tasks |

## Reference Files

- `references/state-schema.md` — state file JSON schema and skip logic
- `references/decision-framework.md` — auto-fix vs escalate classification rules
- `references/dashboard-format.md` — live dashboard via pidash
