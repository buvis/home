# Agoge Plugin Extraction: buvis/claude-agoge

Source: `dev/local/discovery/00091-product-qa-agent-pack.md` (PRD 5 of 5; depends on 00100-00102 being done).

## Overview

### Problem Statement

The pack lives in `~/.claude` as personal agents and a skill, which makes it meta-spend and single-machine. Extraction turns it into product: a released buvis plugin others (and other machines) can install from the marketplace.

### Target Users

Any Claude Code user installing from the buvis marketplace; the author, whose meta-budget stops carrying the pack.

### Success Metrics

- `extract-plugin` check-readiness passes on the pack with zero rewrites (the discovery's extraction-clean success criterion).
- Plugin installs from the marketplace; all seven agents dispatch and `/run-agoge` invokes from the plugin, not from `~/.claude` copies.
- First release tagged and live via `dev/bin/release`.

## Functional Decomposition

### Capability: Plugin Packaging

#### Feature: Repo Assembly
- **Description**: Extract agents + skill into a canonical buvis plugin repo.
- **Inputs**: `~/.claude/agents/{olivia,walter,heidi,judy,wendy,peggy,trudy}.md`, `~/.claude/skills/run-agoge/` (aegis and strunk repos as structural templates).
- **Outputs**: `~/git/src/github.com/buvis/claude-agoge` with `.claude-plugin/plugin.json` (exactly the four standard keys: `{name, version, description, author: {name: "buvis"}}`), `agents/` and `skills/` at plugin root relying on auto-discovery, README, CHANGELOG, LICENSE, `dev/bin/release`. No `hooks/` (the pack ships none; the batch-drain wiring is explicitly excluded below).
- **Behavior**: extract-plugin Phase 5 literal `cp` of flat agent files; skill references use `${CLAUDE_SKILL_DIR}` pathing (already true from 00100/00101; premise: the source files are still extraction-clean at execution time - re-run the personal-path grep before copying, and if residue crept in, fix it in `~/.claude` first, then re-check, never patch only the copies).

#### Feature: Exclusions
- **Description**: Keep personal infra personal.
- **Inputs**: The full agoge footprint.
- **Outputs**: A README section stating what intentionally stays out.
- **Behavior**: The autoclaude batch-drain wiring (00102, lives in buvis dotfiles) and the gym (00099, local eval asset at `buvis/agoge-gym`) do not ship in the plugin. README's development section points at the gym repo as the pack's eval.

### Capability: Marketplace Release

#### Feature: Marketplace Registration
- **Description**: Register the plugin in the central buvis marketplace.
- **Inputs**: `~/git/src/github.com/buvis/claude-plugins` checkout.
- **Outputs**: `.claude-plugin/marketplace.json` entry pointing at `https://github.com/buvis/claude-agoge.git`.
- **Behavior**: Same entry shape as the existing shipped plugins (aegis, strunk, warden); pushed to the marketplace repo.

#### Feature: First Release
- **Description**: Cut and publish the first version.
- **Inputs**: Assembled repo, green validations.
- **Outputs**: GitHub repo `buvis/claude-agoge` with the release tag pushed; CHANGELOG carrying the initial entries per `rules/changelog.md`.
- **Behavior**: `dev/bin/release minor` for the initial 0.1.0, matching the shipped-plugin flow.

### Capability: Install Verification

#### Feature: Post-Install Smoke
- **Description**: Prove the marketplace-installed plugin works without the personal copies.
- **Inputs**: Installed plugin; armed CLI gym fixture; personal copies moved aside.
- **Outputs**: A recorded smoke run.
- **Behavior**: With `~/.claude/agents/` agoge files and `~/.claude/skills/run-agoge/` temporarily moved out (restored after), dispatch one plugin agent by name and run `/run-agoge` on the armed CLI fixture end to end. Both must resolve from the plugin.

## Structural Decomposition

### Repository Structure

```
~/git/src/github.com/buvis/claude-agoge/
├── .claude-plugin/
│   └── plugin.json          # Maps to: Plugin Packaging (four standard keys)
├── agents/                  # Maps to: Plugin Packaging (literal cp of the seven)
│   ├── olivia.md
│   ├── walter.md
│   ├── heidi.md
│   ├── judy.md
│   ├── wendy.md
│   ├── peggy.md
│   └── trudy.md
├── skills/
│   └── run-agoge/           # Maps to: Plugin Packaging (skill + references)
├── dev/bin/release          # Maps to: Marketplace Release
├── README.md                # Maps to: Exclusions (dev section points at agoge-gym)
├── CHANGELOG.md
└── LICENSE
```

### Module: claude-agoge
- **Maps to capability**: Plugin Packaging
- **Responsibility**: The shippable pack: seven agents + one skill, auto-discovered.
- **Exports**: Plugin `agoge` (agents olivia..trudy, skill `run-agoge`).

### Module: claude-plugins (marketplace entry)
- **Maps to capability**: Marketplace Release
- **Responsibility**: Discoverability and install source.
- **Exports**: `marketplace.json` entry for agoge.

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies within this PRD - built first (external deps: 00100-00102 done; 00099 gym used for the smoke).

- **claude-agoge repo assembly**: Everything else operates on it.

### Core Layer (Phase 1)
- **marketplace entry + first release**: Depends on [repo assembly].

### Integration Layer (Phase 2)
- **post-install smoke**: Depends on [marketplace entry + first release].

## Implementation Phases

### Phase 0: Foundation
**Goal**: Clean extraction into a canonical repo.

**Tasks**:
- [ ] Run extract-plugin check-readiness on the pack (no deps) - Acceptance: zero rewrites reported; `/Users/bob` grep over agents and skill returns nothing; `dev/local` references are allowed in skill prose (repo-relative contract paths) but forbidden in agent bodies (premise re-check recorded).
- [ ] Assemble `buvis/claude-agoge` (depends on: check-readiness) - Acceptance: layout matches the tree above; plugin.json has exactly the four keys; README exclusions section present; local `claude plugin validate`-equivalent checks (create-skill validator, validate-agent.sh) pass on the copies.

**Exit Criteria**: Repo assembled and validated locally.

### Phase 1: Core
**Goal**: Published and installable.

**Tasks**:
- [ ] Push repo to GitHub + register in marketplace (depends on: Phase 0) - Acceptance: marketplace.json entry merged and pushed; repo public at github.com/buvis/claude-agoge.
- [ ] First release via `dev/bin/release minor` (depends on: registration) - Acceptance: tag pushed; CHANGELOG release section populated.

**Exit Criteria**: Installable from the buvis marketplace at a tagged version.

### Phase 2: Integration
**Goal**: Plugin stands alone.

**Tasks**:
- [ ] Post-install smoke with personal copies moved aside (depends on: Phase 1) - Acceptance: one agent dispatches by name and `/run-agoge` completes on the armed CLI fixture, both resolving from the plugin; personal copies restored afterward (dir diff clean).
- [ ] Retire personal copies in favor of the installed plugin (depends on: smoke) - Acceptance: agoge agents/skill served by the plugin only; buvis dotfiles commit records the removal; a follow-up gym scored run still passes the 00099 bar.

**Exit Criteria**: Pack runs from the plugin; `~/.claude` no longer carries copies.

## Test Strategy

### Critical Scenarios
- **Happy path**: install from marketplace → dispatch olivia → `/run-agoge` on armed CLI fixture → report produced.
- **Edge case**: plugin installed while personal copies still present → Expected: no duplicate-agent ambiguity; retirement task removes the copies before this state persists.
- **Error case**: check-readiness finds residue → Expected: fix at the source in `~/.claude`, re-run check, never ship patched-only copies.

## Risks

- **Auto-discovery differences plugin-side** (agents from a plugin vs `~/.claude/agents/`): the post-install smoke is the gate; if plugin agents do not dispatch by bare name, record the actual resolution rule in the README and adjust `run-agoge` dispatch accordingly before retiring personal copies.
- **Marketplace entry drift**: copy an existing shipped plugin's entry shape verbatim (aegis) rather than authoring from memory.
- **Retirement breaks the batch-drain hook** (00102 wiring points at the skill): the retirement task re-runs the 00102 drain simulation after the switch; hook invocation must resolve the plugin skill.
- **Meta-vs-product accounting**: after release, agoge work counts as product per the standing meta-budget rule; note it in the release commit message.
