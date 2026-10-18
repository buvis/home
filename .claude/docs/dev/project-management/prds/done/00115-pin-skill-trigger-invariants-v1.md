# Pin Skill Trigger Invariants v1

Source: FASTTRACK-PLAN v4 pending decision 3 (2026-08-01), decided
2026-08-02: write the PRD. Evidence commit: `76feb4475`.

## Overview

### Problem Statement

A skill's `description` is its only router input: the phrases quoted there are
what a session matches against. Nothing checks that those phrases survive an
edit. Commit `76feb4475` ("add memory-to-AGENTS.md promotion mode") added
`"promote memories"` and `"memories to AGENTS.md"` to `manage-agents-md` and
silently dropped `"create AGENTS.md"` and `"improve AGENTS.md"` in the same
line. The loss went unnoticed for three weeks until an authoring audit read
the file by hand, and it was only restored on 2026-08-02.

The existing validator (`skills/create-skill/scripts/validate_skill.py`)
checks shape - name, description length, structure. It has no memory of what
the description said yesterday, so a removed trigger passes cleanly. Nothing
checks the other direction either: two skills quoting the same phrase leave
the router to guess.

### Target Users

The author, editing skills across `~/.claude/skills/` and six plugin repos,
where every trigger edit today is unguarded.

### Success Metrics

- Removing a quoted trigger phrase from any tracked `SKILL.md` surfaces at
  edit time, naming the dropped phrase; re-running `76feb4475`'s diff through
  the check reproduces both lost phrases.
- Two skills quoting the same phrase are reported, with both file paths.
- Adding a phrase, rewording prose outside quotes, or creating a brand-new
  skill produces no output.
- The check costs under 200 ms per `SKILL.md` edit (it joins a hook stack
  already measured at ~80 ms for loupe alone).
- Zero output on a session that edits no `SKILL.md`.

## Functional Decomposition

### Capability: Trigger Extraction

#### Feature: Parse quoted phrases from a description
- **Description**: Pull the trigger set out of a `SKILL.md` frontmatter description.
- **Inputs**: A `SKILL.md` path or its text.
- **Outputs**: The ordered set of double-quoted phrases in `description:`.
- **Behavior**: Read YAML frontmatter, take `description`, extract every
  `"..."` span. A description with no quoted phrase yields an empty set and is
  never an error - some skills trigger on prose alone.

### Capability: Regression Detection

#### Feature: Compare against the committed baseline
- **Description**: Diff the edited file's trigger set against the last committed version of the same file.
- **Inputs**: Edited `SKILL.md` path.
- **Outputs**: The list of phrases present in `HEAD` and absent now.
- **Behavior**: Git is the baseline - no lock file to maintain and no second
  source of truth. Resolve the owning repo (`~/.claude` paths belong to the
  `~/.buvis` bare repo with `--work-tree=$HOME`; anything else uses the
  enclosing repo), read `HEAD:<path>`, extract both sets, report the
  difference. A file with no committed version (new skill) reports nothing.
  A path in no repo at all reports nothing.

### Capability: Collision Detection

#### Feature: Find phrases claimed by two skills
- **Description**: Report a trigger phrase that appears in more than one skill's description.
- **Inputs**: The edited skill's phrases; every other discoverable `SKILL.md`.
- **Outputs**: Per colliding phrase, the skills claiming it.
- **Behavior**: Scan `~/.claude/skills/*/SKILL.md` plus installed plugin
  skills under `~/.claude/plugins/cache/*/*/*/skills/*/SKILL.md`, case-folded
  exact match. Only phrases belonging to the edited skill are checked, so the
  cost is bounded by one directory walk. Pre-existing collisions between two
  other skills are not the edit's problem and stay silent.

### Capability: Delivery

#### Feature: PostToolUse advisory hook
- **Description**: Report findings the moment a `SKILL.md` edit lands.
- **Inputs**: `PostToolUse` hook JSON for `Write|Edit|MultiEdit`.
- **Outputs**: Exit 0 always, with findings on stdout; nothing when clean.
- **Behavior**: Return immediately unless the edited path's basename is
  `SKILL.md`. Advisory only - a dropped trigger is sometimes deliberate, and
  a hook that blocks a rename would be worse than the bug it guards. Fails
  open on any internal error, matching the house hook contract. Python only
  per `rules/claude-tooling.md`.

## Structural Decomposition

### Repository Structure

```
~/.claude/
├── hooks/
│   ├── check_skill_triggers.py     # Maps to: extraction, regression, collision, delivery
│   └── tests/
│       └── test_check_skill_triggers.py
└── settings.json                    # PostToolUse registration
```

### Module: trigger-check
- **Maps to capability**: all four
- **Responsibility**: One file. Extraction, git baseline lookup, collision scan, and the hook entry point.
- **Exports**:
  - `extract_triggers(text)` - quoted phrases from a description
  - `dropped_since_head(path)` - phrases lost against the committed version
  - `collisions(path, phrases)` - other skills claiming the same phrases
  - `main()` - hook entry point

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies. Standard library only; `git` is invoked as a subprocess.

- **trigger-check**

### Downstream (out of scope)
- Rolling the check into `validate_skill.py` or claude-checkup's
  `audit-authoring`. If the hook proves useful, either can import
  `extract_triggers`; neither is built here.

## Implementation Phases

### Phase 0: The check

**Goal**: A hook that names dropped and colliding triggers, and stays silent otherwise.

**Tasks**:
- [ ] Implement `extract_triggers` + `dropped_since_head` + `collisions` +
  `main` in one file (no deps) - Acceptance: `76feb4475`'s before/after
  descriptions, fed in as fixtures, yield exactly `create AGENTS.md` and
  `improve AGENTS.md`.
- [ ] Register the hook in `settings.json` under `PostToolUse` matching
  `Write|Edit|MultiEdit` (depends on: the file existing) - Acceptance: editing
  a `SKILL.md` in a live session prints the finding; editing any other file
  prints nothing.
- [ ] Tests: dropped phrase, added phrase (silent), prose-only reword
  (silent), new uncommitted skill (silent), path outside any repo (silent),
  collision across two skills, git subprocess failure (silent, exit 0)
  (depends on: the file existing) - Acceptance: suite green.

**Exit Criteria**: The regression that motivated this PRD is caught by a test,
the hook is live, and a session that edits no `SKILL.md` sees nothing.

## Test Strategy

### Critical Scenarios
- **Happy path**: Edit a `SKILL.md`, keep every phrase → no output, exit 0.
- **Regression**: Replay `76feb4475`'s two descriptions → both dropped phrases named.
- **Edge case**: Brand-new skill with no committed version → silent.
- **Edge case**: Description with no quoted phrases → silent, not an error.
- **Edge case**: `SKILL.md` outside any git repo → silent.
- **Edge case**: Two skills quoting `"audit config"` → collision reported with both paths.
- **Error case**: `git` missing or the bare repo unreadable → exit 0, no output.

## Risks

- **Bare-repo pathing**: `~/.buvis` resolves pathspecs against cwd, not the
  work tree, so a relative path silently returns nothing and the check
  reports a clean file. Mitigation: absolute paths only, and a test that
  asserts a known-tracked file resolves.
- **Hook stack cost**: this joins gateguard, cartographer-echo, aegis and
  loupe on the same event. Mitigation: the basename guard returns before any
  git call or directory walk, so a non-`SKILL.md` edit costs one string
  compare.
- **Deliberate removals become noise**: renaming a trigger legitimately drops
  the old phrase. Mitigation: advisory, one line, no blocking. If it nags, the
  next step is a marker in the commit message, not a lock file.
- **Premise**: this assumes trigger phrases still live in `description`. If
  the harness ever moves matching to a separate field, the extractor is wrong
  rather than merely incomplete. Re-check before building.

## Open Questions

- Should the collision scan cover dormant skills in `~/.claude/skills-library/`?
  They cost no boot context and cannot fire, so v1 skips them; reactivating one
  is exactly when a collision would matter.
