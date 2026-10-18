---
design: skip
---

# Cap Session Tails: 150K Context Pin, Turn Tripwire, 1M Opt-In

## Overview

### Problem Statement

The fat tail of long sessions dominates spend: one 1,361-turn session re-read
685M cache tokens (~7% of the fortnight); the top 5 sessions took ~13% (triage
`dev/local/audit-results/2026-07-14-cost-speed-quality-triage.md`). The
autopilot cap hook uses a single flat `USAGE_CAP = 500_000` (verified
2026-07-18: autopilot_context_cap_hook.py:66; no window arm, no
context_window read), and a `[1m]` default model additionally lets 1M
requests above 200K input bill at a long-context premium. Long histories are
also where context-rot quality incidents live (00054 class). This supersedes
the window-aware cap decision recorded in memory
`feedback_context_cap_for_cost` (that memory described a design, not the
shipped hook).

**History that gates this PRD (added 2026-07-19):** 150K is not a new value.
An earlier 150K cap misfired - the hook's own comment (:63-65) records every
cap fire landing at ~163K inside healthy Opus-1M sessions, "aborting good
plans", and 500K was the deliberate fix, not drift. What changes the calculus
now is the `[1m]` strip in this same PRD: on a 200K window a sub-200K cap is
*necessary* (native auto-compact would otherwise preempt the clean rotation),
and observed 250K-cruising build sessions cannot exist at all. The 150K pin
is therefore only safe as a package with the strip - landing the pin while
the default model still carries `[1m]` re-creates the recorded misfire. The
guard in Phase 2 encodes this.

### Target Users

Headless autopilot sessions (cap + tripwire) and interactive sessions (1M opt-in).

### Success Metrics

- Cap hook forces hand-off at 150K tokens regardless of model window.
- Soft cap stays below the hard cap (120K < 150K): the lossless task-boundary
  handoff path still fires; it is not dead code after the pin.
- No autopilot session exceeds ~300 counted tool calls without a forced phase hand-off.
- Default `settings.json` model string carries no `[1m]` suffix (model id itself unchanged, whatever it is at execution time), and the cap pin lands in the same commit as the strip (or after verified absence) - never before it.

## Functional Decomposition

### Capability: Context cap pin

#### Feature: Pin cap at 150K
- **Description**: `autopilot_context_cap_hook.py`'s existing `USAGE_CAP` constant drops from 500_000 to 150_000; it stays a single flat constant (there is no window arm - verified 2026-07-18).
- **Inputs**: existing hook (`USAGE_CAP` at :66).
- **Outputs**: hook with `USAGE_CAP = 150_000`; breach action byte-identical.
- **Behavior**: Premise, re-checked at execution: read the hook first; the breach action (how it forces the hand-off: rotation envelope, `cap_rotations` entry, task reset to pending, `next_phase = "build"`, oversized-task livelock stall on the second consecutive fire) is reused verbatim, only the constant's value changes. Report the observed breach mechanism in the task summary. Update the constant's comment block: it currently justifies 500K by the 150K misfire; the new comment must state the `[1m]`-strip coupling instead, so the next reader does not "fix" the value back.

#### Feature: Rescale the soft cap with the hard cap
- **Description**: `SOFT_CAP` drops from 320_000 to 120_000. The hook's design invariant is soft-below-hard: crossing the soft cap writes `.handoff-requested` and `/work` hands off losslessly at the next task boundary; only tasks that overrun the hard cap mid-task take the rotation path. Dropping `USAGE_CAP` alone would invert the invariant (320K > 150K), turn the soft path into dead code, and make every cap event a mid-task rotation - fat-but-healthy tasks would start parking to `hold/` via the livelock guard.
- **Inputs**: existing hook (`SOFT_CAP` at :73).
- **Outputs**: hook with `SOFT_CAP = 120_000`; soft-path behavior byte-identical.
- **Behavior**: The 30K gap to the hard cap mirrors the current design intent ("roughly one more build task"); the old 180K gap was sized against a 500K ceiling. Premise, re-checked at execution: confirm the soft-cap marker path (`.handoff-requested`, `_handle_below_cap`) still works as documented before rescaling.

### Capability: Turn tripwire

#### Feature: Count tool calls per session
- **Description**: The cap hook counts its own PostToolUse invocations per session id.
- **Inputs**: hook payload session id; counter persisted in the same state location the hook already uses (fallback: `dev/local/autopilot/state/`).
- **Outputs**: monotonic per-session counter.
- **Behavior**: Counter increments once per invocation; unit is tool calls, not API turns (proxy chosen because the hook sees exactly one event per counted tool call). Counter file removal or corruption resets to 0 and logs; never crashes the hook.

#### Feature: Force hand-off at 300
- **Description**: At counter >= 300, trigger the exact same hand-off pathway as a context-cap breach.
- **Inputs**: counter, existing breach pathway.
- **Outputs**: forced phase hand-off; log line naming the tripwire.
- **Behavior**: Threshold constant 300 in the hook. Fires once per session (breach flag persisted); a relaunched next-phase session starts a fresh counter. Interactive sessions without autopilot state are exempt (hook already scopes to autopilot runs; premise re-check: confirm that scoping exists, else add it so interactive sessions are never blocked).

### Capability: 1M opt-in

#### Feature: Drop [1m] from the default model
- **Description**: strip the `[1m]` suffix from whatever `settings.json` `model` names; the 1M window becomes per-session opt-in via `/model <model>[1m]`.
- **Inputs**: settings.json `model` (as of 2026-07-14: `opus[1m]`; it was `claude-fable-5[1m]` when this PRD was written - the operator switched mid-flight, which is exactly why the rule below keys on the suffix, not the model name).
- **Outputs**: same model id with the `[1m]` suffix removed; one line documenting the opt-in added to AGENTS.md Toolchain.
- **Behavior**: The model NAME is not this PRD's business - only the suffix is. Premise, re-checked at execution: the current value ends with `[1m]`; if it does not, the opt-in already holds - skip and report. Never rewrite the model id itself, whatever it happens to be.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/run-autopilot/scripts/
├── autopilot_context_cap_hook.py       # Maps to: Context cap pin, Turn tripwire
└── test_autopilot_context_cap_hook.py  # Maps to: regression + tripwire tests (existing file, lives beside the hook)
~/.claude/settings.json             # Maps to: 1M opt-in
~/.claude/AGENTS.md                 # Maps to: 1M opt-in (one doc line)
```

### Module: cap-hook
- **Maps to capability**: Context cap pin, Turn tripwire
- **Responsibility**: One PostToolUse guard that ends sessions before the tail gets expensive.
- **Exports**: `run(payload)`-compatible hook (aligns with PRD 00071 handler interface if that landed; standalone otherwise), `USAGE_CAP = 150_000` and `SOFT_CAP = 120_000` (existing constants, new values), `TURN_TRIPWIRE = 300`.
- **Mirror**: `tracon/model.py` `USAGE_CAP` is a manual mirror (ctx gauge denominator); change it in the same commit or the dashboard gauge lies.

### Module: settings-optin
- **Maps to capability**: 1M opt-in
- **Responsibility**: Default model string and its documentation.
- **Exports**: updated `model` value, AGENTS.md line.

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **cap-hook (read + tests)**: locate breach pathway, write failing tests for new behavior.

### Core Layer (Phase 1)
- **cap-hook (implementation)**: Depends on [cap-hook read + tests].

### Integration Layer (Phase 2)
- **settings-optin**: Depends on [cap-hook implementation] only for single-commit ordering.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Current behavior understood and pinned by tests before changing it.

**Tasks**:
- [ ] Read the cap hook; document its breach pathway and state storage in the task log (no deps) - Acceptance: summary names the mechanism (message/state fields/marker) with line references.
- [ ] Write regression tests for the NEW contract and watch them fail against the old code: cap fires above 150K regardless of model string (fails against the current 500_000 value); soft handoff marker written between 120K and 150K and rotation NOT taken there (fails against the current 320_000 value); tripwire fires at 300 and not at 299; interactive (non-autopilot) payloads untouched (scoping already exists - verified 2026-07-18: hook no-ops without an autopilot state dir and outside build phase) (no deps) - Acceptance: tests exist, run, and fail for the expected reasons (failure output captured).

**Exit Criteria**: Breach pathway documented; new-contract tests failing against old code.

### Phase 1: Core
**Goal**: Pinned cap and tripwire live.

**Tasks**:
- [ ] Set `USAGE_CAP = 150_000` and `SOFT_CAP = 120_000` (both stay single flat constants; nothing to remove), update the constants' comment blocks per the pin feature, and mirror `USAGE_CAP` in `tracon/model.py` (depends on: Phase 0) - Acceptance: Phase 0 cap + soft-cap tests green; tracon test suite green.
- [ ] Add per-session counter + TURN_TRIPWIRE=300 reusing the breach pathway, fire-once flag, corrupt-counter reset (depends on: Phase 0) - Acceptance: tripwire tests green, full existing hook test suite green, no skips (report counts).

**Exit Criteria**: Phase 0 tests all green against the new code.

### Phase 2: Integration
**Goal**: 1M is opt-in; everything committed.

**Tasks**:
- [ ] Premise re-check then strip the `[1m]` suffix from settings.json `model` (keep the model id itself untouched) and add the AGENTS.md opt-in line (depends on: Phase 1) - Acceptance: `python3 -c "import json;print(json.load(open('/Users/bob/.claude/settings.json'))['model'])"` prints the same model id without `[1m]`, or the skip is reported with the observed value.
- [ ] **Coupling guard**: if the strip cannot land (settings.json unwritable, or the operator has deliberately kept `[1m]` - detectable by the suffix reappearing after an earlier strip), do NOT commit the cap pin; revert the constants, set the stall, and park this PRD to `hold/` with the reason. A 150K pin on a 1M-window default re-creates the recorded ~163K misfire (depends on: Phase 1) - Acceptance: either both changes are staged together, or the PRD is parked and nothing landed.
- [ ] Commit hook, tests, tracon model.py mirror, settings.json, AGENTS.md to the buvis bare repo in ONE commit by absolute pathspec, never `-a` (no CHANGELOG, dotfiles exemption) (depends on: all) - Acceptance: `git --git-dir=$HOME/.buvis --work-tree=$HOME log -1 --stat` lists the cap constants and the settings.json strip in the same commit.

**Exit Criteria**: Tests prove 150K pin + 300-call tripwire; default model has no `[1m]`.

## Test Strategy

### Critical Scenarios
- **Happy path**: autopilot session crosses 150K tokens → Expected: same hand-off behavior the hook produced before, at the lower threshold.
- **Soft path**: session crosses 120K but not 150K → Expected: `.handoff-requested` written, no rotation, `/work` hands off at the next task commit.
- **Edge case**: session at 299 calls and under 150K → Expected: no trigger; at 300 → trigger exactly once, flag persists across subsequent calls.
- **Error case**: counter file corrupted mid-session → Expected: reset to 0, logged, hook exits 0.

## Risks

- **150K has a recorded failure mode**: every fire at ~163K on 1M-window sessions, aborting good plans (hook comment :63-65). Mitigated only by the `[1m]` strip landing in the same commit (Phase 2 coupling guard). Watch `cap_rotations` frequency and `hold/` parks in the first post-landing batch; rollback is restoring both constants (500K/320K) and the tracon mirror.
- **More hand-offs mean more boot prefixes paid**: acceptable by design; PRD 00072 shrinks the prefix first. Sequence 00072 before 00073 in the backlog.
- **Tripwire fires mid-critical-step**: it reuses the phase hand-off pathway, which by autopilot design lands at a resumable state.json boundary; the review loop catches truncated work.
- **Tool-call count is a proxy for turns**: threshold 300 is deliberately above the observed healthy-session norm and only bounds the tail; tune later with tracon data (PRD 00079 territory).
- **Oversized tasks park to hold/ more often at 150K**: the livelock guard (two consecutive rotations on one task) is the intended pressure valve; a spike in parks is the signal the cap is too tight for real working sets, not a reason to bypass the guard.
