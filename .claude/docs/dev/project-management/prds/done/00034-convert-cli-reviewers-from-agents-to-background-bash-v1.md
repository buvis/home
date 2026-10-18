# Convert The CLI Reviewers From Async Agents To Background Bash

> Source: 2026-06-23 halt-surface audit + jink 00025 reviewer-strand. Removes 3 of the 4 orphan-prone async Agents from the work-completion review.
> Target: `review-work-completion` skill (`references/agent-invocation.md`, `SKILL.md`).
> **Priority: MEDIUM** - shrinks the exact failure class (orphaned async Agent) the jink strand exposed.

## Overview

### Problem Statement
The work-completion review launches four reviewers via the Task (Agent) tool, `subagent_type: general-purpose` (`agent-invocation.md`). Three — Bob (codex), Carl (gemini), Diana (sonnet) — are thin Agent wrappers whose entire job is "run `~/.claude/skills/use-{tool}/scripts/{tool}-run.sh` and return output verbatim" (`agent-invocation.md:19-65`). Async Agent dispatch is the orphan-prone path: the Stop hook must GUESS from the transcript whether a launched-but-unreported reviewer is alive or dead (`autopilot_stop_hook.py:202-312`), which is exactly what stranded the jink 00025 review (out-of-order completion). Background Bash, by contrast, is covered by the robust `_waiting_on_async` (`autopilot_stop_hook.py:315-417`): it abstains until the last unconsumed bg-bash launch reports, in EVERY phase, with an Edit-after-launch hand-off discriminator that cannot be fooled by completion order.

### Target Users
The operator whose review phase must not strand or idle-deadlock on an orphaned CLI reviewer.

### Success Metrics
- Bob/Carl/Diana run as `run_in_background` Bash invocations of their existing `*-run.sh` scripts, each writing its output to the same `dev/local/tmp/{agent}-output-{id}.txt` file the consolidator already reads (`review-work-completion/SKILL.md:132,143-146`).
- `consolidate-findings.sh` is unchanged — it is already file-based.
- The review phase's in-flight wait is handled by `_waiting_on_async`, not `_pending_background_task`; an orphaned CLI reviewer can no longer strand or idle-deadlock the phase.

### Non-Goals
- Converting Alice. She is a native Claude reviewer with no CLI form (`claude -p` does not work inside a subagent, `agent-invocation.md:5`); she stays an async Agent, so `_pending_background_task` is still needed for her. Reduction is 4→1, not 4→0.
- Changing the review rubric, the consolidator, or the coverage gate.

## Functional Decomposition

### Capability: Background-CLI reviewer dispatch
#### Feature: Direct bg-Bash launch
- **Description**: launch each CLI reviewer as a backgrounded Bash, not an Agent.
- **Inputs**: the reviewer prompt file, the `*-run.sh` path, the output-file path.
- **Outputs**: `dev/local/tmp/{agent}-output-{id}.txt` written by the CLI itself (`-o`/redirect).
- **Behavior**: a single assistant turn launches the three bg-Bash reviewers (plus Alice as an Agent) in parallel; the model yields; `_waiting_on_async` keeps the session alive until all three bg-Bash reviewers report; Alice's Agent completion is handled as today.

#### Feature: Output-file parity
- **Description**: the bg-CLI writes the exact file the consolidator expects.
- **Inputs**: the agreed `{agent}-output-{id}.txt` path.
- **Outputs**: same file, same content shape (the verbatim CLI output the Agent used to relay).
- **Behavior**: removes the model's relay step (Agent return → model Write); the CLI writes directly via `-o`.

## Structural Decomposition

### Files
```
~/.claude/skills/review-work-completion/references/agent-invocation.md   # Bob/Carl/Diana: Agent → bg-Bash
~/.claude/skills/review-work-completion/SKILL.md                         # dispatch step (launch) + consume step (read files)
```

### Module: agent-invocation reference
- **Responsibility**: describe each CLI reviewer as a backgrounded Bash with `-o` to the output file, not an Agent wrapper that relays stdout.

### Module: review SKILL dispatch step
- **Responsibility**: launch 3 bg-Bash + 1 Agent in one parallel turn; consume from the four output files.

## Dependency Graph

### Foundation Layer (Phase 0)
- **rewrite Bob/Carl/Diana invocation**: no deps.

### Core Layer (Phase 1)
- **update dispatch + verify consolidation**: depends on [Phase 0].

## Implementation Phases

### Phase 0: Reviewer invocation
**Goal**: Bob/Carl/Diana are bg-Bash, self-writing their output files.
**Tasks**:
- [ ] Rewrite the Bob/Carl/Diana sections of `agent-invocation.md` to launch `{tool}-run.sh ... -o dev/local/tmp/{agent}-output-{id}.txt` as a `run_in_background` Bash; leave Alice's section unchanged (no deps) — Acceptance: each of the three sections specifies a backgrounded Bash that writes the exact output-file path the consolidator reads; Alice still launches as an Agent. Verify each `*-run.sh` supports `-o`/redirect to that path (fall back to shell redirect if not).
**Exit Criteria**: the three CLI reviewers are documented as bg-Bash; Alice stays an Agent.

### Phase 1: Dispatch + consume
**Goal**: the review phase launches and consumes correctly.
**Tasks**:
- [ ] Update review `SKILL.md` to launch the 3 bg-Bash reviewers + Alice (Agent) in ONE parallel turn, and to read all four output files for consolidation; call out that the model must NOT Write any reviewer output itself between launch and yield (depends on: Phase 0) — Acceptance: a dry-run shows three `run_in_background` Bash launches + one Agent in a single message; `consolidate-findings.sh` reads the four files unchanged; no model Write occurs between launch and the yield.
**Exit Criteria**: review runs end-to-end; `_waiting_on_async` covers the three CLIs; the coverage gate passes.

## Test Strategy
- **bg-Bash wait**: with three unconsumed bg-bash launches and no later Edit, `_waiting_on_async` returns True (abstain) until all report — extend `AutoBackgroundedBashWaitTests` with a 3-reviewer variant.
- **File parity**: the consolidator reads the same paths whether written by relay (old) or directly (new).
- **Alice unchanged**: an Agent-only Alice is still handled by `_pending_background_task` in the (non-gated) review phase.
- **Mixed turn**: 3 bg-Bash + 1 Agent in one turn — confirm each emits its own paired `<task-notification>` (base-36 bash ids vs hex agent ids, `autopilot_stop_hook.py:137-138`).

## Risks
- **Intervening model Write advances `last_edit`** past the bg-bash launch, so `_waiting_on_async` returns False → strand. Mitigation: the CLIs self-write via `-o`; the dispatch step forbids the model Writing reviewer outputs between launch and yield.
- **Mixed Agent+bash turn**: Alice's orphan still needs `_pending_background_task` in the non-gated review phase. Mitigation: keep that path; this PRD moves only the three CLIs.
- **A `*-run.sh` lacks an output-to-file flag**. Mitigation: verify each script's output flag in Phase 0; fall back to a shell redirect to the same path.
