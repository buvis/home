---
design: skip
---

# Close purge-devlocal blind spots

> Source: 2026-07-14 setup-review findings walkthrough (finding 5, "sweep now +
> teach the GC"). The sweep half was executed interactively the same day (17
> manual-sweep rows in `~/.claude/dev/local/.trash/manifest.tsv` - the
> manifest lives at the trash ROOT, all rows pointing into `2026-07-14/`);
> this PRD carries the durable rule changes. Full review:
> `dev/local/audit-results/2026-07-14-claude-setup-brutal-review.md` (U6).

## Overview

### Problem Statement

purge-devlocal's rules missed four debris classes that a manual audit caught
the same day a purge ran (2026-07-14T11:09): (1) un-numbered root strays
(`blake-*.md`, probe scripts, `test-run.log`) classify `unclassified → keep`
even though the working-documents contract says root holds named keepers only;
(2) numbered root debris tied to DONE PRDs (`alice_00054_gate.py`,
`00014/00017-drain-repo/`) survived although the `done-linked` rule should
trash it - cause unknown (min-age guard, root scoping, or a classifier bug);
(3) trash moves collide when a same-named entry already exists in the day's
batch (a second `00017-drain-repo` mv failed today); (4) stale
`autopilot/deferred/` and `autopilot/reports/` files older than
`--autopilot-age-days` (June-29 batch, 15 days) survived the same run.

### Target Users

Solo operator; every repo with a dev/local store the GC sweeps.

### Success Metrics

- A fixture store reproducing all four classes is fully classified: root
  strays FLAGGED, done-linked root debris TRASHED, colliding names trashed
  under a dedupe suffix with a manifest row each, stale autopilot subdir files
  TRASHED.
- The 2026-07-14 survivor set, replayed as fixtures, no longer survives.
- Existing purge test suite stays green.
- Manifest rows with unknown rule tags (e.g. `manual-sweep`) are tolerated by
  every manifest reader.

## Functional Decomposition

### Capability: Root-contract enforcement

#### Feature: Flag un-numbered root strays
- **Description**: root entries outside KEEP_NAMES, curated dirs, and numbered
  satellites become FLAG (reported, never auto-trashed).
- **Inputs**: store root listing; KEEP_NAMES; FLAG_DIRS.
- **Outputs**: flag report lines naming each stray.
- **Behavior**: conservative - flag not trash, because root keepers are named
  by convention and a new keeper appears before anyone updates KEEP_NAMES.

#### Feature: Fix done-linked classification at root
- **Description**: numbered root files/dirs whose PRD is in `prds/done` must
  reach the `done-linked → trash` action.
- **Inputs**: the 2026-07-14 survivors as fixtures. Premise (re-check at
  execution): the current classifier really does keep such fixtures; if it
  already trashes them, the bug is elsewhere (likely `--min-age-days`) -
  investigate and document rather than force a change.
- **Outputs**: failing-first regression test, then the fix.
- **Behavior**: diagnose before patching; the July survivors are the oracle.

### Capability: Mechanical robustness

#### Feature: Collision-safe trash moves
- **Description**: a name collision inside the day's batch gets a dedupe
  suffix (`<name>-2`, `-3`, ...) instead of a failed move.
- **Inputs**: existing trash-move path.
- **Outputs**: suffixed destination + accurate manifest row.
- **Behavior**: never overwrite, never skip silently.

#### Feature: Autopilot subdir staleness
- **Description**: `autopilot/deferred/**` and `autopilot/reports/**` age out
  under `--autopilot-age-days` like the rest of `autopilot/**`.
- **Inputs**: fixture with a 15-day-old deferred/report pair. Premise
  (re-check): confirm the current walker actually skips these subpaths before
  changing anything.
- **Outputs**: regression test + fix (or a documented finding that the guard
  was `--min-age-days`, with the guard's interaction documented in the
  docstring table).
- **Behavior**: `ledger/**` keep-rule stays untouched.

## Structural Decomposition

### Repository Structure

```
.claude/skills/purge-devlocal/
├── scripts/purge_devlocal.py   # Maps to: all four features (rule table + walker)
└── scripts/test_purge_devlocal.py  # Maps to: fixtures for all four classes
```

### Module: purge_devlocal
- **Maps to capability**: Root-contract enforcement, Mechanical robustness
- **Responsibility**: classification rules, trash mechanics, manifest writing
- **Exports**: CLI (`--repo`, `--apply`, age flags); rule table in module docstring
  updated to match behavior

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **fixture set**: replay of the 2026-07-14 survivor list as test fixtures

### Core Layer (Phase 1)
- **classifier fixes + collision suffix**: Depends on [fixture set]

### Integration Layer (Phase 2)
- **docstring table + live re-run**: Depends on [classifier fixes]

## Implementation Phases

### Phase 0: Foundation
**Goal**: The four blind spots exist as failing tests.

**Tasks**:
- [ ] Build fixtures replaying the survivor set (no deps) - Acceptance: four
  tests exist, each red against the unmodified script (fail-first proven in
  the test run log).

**Exit Criteria**: red suite documents current behavior.

### Phase 1: Core
**Goal**: All four classes handled.

**Tasks**:
- [ ] Root-stray FLAG rule (depends on: Phase 0) - Acceptance: stray fixture
  flagged; KEEP_NAMES/curated/numbered entries unaffected.
- [ ] Done-linked root fix or documented root-cause (depends on: Phase 0) -
  Acceptance: survivor fixtures trash, or the investigation note names the
  real guard with a test pinning it.
- [ ] Collision suffix + manifest row (depends on: Phase 0) - Acceptance:
  colliding fixture lands as `<name>-2` with correct manifest line.
- [ ] Autopilot subdir aging (depends on: Phase 0) - Acceptance: 15-day
  deferred/report fixtures trash; `ledger/**` fixture survives.

**Exit Criteria**: full suite green including the four new tests.

### Phase 2: Integration
**Goal**: Docs match behavior; live store verified.

**Tasks**:
- [ ] Update the module-docstring rule table + re-run against `~/.claude`
  store in dry-run (depends on: Phase 1) - Acceptance: dry-run output shows
  zero survivors of the four classes and no new false positives on keepers
  (`ecc-cursor`, `project-capsule.md`, curated dirs, live batch files).

**Exit Criteria**: Success Metrics all verifiably true.

## Test Strategy

### Critical Scenarios
- **Happy path**: fixture store with mixed live/dead entries → Expected: only
  the four dead classes move, manifest rows accurate.
- **Edge case**: root file added yesterday matching no rule → Expected:
  flagged, never trashed (min-age + flag-not-trash double guard).
- **Error case**: trash destination already exists → Expected: dedupe suffix,
  no failure, no overwrite.

## Risks

- **Over-eager root rule trashes a new keeper**: FLAG action only; trashing
  root strays stays a human decision.
- **Fixing done-linked exposes files the operator still wanted**: trash-first
  design already guarantees a recovery window (`--empty-trash-days`).
