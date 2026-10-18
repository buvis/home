---
catchup: skip
design: skip
---

# Instrument Loop Sessions

## Overview

### Problem Statement

The autopilot loop has zero timing data. Every efficiency claim to date ("takes ages", "kiro replication was faster", "ceremony ~26% of tool calls") rests on manual transcript archaeology or gut feel. The 2026-06-09 waste audit took a full session to reconstruct what one JSONL line per session would have recorded for free. Six PRDs in this backlog (00014-00019) change the loop's architecture, review shape, model routing, and qwen usage; without a baseline, none of their wins are measurable. The wrapper (`autoclaude` in `~/.config/bash/plugins/development.plugin.bash`) already brackets every session launch and reads `state.json` before and after - it just throws that information away.

### Target Users

The user evaluating whether autopilot improvements (PRDs 00014-00019) actually pay, and any future waste audit.

### Success Metrics

- Every `autoclaude`-launched session appends exactly one line to `dev/local/autopilot/loop-metrics.jsonl` with start/end timestamps, wall seconds, PRD, batch id, phase launched, phase at exit, and signal observed.
- The Phase 9 batch report renders a Loop Metrics section: sessions per PRD, wall-clock per phase, batch total.
- `loop-metrics.jsonl` survives batch-end cleanup (durable, not disposable).
- Zero behavior change to the loop itself: metrics are append-only observation.

## Functional Decomposition

### Capability: Record per-session metrics in the wrapper

#### Feature: Append a metrics line per session

- **Description**: `autoclaude` records one JSONL line per `claude` invocation.
- **Inputs**: `~/.config/bash/plugins/development.plugin.bash`, the `autoclaude` function loop body (the `claude --model ... "/run-autopilot"` call and the signal read that follows it).
- **Outputs**: After the signal read, append to `$_ap_dir/loop-metrics.jsonl` one JSON object: `{"ts_start": <epoch>, "ts_end": <epoch>, "wall_secs": <int>, "prd": <state.prd or "">, "batch": <state.batch.id or "">, "phase_launched": <state.next_phase read before launch, "" if no state>, "phase_end": <state.next_phase after exit, "" if no state>, "signal": <signal value or "none">}`. Use `date +%s` around the `claude` call and `jq -r` reads of `state.json`; when `state.json` is absent, empty-string the state fields, never skip the line.
- **Behavior**: Append never blocks or fails the loop - guard with `2>/dev/null || true` semantics. The line is written on every loop iteration including the exit paths (done, no-signal, unknown-signal), before the `return`.

#### Feature: Mark metrics durable in retention

- **Description**: The retention contract must not delete the metrics file at batch end.
- **Inputs**: `~/.claude/skills/run-autopilot/SKILL.md`, "### Retention" durable list.
- **Outputs**: `dev/local/autopilot/loop-metrics.jsonl` added to the Durable list.
- **Behavior**: Batch-end cleanup and the disposable-list enumeration leave the file untouched; it accumulates across batches.

### Capability: Summarize metrics in the batch report

#### Feature: Render Loop Metrics in Phase 9

- **Description**: The batch report shows what the batch cost in sessions and wall-clock.
- **Inputs**: `~/.claude/skills/run-autopilot/SKILL.md` Phase 9 step 7 (batch report append), `references/batch-report-format.md`.
- **Outputs**: A `### Loop Metrics` subsection per PRD summary: session count, wall seconds per `phase_launched` value, PRD total. Computed by reading `loop-metrics.jsonl` lines whose `prd` matches, filtered to the current `batch` id.
- **Behavior**: When the metrics file is missing or has no matching lines (manual runs outside the loop), render `no loop metrics (manual run)` - never fail the report.

## Structural Decomposition

### Repository Structure

```
~/.config/bash/plugins/development.plugin.bash   # Maps to: Record per-session metrics (append line)
~/.claude/skills/run-autopilot/SKILL.md          # Maps to: Retention entry + Phase 9 render
~/.claude/skills/run-autopilot/references/batch-report-format.md  # Maps to: Loop Metrics format
~/.claude/skills/run-autopilot/scripts/test_loop_metrics.sh       # Maps to: runnable check
```

### Module: autoclaude wrapper

- **Maps to capability**: Record per-session metrics in the wrapper
- **Responsibility**: Timing capture and append; zero control-flow change
- **Exports**: `loop-metrics.jsonl` line format

### Module: run-autopilot skill

- **Maps to capability**: Summarize metrics in the batch report
- **Responsibility**: Retention entry, Phase 9 render instruction, format doc
- **Exports**: `### Loop Metrics` report subsection

## Dependency Graph

### Foundation Layer (Phase 0)

- **wrapper append**: independent edit
- **retention entry**: independent edit

### Core Layer (Phase 1)

- **Phase 9 render**: depends on [wrapper append] (line format defined there)

### Integration Layer (Phase 2)

- **verification**: depends on all

## Implementation Phases

Premise rule: before editing, re-verify the `autoclaude` function still reads the signal into `signal=` and that no `loop-metrics` string already exists anywhere under `~/.claude/skills/run-autopilot/` or in the plugin file (`rg -n "loop-metrics"`). If either premise fails, stop and report.

### Phase 0: Foundation

**Goal**: Wrapper records, retention protects.

**Tasks**:

- [ ] Append metrics line in autoclaude (no deps) - Acceptance: plugin file contains the append after the signal read; all exit paths write the line; `bash -n` clean
- [ ] Add loop-metrics.jsonl to the Retention durable list (no deps) - Acceptance: Durable list names the file; disposable list unchanged

**Exit Criteria**: Both edits in place.

### Phase 1: Core

**Goal**: Report renders the data.

**Tasks**:

- [ ] Render Loop Metrics in Phase 9 (depends on: Phase 0) - Acceptance: SKILL.md Phase 9 step 7 instructs the render; batch-report-format.md documents the subsection with the missing-file fallback

**Exit Criteria**: Render instruction present with fallback.

### Phase 2: Integration

**Goal**: Proof.

**Tasks**:

- [ ] Runnable check (depends on: all) - Acceptance: `scripts/test_loop_metrics.sh` sources the plugin file with a stubbed `claude` function and fake state.json, runs one loop iteration, asserts one valid JSON line with all eight keys (`jq -e` per key); test output pasted

**Exit Criteria**: Test green; success metrics hold.

## Test Strategy

### Critical Scenarios

- **Happy path**: session runs, state.json present before and after → Expected: one line, all fields populated, wall_secs plausible
- **Edge case**: state.json absent (first-ever run) → Expected: line still written, state-derived fields empty strings
- **Edge case**: no signal (died/paused exit path) → Expected: line written with `"signal": "none"` before the loop returns
- **Error case**: metrics dir unwritable → Expected: loop proceeds untouched; append failure is silent by design (observation must never break orchestration; this is the one sanctioned silent-failure, scoped to the append itself)

## Risks

- **PRD 00014 rewrites the same loop body** (headless conversion): it runs after this PRD by sequence and its acceptance explicitly requires the metrics append to survive the rewrite.
- **Repo specifics**: `$HOME` work-tree of bare repo `~/.buvis`; no CHANGELOG entries.
