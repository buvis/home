# Decommission pidash on this machine and queue the gem retirement

> **Guard: do not start before 00061 is done.** pidash must not be removed before its replacement is verified working.

## Overview

### Problem Statement

pidash is dead weight: broken against the current autopilot schema (its required `prd` object is now a bare string, so every parse fails and it renders "no active PRD cycle"), yet its hook family still runs - six settings.json entries, three of which execute on EVERY PostToolUse of EVERY interactive session - and `~/.pidash/sessions/` holds ~1,350 stale mirror files. Tracon (00061) is the successor. Additionally, once 00062 makes tracon the default front-end, `render_stream.py` remains the fallback view and still interleaves parallel agents anonymously - the one visibility gap tracon fixed that the fallback keeps.

Exploration evidence (2026-07-13, recorded in memory `project-pidash-superseded`; the spike dir `dev/local/spikes/autopilot-tui/` has since been GC'd - its contract graduated into PRDs 00061-00063): pidash lives in buvis-gems 0.12.0; gems PRDs `00049-pidash-hook-durability-v1` and `00059-pidash-state-schema-contract-v1` (both parked in the gems repo's `dev/local/prds/hold/`) propose fixing it and are superseded by replacement.

### Target Users

Solo operator; every interactive Claude session on this machine (hook-tax removal).

### Success Metrics

- Zero `pidash` matches in `~/.claude/settings.json` hooks; PostToolUse hook count reduced by 3.
- `~/.pidash/` no longer exists; legacy pidash hook scripts and their test removed from `~/.claude/hooks/`.
- gems repo carries a local backlog PRD for the gem-side retirement; gems PRDs 00049/00059 are marked superseded.
- render_stream fallback view lane-tags subagent lines (pytest-verified), keeping parallel phases readable without tracon.

## Functional Decomposition

### Capability: Machine-side pidash removal

#### Feature: Unregister pidash hooks
- **Description**: Remove the six pidash hook registrations.
- **Inputs**: `~/.claude/settings.json`. Premise: entries with command prefix `pidash hooks run ` or `python3 ~/.claude/hooks/*pidash*` exist at execution time - re-check before editing; if absent, skip and report.
- **Outputs**: settings.json without pidash entries; unrelated hooks byte-preserved.
- **Behavior**: Prefer `pidash hooks uninstall` when the binary resolves (it removes exactly its own entries idempotently); otherwise edit settings.json surgically. Diff shown in the work log either way.

#### Feature: Remove legacy hook scripts and runtime data
- **Description**: Delete the dead pidash plumbing.
- **Inputs**: `~/.claude/hooks/{update-pidash-tasks,set-pidash-attention,clear-pidash-attention,sync-pidash-on-agent-return,cleanup-pidash-session,pidash_session}.py`, `~/.claude/hooks/tests/test_update_pidash_tasks.py`, `~/.pidash/`. Premise: no OTHER file under `~/.claude` imports `pidash_session` and no non-pidash settings entry references these scripts - re-check with a grep at execution; on any hit, stop and report instead of deleting.
- **Outputs**: Files removed and committed (buvis home repo); `~/.pidash/` deleted after logging its file count.
- **Behavior**: `~/.pidash` is outside any repo - deletion is permanent; log the count and newest mtime first so the work log records what was discarded.

### Capability: Fallback renderer parity

#### Feature: Lane-tag render_stream
- **Description**: Port tracon's lane attribution to the in-pipe fallback renderer (render_stream already dims/indents subagent lines via `parent_tool_use_id`; stable per-lane labels/colors are the missing part).
- **Inputs**: The stream events render_stream already parses (parent tool_use Task/Agent blocks, `parent_tool_use_id`).
- **Outputs**: Subagent lines prefixed `⟨label⟩` with a stable per-lane ANSI color; parent lines unchanged; raw log untouched (renderer is display-only).
- **Behavior**: `main()` holds the lane registry across lines (mirrors 00061's AgentTracker registration/labeling rules; retirement is unnecessary for a linear stream). Rendering stays fail-open: unknown shapes fall through to today's output.

### Capability: Gem-side retirement queue

#### Feature: Queue gems-repo PRD and supersede 00049/00059
- **Description**: Hand the gems-repo work to the gems backlog rather than doing cross-repo surgery from here.
- **Inputs**: gems repo at `~/git/src/github.com/buvis/gems`. Premise: `src/tools/pidash/` still exists and PRDs 00049/00059 are still parked in the gems repo's `dev/local/prds/hold/` - re-check at execution; if already gone/moved, skip and report.
- **Outputs**: A new PRD written to the gems repo's `dev/local/prds/backlog/` (next free sequence there) scoping: remove the pidash tool, its docs page, its packaging extra; note the successor (`tracon`, in the buvis home repo). 00049/00059 each get a one-line `> Superseded by <new PRD>` note prepended (dev/local is gitignored in gems - these are local planning artifacts, no gems commit involved).
- **Behavior**: This PRD does NOT modify gems source; the gems loop executes the retirement on its own schedule.

## Structural Decomposition

### Repository Structure

```
.claude/settings.json                                   # Maps to: Unregister pidash hooks
.claude/hooks/                                          # Maps to: Remove legacy hook scripts (deletions)
.claude/skills/run-autopilot/scripts/render_stream.py   # Maps to: Lane-tag render_stream
.claude/skills/run-autopilot/scripts/test_render_stream.py  # extended lane-tag tests
~/git/src/github.com/buvis/gems/dev/local/prds/backlog/ # Maps to: Gem-side retirement queue (local file drop)
```

### Module: settings.json (hooks block)
- **Maps to capability**: Machine-side pidash removal
- **Responsibility**: hook registrations minus pidash
- **Exports**: n/a (config)

### Module: render_stream.py
- **Maps to capability**: Fallback renderer parity
- **Responsibility**: one-line event rendering, now lane-tagged
- **Exports**: `render(event)` (signature unchanged; module-level lane state added), `main()`

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **render_stream lane tags**: independent of removals; lands with its tests

### Core Layer (Phase 1)
- **hook unregistration + script/data removal**: Depends on [00061 verified] (guard above); internally: unregister before deleting scripts the registrations point at

### Integration Layer (Phase 2)
- **gems retirement queue**: Depends on [machine-side removal] (the queued PRD states pidash is already inert on the operator machine)

## Implementation Phases

### Phase 0: Foundation
**Goal**: Fallback renderer reaches TUI-grade readability.

**Tasks**:
- [ ] Lane-tag render_stream.py + extend test_render_stream.py (no deps) - Acceptance: pytest covers label from Task description, stable color per lane, `⟨agentN⟩` fallback, non-subagent lines unchanged; existing render tests green; `last-session.log` byte-identity property untouched (renderer reads stdin only).

**Exit Criteria**: Fallback renderer lane-tags a captured parallel-review log in tests.

### Phase 1: Core
**Goal**: pidash inert on this machine.

**Tasks**:
- [ ] Unregister the six hook entries (premise re-check per Feature) (depends on: Phase 0) - Acceptance: `rg pidash ~/.claude/settings.json` empty; a fresh session shows 3 fewer PostToolUse hook firings; unrelated hooks diff-clean.
- [ ] Delete legacy hook scripts + test + `~/.pidash/` (premise re-checks per Feature) (depends on: unregister) - Acceptance: files gone and committed; `~/.pidash` absent; work log records the purged session-file count; full hooks pytest suite green after removal. If the permission layer denies a removal command, record the denial and pause (skip-and-report), never retry the same command.

**Exit Criteria**: pidash inert on this machine; no settings reference, no scripts, no runtime data.

### Phase 2: Integration
**Goal**: gems repo owns the rest.

**Tasks**:
- [ ] Write the gems backlog PRD + supersede notes on 00049/00059 (premise re-check per Feature) (depends on: Phase 1) - Acceptance: new PRD exists in gems backlog with correct next sequence; 00049/00059 carry the superseded banner; no file outside `dev/local/` in the gems repo was touched.

**Exit Criteria**: Success Metrics all verifiably true; nothing in any repo references the deleted hook scripts.

## Test Strategy

### Critical Scenarios
- **Happy path**: parallel review through the fallback renderer → Expected: every subagent line lane-tagged, colors stable within a session.
- **Edge case**: `pidash` binary absent when unregistering → Expected: surgical settings.json edit path taken; result identical.
- **Error case**: premise re-check finds a non-pidash consumer of `pidash_session.py` → Expected: deletion skipped, finding reported, PRD pauses rather than forces.

## Risks

- **Deleting something still consumed**: every removal task carries an execution-time premise re-check (grep for consumers, skip-and-report on hits).
- **`~/.pidash` removal is irreversible**: count + newest-mtime logged first; contents are derived mirrors of state.json files that still exist in their repos.
- **gems drift before its loop runs the retirement**: the queued PRD embeds its own premise re-checks, so staleness degrades to skip-and-report there too.

## Outcome (2026-07-14, fast-tracked interactively, no autopilot)

- Phase 1 hooks: the six registrations and seven files were already removed earlier the same day (user-ordered; buvis `99b108ee1`). Premise re-check at execution confirmed zero pidash entries remained — skip-and-report path taken as specified.
- Phase 1 data: `~/.pidash/` purged after logging 1,382 files, newest mtime 2026-07-14 13:13:39 (inventory: session scratchpad `pidash-files.txt`). Dir verified absent.
- Phase 0: `render_stream.py` lane-tags subagent lines — `⟨label⟩` from the spawning Task description, `⟨agentN⟩` fallback, stable per-lane color; errors carry the lane too. 6 new tests; suite 15/15.
- Beyond original scope (hooks were deleted before doc scrub could be planned): 11 doc references across run-autopilot/work rewritten; counter ownership moved to state.tasks snapshot writers (`tasks_total = len(tasks)` recomputed per write); `needs_attention` documented as advisory-only with no auto-clearer until tracon (00062); `dashboard-format.md` rewritten for tracon.
- Phase 2: gems `00071-retire-pidash-v1.md` queued; supersede banners prepended to gems 00049/00059.
- Hooks pytest suite: 384/385 green. The one failure (`test_survey.py::test_placeholder_fields_present_with_empty_defaults`) is pre-existing survey/test drift, unrelated to this PRD (naming buckets vs `{}` placeholder).
