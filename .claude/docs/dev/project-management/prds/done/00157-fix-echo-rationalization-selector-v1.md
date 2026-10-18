# Fix the Echo Rationalization Selector

Source: review of PRD 00156 (2026-08-30), findings 3 and A -
`~/.claude/dev/local/reviews/00156-review-findings.md`.

## Overview

### Problem Statement

`~/.claude/rules-library/rationalizations.md` is a catalog of excuses that
`hooks/cartographer-echo.py` is supposed to cite in its deny messages. It parses
every entry and then shows almost none of them.

`_pick_rationalization` (`cartographer-echo.py:791-807`) picks in three steps:

1. If any duplicate symbol contains a helper verb, use the entry keyed
   `"Couldn't find existing helper"`.
2. Otherwise use the entry keyed `"Quick fix, skip atlas"`.
3. Otherwise `next(iter(rats.items()))` - the first entry in file order.

Step 2 is dead. The heading was renamed to `"Quick fix, skip the map"` when the
cartographer atlas was retired (PRD 00138), and the lookup key was never updated,
so it never matches. Step 3 therefore absorbs every non-helper-verb deny and
always shows the same first entry.

Net effect: of the five catalog entries, one fires on a verb heuristic and one
fires because it happens to be first. The other three are unreachable, and any
entry added later is unreachable by construction. PRD 00156's `encode-incident`
skill writes into this file, so it inherits the dead end: it ships with a
disclaimer saying the entry will not appear in a deny message unless it is first.

Two defects, one shallow and one structural. The stale key is a one-line
leftover. The first-entry fallback is the real limit: there is no matching
between what the session was actually doing and which excuse gets quoted.

### Target Users

The solo maintainer, and any session that trips Echo's duplicate-symbol deny -
the deny message is the only place these entries are ever shown.

### Success Metrics

- No lookup key in `cartographer-echo.py` names a heading absent from
  `rationalizations.md`; a test fails if one does.
- A deny for a non-helper-verb duplicate cites an entry chosen by relevance, not
  by file position.
- An entry appended to the catalog is reachable without being moved to the top.
- `encode-incident`'s Step 5 disclaimer is removed, because it is no longer true.

## Functional Decomposition

### Capability: Key integrity

#### Feature: Fail when a hardcoded key does not exist

- **Description**: Stop a rename from silently killing a branch.
- **Inputs**: `rationalizations.md`, the key set in `cartographer-echo.py`.
- **Outputs**: A failing test naming the missing key.
- **Behavior**: Every heading the selector looks up must exist in the catalog.
  This is the regression test for the `"Quick fix, skip atlas"` bug and must fail
  against the current code before the fix lands.

### Capability: Relevance selection

#### Feature: Choose the entry by what the session was doing

- **Description**: Replace the first-entry fallback with a real match.
- **Inputs**: The duplicate symbols, the tool, and the catalog entries.
- **Outputs**: The chosen entry, or none.
- **Behavior**: Deterministic and in code, never a model call - the same input
  must always produce the same entry (`rules/ai-app-design.md`). Extend the
  existing verb heuristic rather than inventing a scoring engine: give each entry
  its own trigger terms, and match against them. Where nothing matches, showing
  no rationalization is better than showing an irrelevant one, so the deny
  message must render correctly with none.

#### Feature: Keep triggers next to the entries

- **Description**: Stop the key set drifting from the catalog again.
- **Inputs**: `rationalizations.md`.
- **Outputs**: Trigger terms parsed from the catalog itself.
- **Behavior**: The root cause of the stale key is that the selector's knowledge
  of the catalog lives in a different file from the catalog. Triggers belong in
  the entry, in a form the existing parser can read, so adding an entry makes it
  reachable with no code change. This is what makes an appended entry work, and
  it is the whole point.

## Structural Decomposition

```
hooks/
├── cartographer-echo.py            # Maps to: both capabilities
└── tests/
    └── test_cartographer_echo.py   # Maps to: Key integrity
rules-library/
└── rationalizations.md             # Maps to: Keep triggers next to the entries
skills/
└── encode-incident/SKILL.md        # Step 5 disclaimer removal
```

### Module: selector

- **Maps to capability**: Key integrity, Relevance selection
- **Responsibility**: `_load_rationalizations` gains trigger parsing;
  `_pick_rationalization` matches on triggers and returns `None` on no match.
- **Exports**: unchanged signature - `(excuse, why, counter) | None`. Callers in
  `build_deny_envelope` already handle `None`; verify before relying on it.

## Dependency Graph

### Foundation Layer (Phase 0)

- **regression test**: no dependencies. Must fail first.

### Core Layer (Phase 1)

- **trigger parsing + selector**: Depends on [regression test]

### Integration Layer (Phase 2)

- **catalog triggers + disclaimer removal**: Depends on [trigger parsing + selector]

## Implementation Phases

### Phase 0: Foundation

**Goal**: The bug is captured by a test that fails against today's code.

**Tasks**:

- [x] Add a test asserting every hardcoded lookup key in `cartographer-echo.py`
  resolves to a heading in `rationalizations.md` (no deps)
  - Acceptance: run it against unmodified `cartographer-echo.py` and watch it
    fail on `"Quick fix, skip atlas"`. Paste the failing output.
- [x] Add a test asserting an entry appended to the catalog is reachable (no deps)
  - Acceptance: fails today, because the fallback returns the first entry.

**Exit Criteria**: Both tests fail for the stated reasons, output pasted.

### Phase 1: Core

**Goal**: Selection is by relevance and cannot silently rot.

**Tasks**:

- [x] Parse per-entry trigger terms in `_load_rationalizations` (depends on: Phase 0)
  - Acceptance: an entry with no triggers still parses; the cache still works.
- [x] Rewrite `_pick_rationalization` to match on triggers and return `None` when
  nothing matches (depends on: Phase 0)
  - Acceptance: both Phase 0 tests pass; no hardcoded heading strings remain in
    the module.
- [x] Verify `build_deny_envelope` renders a deny with no rationalization
  (depends on: Phase 0)
  - Acceptance: a test covers the `None` path end to end.

**Exit Criteria**: Full hooks suite green
(`uv run --with pytest --with tree-sitter-language-pack`, baseline zero failures).

### Phase 2: Integration

**Goal**: The catalog carries its own triggers and the skill stops apologising.

**Tasks**:

- [x] Add trigger terms to all five existing entries (depends on: Phase 1)
  - Acceptance: each entry is reachable by at least one realistic symbol set.
- [x] Remove the "What this actually buys, today" disclaimer from
  `skills/encode-incident/SKILL.md` Step 5 (depends on: Phase 1)
  - Acceptance: the paragraph is gone and Step 5 states the entry is live.
- [x] Commit `rationalizations.md` and the skill to `~/.buvis` by explicit
  `:(top)` pathspec (depends on: Phase 1)

**Exit Criteria**: An entry appended to the bottom of `## Excuses` is cited by a
deny message with no code change.

## Test Strategy

### Critical Scenarios

- **Regression**: a hardcoded key naming a renamed heading → test fails.
- **Happy path**: helper-verb symbols → the helper entry, as today.
- **Happy path**: an entry appended last, matching the symbols → that entry.
- **Edge case**: no entry matches → deny renders with no rationalization.
- **Edge case**: catalog missing or empty → `None`, no crash (holds today).

## Risks

- **Fewer denies cite an excuse than before.** Returning `None` instead of the
  first entry is the point, but it will read as a regression. Mitigation: state
  it in the changelog entry.
- **`cartographer-echo.py` is a live PreToolUse enforcement hook.** A crash here
  fails closed and blocks every edit. Mitigation: the selector already sits
  behind the parse cache, and `None` is an existing return value.
- **Trigger terms rot too**, just more slowly. Mitigation: they live in the
  catalog beside the text they select, so an author edits both at once.
