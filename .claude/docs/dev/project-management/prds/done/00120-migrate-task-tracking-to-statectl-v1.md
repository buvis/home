# Migrate Task Tracking to Statectl

## Overview

### Problem Statement

Claude Code v2.1.233 removes the harness task tools (TaskCreate/TaskGet/TaskUpdate/TaskList, TodoWrite) on Opus 4.8, Sonnet 5, Fable 5, Mythos 5 and newer: those models track multi-step work internally, and the tool definitions plus reminders cost context. The autopilot skill chain (plan-tasks, work, review-work-completion, run-autopilot) still leans on these tools as its in-session task store, kept alive only by `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` in `~/.claude/settings.json` env. Everything durable already lives in `dev/local/autopilot/state.json` (written solely by statectl; read by tracon, `cli/loop.py`, the context-cap hook), but `state.tasks` round-trips only id/name/status/metadata. Full task bodies (description, acceptance criteria) and dependency links (blocked-by) exist only in per-session tool storage, so the hydration sub-step rebuilds them name-only and blocker-less after every handoff or rotation - a standing lossy spot plus measured per-session overhead (10 TaskCreate + ~7 TaskUpdate calls per build session, 2026-08-02 engram analysis).

### Target Users

The unattended autopilot pipeline and its operator. Fixing this removes a permanent dependency on an upstream escape hatch, the per-session hydration tax on every loop session, and the silent body/blocker loss across session boundaries.

### Success Metrics

- Zero task-tool references in the instruction text of the four skills and their references (`rg -c` sweep = 0 outside explicitly-retired historical notes).
- Zero hydration turns per session (section deleted; was 2 batched turns covering ~17 calls per build session).
- Task bodies and blockers survive a session boundary: statectl round-trip fixture test passes (write via verbs, re-read, derive `/work` dispatch placeholders).
- `CLAUDE_CODE_ENABLE_TODO_TOOLS` absent from `settings.json`; the next full PRD run on Fable 5 completes plan-build-review-done without it.

## Functional Decomposition

### Capability: Durable Task State

state.json becomes the single, complete task store; nothing about a task lives only in session memory.

#### Feature: Task body and blocker fields

- **Description**: Extend `state.tasks[]` with `description` (string, optional: the full task body plan-tasks authors today - the text previously passed to TaskCreate, including contract and acceptance-criteria sections) and `blocked_by` (int[], optional: ids of tasks that must complete first, replacing `TaskUpdate.addBlockedBy`).
- **Inputs**: Task content from plan-tasks step 4.7; split subtasks from work's task-splitting path.
- **Outputs**: `state.tasks[]` entries carrying id, name, status, description, blocked_by, model/metadata mirrors, attempts.
- **Behavior**: Readers treat an absent `description` as a name-only body and absent `blocked_by` as no blockers - exactly today's post-hydration behavior, so legacy state files (and state written mid-migration by old writers) keep working. `cli/schema.py` validates both fields as optional; `references/state-schema.md` task rows (currently `:167`-`:174`) are rewritten to drop "from TaskList" / "via TaskCreate(metadata)" framing and document state.json as canonical.

#### Feature: Statectl task verbs

- **Description**: Statectl grows the write operations the skill chain needs once the harness tools are gone; it remains the sole writer of state.json.
- **Inputs**: Task payloads (name, description, metadata, blockers), task ids, status values, body/metadata patches.
- **Outputs**: Atomic, locked state.json writes with `tasks_total`/`tasks_completed` recomputed in the same transaction (existing `_recount_completed` path).
- **Behavior**: Needed operations - add a task (planning, splitting, review follow-ups), set body (work's repair path), set metadata (tier escalation), set status (reopen, reset-to-pending, mark-deleted), clear all tasks (phase-done / recovery sweeps). Provisional verb names `task-add`, `task-set-body`, `task-set-meta`, `task-set-status`, `tasks-clear`; final CLI shapes are fixed by this PRD's Phase 1.5 design doc. Existing `task-start` / `task-done` verbs are untouched. A verb targeting an unknown task id exits non-zero and leaves state unchanged.

### Capability: Skill-Chain Cutover

Every task-tool instruction in the four skills becomes a state.json read or a statectl write.

#### Feature: Planning writes state directly

- **Description**: plan-tasks persists tasks through statectl instead of TaskCreate/TaskUpdate.
- **Inputs**: Planned tasks with bodies, tier metadata (model, estimated_tokens, est_context_peak, qwen_eligible, qwen_excluded_reason), dependency edges.
- **Outputs**: A complete `state.tasks` snapshot; no separate Phase 3 mirror step needed for content the writer already persisted.
- **Behavior**: Replaces task creation (step 4, currently `:69`), metadata carriage (`:162`/`:316`), addBlockedBy linking (`:332`), and the `taskcreate_failed` rollback (`:138`/`:222`, which becomes statectl-transaction cleanup). The `Harness tools` dependency line (`SKILL.md:13`) is dropped.

#### Feature: Execution reads and writes state only

- **Description**: work claims, reads, repairs, escalates, splits, and completes tasks against state.json.
- **Inputs**: `state.tasks` (pending scan honoring `blocked_by`, rework ids from `state.rework_task_ids`), attempt records.
- **Outputs**: Lifecycle via existing `task-start`/`task-done`; body repairs via `task-set-body`; tier escalation via `task-set-meta`; splits via `task-add` + `blocked_by`.
- **Behavior**: Collapses the paired TaskUpdate+statectl lifecycle (steps a/i, claim `:186`/`:196`, completion `:652`, reopen `:710`) to statectl-only; dispatch placeholders `{{task_subject}}`/`{{task_description}}`/`{{task_acceptance_criteria}}` (`:604`, `references/self-deslop-prompt.md`) derive from `tasks[].description` the same way they derive from TaskGet today; TaskList pending scan (`:159`) and rework TaskGet (`:172`) become state reads; `references/task-splitting.md` updated.

#### Feature: Review and orchestration read state

- **Description**: review-work-completion and run-autopilot key every task check on `state.tasks`; the hydration sub-step is deleted.
- **Inputs**: `state.tasks` snapshot; review follow-up definitions.
- **Outputs**: Same gate semantics (any `in_progress` task still STOPs review); follow-ups appended via `task-add`; phase-done and recovery sweeps become `tasks-clear`.
- **Behavior**: Premise: the hydration sub-step (`run-autopilot/SKILL.md` § "Hydrate TaskList from state.tasks", currently `:121`-`:136`) exists solely to rebuild the per-session tool store, and phase-review's "Hydrate before any TaskUpdate" rules (`phase-review.md:218`-`:220`) exist solely to guard it; re-check both claims by rg before deleting - a surviving consumer means stop and report, not force. Planning-skip checks (`phase-build.md:171`-`:173`, `state-schema.md:422` row) test `state.tasks` non-empty instead of TaskList. review-work-completion's empty-task fallback (step 2, `:97`) degrades to proceeding without task context when `state.tasks` is empty. Also fixes the stale `phase-review.md:239` claim that a PostToolUse status-sync hook treats TaskUpdate as ground truth - that hook was retired by PRD 00063 and the line misleads today; Phase 6 escalation writes (`:236`/`:253`) go through `task-set-meta`/`task-add`.

### Capability: Flag Retirement

#### Feature: Remove the compatibility env var

- **Description**: Delete `CLAUDE_CODE_ENABLE_TODO_TOOLS` from `settings.json` env once nothing needs the tools.
- **Inputs**: The completed cutover.
- **Outputs**: settings.json without the flag; sessions no longer carry task-tool definitions or reminders.
- **Behavior**: Premise: after the cutover, no skill, hook, or agent on this machine instructs task-tool use; re-check with an rg sweep over `~/.claude/skills/`, `~/.claude/hooks/`, and `~/.claude/agents/` immediately before removal - any hit outside explicitly-retired historical notes means skip and report. Ordered last.

## Structural Decomposition

### Repository Structure

```
~/.claude/
├── settings.json                        # Maps to: Flag Retirement
└── skills/
    ├── run-autopilot/
    │   ├── SKILL.md                     # Maps to: Review and orchestration read state (hydration removal)
    │   ├── cli/schema.py                # Maps to: Task body and blocker fields (validation)
    │   ├── scripts/statectl.py          # Maps to: Statectl task verbs (shim; core in cli/ state transaction)
    │   └── references/
    │       ├── state-schema.md          # Maps to: Task body and blocker fields (docs)
    │       ├── phase-build.md           # Maps to: Review and orchestration read state (skip rule)
    │       ├── phase-review.md          # Maps to: Review and orchestration read state (escalation, stale hook line)
    │       ├── phase-done.md            # Maps to: Review and orchestration read state (sweep -> clear)
    │       └── recovery.md              # Maps to: Review and orchestration read state (sweep -> clear)
    ├── plan-tasks/SKILL.md              # Maps to: Planning writes state directly
    ├── work/
    │   ├── SKILL.md                     # Maps to: Execution reads and writes state only
    │   └── references/                  # task-splitting.md, self-deslop-prompt.md placeholder sourcing
    └── review-work-completion/SKILL.md  # Maps to: Review and orchestration read state (gates, follow-ups)
```

### Module: state-core

- **Maps to capability**: Durable Task State
- **Responsibility**: Schema, validation, statectl verbs, and state-schema.md documentation for the complete task record.
- **Exports**:
  - `tasks[].description`, `tasks[].blocked_by` - optional schema fields, legacy-tolerant
  - `task-add`, `task-set-body`, `task-set-meta`, `task-set-status`, `tasks-clear` - statectl verbs (final shapes per design doc)

### Module: planning-cutover

- **Maps to capability**: Skill-Chain Cutover
- **Responsibility**: plan-tasks persists tasks exclusively through statectl.
- **Exports**: Rewritten plan-tasks step 4 / 4.7 instruction text; statectl-based rollback path.

### Module: execution-cutover

- **Maps to capability**: Skill-Chain Cutover
- **Responsibility**: work's claim/read/repair/escalate/split/complete flow against state.json.
- **Exports**: Rewritten work SKILL.md lifecycle text; state-sourced dispatch placeholders; updated task-splitting.md.

### Module: review-orchestration-cutover

- **Maps to capability**: Skill-Chain Cutover
- **Responsibility**: review gates, follow-up creation, hydration removal, sweep-to-clear conversion, stale-hook-line fix.
- **Exports**: Rewritten review-work-completion step 2 / follow-up text; run-autopilot SKILL.md and phase references without hydration.

### Module: flag-retirement

- **Maps to capability**: Flag Retirement
- **Responsibility**: settings.json env cleanup and the final no-references sweep.
- **Exports**: settings.json without `CLAUDE_CODE_ENABLE_TODO_TOOLS`; plan-tasks without the harness-tools dependency line.

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first.

- **state-core**: Complete durable task record and the verbs to write it.

### Core Layer (Phase 1)

- **planning-cutover**: Depends on [state-core]
- **execution-cutover**: Depends on [state-core]

### Integration Layer (Phase 2)

- **review-orchestration-cutover**: Depends on [planning-cutover, execution-cutover]
- **flag-retirement**: Depends on [review-orchestration-cutover]

## Implementation Phases

### Phase 0: Foundation

**Goal**: State.json can hold everything the tool store holds today, with verbs to write it.

**Tasks**:

- [ ] Add `description` and `blocked_by` to the task schema (no deps) - Acceptance: `cli/schema.py` accepts states with and without both fields; pytest covers both directions; `state-schema.md` task rows rewritten with state.json as canonical.
- [ ] Add statectl task verbs (no deps) - Acceptance: each verb has a pytest against a fixture state file; counts recomputed atomically in the same write; unknown-id calls exit non-zero leaving state byte-identical; `task-start`/`task-done` behavior unchanged; round-trip test derives the three `/work` placeholders from a written task.

**Exit Criteria**: Fixture round-trip test green; legacy fixture (body-less, blocker-less) still validates and runs.

### Phase 1: Core

**Goal**: The two writer skills operate on state.json alone.

**Tasks**:

- [ ] Rewrite plan-tasks persistence onto statectl (depends on: Phase 0) - Acceptance: `rg "TaskCreate|TaskUpdate|TaskList|TaskGet|TodoWrite" skills/plan-tasks/` = 0 hits; instruction text covers bodies, metadata, blockers, and rollback via statectl.
- [ ] Rewrite work onto state reads and statectl writes (depends on: Phase 0) - Acceptance: same rg sweep over `skills/work/`, excluding `skills/work/scripts/check_build_overhead.py` and its test, = 0 hits; pending scan text honors `blocked_by`; placeholders sourced from `tasks[].description` with the documented name-only fallback when absent.

**Exit Criteria**: Both skills' texts reference only state.json and statectl for task tracking.

### Phase 2: Integration

**Goal**: Orchestration and review follow, hydration dies, the flag goes.

**Tasks**:

- [ ] Cut review-work-completion over to state (depends on: Phase 1) - Acceptance: rg sweep over the skill = 0 hits; in-progress STOP gate and empty-tasks fallback text read `state.tasks`; follow-up creation uses `task-add`.
- [ ] Delete hydration and convert run-autopilot task plumbing (depends on: Phase 1) - Acceptance: hydration section and phase-review hydrate-before rules gone (premise re-checked first); skip rules and sweeps reference state.tasks / `tasks-clear`; `phase-review.md` stale hook claim replaced with the statectl write path; rg sweep over `skills/run-autopilot/` finds task-tool names only in notes explicitly marked retired/historical.
- [ ] Remove the env flag and the plan-tasks dependency line (depends on: previous two) - Acceptance: premise sweep over skills/hooks/agents = 0 instruction hits, then `settings.json` no longer contains `CLAUDE_CODE_ENABLE_TODO_TOOLS` and `plan-tasks/SKILL.md` no longer lists harness task tools.

**Exit Criteria**: Success-metric sweeps all pass; next PRD run needs no task tools.

## Test Strategy

### Critical Scenarios

- **Happy path**: statectl writes a task with body, metadata, blockers; re-read derives id, status, placeholders → Expected: round-trip fixture test green, counts correct.
- **Edge case**: legacy state.json without `description`/`blocked_by` (or written mid-migration by old writers) → Expected: validates, readers fall back to name-only body and no blockers - today's post-hydration behavior, no crash.
- **Edge case**: simulated rotation - fresh read of a mid-build state file → Expected: full task body recoverable from state.json alone (the previously lossy spot).
- **Error case**: verb on unknown task id → Expected: non-zero exit, state file byte-identical.

## Risks

- **Self-hosting**: this PRD edits the pipeline executing it; later phases of its own run load edited skill text against state written by old writers. Mitigation: both new fields optional with defined fallbacks, flag removal ordered last, one commit per task.
- **PRD 00025-era invariants keyed on TaskList** (hydration-before-TaskUpdate, id-alignment-by-creation-order): Mitigation: the premise re-check before deletion plus the review lenses; id alignment becomes moot once ids are written, not inferred from creation order.
- **`cli/schema.py` strictness breaking legacy state files**: Mitigation: both fields optional; fixture tests in both directions are Phase 0 acceptance.
- **Statectl verb surface grows beyond need**: Mitigation: Phase 1.5 design doc fixes the final shapes; anything a skill never calls gets cut there.
