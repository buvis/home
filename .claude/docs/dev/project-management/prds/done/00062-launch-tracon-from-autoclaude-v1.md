---
design_gate: user
---

# Launch tracon from autoclaude by default

> **Guard: do not start before 00061 is done.** Tracon must exist and be verified first.

## Overview

### Problem Statement

Tracon (PRD 00061) runs in a second terminal the operator must remember to open; the loop's own terminal still shows the flat render_stream view. The user wants `autoclaude` to present tracon by default. Separately, tracon cannot tell a live wrapper from an orphaned state dir - it infers liveness from file mtimes; only the wrapper knows its own PID.

`design_gate: user` is set deliberately: this PRD edits the autoclaude wrapper, the highest-incident surface in this codebase (eight loop-halt classes to date). The design gets one human review before tasks are planned.

### Target Users

Solo operator starting loops with a bare `autoclaude` in a terminal.

### Success Metrics

- `autoclaude` on a tty with `uv` available opens tracon; the loop runs underneath; the raw `last-session.log` stays byte-identical to today's (verified with `cmp` against a control run).
- `q` detaches tracon and the loop keeps running (next session boundary proceeds); re-running tracon re-attaches.
- The stop key writes `pause-requested` and the loop pauses at the next session boundary, exactly like `touch pause-requested` today.
- Ctrl-C ends both tracon and the loop with today's cleanup semantics (traps fire, orphans reaped, `_AUTOPILOT_LOOP` unset).
- A registry entry exists for every running wrapper and for none after exit on every path (drain, pause, die, INT/TERM); tracon badges wrapper-alive loops from it.
- Every running wrapper appears on the fleet dashboard regardless of gita registration (discovery unions live registry roots), and a tracon launched by `autoclaude --root` can switch to any discovered loop (dashboard lists the full fleet; escape/enter navigation).
- Fallbacks intact: no tty, no uv, or `_AUTOPILOT_TRACON=0` → today's render_stream pipe, unchanged.

## Functional Decomposition

### Capability: Loop registry

#### Feature: Wrapper registry file
- **Description**: Exact loop-to-process mapping, written by the wrapper.
- **Inputs**: Loop start (after `_ap_dir` resolution), every exit path.
- **Outputs**: `~/.claude/autopilot-loops/<pid>.json` containing `{"pid": <int>, "root": "<abs repo root>", "ap_dir": "<abs>", "started_at": "<ISO-8601 UTC>"}`; file removed on exit.
- **Behavior**: Written once per `autoclaude` invocation; removal added to the existing INT/TERM traps and to every `return` path (memory-pressure, pause, drained, died, paused-by-state). Stale files (PID dead) are tolerated readers' concern.

#### Feature: Tracon wrapper-alive badge
- **Description**: Tracon distinguishes a running wrapper from parked state.
- **Inputs**: Registry dir entries; `os.kill(pid, 0)` liveness probe.
- **Outputs**: Dashboard/detail status gains a wrapper-alive marker; a dead PID with a leftover file reads as not-running (and the stale file is ignored, not deleted - tracon stays read-only).
- **Behavior**: Registry consulted alongside the existing mtime heuristics; absence of a registry entry (loop predating this PRD, or manual state) degrades to mtime-only classification. Live registry entries also feed discovery: their roots join the fleet row set, so a running wrapper is visible without gita registration (gita remains a source for parked loops only).

### Capability: Tracon front-end launch

#### Feature: Default tracon launch
- **Description**: `autoclaude` presents tracon instead of the flat render.
- **Inputs**: tty on stdout, `uv` resolvable, `_AUTOPILOT_TRACON` not `0`.
- **Outputs**: Tracon in the foreground attached to this loop's root; the session pipeline's render stage writes to `/dev/null` instead of the terminal (the `tee` to `last-session.log` is untouched - detect_usage_limit.py and the metrics parse depend on it).
- **Behavior**: Loop body runs as a background job of the wrapper function; tracon runs foreground and exits when the loop exits (drained/paused/died banner shown in tracon). When any precondition fails, launch exactly today's `render_stream.py || cat` pipeline - zero behavior change.

#### Feature: Detach and stop keys
- **Description**: Operator control from inside tracon.
- **Inputs**: `q` (detach), `p` (pause loop), Ctrl-C.
- **Outputs**: `q`: tracon exits, loop continues, wrapper prints the reattach command (`uv run .../tracon.py --root <root>`); `p`: writes `<ap_dir>/pause-requested` (the sanctioned signal; wrapper consumes it at the next session boundary); Ctrl-C: tracon exits AND the wrapper receives INT so the existing traps run (loop stops, cleanup fires).
- **Behavior**: Ctrl-C routing is the riskiest contract: the wrapper arranges signal delivery such that the observed outcome equals today's Ctrl-C in the loop terminal. The design doc must specify the process-group/trap arrangement explicitly and the shell test must prove all three keys.

## Structural Decomposition

### Repository Structure

```
.config/bash/plugins/development.plugin.bash   # Maps to: Loop registry (write/remove) + Tracon front-end launch
.claude/skills/run-autopilot/scripts/
├── tracon.py                                  # Maps to: Detach and stop keys (bindings), wrapper-alive badge, exit banner
├── tracon/discovery.py                        # Maps to: Tracon wrapper-alive badge (registry read)
└── test_autoclaude_tracon_launch.sh           # Maps to: shell tests for launch/detach/stop/registry lifecycle
```

### Module: development.plugin.bash (autoclaude)
- **Maps to capability**: Loop registry; Tracon front-end launch
- **Responsibility**: registry file lifecycle; conditional tracon vs render_stream presentation; unchanged decision table
- **Exports**: `autoclaude()` (unchanged name/signature)

### Module: tracon (extension of 00061 modules)
- **Maps to capability**: Tracon front-end launch; Detach and stop keys; wrapper-alive badge
- **Responsibility**: `--root` attach mode gains `p` binding, exit banner, registry-aware status
- **Exports**: `run_app()` (extended bindings), `discovery.wrapper_alive(root)`

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **registry write/remove (wrapper)**: pure addition; every exit path covered

### Core Layer (Phase 1)
- **wrapper-alive badge (tracon)**: Depends on [registry write/remove]
- **p/q bindings + exit banner (tracon)**: Depends on [00061 screens]

### Integration Layer (Phase 2)
- **default tracon launch (wrapper)**: Depends on [registry, bindings]

## Implementation Phases

### Phase 0: Foundation
**Goal**: Registry lifecycle correct before any UX changes.

**Tasks**:
- [ ] Wrapper writes/removes `~/.claude/autopilot-loops/<pid>.json` on all paths (no deps) - Acceptance: shell test (test_loop_metrics.sh harness pattern) proves create-at-start and removal on drain, pause, died, and INT; `bash -n` clean; existing loop-metrics + watchdog tests still green.

**Exit Criteria**: Registry lifecycle shell test green on every exit path.

### Phase 1: Core
**Goal**: Tracon knows about wrappers; keys exist.

**Tasks**:
- [ ] `discovery.wrapper_alive()` + status badge (depends on: Phase 0) - Acceptance: pytest with fixture registry files (live PID, dead PID, absent) drives the three classifications.
- [ ] `p` (pause-requested write is tracon's ONLY write, to that one filename) and `q` bindings + loop-exit banner (depends on: 00061) - Acceptance: pilot test asserts `p` creates the marker file in a tmp root and `q` exits the app cleanly.

**Exit Criteria**: Tracon badges a live wrapper correctly and both keys pass their pilot tests.

### Phase 2: Integration
**Goal**: `autoclaude` presents tracon.

**Tasks**:
- [ ] Conditional launch in the wrapper with all fallbacks (depends on: Phase 1) - Acceptance: shell test matrix: tty+uv → tracon path chosen (stubbed `uv`), no-tty → render path, `_AUTOPILOT_TRACON=0` → render path; raw log `cmp`-identical between paths for a stubbed session.
- [ ] Ctrl-C routing per the reviewed design (depends on: launch) - Acceptance: shell test sends INT to the foreground arrangement and asserts loop cleanup ran (trap markers), registry file removed, no orphaned `claude` stub.

**Exit Criteria**: A real `autoclaude` run on a tty shows tracon; q/p/Ctrl-C behave per Success Metrics; unattended cron/headless invocations are pixel-identical to today.

## Test Strategy

### Critical Scenarios
- **Happy path**: tty run → tracon, loop drains a stubbed backlog → tracon shows drained banner and exits 0.
- **Edge case**: `q` mid-session → loop finishes the batch unattended; registry file persists until real exit.
- **Edge case**: tracon crashes (kill -9 it) → loop unaffected (presentation-only contract), wrapper prints reattach hint.
- **Error case**: `uv` missing → render_stream path, no error output difference vs today.

## Risks

- **Wrapper fragility** (eight prior loop-halt classes): mitigations - decision table untouched, additions are presentation + registry only, `design_gate: user` review, shell-test matrix before merge, `_AUTOPILOT_TRACON=0` escape hatch.
- **Signal routing across bg job + foreground tracon**: the one genuinely hard part; resolved in the gated design doc, proven by the INT shell test before integration.
- **Detached loops become invisible**: mitigated by the registry badge and the notify.py alerts already in place.
