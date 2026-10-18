---
consensus_engine: shadow
---

# Register Reviewer Agents

> Renumbered 00094 → 00109 on 2026-08-01 (backlog tail resequence; mapping in memory `project_backlog_renumber_2026_08`).

## Overview

### Problem Statement

Reviewer personas are prose scattered across four homes: the consensus
template + Bob/Carl/Quinn appendices in
`review-work-completion/references/agent-prompts.md`, Blake in
`references/blind-lens-prompt.md`, the doubt lens in
`run-autopilot/prompts/doubt-review.md`, five dimension checklists plus rubric
and skeptic prompts inline in `workflows/review-fanout.workflow.js`, and the
per-task patch reviewer assembled ad hoc in `work/SKILL.md` §5.7. No persona
can be tuned per-agent (tools, model), none is plugin-extractable
(`extract-plugin` Phase 5 copies `~/.claude/agents/*.md`, a directory that
does not exist), and the QA pack (00091) needs the registry conventions this
PRD sets. Source: discovery 00092, must-haves 2-5.

### Target Users

The autopilot review stack (consensus, blind, doubt, per-task lenses), the
`review-fanout` workflow, and the future plugin extraction (track F) plus the
QA agent pack (00091), which reuses the conventions.

### Success Metrics

- All 14 personas exist as `~/.claude/agents/*.md`; zero persona prompt text
  remains inline in the workflow JS or in skill reference files.
- On a fixture diff, every dispatch path assembles a prompt byte-identical to
  its pre-extraction prompt (parity on prompt text, not findings).
- A missing-agent-file fixture yields CHANGES_REQUESTED (native lanes) or a
  runner error (CLI lanes). No fallback prompt anywhere.
- Boot-prefix delta from the registry stays ~1-2K tokens (proxy: every
  description one line, ≤120 chars).

## Functional Decomposition

### Capability: Agent Registry
Fourteen named reviewer personas as flat agent files with per-agent tuning.

#### Feature: Registry conventions
- **Description**: File format every registry agent (and later the QA pack)
  follows.
- **Inputs**: Claude Code agent-file format (frontmatter `name`,
  `description`, optional `tools`, `model`).
- **Outputs**: Convention section in `review-work-completion`'s references
  (shared ground with 00091).
- **Behavior**: Flat files in `~/.claude/agents/`; frontmatter `name` +
  one-line `description` (≤120 chars) required; native reviewers carry
  `tools: Read` (no Edit/Write; Victor alone adds Bash; per discovery
  must-have 5), Eve pins `model: fable`; CLI-dispatched personas carry
  name+description only. Bodies contain no personal paths (`/Users/`,
  `~/.claude`) - run-specific content enters via named placeholders
  (`{RUBRIC}`, `{CONTEXT_FILE}`, `{DIFF_FILE}`) substituted by the consuming
  skill, which owns path resolution.

#### Feature: Consensus, blind, and doubt persona files
- **Description**: alice, blake, bob, carl, quinn, eve absorb today's prompt
  sources.
- **Inputs**: `agent-prompts.md` (shared template + appendices),
  `blind-lens-prompt.md`, `prompts/doubt-review.md` (post-00108 ex-00093, D-ids).
- **Outputs**: `agents/{alice,blake,bob,carl,quinn,eve}.md`.
- **Behavior**: alice/quinn/carl/bob bodies are self-contained (shared
  template text inlined per file; appendices merged in). The doubt lens lives
  once, in `eve.md` (decision: it is the native doubt persona's system
  prompt; the existing one-base-file invariant in `agent-invocation.md`
  carries over); `bob.md` holds the codex sandbox appendix, and Bob's
  assembly appends the "Two lenses" + "Rubric verdicts" sections from
  `eve.md`'s body. Rubric text stays in its rubric.md sources, inlined at
  dispatch via placeholder.

#### Feature: Ensemble and patch persona files
- **Description**: rita, cora, grace, toby, mallory, trent, victor, pat
  absorb the workflow's inline prompts and /work's ad hoc reviewer.
- **Inputs**: `DIMENSIONS` entries (requirements→rita, correctness→cora,
  quality→grace, tests→toby, security→mallory), `rubricPrompt`→trent,
  `skepticPrompt`→victor in `review-fanout.workflow.js`; `work/SKILL.md`
  §5.7 prompt parts→pat.
- **Outputs**: `agents/{rita,cora,grace,toby,mallory,trent,victor,pat}.md`.
- **Behavior**: Each body carries the persona + checklist text verbatim
  (cut so that persona body + run-input block reproduces today's assembled
  prompt exactly). `pat.md` keeps the simplification mandate as a
  placeholder referencing `work/references/simplification-mandate.md`
  content, inlined at dispatch.

### Capability: Dispatch From the Registry
Every review lane sources its prompt from agent files; inline sources are
deleted.

#### Feature: Workflow dimension dispatch
- **Description**: `review-fanout` dispatches rita/cora/grace/toby/mallory/
  trent/victor from the registry.
- **Inputs**: agent files; workflow args (diff, context, rubric_text).
- **Outputs**: Same findings/verdict schemas as today.
- **Behavior**: Primary mechanism is `agentType: '<name>'` (persona = agent
  system prompt; run inputs stay in the `agent()` prompt arg). Phase 0 runs a
  probe: a trivial workflow dispatching one registry agent by agentType. If
  the probe shows user-level agents do not resolve in workflows, the decided
  fallback is: the orchestrating skill reads the agent bodies at invocation
  and passes them via workflow args - either way no persona text lives in
  the JS. Security arming, dedup, verify cap, and renderer are unchanged.

#### Feature: Skill-orchestrated lane assembly
- **Description**: The prose-driven lanes assemble prompts from agent files.
- **Inputs**: agent files (frontmatter stripped), gather-context outputs,
  rubric sources, incremental-cycle addenda.
- **Outputs**: Per-agent prompt files in `dev/local/tmp/` (Write tool, as
  today) for CLI lanes; Agent-tool dispatch for native lanes.
- **Behavior**: review-work-completion assembles Alice (legacy leg), Bob,
  Carl, Quinn from their agent bodies + substitutions; Blake from
  `blake.md` + PRD only (stays pack/context-free by construction); Eve from
  `eve.md` via Agent tool with `model: fable` from frontmatter. /work §5.7
  assembles Pat from `pat.md` + task fields + diff + mandate, still
  dispatched through `sonnet-run.sh -f`. CLI runners are untouched (they
  already take `-f` prompt files). Assembly rules live in
  `agent-invocation.md`; `agent-prompts.md`, `blind-lens-prompt.md`, and
  `prompts/doubt-review.md` are deleted. Premise: those three files are
  still the live prompt sources at execution (re-check: no other consumer
  surfaced by `rg`; a new consumer means stop and report, not force).

#### Feature: Fail-closed dispatch
- **Description**: A missing or malformed agent file makes the review fail
  loudly; no fallback prompt.
- **Inputs**: Registry file set at dispatch time.
- **Outputs**: CHANGES_REQUESTED (native) / runner error (CLI) / workflow
  fail-closed verdict.
- **Behavior**: Before dispatch, the orchestrator verifies each roster
  agent file exists and parses (frontmatter has name + description); a
  failure marks that reviewer failed, which the existing retry policy and
  fail-closed verdict logic already escalate. In the workflow, a dimension
  whose agent cannot be dispatched contributes a null result, which the
  existing `decide_verdict` fail-closed path turns into CHANGES_REQUESTED.

### Capability: Registry Verification
Prove parity, fail-closed behavior, and registry hygiene headlessly.

#### Feature: Prompt parity harness
- **Description**: Fixture-diff goldens prove byte-identical assembly.
- **Inputs**: Pre-change assembled prompts captured as goldens for every
  dispatch path; post-change assembly from agent files.
- **Outputs**: Test module(s) in the existing suites (node tests may read
  agent files; the workflow script itself cannot).
- **Behavior**: For each path, golden = today's assembled prompt on the
  fixture; test rebuilds from agent body + run-input block and compares
  bytes. Capture goldens BEFORE deleting inline sources.

#### Feature: Registry hygiene checks
- **Description**: Enforce conventions mechanically.
- **Inputs**: `~/.claude/agents/*.md`.
- **Outputs**: A pytest module in `review-work-completion/scripts/`.
- **Behavior**: Asserts 14 files present; frontmatter valid; description
  ≤120 chars; `tools`/`model` pins per convention (Eve `model: fable`,
  Victor `Read, Bash`, native reviewers no Edit/Write); zero `/Users/` or
  `~/.claude` occurrences in bodies; missing-agent fixture behavior text
  present in the dispatch references.

## Structural Decomposition

### Repository Structure

```
~/.claude/
├── agents/                          # Maps to: Agent Registry (14 files, NEW)
├── skills/review-work-completion/   # Maps to: Dispatch, Verification
│   ├── SKILL.md                     # assembly steps, fail-closed check
│   ├── references/agent-invocation.md   # assembly rules (absorbs deletions)
│   └── scripts/test_agent_registry.py   # hygiene + parity (NEW)
├── skills/run-autopilot/            # Maps to: Dispatch (doubt lane)
├── skills/work/                     # Maps to: Dispatch (Pat lane, §5.7)
└── workflows/                       # Maps to: Workflow dimension dispatch
    ├── review-fanout.workflow.js    # inline prompts removed
    └── *.test.mjs                   # parity goldens vs agent files
```

### Module: agents
- **Maps to capability**: Agent Registry
- **Responsibility**: Single source of every reviewer persona.
- **Exports**: 14 agent files (alice, blake, bob, carl, quinn, eve, rita,
  cora, grace, toby, mallory, trent, victor, pat).

### Module: review-work-completion
- **Maps to capability**: Dispatch From the Registry, Registry Verification
- **Responsibility**: Consensus/blind/doubt orchestration assembling from the
  registry; hygiene and parity tests.
- **Exports**: Updated SKILL steps, `agent-invocation.md` assembly rules,
  `scripts/test_agent_registry.py`.

### Module: run-autopilot
- **Maps to capability**: Dispatch From the Registry
- **Responsibility**: Doubt-phase references point at the registry;
  `prompts/doubt-review.md` deleted; prompt-contract tests re-anchored to
  `eve.md`.
- **Exports**: Updated references + `scripts/test_review_prompt_contracts.py`.

### Module: work
- **Maps to capability**: Dispatch From the Registry
- **Responsibility**: §5.7 Pat assembly from `pat.md`.
- **Exports**: Updated SKILL.md §5.7.

### Module: workflows
- **Maps to capability**: Workflow dimension dispatch, Prompt parity harness
- **Responsibility**: Registry-dispatched dimensions; inline persona text
  gone; contract tests and pure-region harness updated.
- **Exports**: `review-fanout.workflow.js`, updated `*.test.mjs`,
  `_harness.mjs`.

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **agents**: The 14 persona files + conventions + agentType probe result.

### Core Layer (Phase 1)
- **workflows**: Depends on [agents] (dispatch mechanism per probe).
- **review-work-completion**: Depends on [agents].
- **run-autopilot**: Depends on [agents].
- **work**: Depends on [agents].

### Integration Layer (Phase 2)
- **Verification suites**: Depend on [all Core modules] - parity goldens,
  fail-closed fixtures, hygiene tests, inline-source deletion sweep.

## Implementation Phases

### Phase 0: Registry foundation
**Goal**: The registry exists with proven dispatch mechanics.

**Tasks**:
- [ ] Capture pre-change golden prompts for every dispatch path on a fixture
  diff (no deps) - Acceptance: goldens committed beside the test suites.
- [ ] Write conventions + 14 agent files from today's sources (no deps) -
  Acceptance: hygiene pytest passes (count, frontmatter, description length,
  tool/model pins, no personal paths).
- [ ] Run the agentType probe workflow against one registry agent (no deps) -
  Acceptance: probe outcome recorded in `agent-invocation.md`; dispatch
  mechanism (agentType vs args-passthrough) fixed accordingly.

**Exit Criteria**: Hygiene suite green, goldens captured, probe recorded.

### Phase 1: Rewire dispatch
**Goal**: Every lane sources prompts from the registry; fail closed.

**Tasks**:
- [ ] Rewire `review-fanout.workflow.js` per probe; remove DIMENSIONS/
  rubricPrompt/skepticPrompt persona text; keep schemas, dedup, arming,
  renderer (depends on: Phase 0) - Acceptance:
  `node --test workflows/*.test.mjs` green including updated pure-region
  harness; null-dispatch fixture yields CHANGES_REQUESTED.
- [ ] Rewire review-work-completion assembly (Alice/Bob/Carl/Quinn/Blake/Eve)
  + fail-closed preflight; update `agent-invocation.md`; delete
  `agent-prompts.md` + `blind-lens-prompt.md` (depends on: Phase 0) -
  Acceptance: reference sweep shows no dangling links
  (premise re-check: `rg` for other consumers of the deleted files first).
- [ ] Rewire doubt lane to `eve.md`; delete `prompts/doubt-review.md`;
  re-anchor `test_review_prompt_contracts.py` (depends on: Phase 0) -
  Acceptance: that suite green with D-ids sourced from `eve.md`.
- [ ] Rewire /work §5.7 Pat assembly to `pat.md` (depends on: Phase 0) -
  Acceptance: §5.7 names `pat.md` as source; no inline reporting-contract
  text remains in SKILL.md.

**Exit Criteria**: All lanes registry-sourced, inline sources deleted, python
and node suites green.

### Phase 2: Verification
**Goal**: Parity and hygiene proven headlessly.

**Tasks**:
- [ ] Parity tests: rebuilt prompt bytes == goldens for every path (depends
  on: Phase 1) - Acceptance: all parity tests green.
- [ ] Fail-closed fixtures: missing-agent-file scenarios for one native and
  one CLI lane (depends on: Phase 1) - Acceptance: fixtures assert
  CHANGES_REQUESTED / runner-error text contracts.
- [ ] Sweep: no persona prompt text inline anywhere (depends on: Phase 1) -
  Acceptance: `rg` for distinctive persona phrases (e.g. "adversarial
  verifier", the shared-template opening line) matches only `agents/` and
  goldens; full python + node suites green.

**Exit Criteria**: Parity and fail-closed proven, sweep clean.

## Test Strategy

### Critical Scenarios
- **Happy path**: Fixture diff through each dispatch path → assembled prompt
  byte-identical to golden.
- **Edge case**: Security dimension unarmed / quiet diff → no mallory
  dispatch, no registry error.
- **Error case**: `eve.md` deleted in a fixture → native doubt lane reports
  reviewer failure → CHANGES_REQUESTED path; `bob.md` deleted → CLI assembly
  preflight fails loudly, no prompt file written.

## Risks

- **User-level agentType may not resolve in workflows**: Probe in Phase 0;
  decided fallback (bodies via workflow args) keeps scope unattended-safe.
- **Byte-parity across the system/user prompt split**: Cut agent bodies at
  the exact assembly seam; goldens captured before deletion make drift
  visible immediately.
- **Reviewers lose tools they had as general-purpose subagents** (read-only
  sets are a behavior change; e.g. Blake could previously run commands):
  accepted per discovery must-have 5; per-agent tuning is the registry's
  purpose - loosen a specific agent's tools later if review quality drops.
- **Boot-prefix growth**: description-length cap enforced by hygiene test.
- **Live work-tree**: ~/.claude is the user's active config; land the
  registry and rewiring in the same batch, keep each commit green.
