# Agoge Autopilot Hook: Batch-Drain Run + Findings-to-PRD Flow

Source: `dev/local/discovery/00091-product-qa-agent-pack.md` (PRD 4 of 5; depends on core pack 00100, best after harnesses 00101).

## Overview

### Problem Statement

Standalone `/run-agoge` only fires when a human remembers to run it. Autopilot's whole point is unattended draining, which is exactly when code-correct, product-wrong changes pile up uncaught. The pack must run once per drained batch automatically, and accepted findings must have a durable exit into the backlog instead of dying in chat.

### Target Users

The autoclaude wrapper (fires the run), and the repo owner who returns to written packets and turns accepted ones into backlog PRDs.

### Success Metrics

- A drained batch (>=1 PRD completed) triggers exactly one agoge run; a zero-drain batch triggers none.
- Unattended runs write walkthrough-shaped packets and stop; zero writes to `dev/local/prds/`.
- Interactive acceptance of a finding produces a create-prd-compliant backlog PRD with a collision-safe sequence number.

## Functional Decomposition

### Capability: Batch-Drain Trigger

#### Feature: Drain Hook
- **Description**: Fire one agoge run when autopilot drains a batch.
- **Inputs**: Drain event in the autoclaude wrapper (drain branch currently at `~/.config/bash/plugins/development.plugin.bash:789-810`) plus the batch's drained-PRD list.
- **Outputs**: One unattended `run-agoge` invocation against the drained repo; run reference recorded next to the batch's autopilot artifacts.
- **Behavior**: Once per batch, never per cycle or per PRD; skips when the batch drained nothing. Whether the invocation lives in the wrapper drain branch or as a done-phase step is a design-phase choice; no new autopilot gate and no state-schema change either way (discovery rejected the fourth-gate option). Premise: the drain branch still lives in `development.plugin.bash:789-810`; PRD 00089 (extract-autopilot-lifecycle-core) may move it. Re-check the location at execution time; if moved, wire into the relocated drain path, and if no equivalent drain point exists, stop and report instead of forcing.

#### Feature: Unattended Run Mode
- **Description**: Headless agoge run that ends in packets, not questions.
- **Inputs**: Drained repo path; existing QA profile (Olivia refreshes if stale).
- **Outputs**: Report with walkthrough-shaped packets in the repo's `dev/local/audit-results/`; a stop marker line telling the returning human to run the walkthrough.
- **Behavior**: Follows the unattended branch of 00100's report contract: write packets, stop; never guess approvals, never auto-emit PRDs (discovery rejected ungated machine PRDs). Headless-safe per 00101's rules; interactive-only surfaces skip loud.

### Capability: Findings-to-PRD Flow

#### Feature: Walkthrough Resumption
- **Description**: The returning human walks written packets as if the review had just finished.
- **Inputs**: Packet report from an unattended (or interactive) run.
- **Outputs**: Per-finding decision recorded in the report: applied / queued / deferred / rejected.
- **Behavior**: `run-agoge` gains a resume path: pointed at an existing packet report, it walks findings per the findings-walkthrough protocol instead of re-running specialists. For headless verification the resume path also accepts a scripted decisions input (finding id → accept/defer/reject); live AskUserQuestion flow is the interactive default.

#### Feature: PRD Emission
- **Description**: Accepted findings become backlog PRDs.
- **Inputs**: Findings the human accepted during walkthrough.
- **Outputs**: One PRD per accepted finding (or one per merged cluster the human approves) in the target repo's `dev/local/prds/backlog/`, create-prd template-compliant, named `NNNNN-<slug>-v1.md`.
- **Behavior**: Sequence number scanned across all PRD subdirs + discovery, with the create-prd concurrent-collision re-scan. The PRD body carries the finding's evidence and the packet's chosen option as its solution direction. Emission happens only on explicit per-finding acceptance; deferred/rejected findings stay in the report only.

## Structural Decomposition

### Repository Structure

```
~/.config/bash/plugins/
└── development.plugin.bash       # Maps to: Batch-Drain Trigger (drain-branch wiring; exact
                                  # placement per design; premise re-check per above)
~/.claude/skills/run-agoge/
├── SKILL.md                      # Maps to: Unattended Run Mode, Walkthrough Resumption
└── references/
    └── prd-emission.md           # Maps to: PRD Emission (template mapping + numbering rules)
```

### Module: drain-wiring
- **Maps to capability**: Batch-Drain Trigger
- **Responsibility**: Detect drain-with-work, invoke one unattended run, record the reference.
- **Exports**: Wrapper-internal call; no new CLI surface, no state-schema field.

### Module: run-agoge (extended)
- **Maps to capability**: Findings-to-PRD Flow, Unattended Run Mode
- **Responsibility**: Unattended packet mode, resume-from-report walkthrough, gated PRD emission.
- **Exports**: `/run-agoge` (unchanged), `/run-agoge --resume <report>` walkthrough entry.

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies within this PRD - built first (external deps: 00100 pack; 00101 recommended for lane depth).

- **run-agoge unattended mode**: The thing the wrapper will invoke; testable standalone via `claude -p`.

### Core Layer (Phase 1)
- **drain-wiring**: Depends on [unattended mode].

### Integration Layer (Phase 2)
- **walkthrough resumption + PRD emission**: Depends on [unattended mode] (consumes its packet reports).

## Implementation Phases

### Phase 0: Foundation
**Goal**: Unattended mode proven headless.

**Tasks**:
- [ ] Add unattended packet mode to run-agoge (no deps) - Acceptance: `claude -p` run against the armed CLI gym fixture writes a packet report ending in the stop marker; `dev/local/prds/` untouched (asserted by diffing the dir listing before/after).

**Exit Criteria**: Packet report from a headless run, zero backlog writes.

### Phase 1: Core
**Goal**: The wrapper fires it once per drained batch.

**Tasks**:
- [ ] Wire the drain trigger (depends on: Phase 0) - Acceptance: premise re-check performed and recorded (drain branch located, 00089 relocation checked); a simulated drained batch (wrapper driven against stub state with 1 drained PRD) produces exactly one agoge invocation; zero-drain simulation produces none; two batches produce two runs, never more.

**Exit Criteria**: Trigger fires once per drained batch in simulation.

### Phase 2: Integration
**Goal**: Findings exit into the backlog, gated by a human.

**Tasks**:
- [ ] Build `--resume <report>` walkthrough (depends on: Phase 0) - Acceptance: driven by a scripted decisions input, resuming a packet report records per-finding minutes without dispatching any specialist; the live interactive flow is verified by prose inspection (a headless build cannot answer AskUserQuestion).
- [ ] Build PRD emission with collision-safe numbering (depends on: resume) - Acceptance: a scripted acceptance of a fixture finding emits a template-compliant PRD in the gym fixture's `dev/local/prds/backlog/`; number survives the collision re-scan; a scripted rejection emits nothing.

**Exit Criteria**: Accepted finding → backlog PRD; rejected finding → report entry only.

## Test Strategy

### Critical Scenarios
- **Happy path**: drained batch → one unattended run → packets → resume walkthrough → accepted finding → backlog PRD.
- **Edge case**: batch drains zero PRDs (all parked) → Expected: no agoge run, drain log line says skipped.
- **Error case**: agoge run dies mid-batch-drain → Expected: wrapper drain path completes anyway (agoge failure never blocks the drain); failure recorded where the run reference would be.

## Risks

- **Drain branch moves under this PRD** (00089 refactor): premise re-check in the wiring task; stop-and-report if the drain point vanished.
- **Unattended run cost per batch**: once per batch by construction; armed-only dispatch (00100) keeps the fan-out gated; meta-budget watched via portfolio brief.
- **Wrapper fragility** (bash, live infra): agoge invocation isolated so its failure cannot break the drain path; simulation-based acceptance keeps the test off live batches.
- **Emission drift from create-prd conventions**: `prd-emission.md` maps packet fields to the create-prd template explicitly; emitted PRDs are subject to `/review-prd-backlog` like any other.
