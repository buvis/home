---
catchup: skip
design: run
---

# Restructure Run-Autopilot Skill for Per-Gate Loading

## Overview

### Problem Statement

`~/.claude/skills/run-autopilot/SKILL.md` is 853 lines (~38K tokens by harness count) as of the 2026-07-07 audit; PRDs 00014-00016 (earlier by sequence) delete the signal/Stop-hook prose, Phases 7/8, and the coverage-block prose before this PRD runs, so re-measure at execution - the file stays several hundred lines. Every autopilot session loads it in full (2+ sessions per PRD post-00015, 5+ before), so a single PRD still pays multiple full re-reads of orchestration prose, most of it for phases that session never runs. The file also repeats itself: four near-identical session-handoff blocks, two "Frontmatter examples" sections restating Phase 0 step 4, the "do NOT add to phases_completed" warning five times, the "do NOT rewrite state.tasks" warning three times, and inline incident history (warden-00011, warden 00020, dated 2026-06-xx postmortems) woven through normative rules. Repetition with drift is the documented root cause of past loop halts.

### Target Users

Every autopilot session (each loads this skill first); Bob when auditing or extending autopilot.

### Success Metrics

- Core `SKILL.md` at most 350 lines; create-skill validator length warning gone.
- Per-session prose load (core + exactly one gate reference) at most 60% of the pre-split file's token count as measured at execution (after 00014-00016's deletions); measure with harness token counts (the Read-banner figure) or a real tokenizer, not raw word counts (words undercount markdown roughly 2x), and report before/after numbers.
- All existing contract tests green, unchanged: `pytest` over `~/.claude/skills/run-autopilot/scripts/` (do not edit any test).
- `scripts/`, `prompts/`, and hook registrations byte-unchanged.
- A migration map accounts for every original section and every normative rule (no rule silently dropped).

## Functional Decomposition

### Capability: Per-gate reference layout

Split phase instructions so a session reads only its own gate.

#### Feature: Split phase docs into gate references

- **Description**: Move phase bodies out of SKILL.md into five new reference files.
- **Inputs**: Current `SKILL.md` sections Phase 0 through Phase 9.
- **Outputs**: One gate file per value of the phase enum in force at execution, under `~/.claude/skills/run-autopilot/references/`. Post-00015 (`build|review|done`):
  - `phase-build.md`: Phase 0 (PRD Selection incl. abort handlers), Phase 1 (Catchup incl. batch cache), Phase 1.5 (Design), Phase 2 (Planning), Phase 3 (Work incl. build-to-review handoff)
  - `phase-review.md`: the merged review cycle (reviewer batch incl. the blind/doubt lenses, Decision Gate incl. cap check and cap-pause, Rework)
  - `phase-done.md`: Completion, Continuation, Batch-End Review, the `review-batch` entry (00014)
  If 00015 stalled and Phases 7/8 still exist at execution, additionally create `phase-blind.md` and `phase-doubt.md` (incl. Eve dual-reviewer leg and coverage gate) - derive the gate set from the file, never from this list.
- **Behavior**: Move, do not rewrite semantics. Every normative statement (MUST, NEVER, "do NOT", Skip-if, PAUSE, STOP conditions, state-field writes) is preserved verbatim or with meaning-preserving compression. Each gate file must be self-contained for its session: restate one-line pointers to the shared sub-steps it uses (hydration, handoff procedure) rather than assuming the reader saw another gate file.

#### Feature: Gate dispatch core

- **Description**: Rebuild SKILL.md as the always-loaded core.
- **Inputs**: Current SKILL.md minus the moved phases.
- **Outputs**: Core retains: frontmatter, Execution Model, Entry Points, State Management (Retention, Resuming, Task Counts, the "Hydrate TaskList from state.tasks" sub-step, Live Dashboard, Phase Banners), Session Loop (the post-00014 end-turn hand-off contract: state writes, banner, end turn, wrapper reads `state.json` - plus Loop Detection, coverage-gate coordination, STOP discipline), Shell Command Rules, Error Handling table, and a new gate dispatch table.
- **Behavior**: The dispatch table maps resume state to a gate file and makes reading it mandatory before executing the gate: `phase: "build"` or missing state -> Read `references/phase-build.md`; `"review"` -> `references/phase-review.md`; `"done"` -> `references/phase-done.md`; `"paused"` -> the Phase 0 handlers in `references/phase-build.md`; legacy `"blind"`/`"doubt"` values (pre-00015 state files) -> `references/phase-review.md`, consistent with 00015's legacy-value mapping. Wording must be an instruction ("Read the matching gate file now; do not execute a gate from memory"), not a suggestion.

### Capability: Deduplication

Say each rule once.

#### Feature: Canonical session handoff procedure

- **Description**: Replace the near-identical per-site handoff blocks with one procedure plus a per-site table.
- **Inputs**: Every near-identical handoff block present at execution (post-00015: build-to-review at Phase 3, review-to-done at Phase 5 convergence, PRD-to-PRD at Phase 9 step 10; pre-00015 also review-to-blind and blind-to-doubt).
- **Outputs**: One "Session handoff" procedure in the core's Session Loop section (update state fields, print banner, end the turn; in loop mode the wrapper reads `state.json` and relaunches - the 00014 contract), plus a table: site | state writes (`next_phase`, `phases_completed` marker) | banner text.
- **Behavior**: Gate files invoke it by name with their site row. No handoff mechanics duplicated in gate files.

#### Feature: Frontmatter parse table

- **Description**: Collapse Phase 0 step 4's per-field parsing prose and both "Frontmatter examples" sections.
- **Inputs**: Phase 0 step 4; "Frontmatter examples" (after Phase 1); "Design frontmatter examples" (after Phase 1.5).
- **Outputs**: One table in `phase-build.md`: field | accepted values | default | state target | on-invalid. One shared fallback sentence (warn once, never crash Phase 0, do not re-parse after Phase 0). Both standalone example sections deleted; any example not implied by the table moves to `references/state-schema.md`.
- **Behavior**: Fields covered: `catchup`, `rework_cap`, `design`, `design_gate`, `doubt_reviewer` (and note `default_model` is parsed by `/plan-tasks` and re-read at Phase 6).

#### Feature: Extract incident rationale

- **Description**: Move incident history out of the rule text into a rationale reference.
- **Inputs**: Inline postmortem passages (warden-00011 retention and mkdir rationale, warden 00020 cycle-persistence story, 2026-06-11/12 signal-race narrative, 2026-06-15 AskUserQuestion strands, 2026-06-17 doubt-yield thrash, 2026-06-19 stranded dispatches, stale batch-id forensics, 2026-06-25 RAM lockout reference if present).
- **Outputs**: New `references/design-rationale.md` (same pattern review-work-completion already uses) holding the why; the rule text keeps the imperative plus a one-line pointer.
- **Behavior**: The RULE always stays inline where it is enforced; only the story moves. A rule whose meaning would weaken without its rationale keeps a one-sentence justification inline.

### Capability: Consistency proof

Make "nothing lost" checkable.

#### Feature: Migration map artifact

- **Description**: A reviewable old-to-new mapping.
- **Inputs**: Pre-change SKILL.md (git HEAD version).
- **Outputs**: `dev/local/tmp/00043-migration-map.md`: one row per original `##`/`###` section and per normative rule (MUST/NEVER/"do NOT"/Skip-if/PAUSE/STOP), giving its new location (file + heading) or "deleted: exact duplicate of <location>".
- **Behavior**: Review surfaces use this to verify completeness; the doubt lens must spot-check at least every handoff-table site, the cap-pause writer, the hydration call sites, and the Phase 9 step 10 reset list against it.

#### Feature: Update cross-skill anchors

- **Description**: Fix references that point into run-autopilot's SKILL.md sections.
- **Inputs**: `rg -n "run-autopilot/SKILL.md" ~/.claude/skills ~/.claude/commands` hits (work, plan-tasks, and others reference "Phase 6", "state-schema", section names).
- **Outputs**: Each pointer updated to the new file (e.g. `run-autopilot/references/phase-review.md` Phase 6).
- **Behavior**: Only pointer text changes in consumer skills; no consumer semantics change.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/run-autopilot/
├── SKILL.md                          # Maps to: Gate dispatch core (<=350 lines)
├── references/
│   ├── phase-build.md                # NEW  Maps to: Per-gate reference layout
│   ├── phase-review.md               # NEW  (absorbs the blind/doubt lens prose post-00015)
│   ├── phase-done.md                 # NEW
│   ├── (phase-blind.md, phase-doubt.md only if 00015 stalled)
│   ├── design-rationale.md           # NEW  Maps to: Extract incident rationale
│   ├── state-schema.md               # existing; may absorb frontmatter examples
│   └── (recovery.md, decision-framework.md, audit-log-format.md,
│        batch-report-format.md, dashboard-format.md, doubt-review-rubric.md
│        unchanged)
├── prompts/                          # byte-unchanged
└── scripts/                          # byte-unchanged, tests must stay green
```

### Module: run-autopilot core

- **Maps to capability**: Per-gate reference layout, Deduplication
- **Responsibility**: Always-loaded orchestration contract: state, loop, handoff, error handling, gate dispatch
- **Exports**: gate dispatch table, Session handoff procedure, Hydrate sub-step

### Module: gate references

- **Maps to capability**: Per-gate reference layout
- **Responsibility**: Full instructions for exactly one gate each
- **Exports**: one `phase-*.md` per phase-enum value (post-00015: `phase-build.md`, `phase-review.md`, `phase-done.md`)

### Module: rationale reference

- **Maps to capability**: Extract incident rationale, Consistency proof
- **Responsibility**: Incident history and design-why, out of the hot path
- **Exports**: `design-rationale.md`

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies; built first.

- **migration map skeleton**: enumerate current sections and normative rules before any edit (the checklist everything else fills in)

### Core Layer (Phase 1)

- **gate references + core rebuild**: depends on [migration map skeleton]
- **handoff procedure, parse table, rationale extraction**: part of the same rebuild, same dependency

### Integration Layer (Phase 2)

- **cross-skill anchor updates**: depends on [gate references + core rebuild]
- **verification (tests, validator, token measurement)**: depends on all above

## Implementation Phases

Premise rule: PRDs 00014-00016 run first by sequence and reshape this file (headless end-turn hand-offs, `build|review|done` enum, slimmed gate prose). Before any edit, derive the actual phase enum and Session Loop shape from the file as it exists (`rg -n "^## Phase|next_phase" SKILL.md`) and size the gate set to what is found; if the overhaul PRDs stalled, apply the legacy five-gate split (blind/doubt gates included) and keep the loop prose as found. The migration-map discipline is unconditional.

### Phase 0: Foundation

**Goal**: Complete inventory before surgery.

**Tasks**:

- [ ] Migration map skeleton (no deps) - Acceptance: `dev/local/tmp/00043-migration-map.md` lists every `##`/`###` heading of the current SKILL.md and every normative-rule line (MUST/NEVER/"do NOT"/Skip-if/PAUSE/STOP), each with an empty "new location" column

**Exit Criteria**: Migration map skeleton covers the whole current file.

### Phase 1: Core

**Goal**: New layout in place, nothing lost.

**Tasks**:

- [ ] Split phase docs into gate references (depends on: Phase 0) - Acceptance: one gate file per phase-enum value in force (post-00015: three) with the phase assignments listed in the Feature; every migration-map row for phase content filled
- [ ] Gate dispatch core (depends on: split) - Acceptance: SKILL.md at most 350 lines; contains the dispatch table with the mandatory-read wording; retains all State Management and Session Loop content listed in the Feature
- [ ] Canonical session handoff procedure (depends on: split) - Acceptance: exactly one handoff procedure in core; per-site table covers every hand-off site present (post-00015: three); gate files invoke the procedure by name with their site row - rg for the procedure name across `references/phase-*.md` shows pointers, not restated mechanics
- [ ] Frontmatter parse table (depends on: split) - Acceptance: both example sections gone; parse table present in phase-build.md covering the five fields; fallback sentence present
- [ ] Extract incident rationale (depends on: split) - Acceptance: `design-rationale.md` exists; dated postmortem narratives no longer appear in core or gate files except as one-line pointers; every rule they justified still present (map rows filled)

**Exit Criteria**: Core and five gate files in place; every migration-map row filled.

### Phase 2: Integration

**Goal**: Consumers aligned, contract proven.

**Tasks**:

- [ ] Update cross-skill anchors (depends on: Phase 1) - Acceptance: `rg -n "run-autopilot/SKILL.md Phase" ~/.claude/skills` returns no stale section pointers; consumers point at the correct gate file
- [ ] Verification (depends on: all) - Acceptance: full `pytest` run over run-autopilot/scripts/ green with zero test edits (counts pasted); create-skill validator on run-autopilot emits no length warning; before/after token counts (harness Read banner or tokenizer) for core and each gate file pasted; migration map has no empty rows

**Exit Criteria**: Success metrics all hold.

## Test Strategy

### Critical Scenarios

- **Happy path**: fresh session resumes at `phase: "review"` → Expected: core instructs reading `phase-review.md` before any Phase 4 action; all Phase 4-6 rules reachable from that one file plus core
- **Edge case**: cap-pause resume (`phase: "paused"` + `cap_pause_reason`) → Expected: dispatch table routes to phase-build.md Phase 0 handlers; handler text intact per migration map
- **Edge case**: `_AUTOPILOT_LOOP` unset (interactive run) → Expected: handoff procedure still distinguishes loop mode (wrapper relaunches after the turn ends) from interactive (user re-invokes manually)
- **Error case**: a normative rule found in neither core, gate files, nor map → Expected: review phases flag it as a blocker (this is the failure the migration map exists to catch)

Existing `scripts/test_*.py` suites are the regression net for hook/scripts behavior and must pass without modification.

## Risks

- **Prose-behavior regression in rare paths**: the highest risk in this backlog. Mitigations: design phase runs (frontmatter `design: run`), migration map with per-rule accounting, the full review-lens roster (post-00015), and the doubt-lens spot-check list named above.
- **Model skips reading the gate file**: mitigated by imperative dispatch wording in core and by keeping ALL shared mechanics (state, handoff, hydration) in the always-loaded core so a skipped gate file fails loudly (no phase instructions) rather than subtly.
- **Cross-skill pointer rot**: swept in Phase 2 via `rg`; PRD 00044 touches some of the same consumer files and runs after this PRD.
- **Repo specifics**: `$HOME` work-tree of bare repo `~/.buvis`; no CHANGELOG entries.
