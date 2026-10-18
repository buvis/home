# Eve (Fable 5) Doubt-Review Reviewer

## Overview

### Problem Statement

The review-work-completion panel has four named, documented reviewers
(Alice, Bob, Carl, Diana), each with an exact dispatch pattern in
`agent-invocation.md`. There is no fifth, documented way to dispatch Claude
Fable 5 (`claude-fable-5`) as a reviewer — even though the Task/Agent tool's
`model` parameter already accepts `"fable"` as a valid alias (the same tier
as `"sonnet"`/`"opus"`/`"haiku"`), so nothing prevents it beyond the missing
documentation and prompt-assembly wiring. Fable 5 is well-suited to
skeptical, high-scrutiny review work, but no reviewer role currently exists
to invoke it that way.

### Target Users

Whoever wires a specific pipeline phase to use Fable 5 as a reviewer (the
immediate consumer is a follow-on PRD wiring this into `/run-autopilot`
Phase 8's doubt review) — this PRD's job is to make Fable 5 a
standalone-dispatchable, contract-satisfying reviewer first, independent of
any specific phase.

### Success Metrics

- Eve dispatches via the Task tool with `model: fable`, following the exact
  three-part pattern Diana already uses (tool-call form, prompt assembly, no
  relative-path resolution needed).
- Eve's output — given the same four inputs codex already receives (PRD,
  diff range, changed-file list, `prompts/doubt-review.md` base) —
  satisfies the existing doubt-review contract (FIX/VERIFY/KNOWN, `R1`-`R5`
  verdicts, `---review-coverage---` block) without any change to
  `prompts/doubt-review.md` itself.
- `test_doubt_review_prompt_contract.py` passes unmodified against a fixture
  shaped like Eve's output.

## Functional Decomposition

### Capability: Eve Reviewer Dispatch

Adds a fifth named reviewer to the roster documented in
`agent-invocation.md`, dispatched as a Fable 5 subagent using the same
pattern Diana already uses for Sonnet.

#### Feature: Eve dispatch pattern
- **Description**: Documents how to invoke Eve as a Task-tool subagent
  pinned to Fable 5.
- **Inputs**: `prompts/doubt-review.md` content, the PRD, the diff range,
  the changed-file list — the same four inputs codex and the Claude
  fallback already receive.
- **Outputs**: A Task-tool invocation block (`model: fable`) added to
  `agent-invocation.md` alongside Alice/Bob/Carl/Diana.
- **Behavior**: Native Task subagent (like Diana), not a CLI shell-out
  (like Bob/Carl) — no background-Bash hang risk, no `-o` output file, no
  `codex-run.sh`-style wrapper needed. The subagent has native
  Read/Grep/Glob/Bash access.

#### Feature: Eve prompt assembly
- **Description**: Builds Eve's prompt from the same base document codex
  uses.
- **Inputs**: `prompts/doubt-review.md`, PRD content, diff range,
  changed-file list.
- **Outputs**: A self-contained Task-tool prompt.
- **Behavior**: Structurally identical to the prompt codex receives (same
  base file, same three appended inputs) — differs only in delivery
  mechanism (inlined Task prompt vs. a written temp file for the CLI path).
  Eve must produce output satisfying the exact same contract:
  FIX/VERIFY/KNOWN sections, `R1`-`R5` verdicts, and the
  `---review-coverage---` block.

## Structural Decomposition

### Repository Structure

```
~/.claude/skills/review-work-completion/
├── references/
│   └── agent-invocation.md                   # Maps to: Eve Reviewer Dispatch (new "Eve (Fable 5)" section)
└── scripts/
    └── test_review_coverage.py               # Unchanged — confirms no coverage-gate changes needed

~/.claude/skills/run-autopilot/
├── prompts/
│   └── doubt-review.md                       # Reused as-is by Eve — no changes
└── scripts/
    └── test_doubt_review_prompt_contract.py  # Maps to: Eve Reviewer Dispatch (contract verification)
```

### Module: review-work-completion/references/agent-invocation.md
- **Maps to capability**: Eve Reviewer Dispatch
- **Responsibility**: Documents the exact Task/CLI dispatch pattern for each
  named reviewer
- **Exports**:
  - "Eve (Fable 5)" section — Task-tool invocation, `model: fable`, prompt
    assembly

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies — built first.

- **Eve Reviewer Dispatch (dispatch pattern)**: The documented Task-tool
  invocation shape. Standalone — requires no prerequisite state, frontmatter,
  or pipeline wiring to exist and be manually dispatchable.

### Core Layer (Phase 1)
- **Eve Reviewer Dispatch (prompt assembly)**: Depends on [dispatch
  pattern] — the assembly logic needs the dispatch shape defined first so
  the prompt lands in the right place in the Task-tool call.

### Integration Layer (Phase 2)
N/A for this PRD. Wiring Eve into a specific pipeline phase (frontmatter
opt-in, sequencing, state merge) is deliberately out of scope here — see the
follow-on PRD that consumes this one.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Eve exists as a documented, invocable reviewer using the standard
Task-tool subagent pattern.

**Tasks**:
- [ ] Add an "Eve (Fable 5)" section to `agent-invocation.md`, modeled
  directly on the existing Diana section (no deps) - Acceptance: the new
  section has the same three-part shape as Diana's (tool-call form, prompt
  assembly, no relative-path resolution needed); `model: fable` is the only
  substantive difference from Diana's `model: sonnet` block.

**Exit Criteria**: Eve is documented as a dispatchable reviewer identical in
shape to the existing four.

### Phase 1: Core
**Goal**: Eve's prompt assembly matches the existing doubt-review contract
exactly, verified independent of any specific pipeline phase.

**Tasks**:
- [ ] Wire Eve's prompt assembly to accept the same four inputs codex
  already receives — PRD content, diff range, changed-file list,
  `prompts/doubt-review.md` base (depends on: Phase 0) - Acceptance: Eve's
  assembled prompt is structurally identical to codex's (same base file +
  same three appended inputs), differing only in delivery mechanism.
- [ ] Dry-run Eve against a sample PRD + diff range and verify the output
  against `test_doubt_review_prompt_contract.py`'s existing contract checks
  (depends on: prior task) - Acceptance: the dry-run output passes the
  existing test suite unmodified — no new test logic is added to
  accommodate Eve; her output must conform to the contract as-is.

**Exit Criteria**: Eve can be dispatched standalone (given a PRD and diff
range) and her output passes the existing doubt-review contract test without
modification to that test.

### Phase 2: Integration
N/A for this PRD. Wiring Eve into a specific pipeline phase is deliberately
out of scope here — see `00037-add-doubt-reviewer-frontmatter-flag-v1.md`
and `00038-merge-fable5-doubt-review-findings-v1.md`.

## Test Strategy

### Critical Scenarios

- **Happy path**: Dispatch Eve against a real PRD + diff range with known
  findings → Expected: output contains FIX/VERIFY/KNOWN sections, all five
  `R{n}: pass|fail` lines, and a well-formed `---review-coverage---` block
  matching `prompts/doubt-review.md`'s exact delimiter format.
- **Edge case**: PRD or diff range produces zero findings → Expected: Eve
  still emits all four required sections with `- (none)` under empty
  buckets, per the existing contract — not an empty or malformed response.
- **Error case**: Eve's Task-tool dispatch fails or times out → Expected:
  the failure is observable and distinguishable from a valid empty-findings
  response (out of scope for *how* a consuming phase reacts to that failure
  — that's the follow-on PRD's concern; this PRD only needs the failure mode
  to be legible).

## Risks

- **Fable 5 turns running 15+ minutes on a dry run makes manual testing
  slow**: mitigate by testing against a small, well-scoped sample PRD/diff
  first, not a large real one, when verifying the contract.
- **Prompt drift if `prompts/doubt-review.md` is later edited for the
  codex/Claude-fallback path without re-verifying Eve**: mitigate by keeping
  Eve's prompt assembly a thin wrapper around the same base file (no
  reviewer-specific fork of the prompt content) so any future edit applies
  to all three reviewers uniformly.
