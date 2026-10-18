---
catchup: run
design: skip
---

# Extract Autopilot Lifecycle Core

> Split out of PRD 00051 on 2026-07-29 (operator decision at 00051's design gate).
> Shared design doc: `dev/local/designs/00051-autopilot-state-machine-core-v1-design.md`
> — this PRD owns the sections that doc marks as deferred. `design: skip` because
> that doc already covers this scope through three reviewer dispatches; do not
> re-run `/design-solution`.
>
> **Premise: 00051 must have landed.** This PRD builds on `cli/state.transaction`,
> `cli/schema.py` and the package's import bootstrap. Verify `cli/state.py` exposes
> `transaction` before starting; if it does not, stall — do not rebuild the boundary.

## Overview

### Problem Statement

PRD 00051 moved the autopilot's *recovery procedures* (park, stall, per-PRD reset)
out of SKILL.md prose and into a locked, validated Python boundary. It deliberately
left the *lifecycle* half in prose: PRD selection, frontmatter parse, phase
transitions, and resume mapping are still English executed by an LLM each session,
and `statectl.py` is still a second writer of `state.json` — locked and atomic, but
schema-unvalidated, so a malformed field value reaches disk unchallenged.

That leaves 00051's headline metric unmet ("every `state.json` write passes through
one schema-validated boundary") and leaves four deterministic decisions being
re-derived by a model every session, which is what drift is made of.

### Target Users

The autopilot loop wrapper, interactive `/run-autopilot` sessions, and PRD 00106
(the orchestrator cutover, ex-00052), which needs these as importable pure
functions when the loop moves to Python.

### Success Metrics

- **Every `state.json` write passes through one schema-validated boundary.**
  `statectl.py` is a re-export shim over `cli/state.py`; no code path writes
  `state.json` outside it. The documented human forensic hand-edit remains, guarded
  by the PostToolUse schema check.
- **Selection, frontmatter parse, phase transitions and resume mapping are pure,
  tested functions** — no prose path re-derives them.
- **A phase transition owns every field effect it mandates.** `phase-done --outcome`
  applies the next phase plus the transition's declared effects in one commit; no
  caller supplies a phase pair or an optional flag for a mandatory effect.
- **The 100+ existing `statectl.py` call sites and the three existing test suites
  (`test_statectl.py`, `test_autopilot_resume.py`, `test_golden_contracts.py`) pass
  UNMODIFIED.** That is the regression gate on the shims. Note
  `test_statectl.py::test_del_removes_field` deletes `phase` and expects exit 0, so
  schema fields must validate as "if present, must match" — never as required.
- ~~**[F5] A loop PRD over the task ceiling stalls instead of starting.**~~
  **STRUCK 2026-08-07: already shipped.** Lifted out of this PRD by hand on
  2026-08-02 (commit `93db0f0b`: `cli/policy.py`, `cli/test_policy.py`, the
  `check-plan` subcommand, `plan-tasks` step 5.5, `recovery.md`'s
  `oversized_plan` stall row). Verified present at HEAD. Do not rebuild it.

## Functional Decomposition

### Capability: PRD lifecycle logic

The deterministic decisions that move a batch through PRDs and phases, as pure
functions over data.

#### Feature: PRD selection
- **Description**: Pick the next PRD.
- **Inputs**: `wip/` and `backlog/` listings.
- **Outputs**: The chosen basename, or drained.
- **Behavior**: `wip/` first, then `backlog/`, lowest `00XXX-` sequence in each. `hold/` is never scanned — that IS the parked/deferred exclusion.

#### Feature: Frontmatter parse
- **Description**: Parse a PRD's frontmatter and apply the Phase-0 defaults.
- **Inputs**: PRD file text.
- **Outputs**: The recognized fields with effective values.
- **Behavior**: Stdlib only (no PyYAML). Invalid values fall back to the default with one warning; unknown keys ignored; a malformed block yields all defaults.

#### Feature: Phase transitions
- **Description**: The table mapping (phase, outcome) to the next phase AND its full field effects.
- **Inputs**: Current state, an outcome.
- **Outputs**: A committed state advance.
- **Behavior**: Convergence appends `"review"` because it is convergence, not because a flag was passed; review→review increments `cycle` and clears `rework_task_ids` in the same commit; `more_prds` applies the per-PRD reset; `drained` writes the empty `next_phase`. Unknown pairs raise.

#### Feature: Resume mapping
- **Description**: Map a parked state to its re-entry action.
- **Inputs**: Current state.
- **Outputs**: The re-entry description, or a version signal.
- **Behavior**: Absorbs `resume_target.py` verbatim (its string-returning contract is test-bound); surfaces an old/future schema rather than resuming blindly.

### Capability: Single validated writer

#### Feature: statectl absorption
- **Description**: `statectl.py` becomes a thin shim over the 00051 boundary.
- **Inputs**: Its existing CLI and Python surface.
- **Outputs**: Identical behavior on the success path, plus a loud reject when a mutation's own field value is malformed.
- **Behavior**: Re-exports `read_and_parse`, `atomic_write`, `mutate`, `parse_path`, `get_value`, `StateError`, `UsageError` behind a `sys.path` bootstrap; exit codes 0/1/2 unchanged; `del` of a required field still allowed.

### ~~Capability: Plan-size policy~~ — STRUCK, shipped in `93db0f0b`

`[F5]` and its whole capability left this PRD on 2026-08-02. `cli/policy.py`,
`cli/test_policy.py` and the `check-plan` subcommand are at HEAD.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/run-autopilot/cli/     # extends 00051's package
├── selection.py           # PRD selection
├── frontmatter.py         # frontmatter parse + Phase-0 defaults
├── transitions.py         # TRANSITIONS table + next_phase
├── resume.py              # resume_target + park_decision (absorbed)
├── policy.py              # SHIPPED 93db0f0b - do not rebuild
└── test_*.py
```

Edits: `scripts/statectl.py` and `scripts/resume_target.py` become shims;
`__main__.py` gains `select | frontmatter | phase-done | resume-target`
(`check-plan` already shipped);
SKILL.md / `references/*` drop the prose these replace.

## Implementation Phases

### Phase 0: Pure functions
**Goal**: Port the four deterministic decisions with tests, importing nothing new.

**Tasks**:
- [ ] Verify the 00051 premise and implement `selection.py` - Acceptance: `cli/state.transaction` exists; selection picks lowest-sequence wip-then-backlog and never scans `hold/`.
- [ ] Implement `frontmatter.py` - Acceptance: every Phase-0 field parses with its default; each invalid value falls back with a warning; `golden/prd-frontmatter.md` parses clean.
- [ ] Implement `transitions.py` - Acceptance: every row asserts its FULL effect set, not just the phase; unknown pairs raise.
- [ ] Implement `resume.py` absorbing `resume_target` + `park_decision` - Acceptance: the three `golden/state-*.json` fixtures resolve their documented targets.
- [x] ~~Implement `policy.py` [F5]~~ - **SHIPPED 2026-08-02 in `93db0f0b`.**

**Exit Criteria**: Four new pure modules (plus the shipped `policy.py`), each
tested, none touching disk.

### Phase 1: Cutover
**Goal**: One validated writer, subcommands exposed, prose retired.

**Tasks**:
- [ ] Add the `select | frontmatter | phase-done | resume-target` subcommands (`check-plan` already shipped) - Acceptance: `phase-done --outcome` computes and applies the transition and its effects in one commit; subprocess-tested from four cwds.
- [ ] Convert `statectl.py` and `resume_target.py` to shims - Acceptance: the three existing suites pass UNMODIFIED; a shim test pins every re-exported symbol.
- [ ] Rewire the remaining prose to the subcommands and update the migration map - Acceptance: no prose path derives a transition, a selection, or a frontmatter default; manifest set-equality holds.

**Exit Criteria**: Metric 1 is literally true; the pure functions are import-clean for PRD 00106 (ex-00052).

## Test Strategy

### Critical Scenarios
- **Happy path**: `autopilot phase-done --outcome converged` → `phase: done`, `next_phase: done`, `"review"` appended, one commit.
- **Edge case**: a frontmatter block with every field invalid → every default applied, one warning, Phase 0 does not crash.
- **Error case**: a `statectl set` with a malformed value for the field it targets → rejected loudly, file byte-unchanged, while an unrelated pre-existing odd field blocks nothing.

## Risks

- **Shim compatibility is the whole risk.** ~100 shell call sites and two different
  Python import styles. Mitigation: the three existing suites must pass unmodified,
  and the shims are cut over in their own commit with no batch running.
- **Doc-contract tests**: retiring prose retires its test only WITH a named
  replacement recorded in the migration map.
- ~~**[F5] the ceiling is a heuristic on two data points**~~ — struck with F5.
