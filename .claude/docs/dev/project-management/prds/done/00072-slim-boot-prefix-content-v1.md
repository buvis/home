---
design: skip
---

# Slim the Always-Loaded Boot Prefix Content

## Overview

### Problem Statement

Every session boots with a median 57.4K-token prefix re-read on every turn
(~3,500 turns/day; 44% of weighted spend is cache-read, triage
`dev/local/audit-results/2026-07-14-cost-speed-quality-triage.md`). Three
controllable slices: `~/.claude/rules/` (29.1KB, much of it prose duplicating
what aegis/warden hooks hard-enforce), the always-listed catalog of 36 personal
skills, and LSP plugins enabled for languages not in active use. Out of scope:
pidash hook removal (PRD 00063), strunk-via-hook JIT delivery (PRD 00064),
`skillListingBudgetFraction` tuning (semantics unverified).

### Target Users

The operator and every future agent session in every project.

### Success Metrics

- `wc -c ~/.claude/rules/*.md` total <= 8192 bytes (raised from the original
  12288 target per the 2026-07-14 walkthrough decision, finding 6; per-file
  verdicts in `dev/local/audit-results/2026-07-14-claude-setup-brutal-review.md`
  section U2).
- Personal skills dir contains only DAILY skills; dormant ones relocated, none deleted.
- First-turn context of a fresh `claude -p` session in `~/.claude` drops by >= 8K tokens vs the 57.4K baseline.

## Functional Decomposition

### Capability: Rules diet

Shrink `rules/` to guidance hooks cannot express; point to enforcement for the rest.

#### Feature: Dedupe enforced prose
- **Description**: Replace rule text that aegis/warden already hard-enforce with a one-line pointer to the enforcing hook.
- **Inputs**: `rules/tools.md`, `rules/coding-style.md` (Warnings section), `rules/development-workflow.md` (commit message format), `rules/working-documents.md` (dev/local write mechanics).
- **Outputs**: trimmed files, each keeping a pointer line naming the enforcing hook and its plugin doc.
- **Behavior**: Premise per deletion, re-checked at execution: the named enforcer exists in the enabled plugin cache (`prefer_tools.py`, `block-suppression-markers.py`, `validate_commit_msg.py`, `block_devlocal_redirects.py` under `~/.claude/plugins/cache/buvis-plugins/aegis/<latest>/`); if an enforcer is missing, keep that prose and report. Byte targets: tools.md ~1600 (PROTECTED, keep verbatim: Search Strategy section for missing Grep/Glob, ripgrep regex notes), development-workflow.md ~1300 (keep commit/push policy overrides and git safety), coding-style.md ~1400, working-documents.md ~900.

#### Feature: Relocate the rationalizations catalog into echo payloads
- **Description**: Deliver the rationalizations content at violation time instead of every session. The embedding ALREADY EXISTS (verified 2026-07-18: `_RATIONALIZATIONS_PATH` at `hooks/cartographer-echo.py:562` loads the file at runtime and deny messages cite the excuses); the remaining work is the move: relocate the catalog to `~/.claude/rules-library/`, update `_RATIONALIZATIONS_PATH`, keep a <= 200B pointer in rules/.
- **Inputs**: `rules/rationalizations.md` (3174B), `hooks/cartographer-echo.py` (`_RATIONALIZATIONS_PATH`), `hooks/tests/test_cartographer_echo.py`.
- **Outputs**: catalog in `rules-library/`; `_RATIONALIZATIONS_PATH` updated; pointer in place; deny payload text byte-identical before/after the move (attribution already present - the 2026-07-14 canary showed unattributed injections get refused as prompt injection).
- **Behavior**: Premise, re-checked at execution: cartographer-echo.py is the ONLY runtime reader (`rg -l 'rationalizations' ~/.claude/hooks ~/.claude/skills ~/.claude/plugins/cache`; design-solution/SKILL.md mentions are doc text - update the path there too). Echo tests extended to pin the payload text against the new path; move and path update land together so no session boots into a dangling read. Rationale: guidance read at the moment of violation beats guidance taxed on every boot; the channel is the measured 3/3-obeyed one (PRD 00064 Phase 0).

#### Feature: Delete rules that textbook knowledge already covers
- **Description**: Delete `rules/patterns.md` outright and fold-then-delete `rules/security.md` and `rules/code-review.md`; the model does these unprompted and the few local facts survive as single lines elsewhere.
- **Inputs**: `rules/patterns.md` (584B, generic repository/envelope patterns), `rules/security.md` (surviving line: rotate exposed secrets -> AGENTS.md), `rules/code-review.md` (surviving lines: review triggers + N+1 emphasis -> development-workflow.md).
- **Outputs**: three files deleted; two surviving lines folded; buvis commit records the deletions.
- **Behavior**: Premise, re-checked at execution: `rg -l 'rules/(patterns|security|code-review)\.md' ~/.claude` returns no runtime reader; any hit updates the referrer first. Fold before delete, never lose a normative local statement.

#### Feature: Merge the three personality rules
- **Description**: `critical-thinking.md`, `fail-loud.md`, and `surgical-changes.md` are one personality in three files; merge into a single `operating-principles.md`, cutting roughly a third.
- **Inputs**: the three files (409 words combined).
- **Outputs**: one merged file; three originals deleted; every normative statement preserved or consciously dropped in the commit message.
- **Behavior**: Merge is content-preserving first, then condensed; the review lenses judge the drops.

#### Feature: Condense advisory rules
- **Description**: Tighten prose without dropping meaning in the remaining files.
- **Inputs**: testing.md.
- **Outputs**: same rules, fewer bytes (target: ~1100).
- **Behavior**: Keep every normative statement; cut examples, tables, and restatements. Untouched: communication.md, writing.md, memory.md, claude-tooling.md, ai-app-design.md, changelog.md, AGENTS.md, rules/python/*. Aegis-owned deny texts (prefer_tools and friends) are OUT of scope here - a follow-up in the claude-aegis repo can absorb tools.md scar-tissue into its deny messages.

### Capability: Skill catalog sort

Only skills that earn their catalog slot stay always-listed.

#### Feature: Measure skill usage
- **Description**: Count Skill-tool invocations per personal skill over the last 60 days of transcripts.
- **Inputs**: `~/.claude/projects/*/*.jsonl` (all projects), skill names from `~/.claude/skills/*/SKILL.md`.
- **Outputs**: `dev/local/tmp/00072-skill-usage.json` mapping skill name to invocation count.
- **Behavior**: Parse assistant tool_use records with name `Skill`. Canary premise, re-checked at execution: the parser finds >= 1 `create-prd` invocation dated 2026-07-14 (this PRD's authoring session); zero canary hits means the parse is wrong - stop and report, do not classify.

#### Feature: Relocate dormant skills
- **Description**: Move personal skills with 0 invocations in 60 days to `~/.claude/skills-library/`, excluding a protected DAILY allowlist.
- **Inputs**: usage JSON; allowlist: work, run-autopilot, plan-tasks, create-prd, create-skill, design-solution, elicit-requirements, review-work-completion, review-blindly, review-with-doubt, review-prd-backlog, review-plan, purge-devlocal, survey, brush, brief-portfolio (PRD 00081 edits it this batch), use-codex, use-gemini, use-qwen, use-sonnet.
- **Outputs**: `mv` per dormant skill dir; one line added to AGENTS.md Conventions: dormant skills live in `~/.claude/skills-library/`, `mv` back to reactivate.
- **Behavior**: Premise per move, re-checked at execution: count is 0 in the fresh measurement AND the skill is not referenced by another skill's `## Dependencies` section (`rg -l '<name>' ~/.claude/skills/*/SKILL.md`); referenced or nonzero means keep and report. Moves only, no deletions; `skills-library/` is buvis-tracked.

### Capability: Plugin trim

#### Feature: Disable unused LSP plugins
- **Description**: Turn off lua-lsp and swift-lsp in `settings.json` enabledPlugins; verify pr-review-toolkit stays disabled (absent from enabledPlugins or false - it is absent as of 2026-07-18).
- **Inputs**: `settings.json`; active-repo language scan.
- **Outputs**: both flags false.
- **Behavior**: Premise, re-checked at execution: `find ~/git/src -name '*.lua' -o -name '*.swift' -mtime -90` (excluding vendored dirs and `~/git/src/github.com/tbouska/playground-hardware*`) returns nothing; any hit keeps that plugin enabled and reports it.

## Structural Decomposition

### Repository Structure

```
~/.claude/
├── rules/                        # Maps to: Rules diet (trim in place)
├── rules-library/                # Maps to: Demote reference-only rules (new)
├── skills/                       # Maps to: Skill catalog sort (DAILY survivors)
├── skills-library/               # Maps to: Relocate dormant skills (new)
├── AGENTS.md                     # Maps to: Relocate dormant skills (one pointer line)
├── settings.json                 # Maps to: Plugin trim
└── dev/local/tmp/00072-skill-usage.json  # Maps to: Measure skill usage (ephemeral)
```

### Module: rules
- **Maps to capability**: Rules diet
- **Responsibility**: Always-loaded behavioral guidance only; enforcement lives in hooks.
- **Exports**: trimmed `rules/*.md` with pointer lines.

### Module: skills-sort
- **Maps to capability**: Skill catalog sort
- **Responsibility**: Evidence-based DAILY/LIBRARY split of personal skills.
- **Exports**: `dev/local/tmp/00072-skill-usage.py` (measurement script), relocated skill dirs.

### Module: plugin-flags
- **Maps to capability**: Plugin trim
- **Responsibility**: enabledPlugins hygiene in settings.json.
- **Exports**: updated `enabledPlugins` block.

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **skills-sort (measurement only)**: produces the usage evidence.

### Core Layer (Phase 1)
- **rules**: no dependency on measurement; runs parallel-safe after Phase 0 starts.
- **skills-sort (relocation)**: Depends on [skills-sort measurement].

### Integration Layer (Phase 2)
- **plugin-flags**: Depends on [rules, skills-sort] only for commit ordering; single commit closes the PRD.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Usage evidence exists and parses correctly.

**Tasks**:
- [ ] Write and run `dev/local/tmp/00072-skill-usage.py` (no deps) - Acceptance: JSON written; canary check passes (>= 1 create-prd hit on 2026-07-14); per-skill counts printed.

**Exit Criteria**: Trustworthy per-skill usage counts on disk.

### Phase 1: Core
**Goal**: Rules trimmed, dormant skills relocated.

**Tasks**:
- [ ] Trim the four enforced-prose rules with premise re-checks (no deps) - Acceptance: each trimmed file contains a pointer naming its enforcer; enforcer file exists in plugin cache; protected tools.md sections byte-identical.
- [ ] Move rationalizations to rules-library + update `_RATIONALIZATIONS_PATH` (no deps) - Acceptance: echo tests pin the attributed payload text against the new path and pass; `rg -l 'rules/rationalizations'` over ~/.claude/hooks ~/.claude/skills empty after path updates; pointer <= 200B; deny payload text unchanged.
- [ ] Delete patterns.md; fold-and-delete security.md and code-review.md (no deps) - Acceptance: premise rg finds no runtime reader; surviving lines present in AGENTS.md / development-workflow.md; files gone.
- [ ] Merge critical-thinking + fail-loud + surgical-changes into operating-principles.md (no deps) - Acceptance: merged file exists, three originals gone, commit message lists every consciously dropped statement.
- [ ] Condense testing.md (no deps) - Acceptance: `wc -c ~/.claude/rules/*.md` total <= 8192.
- [ ] Relocate dormant skills per measurement + allowlist + dependency re-check (depends on: Phase 0) - Acceptance: every moved skill has count 0 and no `## Dependencies` referrer; move list reported; AGENTS.md pointer line present.

**Exit Criteria**: rules/ within byte budget; dormant skills relocated with evidence.

### Phase 2: Integration
**Goal**: Plugin flags set; everything committed; prefix drop verified.

**Tasks**:
- [ ] Disable lua-lsp and swift-lsp after the language-scan premise (depends on: Phase 1) - Acceptance: both false in settings.json, or a reported premise hit keeping one.
- [ ] Commit rules/, rules-library/, skills/, skills-library/, AGENTS.md, settings.json to the buvis bare repo by absolute pathspec, never `-a` (new files need explicit adds; status hides untracked) (depends on: all) - Acceptance: `git --git-dir=$HOME/.buvis --work-tree=$HOME log -1 --stat` lists them.
- [ ] Measure new first-turn context: run `claude -p "reply ok"` in `~/.claude`, parse the fresh transcript's first assistant usage (input + cache_read + cache_creation) (depends on: all) - Acceptance: <= 49K tokens (>= 8K drop vs 57.4K baseline); actual number reported either way.

**Exit Criteria**: rules/ under budget, dormant skills in library, prefix drop measured and reported.

## Test Strategy

### Critical Scenarios
- **Happy path**: fresh session boots, trimmed rules load, gateguard/warden still enforce → Expected: prefix smaller, blocks unchanged.
- **Edge case**: a "dormant" skill is referenced by a DAILY skill's Dependencies → Expected: kept in place and reported, not moved.
- **Error case**: usage parser finds zero Skill invocations anywhere → Expected: canary fails, classification aborts, nothing moves.

## Risks

- **A trimmed rule changes agent behavior subtly**: the review lenses run on this PRD like any other; trims land as one reviewed commit, easy to revert file-wise from buvis history.
- **Deny-payload guidance loses ambience**: relocated rules only surface when a block fires, so rare-path guidance may go unseen for weeks; mitigated by keeping a one-line pointer per relocated rule in the merged operating-principles file.
- **Skill needed next month was moved**: moves are `mv`-reversible and the AGENTS.md pointer documents restore; nothing is deleted.
- **Usage window bias (60d misses quarterly skills)**: allowlist protects pipeline-critical skills; brief-portfolio-style cadence skills survive via their monthly use or get restored on demand.
