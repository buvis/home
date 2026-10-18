---
catchup: skip
design: skip
---

# Route Phase Models in the Wrapper

## Overview

### Problem Statement

Every autopilot session launches on Opus (`claude --model claude-opus-4-8` hardcoded in `autoclaude`). The wrapper's old model dispatch (`_autoclaude_pick_model`) was deleted with the comment "it never switched a model in practice" - it failed because it guessed the phase before launch from stale state. PRD 00014 removed the guessing: the wrapper now reads `state.json.next_phase` to decide whether to relaunch at all, so it knows exactly which phase the next session runs. Routing becomes a case statement.

The waste is concentrated in orchestration, not implementation: per-task implementor tiering inside `/work` already runs haiku/sonnet/opus/qwen per task, but the orchestrator session wrapping it - and the finalize session that renders reports and moves files - always burns Opus. Phase 9 (finalize) is pure mechanics: render audit.md from state arrays, append the batch report, mv the PRD, update the capsule. The build session's own value is planning judgment; review-phase value lives in the reviewers, but its decision gate does real classification. Ship conservative defaults, measure with the PRD 00013/00014 metrics, then tighten.

### Target Users

Quota and cost per unattended batch.

### Success Metrics

- The wrapper resolves the launch model per phase from `next_phase`: `build` → opus, `review` → opus, `done` (finalize) → sonnet; overridable per phase via `_AUTOPILOT_MODEL_BUILD` / `_AUTOPILOT_MODEL_REVIEW` / `_AUTOPILOT_MODEL_DONE`; unknown/absent phase → opus (fail expensive, never fail dumb).
- `loop-metrics.jsonl` lines gain `"model"` and, when the headless JSON output provides them, `"cost_usd"` and token usage - making the routing's effect measurable per phase.
- Finalize sessions demonstrably run on sonnet (metrics line) and produce a complete batch report (no quality regression on the mechanical phase).
- Zero routing logic anywhere in skills or hooks - the wrapper owns it, keyed on state it already reads.

## Functional Decomposition

### Capability: Per-phase model selection at launch

#### Feature: Resolve model from next_phase

- **Description**: A case statement replaces the hardcoded model.
- **Inputs**: `~/.config/bash/plugins/development.plugin.bash`, the launch line and the pre-launch `state.json` read (both post-00014).
- **Outputs**: Before launch, read `next_phase` (`jq -r`, absent state → empty). Map: `build`→`${_AUTOPILOT_MODEL_BUILD:-claude-opus-4-8}`, `review`→`${_AUTOPILOT_MODEL_REVIEW:-claude-opus-4-8}`, `done`→`${_AUTOPILOT_MODEL_DONE:-claude-sonnet-5}`, anything else (including first-ever launch with no state) → `claude-opus-4-8`. Launch passes `--model "$_model"`.
- **Behavior**: A comment records why the old dispatch died and why this one is safe (phase is now read from the same state the relaunch decision uses, not guessed). The deleted-dispatch comment block at the old site is replaced by this implementation.

#### Feature: Record model and cost in metrics

- **Description**: The metrics line proves what ran and what it cost.
- **Inputs**: The PRD 00013 metrics append; the headless launch (00014) which can emit usage via `--output-format json` on the final result line of `last-session.log`.
- **Outputs**: The metrics line gains `"model": "<resolved model>"` always, and `"cost_usd"`/`"tokens_out"` parsed from the session output when present (absent → omit the keys, never fake zeros). Batch-report Loop Metrics section renders per-phase model + cost columns when available.
- **Behavior**: Parsing failure of the usage payload degrades to model-only - never blocks the loop.

### Capability: Keep phase semantics model-agnostic

#### Feature: Assert no skill-side model assumptions

- **Description**: Phases must not silently depend on the orchestrator being Opus.
- **Inputs**: `rg -n "opus|claude-opus" ~/.claude/skills/run-autopilot/SKILL.md ~/.claude/skills/review-work-completion/SKILL.md` at execution time.
- **Outputs**: Any prose asserting the session model (if found) is updated to reference "the session model (wrapper-routed per phase)"; per-task tier rules (`metadata.model`, escalation chain) are explicitly unaffected - they govern subagent dispatch, not the session.
- **Behavior**: Documentation-only sweep; per-task dispatch contract byte-unchanged.

## Structural Decomposition

### Repository Structure

```
~/.config/bash/plugins/development.plugin.bash   # model resolution + metrics fields
~/.claude/skills/run-autopilot/SKILL.md          # model-agnostic prose sweep
~/.claude/skills/run-autopilot/references/batch-report-format.md  # cost columns
~/.claude/skills/run-autopilot/scripts/test_loop_metrics.sh       # extended assertions
```

### Module: autoclaude wrapper

- **Maps to capability**: Per-phase model selection at launch
- **Responsibility**: Resolve, launch, record; sole owner of session-model policy
- **Exports**: `_AUTOPILOT_MODEL_{BUILD,REVIEW,DONE}` overrides; metrics `model`/`cost_usd` fields

## Dependency Graph

### Foundation Layer (Phase 0)

- **model resolution**: independent (given 00013/00014 landed)

### Core Layer (Phase 1)

- **metrics fields**: depends on [model resolution]
- **prose sweep**: depends on [model resolution]

### Integration Layer (Phase 2)

- **verification**: depends on all

## Implementation Phases

Premise rule: PRDs 00013/00014 run first by sequence. Re-verify at execution: the wrapper launches `claude -p` and reads `state.json` pre-launch (00014's shape). If 00014 stalled and the loop is still interactive/signal-based, STALL this PRD (the routing safety argument depends on the state read) - do not re-implement pre-launch guessing. The map assumes 00015's `build|review|done` enum; if 00015 stalled, legacy `blind`/`doubt` values route through the default-opus branch - safe by design, no extra mapping needed.

### Phase 0: Resolution

**Tasks**:

- [ ] Model case statement + launch flag (no deps) - Acceptance: mapping and env overrides exactly as specified; unknown phase → opus; `bash -n` clean

### Phase 1: Measurement and sweep

**Tasks**:

- [ ] Metrics model/cost fields + report columns (depends on: Phase 0) - Acceptance: metrics line carries `model` always; cost keys only when parsed; report format documents the columns
- [ ] Model-agnostic prose sweep (depends on: Phase 0) - Acceptance: rg findings addressed or `none found` recorded; per-task tier sections untouched

### Phase 2: Proof

**Tasks**:

- [ ] Scratch-batch verification (depends on: all) - Acceptance: `test_loop_metrics.sh` extended for the new fields and green; one scratch PRD drains with metrics showing `done` session on sonnet and a complete batch report; evidence pasted

**Exit Criteria**: Success metrics all hold.

## Test Strategy

### Critical Scenarios

- **Happy path**: build/review on opus, finalize on sonnet → Expected: three metrics lines with correct `model` values, report complete
- **Edge case**: `_AUTOPILOT_MODEL_REVIEW=claude-sonnet-5` override → Expected: review session launches sonnet; nothing else changes
- **Edge case**: first launch, no state.json → Expected: opus (default path), no error
- **Error case**: usage payload unparseable → Expected: metrics line has `model` but no cost keys; loop unaffected

## Risks

- **Sonnet finalize misses a step**: Phase 9 is mechanical (render, append, mv, cleanup) and its mv-verify + retention contracts are explicit checklists; the metrics + batch report make any gap visible next morning. Rollback is one env var.
- **Review-phase downgrade temptation**: deliberately NOT defaulted to sonnet - the decision gate classifies findings. Revisit with cost data after a few batches (that is what the metrics are for).
- **Repo specifics**: `$HOME` work-tree of bare repo `~/.buvis`; no CHANGELOG entries.
