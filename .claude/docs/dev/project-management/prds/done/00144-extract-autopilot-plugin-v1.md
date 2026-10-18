---
catchup: force
design_gate: user
---

# Autopilot Plugin Extraction: buvis/autopilot

Source: `projects/-Users-bob--claude/memory/project_next_plugins_to_ship.md` item 1, expanded 2026-08-25. No discovery doc (gate skipped deliberately; PRD 00103 `extract-agoge-plugin` is the working precedent for this shape).

Supersedes nothing. Depends on no other PRD.

## Overview

### Problem Statement

Autopilot is the most differentiated cluster still living as personal config, so it is meta-spend rather than product, and it is single-machine. Two things changed on 2026-08-25 that make extraction both easier and more urgent. First, `~/.agents/` now exists: the autopilot skills are already canonical there and reach `~/.claude/skills/` only as `braid` symlinks, so "extract the skills" is now a question of which repo owns them, not of copying files. Second, agent-plugins.org published a vendor-neutral plugin format that Copilot and Kiro already accept, so the packaging decision made now determines whether the pack is Claude-only forever.

The pack also carries a live hazard that only appears once it runs outside Claude. Two reviewers dispatch out to external CLIs (`bob` via `codex-run.sh`, `carl` via `gemini-run.sh`). `~/.agents/skills` is a native discovery path for Codex and Copilot today, so `review-work-completion` is already reachable from Codex, where Bob's lane would spawn codex inside codex.

### Target Users

Any Claude Code, Copilot, or Kiro user installing from the buvis marketplace. The author, whose meta-budget stops carrying the pack once it counts as product.

### Success Metrics

- `extract-plugin` check-readiness passes with zero rewrites.
- Plugin installs from the buvis marketplace; every shipped skill and agent resolves from the plugin with the `~/.agents` sources removed from `braid`'s projection.
- Running the review phase under Codex spawns zero nested `codex` processes.
- Root `plugin.json` validates against the Agent Plugins v1 schema.

## Functional Decomposition

### Capability: Plugin Packaging

#### Feature: Repo Assembly

- **Description**: Assemble the autopilot cluster into one cross-host plugin repo.
- **Inputs**: `~/.agents/skills/{run-autopilot,plan-tasks,work,review-work-completion,review-blindly,review-plan,use-codex,use-gemini,use-sonnet}/`; `~/.claude/agents/{rita,cora,grace,toby,trent,victor,blake,pat,alice,bob,carl,eve}.md`; `~/.claude/commands/review-with-doubt`; `~/.claude/hooks/enforce_prd_location.py`.
- **Outputs**: `~/git/src/github.com/buvis/autopilot`, laid out per Structural Decomposition below.
- **Behavior**: Skills move (not copy) out of their owning checkout, `~/git/src/github.com/buvis/agent-skills` (created 2026-08-25; `~/.agents/skills/<name>` is a symlink into it, and `~/.claude/skills/<name>` a second hop on top), into the plugin repo, which becomes their new owning source. Each move retires one link in both places. The `claude-` repo-name prefix used by `claude-agoge` is dropped deliberately: this package targets more than Claude. **Premise: all twelve agent files and all nine skills still exist at the paths above and are extraction-clean. Re-run the `/Users/bob` grep and confirm each path at execution time; if residue crept in, fix it in the source and re-check, never patch only the copies. A missing path means skip that item and report, never invent it.**

#### Feature: Dual Manifest

- **Description**: Satisfy the Agent Plugins v1 spec and Claude's native discovery at once.
- **Inputs**: The assembled tree.
- **Outputs**: Root `plugin.json` (Agent Plugins v1) plus `.claude-plugin/plugin.json` (Claude's four standard keys, matching the agoge entry shape).
- **Behavior**: Agent Plugins v1 defines exactly two component types, skills and MCP servers; agents, commands, and hooks are outside v1 and belong under a reverse-domain client namespace. So `skills/` sits at the root where both the spec and Claude find it, while `agents/`, `commands/`, and `hooks/` stay at the root for Claude auto-discovery (proven by agoge) and are additionally declared under `extensions["org.anthropic.claude"]` in the root manifest, so a spec-compliant host reads them as vendor data rather than unknown components. No `mcp.json`: the pack ships no MCP server.

#### Feature: Exclusions

- **Description**: Keep personal infra personal.
- **Inputs**: The full autopilot footprint.
- **Outputs**: A README section stating what intentionally stays out and why.
- **Behavior**: Excluded are the `autoclaude` bash front-end (lives in buvis dotfiles), `~/.claude/dev/local/**` state, `notify.py`, and the `save-session`/`resume-session`/`restore-tasks` trio (already classed in `braid.ignore` as Codex storage workflows with no valid Claude projection, so they are not part of this bundle despite the older memory note listing them). `notify.py` imports autopilot detector modules by `~/.claude` path and must be decoupled before release rather than shipped.

### Capability: Cross-Host Recursion Safety

#### Feature: Self-Dispatch Guard

- **Description**: Stop an external-CLI reviewer from invoking the CLI it is already running inside.
- **Inputs**: The host environment at dispatch time; the target vendor of the runner (`codex` for `codex-run.sh`, `gemini` for `gemini-run.sh`).
- **Outputs**: Either a normal dispatch, or a refusal on a documented non-zero exit with a one-line stderr reason.
- **Behavior**: Each runner script detects whether the current process is already inside its own target vendor's CLI and refuses to spawn a nested instance. Detection reads a vendor-set environment marker present in that CLI's own child processes (guess: the exact marker name per vendor is unverified and must be confirmed empirically in Phase 0 before the guard is written). The refusal reuses the existing graceful-degradation path: `review-work-completion` already treats a non-zero `codex-run.sh`/`gemini-run.sh` exit as a failed reviewer that does not block the cycle, so no new control flow is needed in the skill. Only `bob` and `carl` need this. `alice` and `eve` are native subagents (`eve` pins `model: fable` in frontmatter, no shell-out), so they cannot recurse.

#### Feature: Depth Backstop

- **Description**: Bound recursion even where vendor detection fails or is unavailable.
- **Inputs**: `AUTOPILOT_DISPATCH_DEPTH` from the runner's inherited environment.
- **Outputs**: A refusal identical in shape to the Self-Dispatch Guard once depth exceeds 1.
- **Behavior**: Each runner increments the variable in the environment it exports to its child. It must be exported by the runner script itself, never declared in `settings.json`: that env block is session-only and a nested CLI never sees it. This is the backstop for hosts whose marker is unknown, not the primary guard.

### Capability: Release and Cutover

#### Feature: Marketplace Registration

- **Description**: Register the plugin in the central buvis marketplace.
- **Inputs**: `~/git/src/github.com/buvis/claude-plugins` checkout.
- **Outputs**: `.claude-plugin/marketplace.json` entry pointing at `https://github.com/buvis/autopilot.git`.
- **Behavior**: Copy the shape of the existing agoge entry verbatim rather than authoring from memory.

#### Feature: Braid Cutover

- **Description**: Prevent duplicate unnamespaced commands once the plugin owns the skills.
- **Inputs**: `~/.agents/braid.ignore`; the nine shipped skill names.
- **Outputs**: An updated `braid.ignore` with the nine names under the existing "Claude gets these from plugins" heading.
- **Behavior**: Exactly the treatment already applied to `git-ferry` and `strunk` per the `~/.agents/README.md` policy table. Until this lands, Claude sees each skill twice, once via the braid symlink and once via the plugin.

## Structural Decomposition

### Repository Structure

```
~/git/src/github.com/buvis/autopilot/
├── plugin.json                  # Maps to: Dual Manifest (Agent Plugins v1 + extensions key)
├── .claude-plugin/
│   └── plugin.json              # Maps to: Dual Manifest (Claude's four standard keys)
├── skills/                      # Maps to: Repo Assembly (spec-portable, root per v1)
│   ├── run-autopilot/
│   ├── plan-tasks/
│   ├── work/
│   ├── review-work-completion/
│   ├── review-blindly/
│   ├── review-plan/
│   ├── use-codex/               # Maps to: Self-Dispatch Guard (scripts/codex-run.sh)
│   ├── use-gemini/              # Maps to: Self-Dispatch Guard (scripts/gemini-run.sh)
│   └── use-sonnet/
├── agents/                      # Maps to: Repo Assembly (12 reviewer personas)
├── commands/                    # Maps to: Repo Assembly (review-with-doubt)
├── hooks/                       # Maps to: Repo Assembly (enforce_prd_location.py)
├── dev/bin/release              # Maps to: Marketplace Registration
├── README.md                    # Maps to: Exclusions
├── CHANGELOG.md
└── LICENSE
```

### Module: autopilot-plugin

- **Maps to capability**: Plugin Packaging
- **Responsibility**: The shippable cluster: nine skills, twelve agents, one command, one hook, under a dual manifest.
- **Exports**: Plugin `autopilot` (skills `run-autopilot`..`use-sonnet`, agents `rita`..`eve`, command `review-with-doubt`).

### Module: dispatch-runners

- **Maps to capability**: Cross-Host Recursion Safety
- **Responsibility**: Spawn an external model CLI exactly once per lane, never inside itself.
- **Exports**: `codex-run.sh`, `gemini-run.sh`, both gaining a guard clause and a documented refusal exit code.

### Module: braid-config

- **Maps to capability**: Release and Cutover
- **Responsibility**: Keep the `~/.agents` projection free of names the plugin now owns.
- **Exports**: `~/.agents/braid.ignore` entries for the nine skills.

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first.

- **dispatch-runners**: The guard must exist before the pack can be run under another host at all.

### Core Layer (Phase 1)

- **autopilot-plugin**: Depends on [dispatch-runners]. Assembly ships the guarded runners, not the unguarded ones.

### Integration Layer (Phase 2)

- **braid-config**: Depends on [autopilot-plugin]. Only safe to ignore a name once the plugin actually serves it.

## Implementation Phases

### Phase 0: Foundation

**Goal**: Recursion is impossible before anything ships.

**Tasks**:

- [ ] Empirically identify the vendor environment marker each CLI sets in its own children, for codex and gemini (no deps) - Acceptance: a committed note in `use-codex/references/` naming the exact variable and its observed value, captured from a real nested invocation, or recording that no reliable marker exists for that vendor.
- [ ] Add the self-dispatch guard plus the `AUTOPILOT_DISPATCH_DEPTH` backstop to both runners (depends on: marker identification) - Acceptance: a test asserts each runner exits non-zero without spawning a child when its vendor marker is set, and when depth exceeds 1; a second test asserts a normal unguarded environment still dispatches.
- [ ] Verify the guarded refusal path degrades gracefully in `review-work-completion` (depends on: guard) - Acceptance: a test drives the skill's reviewer-failure branch with the guard's exit code and shows the cycle completes with the remaining reviewers.

**Exit Criteria**: Both runners refuse to nest, and a refusal is indistinguishable from any other failed-reviewer case at the skill level.

### Phase 1: Core

**Goal**: Published and installable.

**Tasks**:

- [ ] Run `extract-plugin` check-readiness over the nine skills and twelve agents (depends on: Phase 0) - Acceptance: zero rewrites reported; `/Users/bob` grep over the assembled tree returns nothing; premise re-check recorded per Feature: Repo Assembly.
- [ ] Decouple `notify.py` from autopilot detector modules (depends on: check-readiness) - Acceptance: `notify.py` imports nothing under `~/.claude/skills`; existing notify tests pass.
- [ ] Assemble `buvis/autopilot` with both manifests (depends on: decoupling) - Acceptance: layout matches the tree above; root `plugin.json` validates against the Agent Plugins v1 schema; `.claude-plugin/plugin.json` carries exactly the four standard keys; README exclusions section present; create-skill validator and validate-agent.sh pass on every copy.
- [ ] Push, register in the marketplace, and cut 0.1.0 via `dev/bin/release minor` (depends on: assembly) - Acceptance: marketplace entry pushed; tag pushed; CHANGELOG release section populated per `rules/changelog.md`.

**Exit Criteria**: Installable from the buvis marketplace at a tagged version.

### Phase 2: Integration

**Goal**: The plugin stands alone and nothing is served twice.

**Tasks**:

- [ ] Add the nine skill names to `~/.agents/braid.ignore` and recompose (depends on: Phase 1) - Acceptance: `braid --check` clean; `~/.claude/skills/` contains no symlink for any of the nine; each skill still invocable, resolving from the plugin.
- [ ] Retire the personal agent copies (depends on: braid cutover) - Acceptance: `~/.claude/agents/` no longer carries the twelve; a buvis dotfiles commit records the removal; one full autopilot cycle runs end to end on a PRD with every reviewer resolving from the plugin.
- [ ] Record the cross-host status in the `~/.agents/README.md` policy table (depends on: retirement) - Acceptance: the table gains an `autopilot` row stating which hosts are tested and which are installable-but-untested.

**Exit Criteria**: Autopilot runs from the plugin; `~/.claude` carries no copies; the policy table is accurate.

## Test Strategy

### Critical Scenarios

- **Happy path**: install from marketplace → `/run-autopilot` on a backlog PRD → all reviewer lanes report → cycle converges.
- **Edge case**: the pack invoked from Codex, where `use-codex` is natively discoverable → Expected: Bob's lane refuses, logs one stderr line, and the cycle completes on the remaining reviewers with zero nested codex processes.
- **Edge case**: plugin installed while braid symlinks still present → Expected: caught by the Phase 2 `braid --check`, which is the gate; duplicate names must not survive the phase.
- **Error case**: vendor marker unavailable for a host → Expected: the depth backstop still bounds recursion at one level; the README records the host as untested rather than claiming support.

## Risks

- **The vendor marker does not exist or is unstable**: Phase 0's first task is allowed to conclude that. The depth backstop is the fallback and is sufficient to prevent unbounded recursion, at the cost of permitting exactly one nested call.
- **Agent Plugins v1 moves under us**: v1 excludes agents by design, so the `extensions` namespace is doing real work and a v2 could relocate it. Pin the spec version in the root manifest and treat a spec bump as its own PRD.
- **Claude and the spec disagree on where agents live**: mitigated by keeping `agents/` at the root (what Claude actually resolves today) and declaring it in `extensions`, rather than choosing one. If Claude stops resolving root `agents/` from a plugin, the agoge pack breaks first and gives warning.
- **Retirement breaks a live batch**: do not retire personal copies mid-batch. The Phase 2 retirement task requires a clean `prds/wip/` before it runs.
- **Meta-vs-product accounting**: after release, autopilot work counts as product per the standing meta-budget rule; note it in the release commit message.
