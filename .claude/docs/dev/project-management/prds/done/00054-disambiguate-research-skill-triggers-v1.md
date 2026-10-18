# Disambiguate Research Skill Triggers

> Source: full-config audit 2026-07-10 (audit-authoring confusable-pair finding + audit-sessions matched-but-uninvoked evidence).
> Target: personal skills in `~/.claude/skills/` (buvis-tracked).

## Overview

### Problem Statement

The personal `research` skill and the built-in `deep-research` skill both claim the phrase "deep research": `research`'s description opens "Use when researching a topic in depth via multi-source synthesis" and lists the trigger "deep research"; `deep-research` is literally named by it. The router cannot choose between them, and session telemetry (30d) shows `research` was never invoked even though the trigger word "investigate" appeared in user text.

Three more personal skills had trigger phrases appear in user text without invoking: `manage-agents-md` ("agents.md"), `review-prd-backlog` ("review backlog", "review prds" — twice), `survey` ("/survey" in prose). One shared cause is plausible (descriptions too generic to win routing); this PRD fixes the four with evidence rather than sweeping all 21 never-invoked skills.

### Target Users

The solo operator whose typed trigger phrases should reliably route to the intended skill.

### Success Metrics

- `research` and `deep-research` descriptions share zero trigger phrases; "deep research" belongs to `deep-research` alone.
- Each of the four skills' descriptions leads with a trigger set that includes the exact phrase the telemetry matched (e.g. `review-prd-backlog` owns "review backlog"/"review prds").
- All four pass the create-skill validator (trigger-led description, ≤250 chars).

### Non-Goals

- Renaming skills (action-verb rename queue is separate work).
- Touching the other 17 never-invoked skills (no evidence they mis-route; several are deliberately rare).
- Editing the built-in `deep-research` skill (not ours).

## Functional Decomposition

### Capability: Unambiguous routing for the four evidenced skills

#### Feature: `research` description rewrite
- **Description**: `research` owns literature review / competitive analysis / technology comparison; drops the phrase "deep research".
- **Inputs**: `~/.claude/skills/research/SKILL.md` frontmatter.
- **Outputs**: description with triggers "research this", "investigate", "literature review", "survey the landscape", "compare technologies"; no "deep research".
- **Behavior**: body unchanged.

#### Feature: Trigger-first descriptions for the other three
- **Description**: `manage-agents-md`, `review-prd-backlog`, `survey` descriptions lead with their telemetry-matched phrases.
- **Inputs**: each skill's SKILL.md frontmatter.
- **Outputs**: descriptions whose first trigger list contains the matched phrase verbatim.
- **Behavior**: bodies unchanged.

## Implementation Phases

### Phase 0: Rewrite and validate
**Tasks**:
- [ ] Rewrite the four frontmatter descriptions (no deps). Acceptance: create-skill validator passes on all four dirs; `rg -l "deep research" ~/.claude/skills/research/SKILL.md` returns nothing.
- [ ] Commit to buvis (no deps beyond the rewrite). Acceptance: `git --git-dir=~/.buvis --work-tree=~ log -1` shows the change staged by absolute path.

**Exit Criteria**: validator green; descriptions contain the evidenced trigger phrases.

## Test Strategy

- create-skill validator run per changed skill (the authoring contract for descriptions).
- No pytest surface (frontmatter-only change).

## Risks

- **Over-fitting to one month of telemetry**: matched phrases may be atypical. Mitigation: keep existing sensible triggers, add the evidenced ones; don't remove anything except the colliding "deep research".
