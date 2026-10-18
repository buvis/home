# Agoge Core Pack: Seven Agents + run-agoge Orchestrator

Source: `dev/local/discovery/00091-product-qa-agent-pack.md` (PRD 2 of 5; depends on gym 00099; harnesses 00101, autopilot hook 00102, extraction 00103 follow).

## Overview

### Problem Statement

Autopilot's review pipeline is static and diff-scoped: no lens runs the product, walks a user journey, or checks that the changelog tells the truth. Code-correct, product-wrong changes pass every existing lens and accumulate as autopilot drains PRDs unattended. Agoge fills the product-time layer: named specialist agents that exercise the real product, orchestrated by one skill.

### Target Users

The repo owner running `/run-agoge` on any project, and (from PRD 00102 on) the autopilot batch-drain hook running it unattended.

### Success Metrics

- Named-agent dispatch proven by smoke test before the full roster is built.
- `/run-agoge` on the armed CLI gym fixture (00099) completes end to end: recon → profile → armed dispatch → dedup → report.
- Every CRITICAL gym seed reachable through test or CLI surfaces is caught (full >=70% + 100% CRITICAL bar across both fixtures is PRD 00101's exit, since browser/db/perf/security harnesses land there).
- Report never conflates unverified with passed; `extract-plugin` check-readiness finds zero personal paths in agent bodies.

## Functional Decomposition

### Capability: Agent Registry

Seven flat agent files in `~/.claude/agents/` (joining the reviewer agents PRD 00109 already registered; conventions per plugin-dev `validate-agent.sh` and 00109's files: frontmatter `name` + prose-form `description`, optional `model`/`tools`/`color`). Persona slate: Olivia, Walter, Heidi, Judy, Wendy, Peggy, Trudy (crypto-cast extension; collision-checked 2026-08-03 against `~/.claude/agents/`, the /work personas Tess/Devon/Ivan, and ensemble 00092's cast - Heidi replaced Ivan, which is the /work implementor persona). Agent bodies are extraction-clean: no `/Users/bob`, no `dev/local` paths; output location and report contract arrive via the dispatch prompt.

#### Feature: Dispatch Smoke Test
- **Description**: Prove a named agent in `~/.claude/agents/` is dispatchable before authoring all seven.
- **Inputs**: One minimal agent file (Olivia's skeleton).
- **Outputs**: A dispatch transcript showing the agent ran as its own subagent type and returned a result.
- **Behavior**: Add the skeleton to the existing `~/.claude/agents/` registry, dispatch it via the Agent tool with its name as subagent type. The dispatch mechanism itself is already proven by 00109's reviewer agents; this smoke stays as cheap sanity that agoge's own file and conventions dispatch cleanly. Failure here still halts the PRD; the fallback decision goes back to the user, never silently to prompt-files.

#### Feature: Olivia - Recon
- **Description**: Per-project QA strategy discovery; the only specialist that always runs.
- **Inputs**: Target repo path; existing profile if any.
- **Outputs**: QA profile per the Strategy Profile contract below.
- **Behavior**: Inventories runnable surfaces (test suites, CLI entry points, dev server, browser via Playwright presence, db, external services), assigns each specialist a strategy (armed with concrete tactics, or unarmed with reason), assigns mocking strategy for unreachable externals, may assign durable test authoring to any specialist. Never overwrites human pins/vetoes.

#### Feature: Walter - Journey Walker
- **Description**: Walks end-to-end user journeys through CLI, UI, or API.
- **Inputs**: Dispatch prompt with profile strategy + armed repo path.
- **Outputs**: Findings (journeys broken/degraded) + per-journey verified/unverified status.
- **Behavior**: Executes the real product along documented or inferred journeys; reports what it could not execute as unverified, never passed.

#### Feature: Heidi - Integration Prober
- **Description**: Probes cross-component and external contracts plus db behavior, live where runnable.
- **Inputs**: Profile strategy (live targets, mocking strategy for unreachable externals).
- **Outputs**: Findings; each probe labeled live or mocked; mocked probes never report verified.
- **Behavior**: Exercises contracts with real calls where reachable; applies Olivia's mocking strategy otherwise and says so.

#### Feature: Judy - UX Critic
- **Description**: Drives the real UI and critiques user-facing behavior.
- **Inputs**: Profile strategy (browser surface: Playwright project or interactive browser).
- **Outputs**: Findings + loud skip when no browser surface exists.
- **Behavior**: In this PRD, Judy ships with charter and skip behavior; her real browser harness lands in 00101.

#### Feature: Wendy - Release Warden
- **Description**: Checks upgrade path, changelog-vs-behavior truth, docs truthfulness, breaking-change fallout.
- **Inputs**: Armed repo with git history, tags, changelog, docs.
- **Outputs**: Findings (lying changelog, undocumented breakage, broken upgrade).
- **Behavior**: Diffs claimed behavior (changelog, README) against observed behavior from actually running the product.

#### Feature: Peggy - Performance Prober
- **Description**: Probes runtime performance of real commands and endpoints.
- **Inputs**: Profile strategy (what to measure, any stated budgets).
- **Outputs**: Findings with measured numbers; unverified where nothing runnable.
- **Behavior**: Charter + gap analysis in this PRD; measurement harness lands in 00101.

#### Feature: Trudy - Runtime Security Prober
- **Description**: Probes runtime security behavior on own/authorized projects only.
- **Inputs**: Profile strategy; authorization is asserted in the profile.
- **Outputs**: Findings; refuses to run without the profile's own-project assertion.
- **Behavior**: Charter + gap analysis in this PRD; probing harness lands in 00101.

### Capability: Strategy Profile

#### Feature: Profile Contract
- **Description**: One content contract, one landing spot.
- **Outputs**: A self-contained `dev/local/agoge-profile.md` in the target repo (named keeper, survives dev/local GC).
- **Inputs**: Olivia's recon output; human edits.
- **Behavior**: Sections: surfaces, per-specialist strategy (armed/unarmed + tactics), mocking strategy, authoring assignments, pins/vetoes (human-owned, machine never edits, and carrying Trudy's authorization assertion), freshness stamp.
- **AMENDED 2026-08-04 (operator decision).** The cartographer atlas was specified as a second, preferred landing spot (`qa` layer in `atlas.json` + an `atlas.md` section). Premise re-verified before building and it fails: `/survey --refresh` rebuilds `atlas.md` wholesale, so a planted `## QA strategy` section is wiped (proven with sentinels in a throwaway HOME; only the `[manual]` block in `atlas.json` survived), and `cartographer-recon-brief` injects only the first 1024 bytes of `atlas.md`, so an appended section never reaches a session even between surveys. The one durable slot is a JSON blob outside the target repo, which is a worse home for the human-owned pins section than a file in the repo. The atlas spot is dropped; Phase 1 task 2's acceptance drops its atlas half with it.

### Capability: Orchestration

The `run-agoge` skill. Fan-out is skill-internal direct parallel dispatch - workflow-script orchestration was rejected in discovery 00091 (no plugin packaging story; extraction 00103 needs the pack portable). Boundary rule, scoped: long-running processes and external CLIs inside any lane run as background Bash (Watcher pattern); the specialists themselves are Agent dispatches - the discovery's CLI-lane boundary governs what runs inside lanes, not the lanes. Subagent dispatch discipline per `work/references/subagent-dispatch.md` (50KB prompt budget, watchdog, abort wiring).

#### Feature: Arm and Dispatch
- **Description**: Dispatch armed specialists only, in parallel.
- **Inputs**: Target repo; profile (refreshed via Olivia when missing or stale).
- **Outputs**: Specialist findings from every armed specialist; behavioral gap analysis always runs regardless of arming.
- **Behavior**: Only armed specialists dispatch (cost gate); vetoed strategies never run; each dispatch prompt carries the finding contract (repo-relative paths, domain, severity CRITICAL|HIGH|MEDIUM|LOW, evidence, verified|unverified|mocked|skipped status).

#### Feature: Dedup and Merge
- **Description**: Collapse cross-specialist duplicates (a dead integration also breaks journeys).
- **Inputs**: All specialist findings.
- **Outputs**: One deduped finding list.
- **Behavior**: Evidence-keyed dedup (normalized path + symptom, review-fanout style); on merge, keep the strictest severity and union the evidence.

#### Feature: Report and Findings Flow
- **Description**: One actionable improvement plan per run.
- **Inputs**: Deduped findings; run mode (interactive or unattended).
- **Outputs**: Report at `dev/local/audit-results/agoge-<date>.md`: summary header with per-lane verified/unverified/mocked/skipped counts, findings as walkthrough-shaped packets (`rules/communication.md`), verbatim how-to-proceed block at the end.
- **Behavior**: Interactive: walk findings per the findings-walkthrough protocol; record accepted/deferred/rejected in the report (PRD emission for accepted findings lands in 00102). Unattended: write packets and stop; never auto-emit PRDs. Unverified is never reported as passed.

## Structural Decomposition

### Repository Structure

```
~/.claude/
├── agents/                      # Maps to: Agent Registry
│   ├── olivia.md                # Maps to: Olivia - Recon
│   ├── walter.md                # Maps to: Walter - Journey Walker
│   ├── heidi.md                 # Maps to: Heidi - Integration Prober
│   ├── judy.md                  # Maps to: Judy - UX Critic
│   ├── wendy.md                 # Maps to: Wendy - Release Warden
│   ├── peggy.md                 # Maps to: Peggy - Performance Prober
│   └── trudy.md                 # Maps to: Trudy - Runtime Security Prober
└── skills/run-agoge/
    ├── SKILL.md                 # Maps to: Orchestration
    └── references/
        └── finding-contract.md  # shared finding/report/profile contracts
```

### Module: agents
- **Maps to capability**: Agent Registry
- **Responsibility**: One charter per specialist; extraction-clean bodies; validate-agent-conformant frontmatter.
- **Exports**: Seven dispatchable subagent types (olivia, walter, heidi, judy, wendy, peggy, trudy).

### Module: run-agoge
- **Maps to capability**: Orchestration, Strategy Profile
- **Responsibility**: Profile lifecycle, armed dispatch, dedup, report, walkthrough.
- **Exports**: `/run-agoge [repo-path]`; `references/finding-contract.md` consumed by dispatch prompts and by the gym scorer (00099).

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **agents (smoke skeleton)**: Proves the dispatch mechanism the rest of the PRD stands on.

### Core Layer (Phase 1)
- **agents (full roster)**: Depends on [smoke skeleton].
- **finding-contract.md**: Depends on [smoke skeleton] (contract must match what dispatched agents can actually return).

### Integration Layer (Phase 2)
- **run-agoge**: Depends on [agents, finding-contract.md]; scored against [00099 gym].

## Implementation Phases

### Phase 0: Foundation
**Goal**: Named-agent dispatch proven.

**Tasks**:
- [ ] Create `~/.claude/agents/olivia.md` skeleton and dispatch it by name (no deps) - Acceptance: dispatch returns the agent's structured result; `validate-agent.sh` passes on the file. On failure: stop the PRD and park with the transcript (premise: named `~/.claude/agents/` files are dispatchable as subagent types; this is exactly what the smoke test checks).

**Exit Criteria**: Smoke dispatch green.

### Phase 1: Core
**Goal**: Full roster + contracts.

**Tasks**:
- [ ] Write `references/finding-contract.md` (finding, report, profile contracts as specified above) (depends on: Phase 0) - Acceptance: 00099's `bin/score` parses a hand-written conforming report.
- [ ] Author Olivia fully + profile writing (depends on: Phase 0) - Acceptance: on the armed CLI fixture Olivia writes `dev/local/agoge-profile.md`; pins/vetoes in a pre-seeded profile survive a re-run byte-identical. (Atlas half struck 2026-08-04, see the Profile Contract amendment.)
- [ ] Author walter/heidi/judy/wendy/peggy/trudy charters (depends on: Phase 0) - Acceptance: all pass `validate-agent.sh`; `rg "/Users/bob|dev/local" ~/.claude/agents/{olivia,walter,heidi,judy,wendy,peggy,trudy}.md` returns nothing.

**Exit Criteria**: Seven valid agents; contract file consumed by scorer.

### Phase 2: Integration
**Goal**: End-to-end orchestrated run, scored.

**Tasks**:
- [ ] Build `run-agoge` SKILL.md (profile lifecycle, armed dispatch, dedup, report, walkthrough/unattended split) (depends on: Phase 1) - Acceptance: skill passes create-skill validator and live-profile lints.
- [ ] Scored run on the armed CLI gym fixture (depends on: run-agoge) - Acceptance: `bin/score` shows every CRITICAL seed with a test/CLI-reachable surface caught; report shows Judy loud-skipped (no browser surface); no lane reports passed without execution evidence.

**Exit Criteria**: End-to-end run on the gym CLI fixture with the partial bar above met.

## Test Strategy

### Critical Scenarios
- **Happy path**: `/run-agoge` on armed CLI fixture → Expected: profile written, armed specialists dispatched, deduped report with how-to-proceed block.
- **Edge case**: profile has a human veto on Peggy → Expected: Peggy not dispatched, report says vetoed, veto text untouched.
- **Error case**: a specialist dies mid-run → Expected: its lane reported unverified with the failure, other lanes unaffected, run completes.

## Risks

- **Named-agent dispatch quirks** (mechanism proven by 00109's reviewer agents; residual risk is agoge-specific conventions): Phase 0 smoke test stays as cheap sanity; hard stop, no silent fallback.
- **Convention drift vs reviewer ensemble**: resolved - 00109 landed first; adopt its agent-file conventions.
- **7-way fan-out cost**: only armed specialists dispatch; gap analysis is the only always-on layer; meta-budget watched via portfolio brief.
- **Report shape vs scorer**: 00099's scorer may need a follow-up tweak once the report contract is exercised for real (accepted in discovery Q11).
