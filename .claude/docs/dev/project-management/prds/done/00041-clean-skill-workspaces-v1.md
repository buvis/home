---
catchup: skip
design: skip
---

# Clean Skill Workspaces

## Overview

### Problem Statement

Personal skill directories under `~/.claude/skills/` carry development leftovers: pytest/ruff caches, `__pycache__`, `.serena/` project dirs, and two `.bak` files. Two working skills (`assess-evolution`, `review-discovery-doc`) were never committed to the dotfiles repo, so they are invisible to history and not synced. The `review-with-doubt` command has no frontmatter, so its listing description is a truncated body line. A few one-line cross-references point at skills or paths that do not exist.

### Target Users

Bob (solo dev). Every Claude Code session that loads the skill list, and every autopilot run that invokes these skills.

### Success Metrics

- `validate_skill.py` reports 0 `[ERROR]` lines across all dirs in `~/.claude/skills/*/` except `brief-portfolio` (in active development as of 2026-07-07; excluded); the only remaining `[WARN]`s are the over-500-line bodies of `run-autopilot` and `work` (owned by PRDs 00043 and 00044).
- Zero cache/backup artifacts remain under `~/.claude/skills/` (the purge list below fully gone).
- `assess-evolution` and `review-discovery-doc` are tracked in the `~/.buvis` repo.

## Functional Decomposition

### Capability: Filesystem hygiene

Remove development leftovers from skill directories without touching skill content.

#### Feature: Purge cache and backup artifacts

- **Description**: Delete tool caches and stale backups from skill dirs.
- **Inputs**: The fixed deletion list below. None of these paths are git-tracked (verified 2026-07-07 via `git --git-dir=/Users/bob/.buvis ls-files`).
- **Outputs**: Paths removed from disk. Nothing else deleted.
- **Behavior**: Delete exactly these paths (recursively for directories); treat an already-absent path as success (idempotent):
  - `~/.claude/skills/.pytest_cache/`
  - `~/.claude/skills/.serena/`
  - `~/.claude/skills/run-autopilot/.pytest_cache/`
  - `~/.claude/skills/run-autopilot/.serena/`
  - `~/.claude/skills/run-autopilot/scripts/.pytest_cache/`
  - `~/.claude/skills/run-autopilot/scripts/.serena/`
  - `~/.claude/skills/run-autopilot/scripts/__pycache__/`
  - `~/.claude/skills/review-work-completion/scripts/.pytest_cache/`
  - `~/.claude/skills/review-work-completion/scripts/__pycache__/`
  - `~/.claude/skills/survey/scripts/.pytest_cache/`
  - `~/.claude/skills/survey/scripts/.ruff_cache/`
  - `~/.claude/skills/survey/scripts/__pycache__/`
  - `~/.claude/skills/create-prd/.serena/`
  - `~/.claude/skills/work/.serena/`
  - `~/.claude/skills/work/SKILL.md.2026-06-12.bak`
  - `~/.claude/skills/work/references/attempt-logging.md.2026-06-12.bak`

#### Feature: Make audit-echo report script executable

- **Description**: Fix the missing executable bit.
- **Inputs**: `~/.claude/skills/audit-echo/scripts/report.py`.
- **Outputs**: Same file with `+x`.
- **Behavior**: `chmod +x` on exactly that file. Other non-executable `.py` files under skills are test/library files invoked via `python3` and stay as-is.

### Capability: Metadata and registration

Bring frontmatter and repo tracking up to the house conventions.

#### Feature: Rewrite assess-evolution description

- **Description**: Shrink the 449-char description under the 250-char visibility limit.
- **Inputs**: `~/.claude/skills/assess-evolution/SKILL.md` frontmatter.
- **Outputs**: A trigger-led description of at most 250 characters.
- **Behavior**: Keep the existing trigger phrases ("evolution audit", "assess this project", "health-check the codebase", "what should we refactor"); start with "Use when"; drop the inline feature tour. No other frontmatter or body change in this feature.

#### Feature: Track untracked skills in dotfiles repo

- **Description**: Commit the two never-committed skills.
- **Inputs**: `~/.claude/skills/assess-evolution/` (after the description rewrite) and `~/.claude/skills/review-discovery-doc/`.
- **Outputs**: Both dirs tracked in `~/.buvis`.
- **Behavior**: Use the bare-repo form `git --git-dir=/Users/bob/.buvis --work-tree=/Users/bob add <paths>` then commit (conventional message; this repo takes no CHANGELOG entries). PRD 00045 later restructures `review-discovery-doc`; committing now preserves pre-restructure history. `brief-portfolio` is also untracked but in active development (2026-07-07); leave its tracking to the user, do not commit it.

#### Feature: Add frontmatter to review-with-doubt command

- **Description**: Give the lone command a real description.
- **Inputs**: `~/.claude/commands/review-with-doubt.md` (currently no frontmatter).
- **Outputs**: Same file with a YAML frontmatter block containing `description:` (trigger-led, at most 250 chars, covering: skeptical self-review before finalizing work, doubt review; no phase-numbered wording - PRD 00015, earlier by sequence, dissolves the standalone doubt phase into a review lens).
- **Behavior**: Prepend frontmatter only; body stays byte-identical. The invocation name `/review-with-doubt` derives from the filename and must not change (it is dispatched by name; post-00015 it remains the manual doubt-review entry).

#### Feature: Repair stale cross-references

- **Description**: Fix one-line references to things that do not exist.
- **Inputs/Outputs**: The three files below, edited in place.
- **Behavior**:
  - `~/.claude/skills/agent-sort/SKILL.md`: replace the hand-off target `audit-skills` with `claude-checkup:audit-authoring` (no skill named `audit-skills` exists).
  - `~/.claude/skills/catchup-ecc/SKILL.md`: replace `/tmp/ecc-commits.txt` with `dev/local/tmp/ecc-commits.txt` (working-documents rule: no `/tmp`).
  - `~/.claude/skills/extract-plugin/SKILL.md`: the reference to `~/.claude/agents/` points at a missing directory; verify with `ls`, then correct the path to the real location or delete the mention.
  - Out of scope: `council`'s stale references (PRD 00046 restructures council and fixes them there).

#### Feature: Validator sweep

- **Description**: Prove the hygiene bar.
- **Inputs**: Every dir in `~/.claude/skills/*/`.
- **Outputs**: Validator summary pasted into the task output (fail-loud: report counts, not "passed").
- **Behavior**: Run `python3 ~/.claude/skills/create-skill/scripts/validate_skill.py <skill-dir>` per dir. Acceptance: 0 `[ERROR]`; only `[WARN]`s are the two over-500-line bodies (run-autopilot, work).

## Structural Decomposition

### Repository Structure

```
~/.claude/
├── skills/                      # Maps to: Filesystem hygiene, Metadata and registration
│   ├── (16 junk paths deleted)
│   ├── assess-evolution/SKILL.md    # description rewrite, then tracked
│   ├── review-discovery-doc/        # tracked
│   ├── agent-sort/SKILL.md          # stale-ref fix
│   ├── catchup-ecc/SKILL.md         # stale-ref fix
│   ├── extract-plugin/SKILL.md      # stale-ref fix
│   └── audit-echo/scripts/report.py # chmod +x
└── commands/review-with-doubt.md    # frontmatter added
```

### Module: skills-tree

- **Maps to capability**: Filesystem hygiene, Metadata and registration
- **Responsibility**: Skill sources and their metadata, free of dev leftovers
- **Exports**: validated `SKILL.md` files, executable `audit-echo/scripts/report.py`

### Module: commands-tree

- **Maps to capability**: Metadata and registration
- **Responsibility**: The `review-with-doubt` command with proper frontmatter
- **Exports**: `/review-with-doubt` (name unchanged)

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies; built first.

- **skills-tree (purge, archive, chmod, description rewrite, stale-ref fixes)**: independent edits
- **commands-tree (frontmatter)**: independent edit

### Core Layer (Phase 1)

- **dotfiles tracking**: depends on [assess-evolution description rewrite] (commit the fixed version)

### Integration Layer (Phase 2)

- **validator sweep**: depends on all Phase 0 and Phase 1 edits

## Implementation Phases

Execution-time premise rule: the evidence behind these tasks is a 2026-07-07 audit snapshot and the tree keeps moving (brief-portfolio went from TODO scaffold to live skill mid-audit). Every task re-verifies its stated premise before acting; a failed premise means skip that action and report it, never force it.

### Phase 0: Foundation

**Goal**: All mechanical edits done.

**Tasks**:

- [ ] Purge cache and backup artifacts (no deps) - Acceptance: every path on the deletion list absent; each path re-verified untracked (`git ls-files`) immediately before its deletion; `git --git-dir=/Users/bob/.buvis --work-tree=/Users/bob status` shows no deletions of tracked files
- [ ] Make audit-echo report script executable (no deps) - Acceptance: `test -x ~/.claude/skills/audit-echo/scripts/report.py` succeeds
- [ ] Rewrite assess-evolution description (no deps) - Acceptance: description at most 250 chars, starts "Use when", validator warning gone
- [ ] Add frontmatter to review-with-doubt command (no deps) - Acceptance: file starts with `---`, has `description:` at most 250 chars, body byte-identical after the block; if frontmatter already exists at execution time, skip and report instead of prepending
- [ ] Repair stale cross-references (no deps) - Acceptance: `rg -n "audit-skills" ~/.claude/skills/agent-sort/` empty; `rg -n "/tmp/ecc-commits" ~/.claude/skills/catchup-ecc/` empty; the `~/.claude/agents/` mention in extract-plugin resolved; each fix applied only after re-verifying the stale text still exists at execution time

**Exit Criteria**: Every Phase 0 acceptance check passes; working tree contains only the intended edits.

### Phase 1: Core

**Goal**: New skills tracked in the dotfiles repo.

**Tasks**:

- [ ] Track untracked skills in dotfiles repo (depends on: Phase 0) - Acceptance: `git --git-dir=/Users/bob/.buvis --work-tree=/Users/bob ls-files .claude/skills/assess-evolution .claude/skills/review-discovery-doc` lists both SKILL.md files

**Exit Criteria**: Both skills appear in `git ls-files` output.

### Phase 2: Integration

**Goal**: Hygiene bar proven.

**Tasks**:

- [ ] Validator sweep (depends on: Phase 1) - Acceptance: 0 `[ERROR]` across all skills except brief-portfolio (excluded, active development); only length `[WARN]`s for run-autopilot and work; counts pasted in output

**Exit Criteria**: Success metrics above all hold.

## Test Strategy

### Critical Scenarios

- **Happy path**: run the validator across all skills → Expected: 0 errors, exactly the two known length warnings
- **Edge case**: a purge-list path already absent → Expected: treated as done, no error, no retry loop
- **Error case**: a tracked file turns up in the purge list at run time → Expected: stop and report; never delete tracked files

No runtime code changes ship in this PRD, so no new automated tests; the validator sweep and the acceptance `rg`/`ls`/`git` checks are the verification.

## Risks

- **brief-portfolio is in active development**: deliberately untouched by this PRD; do not clean, validate, or commit anything under `~/.claude/skills/brief-portfolio/`.
- **Bare-repo git mistakes**: this tree is the `$HOME` work-tree of the bare repo `~/.buvis`; always use the explicit `--git-dir/--work-tree` form. No CHANGELOG entries in this repo (dotfiles exemption).
- **Validator path drift**: use the create-skill copy (`~/.claude/skills/create-skill/scripts/validate_skill.py`), not a version-pinned plugin cache path.
