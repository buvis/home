# Consolidate Personal Hooks into Per-Event Dispatchers

## Overview

### Problem Statement

Every Bash tool call fans out into 11 interpreter spawns: warden (node, 1),
aegis (python, 6), personal PreToolUse (python, 2: enforce_prd_location,
cartographer-echo), and PostToolUse (python, 2: observe_tool,
autopilot_context_cap_hook). Stop pays 5. At ~100K tool calls per fortnight
(2026-07-14 triage,
`dev/local/audit-results/2026-07-14-cost-speed-quality-triage.md`) this is
0.3-0.9s of pure interpreter startup per tool call. Source of truth for current
wiring: `~/.claude/settings.json` hooks block (post-2026-07-14: pidash,
context-mode, the personal gateguard copy, and the serena matcher are all gone).

This PRD owns the **personal** hooks. Its sibling in the claude-aegis repo
(PRD 00013) collapses aegis's six Bash hooks the same way. Together they take a
Bash call from 11 spawns to ~4 (warden + aegis dispatcher + personal pre + personal
post). Decided in the 2026-07-14 setup-review walkthrough (finding 9).
Prior art: everything-claude-code shipped the same consolidation (10 PostToolUse
hooks into sync/async dispatchers, ECC commit 0071fa5c, 2026-07-19) and measured
blocking latency 81ms -> 49ms median, 10 processes -> 2, even with hooks spawned
in parallel as the harness does.

### Target Users

The operator and every agent session (interactive and headless autopilot).

### Success Metrics

- Personal `settings.json` hook entries: PreToolUse, PostToolUse, and Stop each
  collapse to exactly 1 entry (from 3, 4, and 5 as of 2026-07-18:
  strunk-ruling-inject added a PreToolUse Read matcher, validate_state_json
  a 4th PostToolUse entry).
- Personal python spawns per Bash tool call: 1 pre + 1 post (from 2 + 2).
- Zero behavior change: same blocks, same injected context, same logs.

## Functional Decomposition

### Capability: Dispatch

One process per hook event runs all registered handlers in-process.

#### Feature: Event dispatcher
- **Description**: `hooks/dispatch.py <event>` reads the hook payload once and runs every handler registered for that event and tool matcher.
- **Inputs**: argv[1] event name (`pre`, `post`, `stop`); hook JSON payload on stdin.
- **Outputs**: aggregated hook response on stdout, exit code 0 or 2.
- **Behavior**: Parse payload once. Look up handlers in an in-file routing table keyed by event and `tool_name` regex, mirroring the settings matchers **as they stand at execution time** (as of 2026-07-18: pre `Edit|Write|MultiEdit` runs enforce_prd_location + cartographer-echo + strunk-ruling-inject; pre `Read` runs strunk-ruling-inject; pre `Bash` runs enforce_prd_location + cartographer-echo; post `Edit|Write|MultiEdit` runs design-quality-check + validate_state_json_hook, post `.*` runs observe_tool, post `Bash|Read|Grep|Glob|Agent|WebFetch|WebSearch|mcp__.*` runs autopilot_context_cap_hook; stop runs notify, review_coverage_hook, track_cost, analyze-instincts, cartographer-stop). Build ROUTES by reading settings.json, never from this list - it is a snapshot, not a contract. Run ALL matching handlers in settings order, never short-circuit on a block (parity with Claude running sibling hooks independently).

#### Feature: Result aggregation
- **Description**: Combine per-handler results into one hook response.
- **Inputs**: list of (exit_code, stdout_text, stderr_text) per handler.
- **Outputs**: single stdout JSON and process exit code.
- **Behavior**: Any handler exit 2 makes the final exit 2; all blocking stderr messages are concatenated in order. JSON stdouts are merged: `additionalContext` strings concatenate with `\n---\n`; other keys take the most restrictive value; on key conflict the earlier handler wins and a stderr line names the losing handler and dropped key, so nothing drops silently. Exit codes other than 0/2 are logged and treated as 0 (parity with today's non-blocking hook errors).

#### Feature: Handler isolation
- **Description**: One broken handler never kills the rest.
- **Inputs**: handler callable or script path.
- **Outputs**: log line in `hooks/dispatch.log`, dispatch continues.
- **Behavior**: Each handler runs inside try/except; exceptions log traceback and contribute exit 0. Per-handler wall clock capped at its former settings timeout.

### Capability: Handler adaptation

Existing scripts become importable without breaking standalone use.

#### Feature: run() interface
- **Description**: Each personal hook script exposes `run(payload: dict) -> tuple[int, str, str]` (exit code, stdout, stderr).
- **Inputs**: parsed hook payload dict.
- **Outputs**: same decision/output the script produces today.
- **Behavior**: Refactor each script's `__main__` body into `run()`; `__main__` becomes `sys.exit`-wrapping call reading stdin (standalone behavior preserved for tests and manual runs). Dash-named files (`cartographer-echo.py`) load via `importlib.util.spec_from_file_location`. Any handler without `run()` falls back to subprocess execution of the script (safety net, not the end state).

#### Feature: Settings rewiring
- **Description**: Replace the multi-entry hooks block with one dispatcher entry per event.
- **Inputs**: current `settings.json`.
- **Outputs**: PreToolUse one entry (matcher `Edit|Write|MultiEdit|Bash|Read` - Read is load-bearing for strunk-ruling-inject, the measured 3/3-obeyed channel from PRD 00064; dropping it is a silent behavior regression - timeout 15), PostToolUse one entry (no matcher, timeout 15), Stop one entry (timeout 45). UserPromptSubmit and Notification keep their single hooks unchanged; SessionStart currently has no personal hook.
- **Behavior**: Plugin-managed hooks (aegis, warden) are out of scope for THIS PRD and must not be moved - aegis PRD 00013 collapses its own six. Premise, re-checked at execution: `rg -c 'pidash|context-mode|gateguard-fact-force|serena' ~/.claude/settings.json` returns nothing (all four were removed 2026-07-14); any surviving entry means the settings drifted back - consolidate only what is actually there and report the difference, never force this PRD's snapshot onto the file.

## Structural Decomposition

### Repository Structure

```
~/.claude/hooks/
├── dispatch.py                  # Maps to: Dispatch (dispatcher, routing table, aggregation)
├── enforce_prd_location.py      # Maps to: Handler adaptation (gains run())
├── cartographer-echo.py         # Maps to: Handler adaptation (gains run())
├── strunk-ruling-inject.py      # Maps to: Handler adaptation (gains run())
├── design-quality-check.py      # Maps to: Handler adaptation (gains run())
├── observe_tool.py              # Maps to: Handler adaptation (gains run())
├── notify.py                    # Maps to: Handler adaptation (gains run())
├── analyze-instincts.py         # Maps to: Handler adaptation (gains run())
├── cartographer-stop.py         # Maps to: Handler adaptation (gains run())
├── track_cost.py                # Maps to: Handler adaptation (gains run())
└── tests/                       # Maps to: dispatcher + parity tests
~/.claude/skills/run-autopilot/scripts/
├── review_coverage_hook.py      # Maps to: Handler adaptation (gains run())
├── autopilot_context_cap_hook.py# Maps to: Handler adaptation (gains run())
└── validate_state_json_hook.py  # Maps to: Handler adaptation (gains run())
~/.claude/settings.json          # Maps to: Settings rewiring
```

### Module: dispatch
- **Maps to capability**: Dispatch
- **Responsibility**: Single entry point per hook event; routing, aggregation, isolation, logging.
- **Exports**:
  - `main(event: str)` - reads stdin, runs handlers, emits aggregate
  - `ROUTES` - routing table (event, matcher regex, handler paths, per-handler timeout)

### Module: handlers
- **Maps to capability**: Handler adaptation
- **Responsibility**: Existing hook logic, unchanged in effect, callable in-process.
- **Exports**:
  - `run(payload)` - per script, returns (exit_code, stdout, stderr)

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **dispatch**: dispatcher core, routing table, aggregation, isolation, tests against stub handlers.

### Core Layer (Phase 1)
- **handlers**: Depends on [dispatch] (interface contract) - add `run()` to each of the 12 handler scripts.

### Integration Layer (Phase 2)
- **settings rewiring**: Depends on [dispatch, handlers] - swap settings.json entries, parity check, commit.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Dispatcher that routes, aggregates, and isolates correctly.

**Tasks**:
- [ ] Write `hooks/dispatch.py` with ROUTES mirroring current settings matchers (no deps) - Acceptance: `pytest hooks/tests/test_dispatch.py` green covering: block propagation (one handler exits 2, final exit 2, message preserved), additionalContext concatenation, merge-conflict stderr warning naming the losing handler, crash isolation (raising stub logged, others still run), routing (each payload runs exactly the handlers settings.json routes for it - as of 2026-07-18: Bash runs 2 pre handlers (enforce_prd_location + cartographer-echo), Read runs 1 (strunk-ruling-inject), Glob runs 0; derive expected sets from settings.json in the test, not from this snapshot).
- [ ] Subprocess fallback for handlers lacking `run()` (no deps) - Acceptance: test proves a run()-less script still executes with identical stdout/exit code.

**Exit Criteria**: Dispatcher suite green against stub handlers; fallback proven.

### Phase 1: Core
**Goal**: All personal hook scripts callable in-process.

**Tasks**:
- [ ] Add `run(payload)` to the 12 handler scripts listed in Repository Structure (all except the new dispatch.py), preserving standalone `__main__` (depends on: Phase 0) - Acceptance: for each script, parity test feeds a recorded payload to standalone subprocess and to `run()`; exit code and stdout are identical.
- [ ] Regression-run existing `hooks/tests` suite (depends on: Phase 0) - Acceptance: full suite green, no test deleted or skipped; report skip counts explicitly.

**Exit Criteria**: All 12 handlers parity-proven in-process; legacy suite green.

### Phase 2: Integration
**Goal**: settings.json uses dispatchers; behavior unchanged.

**Tasks**:
- [ ] Re-check the settings-drift premise (Feature: Settings rewiring) (depends on: Phase 1) - Acceptance: report states which branch was taken.
- [ ] Rewrite hooks block: 1 entry each for PreToolUse/PostToolUse/Stop pointing at dispatch.py (depends on: Phase 1) - Acceptance: `python3 -c "import json;h=json.load(open('/Users/bob/.claude/settings.json'))['hooks'];print(len(h['PreToolUse']),len(h['PostToolUse']),len(h['Stop']))"` prints `1 1 1`, and a live `claude -p` smoke session shows the aegis gateguard block still fires on an unfactored Edit (aegis owns the gate since PRD 00056).
- [ ] Commit hooks/, settings.json to the buvis bare repo by absolute pathspec (never `-a`; no CHANGELOG, dotfiles repo exemption) (depends on: all) - Acceptance: `git --git-dir=$HOME/.buvis --work-tree=$HOME log -1 --stat` lists the files.

**Exit Criteria**: One python spawn pre and one post per matched tool call; all parity and regression tests green.

## Test Strategy

### Critical Scenarios
- **Happy path**: Bash payload through pre dispatcher → all routed handlers (2 as of 2026-07-18) run in order, exit 0, contexts merged → Expected: identical to the same handlers run standalone.
- **Edge case**: one handler blocks (exit 2) while another emits context → Expected: exit 2, both messages present, no handler skipped.
- **Error case**: one handler raises → Expected: others complete, traceback in dispatch.log, exit reflects remaining handlers only.

## Risks

- **Semantics drift vs native multi-hook behavior**: Mitigate with recorded-payload parity tests per handler and the run-all/no-short-circuit rule.
- **A blocked settings.json edit mid-rewire leaves zero hooks active**: Mitigate by writing the new block to a temp file and swapping in one Write; snapshot the current settings.json to `dev/local/tmp/` before the swap (buvis history is the durable rollback - there is no `.bak` file any more).
- **One process, one crash surface**: handler isolation (try/except per handler + per-handler timeout) is what keeps a single broken handler from taking the others down; its tests are Phase 0 acceptance, not an afterthought.
