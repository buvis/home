---
catchup: skip
design: skip
---

# Rename Skills to Action Verbs

## Overview

### Problem Statement

`rules/coding-style.md` requires commands and skills to start with an action verb. Four personal skills violate it: `council` (noun), `agent-sort` (noun-led), `agent-introspection-debugging` (noun-led), `deep-research` (adjective-led). Renaming changes the typed slash-command names, so trigger phrases must survive the rename for model routing, and every consumer reference must be re-pointed.

Rename set (collision-checked 2026-07-07 against all personal and plugin skills; no target name exists anywhere):

| Current | New | Verb |
|---------|-----|------|
| `council` | `convene-council` | convene (already a trigger phrase in its description) |
| `agent-sort` | `sort-agent-setup` | sort (it sorts skills/rules/hooks into DAILY vs LIBRARY) |
| `agent-introspection-debugging` | `debug-stuck-agent` | debug |
| `deep-research` | `research` | research (evocative single word, per naming preference) |

Out of scope: `catchup-ecc` ("catchup" is established verb vocabulary in this setup, e.g. git-ferry's `/catchup`); plugin skills (own repos).

### Target Users

Bob typing slash commands; the model routing on descriptions; every skill or memory file that references the four names.

### Success Metrics

- All four skills live under their new dir names with matching frontmatter `name:` and H1; old dirs gone.
- Old trigger phrases still present in each description (model routing on "council", "agent sort", "deep research", "agent introspection" keeps working).
- Zero skill-denoting references to the old names remain in the swept scope.
- create-skill validator clean on all four renamed skills (name matches dir, description at most 250 chars).

## Functional Decomposition

### Capability: Rename skill directories

Each rename is the same mechanical operation; contracts differ only in names.

#### Feature: Rename council to convene-council

- **Description**: Verb-led rename preserving history and triggers.
- **Inputs**: `~/.claude/skills/council/` (tracked in `~/.buvis`).
- **Outputs**: `~/.claude/skills/convene-council/` with frontmatter `name: convene-council`, H1 updated, description keeping the trigger phrases "council", "convene council", "second opinion", "decision council".
- **Behavior**: `git --git-dir=/Users/bob/.buvis --work-tree=/Users/bob mv .claude/skills/council .claude/skills/convene-council` (history-preserving), then edit frontmatter and H1. Description stays at most 250 chars. Precondition, re-verified at execution time (applies to all four renames): the source dir exists and the target name is absent everywhere (skills and plugin skills); on mismatch, skip that rename and report, and the sweep skips its names too.

#### Feature: Rename agent-sort to sort-agent-setup

- **Description**: Same operation.
- **Inputs**: `~/.claude/skills/agent-sort/`.
- **Outputs**: `~/.claude/skills/sort-agent-setup/` with `name: sort-agent-setup`, H1 updated, description keeping "agent sort", "trim skills for repo", "daily vs library", "project install plan".
- **Behavior**: Same git mv + frontmatter + H1 procedure.

#### Feature: Rename agent-introspection-debugging to debug-stuck-agent

- **Description**: Same operation.
- **Inputs**: `~/.claude/skills/agent-introspection-debugging/` (PRD 00046 adds `references/capture-templates.md`; the mv carries it).
- **Outputs**: `~/.claude/skills/debug-stuck-agent/` with `name: debug-stuck-agent`, H1 updated, description keeping "agent introspection", "debug agent", "agent stuck", "agent loop", "diagnose failure".
- **Behavior**: Same git mv + frontmatter + H1 procedure.

#### Feature: Rename deep-research to research

- **Description**: Same operation.
- **Inputs**: `~/.claude/skills/deep-research/`.
- **Outputs**: `~/.claude/skills/research/` with `name: research`, H1 updated, description keeping "deep research", "research this", "investigate", "literature review".
- **Behavior**: Same git mv + frontmatter + H1 procedure. Note: PRD 00046 pointed `council`'s hand-off at `deep-research` (correct at that time); the sweep below re-points it to `research`.

### Capability: Repoint consumers

#### Feature: Sweep references to old names

- **Description**: Update every skill-denoting reference to the four old names.
- **Inputs**: `rg -n "deep-research|agent-sort|agent-introspection-debugging|council"` over this scope: `~/.claude/skills/`, `~/.claude/commands/`, `~/.claude/rules/`, `~/.claude/CLAUDE.md`, `~/.claude/settings.json`, `~/.claude/hooks/` (if present), `~/.claude/projects/-Users-bob--claude/memory/`.
- **Outputs**: Every hit that denotes one of the four skills (slash command, skill name in prose, path) rewritten to the new name. Hits that are ordinary English ("council" as a word) or historical records stay; list each left-alone hit with a one-line reason in the task output (fail-loud).
- **Behavior**: Excluded from the sweep: `~/.claude/plugins/cache/` (vendored, read-only), `~/.claude/dev/local/` (PRDs, reviews, reports are history), session transcripts. The freshly-edited `convene-council` hand-off to `deep-research` MUST be re-pointed to `research` here.

#### Feature: Validate renamed skills

- **Description**: Prove the rename bar.
- **Inputs**: The four new skill dirs.
- **Outputs**: Validator output pasted (fail-loud, counts not adjectives).
- **Behavior**: `python3 ~/.claude/skills/create-skill/scripts/validate_skill.py <dir>` per renamed skill: zero errors, zero warnings; confirm each old dir is gone and each old name has zero skill-denoting hits in scope.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/
├── convene-council/          # was council        Maps to: Rename skill directories
├── sort-agent-setup/         # was agent-sort
├── debug-stuck-agent/        # was agent-introspection-debugging
├── research/                 # was deep-research
└── (consumers re-pointed)    # Maps to: Repoint consumers
~/.claude/projects/-Users-bob--claude/memory/   # references updated by sweep
```

### Module: renamed skill dirs

- **Maps to capability**: Rename skill directories
- **Responsibility**: Same skill content under verb-led names, history preserved via git mv
- **Exports**: `/convene-council`, `/sort-agent-setup`, `/debug-stuck-agent`, `/research`

### Module: consumer references

- **Maps to capability**: Repoint consumers
- **Responsibility**: Every live pointer resolves to the new names
- **Exports**: none (edits in place)

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies; built first.

- **four directory renames**: independent of each other

### Core Layer (Phase 1)

- **consumer sweep**: depends on [all four renames] (sweep targets must exist under new names)

### Integration Layer (Phase 2)

- **validation**: depends on [consumer sweep]

## Implementation Phases

### Phase 0: Foundation

**Goal**: Skills live under verb-led names.

**Tasks**:

- [ ] Rename council to convene-council (no deps) - Acceptance: new dir exists, old gone, `name:` and H1 match, listed trigger phrases present, description at most 250 chars
- [ ] Rename agent-sort to sort-agent-setup (no deps) - Acceptance: same checks for this pair
- [ ] Rename agent-introspection-debugging to debug-stuck-agent (no deps) - Acceptance: same checks; `references/` content carried over intact
- [ ] Rename deep-research to research (no deps) - Acceptance: same checks for this pair

**Exit Criteria**: Four git mv commits with frontmatter/H1 edits, all acceptance checks green.

### Phase 1: Core

**Goal**: No live pointer names an old skill.

**Tasks**:

- [ ] Sweep references to old names (depends on: Phase 0) - Acceptance: rg over the scoped paths shows zero skill-denoting hits for the four old names; left-alone hits listed with reasons; convene-council's hand-off points at `research`

**Exit Criteria**: Sweep evidence pasted in task output.

### Phase 2: Integration

**Goal**: Proof.

**Tasks**:

- [ ] Validate renamed skills (depends on: Phase 1) - Acceptance: validator clean on all four; old-dir absence and old-name zero-hit checks pasted

**Exit Criteria**: Success metrics all hold.

## Test Strategy

### Critical Scenarios

- **Happy path**: invoke each renamed skill by new slash name → Expected: loads normally (validator name/dir match is the proxy check)
- **Edge case**: "council" as a plain English word in an unrelated file → Expected: left alone, listed with reason
- **Error case**: a git mv fails (target exists, permissions) → Expected: stop and report; never fall back to cp + rm (loses history)

Docs/filesystem-only PRD; verification is validator output plus the rg sweep evidence.

## Risks

- **Typed-command muscle memory**: `/council`, `/agent-sort`, `/deep-research` stop resolving. Accepted by design (user opted in); trigger phrases keep model-side routing working.
- **Sweep false positives**: "council" matches ordinary prose; the skill-denoting judgment is per hit, with left-alone hits reported.
- **Cross-PRD churn**: PRD 00046 (runs earlier) points convene-council's hand-off at `deep-research`; this PRD's sweep re-points it. Expected, harmless.
- **Repo specifics**: `$HOME` work-tree of bare repo `~/.buvis`; use explicit `--git-dir/--work-tree` form; no CHANGELOG entries.
