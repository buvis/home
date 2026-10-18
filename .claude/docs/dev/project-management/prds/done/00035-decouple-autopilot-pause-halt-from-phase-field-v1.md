# Decouple The Autopilot Pause-Halt From The `phase` Field

> Source: 2026-06-23 halt-surface audit (#6). Makes a PAUSE halt the loop even if the model forgets to write `phase="paused"`.
> Target: `run-autopilot` `SKILL.md` (PAUSE rows + Phase 9 reset), `scripts/autopilot_stop_hook.py` (`_compute_signal`), `references/state-schema.md`.
> **Priority: MEDIUM** - the thrash breaker bounds this today (3 wasted cycles, then halt); this makes it a clean immediate halt.

## Overview

### Problem Statement
Every turn-ending PAUSE in loop mode converges on the model writing `phase="paused"`/`next_phase="paused"` (`SKILL.md:780`), and `_compute_signal` halts ONLY on `phase=="paused"` (`autopilot_stop_hook.py:465`). If the model ends a PAUSE turn but FORGETS to set `phase` (leaving a non-empty `next_phase`), the hook writes `next` and the loop RELAUNCHES the failed phase, re-failing until the thrash breaker catches it 3 cycles later. Of all pause sites, only the cap-pause has a durable marker (`cap_pause_reason`, `recovery.md:118`); the sub-skill-fail and reviewer-fail PAUSE sites have NO durable field — they depend entirely on the model remembering `phase`.

A naive hook-only fix (halt on mere `cap_pause_reason` presence) is UNSAFE: "abandon" deliberately leaves `cap_pause_reason` set (`recovery.md:145`), and it is NOT in Phase 9's reset list, so a crash could carry it stale into a later PRD and wrongly halt it. The robust fix gives every pause a durable marker AND clears it on PRD advance.

### Target Users
The operator who must get a clean, immediate pause-halt (not 3 wasted retry cycles) whenever a phase legitimately pauses.

### Success Metrics
- A durable `pause_reason` field is written by EVERY turn-ending PAUSE row (alongside `phase="paused"`).
- `_compute_signal` returns None (halt) when any durable pause marker is set, AND NOT when an auto-recover stall is active (`escalation_exhausted`/`oversized_task` advance, `recovery.md:84,108,114`; `subagent_prompt_overrun` → `task_aborted`).
- Phase 9 PRD-reset clears `pause_reason` AND `cap_pause_reason`, so no pause marker survives into the next PRD.

### Non-Goals
- Removing `phase="paused"` (kept as the primary signal; `pause_reason` is the belt-and-suspenders that survives the model forgetting).
- Changing what any pause MEANS or its resume handler.

## Functional Decomposition

### Capability: Durable pause marker
#### Feature: `pause_reason` on every PAUSE row
- **Description**: each turn-ending PAUSE writes `state.pause_reason = {site, detail}`.
- **Inputs**: the pause site (sub-skill fail, reviewer fail, plan-tasks fail, batch-end "No", mv-verify, replan-exhausted).
- **Outputs**: `pause_reason` in state.json, alongside `phase="paused"`.
- **Behavior**: mirrors `cap_pause_reason` but for all non-cap pauses.

#### Feature: Stale-safe halt predicate
- **Description**: `_compute_signal` halts on any durable pause marker, excluding auto-recover stalls.
- **Inputs**: `phase`, `pause_reason`, `cap_pause_reason`, `stall_reason.stalled`.
- **Outputs**: None (halt) or the normal signal.
- **Behavior**: `if (phase=="paused" or pause_reason or cap_pause_reason) and stalled not in {escalation_exhausted, oversized_task, subagent_prompt_overrun}: return None` — evaluated before the `next`/`done` logic (and `subagent_prompt_overrun` still maps to `task_aborted` as today).

#### Feature: Phase 9 clears the marker
- **Description**: PRD advance resets pause markers.
- **Inputs**: the Phase 9 step-10 reset list.
- **Outputs**: `pause_reason` and `cap_pause_reason` removed.
- **Behavior**: prevents cross-PRD staleness — the footgun that blocks the naive hook-only fix.

## Structural Decomposition

### Files
```
~/.claude/skills/run-autopilot/SKILL.md                         # PAUSE rows write pause_reason; Phase 9 clears it
~/.claude/skills/run-autopilot/scripts/autopilot_stop_hook.py   # _compute_signal predicate
~/.claude/skills/run-autopilot/references/state-schema.md       # document pause_reason
```

## Dependency Graph

### Foundation Layer (Phase 0)
- **pause_reason written + cleared**: SKILL.md PAUSE rows + Phase 9 reset. No deps.

### Core Layer (Phase 1)
- **hook predicate**: depends on [Phase 0] — the field must be WRITTEN by pauses AND CLEARED on advance before the hook keys on it, else a stale marker halts the next PRD.

## Implementation Phases

### Phase 0: Marker write + clear
**Goal**: every PAUSE writes `pause_reason`; Phase 9 clears it.
**Tasks**:
- [ ] Add `pause_reason: {site, detail}` to every turn-ending PAUSE row in `SKILL.md` (sub-skill fail `:181`/`:771`, reviewer fail `:774-775`, plan-tasks `:218`, mv-verify, batch-end "No" `:630`, replan-exhausted), add `pause_reason` + `cap_pause_reason` to the Phase 9 step-10 reset list, and document `pause_reason` in `state-schema.md` (no deps) — Acceptance: each enumerated PAUSE row sets the field; Phase 9 clears both markers; the schema documents it.
**Exit Criteria**: no PAUSE relies on `phase` alone; no marker survives PRD advance.

### Phase 1: Hook predicate
**Goal**: the hook halts on the durable marker, stale-safe.
**Tasks**:
- [ ] In `_compute_signal`, return None when `phase=="paused"` OR `pause_reason` OR `cap_pause_reason` is set, UNLESS `stall_reason.stalled` ∈ {`escalation_exhausted`, `oversized_task`, `subagent_prompt_overrun`} (those advance/abort) (depends on: Phase 0) — Acceptance: unit tests — `pause_reason` set + `phase` unset → None; `cap_pause_reason` set → None; `escalation_exhausted` with no pause marker → the recover signal not a halt; `subagent_prompt_overrun` → `task_aborted`; a normal non-empty `next_phase` → `next`.
**Exit Criteria**: a PAUSE halts immediately even if `phase` is unset; every auto-recover path is unaffected.

## Test Strategy
- **Forgot-phase pause**: `pause_reason` set, `phase` unset, `next_phase` non-empty → None (no relaunch).
- **Cap-pause + abandon**: `cap_pause_reason` set, `phase="paused"` → None (as today).
- **Auto-recover not halted**: `escalation_exhausted`/`oversized_task` (clear stall, set `next_phase=build`, no pause marker) → `next`; `subagent_prompt_overrun` → `task_aborted`.
- **No cross-PRD stale halt**: after a Phase 9 reset, no pause marker remains → the next PRD's first hand-off signals normally.

## Risks
- **Ordering**: if the hook keys on `pause_reason` before Phase 9 reliably clears it, a stale marker halts the next PRD. Mitigation: Phase 0 (write+clear) lands before Phase 1 (hook), enforced by the dependency.
- **Missed PAUSE row**: a pause site not updated still relies on `phase`. Mitigation: enumerate all rows from the audit (section A.1) in Phase 0; the thrash breaker remains the backstop for any miss.
- **Over-broad halt**: keying on `cap_pause_reason` presence could halt a session that should advance. Mitigation: the auto-recover exclusion set; and Phase 9 clearing guarantees the marker is only present during a genuine, unresolved pause.
