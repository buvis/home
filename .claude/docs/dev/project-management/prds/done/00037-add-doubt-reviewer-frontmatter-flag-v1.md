# Add `doubt_reviewer` Frontmatter Flag

**Depends on**: none directly, but is only load-bearing once
`00038-merge-fable5-doubt-review-findings-v1.md` lands (which depends on
this PRD and `00036-doubt-review-fable5-reviewer-v1.md`).

## Overview

### Problem Statement

`/run-autopilot` PRD frontmatter already supports opt-in behavioral flags
(`catchup`, `rework_cap`, `design`, `design_gate`), each parsed at Phase 0
step 4 with a documented default and malformed-value fallback. There is no
equivalent flag for selecting the doubt-review reviewer set, which a
follow-on PRD needs in order to conditionally dispatch a second reviewer
(Eve, Claude Fable 5) in Phase 8 without changing behavior for PRDs that
don't ask for it.

### Target Users

The solo developer authoring a PRD who wants to flag it for a deeper
doubt-review pass — this PRD only adds the flag and its parsing; it does not
yet make anything consume it.

### Success Metrics

- `state.doubt_reviewer` resolves to `"fable"` when a PRD's frontmatter sets
  `doubt_reviewer: fable`, and to `"codex"` for every other case (absent
  field, malformed YAML, unrecognized value) — with a one-line warning
  logged on the fallback path, matching the existing `rework_cap` pattern.
  exactly.
- The flag is documented in both the parsing source of truth (`SKILL.md`
  Phase 0 step 4) and the authoring-side reference (`create-prd/SKILL.md`'s
  "Optional frontmatter fields" list).
- No behavior changes anywhere else in the pipeline — this PRD only adds a
  state field nothing reads yet.

## Functional Decomposition

### Capability: Frontmatter Configuration

Lets a PRD author opt a specific PRD into the Eve (Fable 5) doubt-review
leg via frontmatter, following the same parsing pattern already used for
`catchup`, `rework_cap`, and `design`.

#### Feature: `doubt_reviewer` frontmatter field
- **Description**: Optional PRD frontmatter field selecting the doubt-review
  reviewer set for this PRD.
- **Inputs**: The PRD's YAML frontmatter block, parsed at Phase 0 step 4.
- **Outputs**: `state.doubt_reviewer` — `"codex"` (default) or `"fable"`.
- **Behavior**: Accepted values: `codex`, `fable`. Anything else (other
  value, malformed YAML, missing frontmatter, absent field) defaults to
  `"codex"` with a one-line warning logged — identical fallback semantics to
  the existing `rework_cap`/`catchup`/`design` fields in the same step.
  Re-parsed fresh for every PRD (same lifecycle as `rework_cap`: Phase 0
  overwrites it at the start of each PRD, no explicit Phase 9 clearing
  needed).

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/run-autopilot/
├── SKILL.md                    # Maps to: Frontmatter Configuration (Phase 0 step 4)
└── references/
    └── state-schema.md         # Maps to: Frontmatter Configuration (state.doubt_reviewer field)

~/.claude/skills/create-prd/
└── SKILL.md                    # Maps to: Frontmatter Configuration (Optional frontmatter fields doc)
```

### Module: run-autopilot/SKILL.md
- **Maps to capability**: Frontmatter Configuration
- **Responsibility**: Orchestrates all autopilot phases; owns the Phase 0
  frontmatter-parsing rules
- **Exports**:
  - Phase 0 step 4 — `doubt_reviewer` parsing rule (documented alongside
    `catchup`/`rework_cap`/`design`)

### Module: run-autopilot/references/state-schema.md
- **Maps to capability**: Frontmatter Configuration
- **Responsibility**: Canonical documentation of `state.json`'s field
  shapes
- **Exports**:
  - `doubt_reviewer` top-level field row (mirrors the `rework_cap` row)

### Module: create-prd/SKILL.md
- **Maps to capability**: Frontmatter Configuration
- **Responsibility**: Documents which optional frontmatter fields a PRD
  author can set
- **Exports**:
  - `doubt_reviewer: fable` entry in the "Optional frontmatter fields" list

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies — built first.

- **Frontmatter Configuration**: Provides `state.doubt_reviewer`. Standalone
  — this PRD introduces the field and its parsing rule only; nothing in the
  pipeline reads it yet (a follow-on PRD adds the consumer).

### Core Layer (Phase 1)
N/A for this PRD — single-layer scope by design.

### Integration Layer (Phase 2)
N/A for this PRD — wiring a consumer (Phase 8 dispatch/merge) is
deliberately out of scope; see
`00038-merge-fable5-doubt-review-findings-v1.md`.

## Implementation Phases

### Phase 0: Foundation
**Goal**: A PRD can opt into the Fable 5 doubt reviewer via frontmatter, and
the state schema documents the resulting field.

**Tasks**:
- [ ] Add `doubt_reviewer` frontmatter parsing to `SKILL.md` Phase 0 step 4,
  mirroring the existing `catchup`/`rework_cap`/`design` parsing wording
  exactly (accepted values `codex`|`fable`; malformed/absent → default
  `codex` with a one-line warning) (no deps) - Acceptance: Phase 0 step 4
  documents `doubt_reviewer` with identical fallback semantics to
  `rework_cap`; a PRD frontmatter block with `doubt_reviewer: fable` parses
  to `state.doubt_reviewer == "fable"`; an absent or malformed field parses
  to `"codex"`.
- [ ] Document `state.doubt_reviewer` as a new top-level field in
  `state-schema.md`'s field table, in the same row style as `rework_cap`
  (depends on: prior task) - Acceptance: `state-schema.md` has a
  `doubt_reviewer` row describing type, accepted values, default, and
  per-PRD re-derivation lifecycle (same category as
  `rework_cap`/`design_mode` — Phase 0 overwrites fresh for every PRD, no
  explicit Phase 9 clearing required).
- [ ] Add `doubt_reviewer: fable` to `create-prd/SKILL.md`'s "Optional
  frontmatter fields" list, alongside `catchup`/`rework_cap`/`design`/`design_gate`
  (depends on: first task) - Acceptance: the list documents accepted values
  and default with wording consistent with the SKILL.md Phase 0
  description; the combined-fields example block is updated to show
  `doubt_reviewer: fable` as a fifth option.

**Exit Criteria**: `state.doubt_reviewer` resolves correctly from PRD
frontmatter (explicit value and default/malformed fallback both verified),
and the field is documented in both the parsing source of truth and the
authoring-side reference — before any orchestration logic depends on it.

### Phase 1: Core
N/A for this PRD — single-layer scope by design.

### Phase 2: Integration
N/A for this PRD — wiring a consumer (Phase 8 dispatch/merge) is
deliberately out of scope; see
`00038-merge-fable5-doubt-review-findings-v1.md`.

## Test Strategy

### Critical Scenarios

- **Happy path**: PRD frontmatter contains `doubt_reviewer: fable` →
  Expected: `state.doubt_reviewer == "fable"` after Phase 0.
- **Edge case**: PRD frontmatter has no `doubt_reviewer` field at all (the
  overwhelming majority of PRDs) → Expected: `state.doubt_reviewer ==
  "codex"`, no warning logged (absence is not malformed).
- **Error case**: PRD frontmatter has `doubt_reviewer: opus` (unrecognized
  value) or malformed YAML in the frontmatter block → Expected:
  `state.doubt_reviewer == "codex"`, one-line warning logged, Phase 0 does
  not crash — identical behavior to an unrecognized `rework_cap` value.

## Risks

- **Flag drifts to a silent default of "on"**: mitigate by hard-coding the
  absent-default to `"codex"` directly in the Phase 0 parsing rule, never
  inferred from PRD size or complexity — this PRD's only job is the flag and
  its default, so get the default right once here.
- **Documentation drift between `SKILL.md` (parsing source of truth) and
  `create-prd/SKILL.md` (authoring reference)**: mitigate by writing both
  docs in the same task sequence (one depends on the other, per
  Implementation Phases above) rather than as independent edits that could
  diverge in accepted-values wording.
