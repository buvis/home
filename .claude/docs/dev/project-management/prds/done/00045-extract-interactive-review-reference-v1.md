---
catchup: skip
---

# Extract Shared Interactive-Review Reference

## Overview

### Problem Statement

`review-design-doc` and `review-discovery-doc` are the two interactive one-finding-at-a-time review skills. They duplicate the entire interactive-review machinery across two always-loaded bodies (~1,200 duplicated words): finding-card format, three-resolution-options discipline, picker ordering, ground rules, comprehension/confusion-notes pass, success criteria, and session safety. The copies have already drifted in wording. Their only intended divergence is apply timing (design-doc applies each resolution immediately; discovery-doc batch-applies). Beyond the pair, both bodies inline reference-grade content that loads on every invocation (review-design-doc: card format, resolution taxonomy, a ground-rules subset duplicating `references/ground-rules.md`, the script list twice; review-discovery-doc has no `references/` dir at all, so its five-lens criteria sit inline), and `digest-github-repo` inlines two full output templates next to an existing `references/` dir.

### Target Users

Bob running `/review-design-doc`, `/review-discovery-doc`, `/digest-github-repo`; autopilot's design phase indirectly (design-solution dispatches reviewer prompts built from review-design-doc's references).

### Success Metrics

- The interactive-review machinery exists exactly once, in a shared reference both skills point to.
- `review-design-doc/SKILL.md` and `review-discovery-doc/SKILL.md` body word counts drop at least 40% each (report before/after).
- `digest-github-repo/SKILL.md` no longer inlines the two output templates.
- create-skill validator clean on all three skills; interactive behavior unchanged (migration map proves content moved, not changed).

## Functional Decomposition

### Capability: Shared interactive-review core

#### Feature: Create interactive-review reference

- **Description**: One canonical file for the shared machinery.
- **Inputs**: The duplicated blocks in both SKILL.md bodies; where wording drifted, `review-design-doc`'s text is canonical.
- **Outputs**: New `~/.claude/skills/review-design-doc/references/interactive-review.md` containing: finding-card format, three-resolution-options discipline, option picker ordering, ground rules, comprehension/confusion-notes pass, success criteria, session safety.
- **Behavior**: Apply timing is NOT in the shared file; it stays per-skill (immediate vs batch). The file opens with one line naming its two consumers.

#### Feature: Slim review-design-doc body

- **Description**: The SKILL.md keeps orchestration; reference-grade content moves out.
- **Inputs**: Current body (~2,700 words): inline finding-card format and resolution taxonomy (now in the shared reference), the ground-rules subset duplicating `references/ground-rules.md`, the script list that appears twice, tier conditions restating `references/triage.md`.
- **Outputs**: Body with pointers replacing every moved/duplicated block; the script list appears once; tier conditions defer to triage.md.
- **Behavior**: Its existing `references/` files stay as they are (they are well-factored); only the body changes.

#### Feature: Slim review-discovery-doc body

- **Description**: Give the skill a `references/` dir and defer to the shared core.
- **Inputs**: Current body (~2,660 words, no references dir): five-lens criteria, inline card machinery.
- **Outputs**: New `~/.claude/skills/review-discovery-doc/references/lenses.md` (the five-lens criteria); the card machinery replaced by a pointer to `~/.claude/skills/review-design-doc/references/interactive-review.md` (absolute path, cross-skill pointers are established practice in this tree); batch-apply specifics stay inline as the skill's divergence.
- **Behavior**: `examples/sample-session.md` stays where it is (loads on demand).

### Capability: Digest template extraction

#### Feature: Move digest output templates to references

- **Description**: The two full output templates leave the hot body.
- **Inputs**: `digest-github-repo/SKILL.md` curated-list template and activity-digest template (two inline blocks); existing `references/repos-template.yaml`.
- **Outputs**: New `~/.claude/skills/digest-github-repo/references/output-templates.md` holding both, each under a heading naming its mode; SKILL.md keeps a one-line pointer per mode.
- **Behavior**: Template text moves byte-identical; mode-selection logic in the body is untouched.

### Capability: Consistency proof

#### Feature: Interactive-review migration map

- **Description**: Prove content moved, not changed.
- **Inputs**: Pre-change bodies (git HEAD versions).
- **Outputs**: `dev/local/tmp/00045-migration-map.md`: one row per moved block per skill -> new location, flagging any wording reconciliation (drifted pair -> canonical text) explicitly.
- **Behavior**: Review surfaces verify the map; the doubt review spot-checks the three-options discipline and picker ordering blocks (the drift-prone pair).

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/
├── review-design-doc/
│   ├── SKILL.md                              # slimmed
│   └── references/
│       ├── interactive-review.md             # NEW shared core
│       └── (existing 8 refs unchanged)
├── review-discovery-doc/
│   ├── SKILL.md                              # slimmed, points at shared core
│   ├── references/lenses.md                  # NEW
│   └── examples/sample-session.md            # unchanged
└── digest-github-repo/
    ├── SKILL.md                              # pointers instead of templates
    └── references/
        ├── repos-template.yaml               # unchanged
        └── output-templates.md               # NEW
```

### Module: review-design-doc

- **Maps to capability**: Shared interactive-review core
- **Responsibility**: Owns the canonical interactive-review machinery; design-doc lenses and immediate-apply flow
- **Exports**: `references/interactive-review.md` (consumed cross-skill)

### Module: review-discovery-doc

- **Maps to capability**: Shared interactive-review core
- **Responsibility**: Discovery lenses and batch-apply flow on top of the shared core
- **Exports**: `references/lenses.md`

### Module: digest-github-repo

- **Maps to capability**: Digest template extraction
- **Responsibility**: Repo digest orchestration with on-demand templates
- **Exports**: `references/output-templates.md`

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies; built first.

- **interactive-review reference**: extracted from the two bodies (canonical text decided here)
- **digest template extraction**: independent

### Core Layer (Phase 1)

- **review-design-doc slim**: depends on [interactive-review reference]
- **review-discovery-doc slim**: depends on [interactive-review reference]

### Integration Layer (Phase 2)

- **migration map + verification**: depends on all

## Implementation Phases

### Phase 0: Foundation

**Goal**: Canonical shared content exists.

**Tasks**:

- [ ] Create interactive-review reference (no deps) - Acceptance: file exists with the seven machinery blocks; apply timing absent; drifted wording reconciled to review-design-doc's text
- [ ] Move digest output templates to references (no deps) - Acceptance: `output-templates.md` holds both templates byte-identical; SKILL.md has one pointer per mode and no inline template

**Exit Criteria**: Shared reference and digest templates in place.

### Phase 1: Core

**Goal**: Both review bodies slimmed.

**Tasks**:

- [ ] Slim review-design-doc body (depends on: Phase 0) - Acceptance: body word count down at least 40% (numbers pasted); script list appears once; no block duplicated against its own references
- [ ] Slim review-discovery-doc body (depends on: Phase 0) - Acceptance: body word count down at least 40%; `references/lenses.md` exists; card machinery present only via the shared-core pointer; batch-apply flow still stated inline

**Exit Criteria**: Both bodies slimmed with pointers resolving.

### Phase 2: Integration

**Goal**: Proof.

**Tasks**:

- [ ] Interactive-review migration map + verification (depends on: Phase 1) - Acceptance: map complete; create-skill validator clean on all three skills; before/after word counts pasted

**Exit Criteria**: Success metrics all hold.

## Test Strategy

### Critical Scenarios

- **Happy path**: `/review-design-doc <doc>` after the change → Expected: identical card format and three-options interaction (content reachable via SKILL.md + shared reference)
- **Edge case**: `/review-discovery-doc` batch-apply → Expected: batch timing preserved (the one intended divergence survives extraction)
- **Error case**: shared reference accidentally includes apply timing → Expected: migration map review flags it (timing is per-skill by contract)

Docs-only PRD; verification is validator output, word-count evidence, and the migration map.

## Risks

- **Wording reconciliation changes behavior**: the drifted copies differ in emphasis; canonical = review-design-doc. The map marks every reconciliation for reviewer eyes.
- **Cross-skill pointer**: review-discovery-doc depends on a file inside review-design-doc; acceptable (established pattern: work points into run-autopilot), noted here so a future rename sweeps both.
- **Repo specifics**: `$HOME` work-tree of bare repo `~/.buvis`; no CHANGELOG entries.
