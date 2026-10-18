---
design_gate: user
---

# Merge Fable 5 Doubt-Review Findings into Phase 8

**Depends on**: `00036-doubt-review-fable5-reviewer-v1.md` (Eve must be a
documented, contract-satisfying reviewer) and
`00037-add-doubt-reviewer-frontmatter-flag-v1.md` (`state.doubt_reviewer`
must exist and resolve correctly).

## Overview

### Problem Statement

`/run-autopilot` Phase 8 (doubt review) is the pipeline's last skeptical
gate before a PRD is marked done. With PRD 00036 (Eve exists as a
dispatchable reviewer) and PRD 00037 (`state.doubt_reviewer` exists as a
resolvable flag) both landed, nothing yet reads the flag or dispatches Eve
inside the actual pipeline — the capability and the configuration exist in
isolation. This PRD is the consumer: it makes Phase 8 conditionally dispatch
Eve after codex, and merges her findings into the same state structures the
rest of the pipeline (state, batch report) already reads.

### Target Users

The solo developer running `/run-autopilot` on a PRD with `doubt_reviewer:
fable` set — this PRD is what makes that flag actually do something.

### Success Metrics

- Zero behavior change for any PRD that doesn't set `doubt_reviewer: fable`
  — byte-identical Phase 8 output to current (pre-00036/00037/00038)
  behavior.
- A PRD with `doubt_reviewer: fable` completes Phase 8 with both codex's and
  Eve's findings recorded in `state.doubts`, each tagged by `source`, and
  both reviewers' rubric verdicts visible in the batch report.
- Fable 5 cost/latency stays confined to opted-in PRDs — it never runs
  inside Phase 4's per-rework-cycle panel, and never runs in parallel with
  codex inside Phase 8.

## Functional Decomposition

### Capability: Doubt-Review Sequencing & Merge

Wires Eve into Phase 8's actual control flow and merges her findings into
the existing `state.doubts` / `state.doubts_rubric_verdicts` structures with
source attribution.

#### Feature: Sequential dispatch gate
- **Description**: Decides whether and when to dispatch Eve during Phase 8.
- **Inputs**: `state.doubt_reviewer`, codex's (or the Claude fallback's)
  completed output.
- **Outputs**: Eve dispatched only when `state.doubt_reviewer == "fable"`,
  and only after the codex/fallback output already exists.
- **Behavior**: Codex (or its Claude fallback) always runs first, exactly as
  today — this path is byte-unchanged when the flag is absent. Eve never
  runs in parallel with codex: codex is fast, Fable 5 turns can run 15+
  minutes, and parallelizing would complicate the existing
  codex-unavailable-fallback logic for no benefit.

#### Feature: Finding & verdict merge with source attribution
- **Description**: Combines codex's and Eve's outputs into the single Phase
  8 result the rest of the pipeline consumes.
- **Inputs**: Codex's FIX/VERIFY/KNOWN findings + R1-R5 verdicts, Eve's
  FIX/VERIFY/KNOWN findings + R1-R5 verdicts (when dispatched).
- **Outputs**: `dev/local/reviews/<prd>-doubt-review.md` containing both
  reviewers' findings; `state.doubts` entries each carrying an optional
  `source` field (`"codex"` | `"fable"`, absent = `"codex"` for backward
  compatibility); `state.doubts_rubric_verdicts` containing one entry per
  rule per reviewer that ran, each tagged with `source`.
- **Behavior**: When the flag is absent, no `source` field is written
  anywhere and output is identical to current behavior. The
  `---review-coverage---` block contract and `review_coverage.py` gate logic
  require no changes — both reviewers' output already satisfies the existing
  contract (verified in PRD 00036 for Eve, already true for codex).

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/run-autopilot/
├── SKILL.md                                     # Maps to: Doubt-Review Sequencing & Merge (Phase 8 dispatch gate + merge)
├── references/
│   ├── state-schema.md                          # Maps to: Doubt-Review Sequencing & Merge (doubts[]/doubts_rubric_verdicts[] source field)
│   └── batch-report-format.md                   # Maps to: Doubt-Review Sequencing & Merge (source-tagged rubric rendering)
└── scripts/
    └── test_phase8_doubt_review_file_contract.py  # Maps to: Doubt-Review Sequencing & Merge (extended fixture coverage)
```

### Module: run-autopilot/SKILL.md
- **Maps to capability**: Doubt-Review Sequencing & Merge
- **Responsibility**: Orchestrates all autopilot phases; owns the Phase 8
  doubt-review procedure
- **Exports**:
  - Phase 8 — Eve sequencing gate and finding/verdict merge procedure

### Module: run-autopilot/references/state-schema.md
- **Maps to capability**: Doubt-Review Sequencing & Merge
- **Responsibility**: Canonical documentation of `state.json`'s field
  shapes
- **Exports**:
  - `source?` optional field on the `doubts[]` entry shape
  - `source?` optional field on the `doubts_rubric_verdicts[]` entry shape

### Module: run-autopilot/references/batch-report-format.md
- **Maps to capability**: Doubt-Review Sequencing & Merge
- **Responsibility**: Defines Phase 9's batch report rendering, including
  the Doubt Rubric Verdicts section
- **Exports**:
  - Source-tagged rubric verdict rendering rule (falls back to
    single-reviewer rendering when no `source` is present)

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies within this PRD — built first. (Externally depends on PRD
00036 — Eve dispatch — and PRD 00037 — the `doubt_reviewer` flag — both
already landed.)

- **Doubt-Review Sequencing & Merge (dispatch gate)**: Reads
  `state.doubt_reviewer` (PRD 00037) and invokes Eve (PRD 00036) — the
  minimal glue connecting the two already-built capabilities.

### Core Layer (Phase 1)
- **Doubt-Review Sequencing & Merge (finding/verdict merge)**: Depends on
  [dispatch gate] — merging only makes sense once Eve has actually been
  conditionally dispatched.

### Integration Layer (Phase 2)
- **Doubt-Review Sequencing & Merge (state schema + batch report)**:
  Depends on [finding/verdict merge] — the schema documentation and batch
  report rendering are downstream of the merge shape being finalized.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Phase 8 conditionally dispatches Eve after codex/fallback, with
zero behavior change when the flag is absent.

**Tasks**:
- [ ] Update `SKILL.md` Phase 8 to check `state.doubt_reviewer` after
  codex's (or the Claude fallback's) output exists: dispatch Eve only when
  the value is `"fable"`, strictly sequentially (never in parallel) (no
  deps — consumes PRDs 00036/00037 as external prerequisites) - Acceptance:
  SKILL.md documents the sequential gate exactly as specified —
  codex/fallback always runs first and this path is byte-unchanged when
  `doubt_reviewer` is absent or `"codex"`; Eve dispatches only once codex's
  (or the fallback's) output file already exists, regardless of which of
  the two produced it.

**Exit Criteria**: A PRD with `doubt_reviewer: fable` triggers an Eve
dispatch after codex/fallback returns; a PRD without the flag never
dispatches Eve.

### Phase 1: Core
**Goal**: Codex's and Eve's findings and verdicts merge into a single,
source-tagged Phase 8 result.

**Tasks**:
- [ ] Merge codex's and Eve's FIX/VERIFY/KNOWN findings and R1-R5 verdicts
  into the single Phase 8 result, tagging each finding and each verdict
  with its `source` before writing to `state.doubts` /
  `state.doubts_rubric_verdicts` (depends on: Phase 0) - Acceptance: with
  `doubt_reviewer: fable`, `dev/local/reviews/<prd>-doubt-review.md`
  contains both reviewers' findings; every `state.doubts` entry has
  `source` populated; `state.doubts_rubric_verdicts` contains one entry per
  rule per reviewer that ran (10 entries when both ran); with the flag
  absent, no `source` field is written and output is byte-identical to
  pre-change behavior — verified by extending (not replacing)
  `test_phase8_doubt_review_file_contract.py` with a flagged-path fixture.
- [ ] Confirm the `---review-coverage---` block contract needs no changes —
  Eve's output satisfies the existing `review_coverage.py` gate as-is
  (depends on: Phase 0) - Acceptance: `test_review_coverage.py`'s existing
  suite passes unmodified against a fixture shaped like Eve's output; no
  new gate code path is added to `review_coverage.py`.

**Exit Criteria**: `state.doubts` and `state.doubts_rubric_verdicts` are
correctly source-tagged for a two-reviewer Phase 8 run, and the existing
coverage gate passes unmodified against both single- and dual-reviewer
fixtures.

### Phase 2: Integration
**Goal**: Documentation and the batch report catch up to the merge shape,
so the whole pipeline (not just `state.json`) reflects two-reviewer runs
correctly.

**Tasks**:
- [ ] Document `source?` on the `doubts[]` and `doubts_rubric_verdicts[]`
  entry shapes in `state-schema.md` (depends on: Phase 1) - Acceptance:
  both array shapes document `source?` (`"codex"`|`"fable"`, absent =
  `"codex"`); existing state files with no `source` field remain valid
  documentation examples (no migration implied).
- [ ] Update `batch-report-format.md` and Phase 9 step 7 to render
  source-tagged rubric verdicts when present (e.g. `R1: pass (codex) / pass
  (fable)`) without breaking single-reviewer rendering (depends on: Phase
  1) - Acceptance: a batch report generated from a `doubt_reviewer: fable`
  PRD shows both verdicts per rule; a batch report from a default (no-flag)
  PRD renders identically to current output.

**Exit Criteria**: A full `/run-autopilot` run of a PRD with `doubt_reviewer:
fable` in frontmatter completes Phase 8 with both codex's and Eve's findings
recorded and source-tagged, the coverage gate passes unmodified, the schema
is fully documented, and the batch report reflects both reviewers — while a
PRD without the flag behaves byte-identically to pre-change autopilot.

## Test Strategy

### Critical Scenarios

- **Happy path**: PRD with `doubt_reviewer: fable`; codex finds 0 issues;
  Eve finds 1 FIX → Expected: `state.doubts` has 1 entry with `source:
  "fable"`; `state.doubts_rubric_verdicts` has 10 entries (5 rules × 2
  reviewers); a `[DOUBT]` task is created for the FIX item; Phase 9's batch
  report shows both reviewers' rubric verdicts.
- **Edge case**: PRD with `doubt_reviewer: fable`, but codex is unavailable
  so the existing Claude-fallback path fires first → Expected: fallback
  runs exactly as today, then Eve dispatches after it (the sequencing rule
  keys on "the first reviewer's output exists," not on "codex specifically
  ran"); no crash, no doubled Eve dispatch.
- **Edge case**: PRD without `doubt_reviewer` (absent, the overwhelming
  majority of existing and future PRDs) → Expected: Phase 8 behavior and
  output format are byte-identical to current behavior — zero regression
  for every PRD that doesn't opt in.
- **Error case**: Eve's Task-tool dispatch fails or times out → Expected:
  treated as a failed reviewer using the same graceful-degradation pattern
  Phase 4 already applies to a failed Bob/Carl — codex's (or the
  fallback's) findings alone still gate Phase 8; a one-line warning is
  logged; autopilot does not PAUSE solely because Eve failed.

## Risks

- **Fable 5's 15+ minute turns stalling the Phase 8 fresh-session handoff
  longer than expected**: mitigate by sequencing Eve strictly after
  codex/fallback (never blocking the fast path) and relying on the existing
  fresh-session handoff mechanism, which already tolerates open-ended
  subagent duration, rather than introducing a new timeout.
- **Schema drift breaking `review_coverage.py` or the batch report for the
  non-opted-in majority of PRDs**: mitigate by making `source` strictly
  optional/additive on both `doubts[]` and `doubts_rubric_verdicts[]`, and
  verifying by running the existing test suites unmodified against fixtures
  that omit `source` entirely.
- **Merge logic double-counts or drops findings if codex and Eve report the
  same issue**: out of scope for de-duplication in this PRD — both
  reviewers' findings are recorded independently and tagged by source; a
  future PRD can add cross-reviewer de-dup if duplicate findings prove
  noisy in practice.
