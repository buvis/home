---
catchup: skip
design: skip
---

# Sharpen Small Skills

## Overview

### Problem Statement

Six small skills waste tokens or point users wrong:

1. `audit-recon` instructs an in-model line-by-line parse of `~/.claude/cartographer/audit.jsonl` (13.7 MB today); its sibling `audit-echo` correctly delegates the same file to `scripts/report.py`. `audit-atlas` likewise computes its stats in-model. Each run burns tens of thousands of tokens that a ~200-token script summary replaces.
2. `manage-agents-md` inlines the progressive-disclosure guide, the minimal template, and the "What NOT to Include" list, all of which already exist in its own `references/` files, so the content loads twice.
3. `council` restates its When-NOT table as an Anti-Patterns section, restates its Roles table as "Role emphasis", carries an illustrative Example section in the hot body, and hands off to skills that do not exist (`research`, `save-session`, an "auto memory" CLAUDE.md section).
4. `agent-introspection-debugging` opens by restating its own frontmatter description, duplicates "When to Activate" inside "Scope Boundaries", repeats Phase 4 as "Output Standard", and inlines three capture templates only needed mid-failure.
5. `review-plan` lists 10 review dimensions including enterprise-only ones (deployment/rollout, timeline realism, resource allocation/budget) that do not apply to a solo developer.
6. `elicit-requirements` states "one question per message" three times (CLAUDE.md already mandates it); `assess-evolution` restates the `rules/ai-app-design.md` core stance.

### Target Users

Bob running the cartographer audit trio, planning reviews, and requirement elicitation; every invocation of these skills.

### Success Metrics

- `audit-recon` and `audit-atlas` runs read only a script summary, not raw data files; each ships a tested `scripts/` entry point.
- Body word counts drop at least 25% for `manage-agents-md`, `council`, and `agent-introspection-debugging` (report before/after).
- Zero references to nonexistent skills remain in `council`.
- create-skill validator clean on all six touched skills.

## Functional Decomposition

### Capability: Script offload for audit trio

#### Feature: Add audit-recon report script

- **Description**: Move the audit.jsonl analysis into a script, mirroring audit-echo.
- **Inputs**: `~/.claude/cartographer/audit.jsonl`; `~/.claude/skills/audit-echo/scripts/report.py` as the structural pattern (stdlib-only Python, argparse, prints a plain-text report).
- **Outputs**: New executable `~/.claude/skills/audit-recon/scripts/report.py` printing one section per stat, section titles verbatim: `Inject uniqueness (repo x day)`, `Missing-atlas repos`, `Stale-at-inject rate`, `Excerpt-size distribution`. New `test_report.py` beside it with a small fixture jsonl.
- **Behavior**: The stats compute exactly what the current SKILL.md prose instructs computing in-model. SKILL.md is rewritten to: run the script, read its summary, interpret findings; the in-model parsing instructions are deleted. Test written fail-first against the aggregate contract (section titles plus counts from the fixture).

#### Feature: Add audit-atlas scan script

- **Description**: Same offload for the atlas health audit.
- **Inputs**: `~/.claude/cartographer/projects/*/` atlas files (the paths the current SKILL.md names); audit-echo's script as pattern.
- **Outputs**: New executable `~/.claude/skills/audit-atlas/scripts/report.py` printing sections titled: `Fresh-atlas coverage`, `Staleness distribution`, `Atlas size`, `Layer population`. New `test_report.py` with a fixture project dir.
- **Behavior**: As above: script computes what the prose currently derives in-model; SKILL.md becomes run-and-interpret. Fail-first test.

### Capability: Deduplicate hot bodies

#### Feature: Slim manage-agents-md

- **Description**: Inline copies become pointers to the existing references.
- **Inputs**: SKILL.md inline progressive-disclosure section, inline minimal template, inline "What NOT to Include" list; existing `references/progressive-disclosure.md`, `references/template.md`, `references/checklist.md`.
- **Outputs**: Body keeps workflow plus one pointer per moved block; H1 renamed to match the skill name (`manage-agents-md`).
- **Behavior**: If an inline copy and its reference file differ, reconcile into the reference file first, then delete the inline copy.

#### Feature: Tighten council

- **Description**: Deduplicate, drop filler, fix dead pointers.
- **Inputs**: `council/SKILL.md`: Anti-Patterns section (duplicates the When-NOT table), "Role emphasis" (duplicates the Roles table), the Example section, and the stale hand-offs.
- **Outputs**: Anti-Patterns merged into the When-NOT table; Role-emphasis merged into the Roles table; Example deleted or moved to `references/example.md`; `research` corrected to `deep-research`; the `save-session` and "auto memory in CLAUDE.md" hand-offs replaced with the real persistence mechanism (the memory directory at `~/.claude/projects/-Users-bob--claude/memory/`) or deleted.
- **Behavior**: The decision-protocol content (roles, rounds, verdict rules) is untouched. PRD 00047 later renames deep-research to research and re-points this hand-off in its sweep; the double touch is expected.

#### Feature: Tighten agent-introspection-debugging

- **Description**: Remove self-restatement; move rare-branch templates out.
- **Inputs**: SKILL.md: the intro line restating the frontmatter description, "When to Activate" vs "Scope Boundaries" overlap, "Output Standard" vs Phase 4 overlap, three inline capture templates.
- **Outputs**: Intro line deleted; When-to-Activate merged into Scope Boundaries; Output Standard deleted where it repeats Phase 4; templates moved to new `references/capture-templates.md` with pointers at their use sites.
- **Behavior**: Phase structure and diagnostic method unchanged.

### Capability: Fit guidance to the user profile

#### Feature: Trim review-plan dimensions

- **Description**: Drop enterprise-only review dimensions.
- **Inputs**: The 10-dimension list in `review-plan/SKILL.md`.
- **Outputs**: The list without deployment/rollout, timeline realism, and resource allocation/budget; remaining dimensions renumbered; a one-line note that enterprise dimensions were dropped for the solo-dev profile.
- **Behavior**: `references/question-examples.md` swept for questions belonging only to the dropped dimensions; those removed too.

#### Feature: Drop global-rule restatements

- **Description**: Skills stop re-teaching what CLAUDE.md and rules/ already load.
- **Inputs**: `elicit-requirements` ("one question per message" three times: SKILL.md, question-bank.md, both duplicating CLAUDE.md); `assess-evolution` (ai-app-design stance restated).
- **Outputs**: One mention each, phrased as a pointer to the global rule; duplicates deleted.
- **Behavior**: No workflow change in either skill.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/
├── audit-recon/
│   ├── SKILL.md                          # run-and-interpret rewrite
│   └── scripts/{report.py, test_report.py}   # NEW
├── audit-atlas/
│   ├── SKILL.md                          # run-and-interpret rewrite
│   └── scripts/{report.py, test_report.py}   # NEW
├── manage-agents-md/SKILL.md             # pointers, H1 fix
├── council/SKILL.md                      # dedup + dead-pointer fixes
├── agent-introspection-debugging/
│   ├── SKILL.md                          # dedup
│   └── references/capture-templates.md   # NEW
├── review-plan/
│   ├── SKILL.md                          # trimmed dimensions
│   └── references/question-examples.md   # swept
├── elicit-requirements/                  # restatement removal
└── assess-evolution/SKILL.md             # restatement removal
```

### Module: audit-trio scripts

- **Maps to capability**: Script offload for audit trio
- **Responsibility**: Deterministic aggregation of cartographer telemetry (code answers, not the model)
- **Exports**: `audit-recon/scripts/report.py`, `audit-atlas/scripts/report.py`, each with tests

### Module: skill bodies

- **Maps to capability**: Deduplicate hot bodies, Fit guidance to the user profile
- **Responsibility**: Lean always-loaded instructions with on-demand references
- **Exports**: slimmed SKILL.md files, `agent-introspection-debugging/references/capture-templates.md`

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies; built first.

- **audit-trio scripts**: fail-first tests then scripts (independent of prose edits)

### Core Layer (Phase 1)

- **SKILL.md rewrites for audit-recon and audit-atlas**: depend on [audit-trio scripts]
- **all other body edits**: no dependencies (grouped here to keep Phase 0 small)

### Integration Layer (Phase 2)

- **verification**: depends on all

## Implementation Phases

Execution-time premise rule: these small skills are user-editable and may have changed since the 2026-07-07 audit (brief-portfolio did, mid-audit). Every edit re-verifies the quoted duplicate or stale text still exists before acting; if a target materially changed, adapt or skip and report.

### Phase 0: Foundation

**Goal**: Tested scripts exist.

**Tasks**:

- [ ] Add audit-recon report script (no deps) - Acceptance: `test_report.py` written first and failing (output pasted), then green; script executable; section titles match the Feature verbatim
- [ ] Add audit-atlas scan script (no deps) - Acceptance: same as above for audit-atlas

**Exit Criteria**: Both scripts executable with green, fail-first-proven tests.

### Phase 1: Core

**Goal**: All prose slimmed and corrected.

**Tasks**:

- [ ] Rewrite audit-recon and audit-atlas SKILL.md to run-and-interpret (depends on: Phase 0) - Acceptance: neither SKILL.md instructs reading the raw data files directly; both instruct running their script
- [ ] Slim manage-agents-md (no deps) - Acceptance: word count down at least 25%; no block duplicated against its references; H1 matches skill name
- [ ] Tighten council (no deps) - Acceptance: word count down at least 25%; `rg -n "save-session|auto memory" ~/.claude/skills/council/` empty; `research` hand-off points at `deep-research`
- [ ] Tighten agent-introspection-debugging (no deps) - Acceptance: word count down at least 25%; `references/capture-templates.md` exists; no section restates another
- [ ] Trim review-plan dimensions (no deps) - Acceptance: dropped dimensions absent from SKILL.md and question-examples.md
- [ ] Drop global-rule restatements (no deps) - Acceptance: "one question" appears at most once in elicit-requirements files; ai-app-design restatement gone from assess-evolution

**Exit Criteria**: All six skill bodies edited per their acceptance checks.

### Phase 2: Integration

**Goal**: Proof.

**Tasks**:

- [ ] Verification (depends on: all) - Acceptance: pytest green for both new test files (counts pasted); create-skill validator clean on all six skills; before/after word counts pasted

**Exit Criteria**: Success metrics all hold.

## Test Strategy

### Critical Scenarios

- **Happy path**: `report.py` on a fixture jsonl/project dir → Expected: all named sections present with correct counts
- **Edge case**: empty or missing audit.jsonl / empty projects dir → Expected: script prints the sections with zero counts and exits 0 (no traceback)
- **Edge case**: malformed jsonl line → Expected: line skipped and counted as `malformed: N` in output, exit 0
- **Error case**: a body edit deletes a rule instead of a duplicate → Expected: review surfaces catch it via the acceptance word-count + rg checks (duplicates are named precisely in the Features)

## Risks

- **Aggregate semantics drift**: the scripts encode what prose described; the fail-first fixture tests pin the contract before the prose is deleted.
- **Council hand-off replacement**: pointing at the memory directory changes a suggestion, not a protocol; if unclear at work time, deleting the dead line is the safe minimum.
- **Repo specifics**: `$HOME` work-tree of bare repo `~/.buvis`; no CHANGELOG entries.
