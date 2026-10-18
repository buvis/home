---
catchup: skip
default_model: opus
---

# Convert Loop to Headless Sessions

## Overview

### Problem Statement

The loop's instability is architectural, not a bug backlog. Ten distinct root-caused halt classes in five weeks (strand saga 8cea516, orphan reviewer 2026-06-20, auto-backgrounded Bash 2026-06-21, batch strand 2026-06-22, review-gated strand 2026-06-24, cycle-not-persisted 2026-06-25, nested Stop event 8f43cf74e, usage-limit idle 3f760d622, codex Agent hang eb068da4a, warden ask-deadlock 2026-06-30), 22 loop-death notifications in `notify.log`/`notify.log.1`, an 890-line Stop hook with a 90KB test file, plus a watchdog sidecar that SIGINT/SIGKILLs sessions. All of it exists to answer one question the architecture makes unanswerable: "is this interactive session actually done?" The Stop hook must infer turn-completion from transcripts, mtimes, ancestor PIDs, and marker files, then force the exit with SIGINT - and every new harness behavior mints a new failure class.

Headless mode dissolves the question. `claude -p "/run-autopilot"` runs one turn and exits when the turn ends. No inference, no SIGINT, no signal file (the signal was only ever a projection of `state.json`, which the wrapper can read directly), no thrash guard, no yield markers, no idle-marker sidecar. The wrapper - a while loop - becomes the orchestrator it was always pretending not to be.

### Target Users

Unattended `autoclaude` runs. Interactive `/run-autopilot` (manual, in a live session) keeps working unchanged.

### Success Metrics

- `autoclaude` launches every session as `claude -p` and decides continue/pause/done by reading `state.json` after exit - the signal file and all Stop-hook signal logic are deleted.
- `autopilot_stop_hook.py` (890 lines), its 90KB test file, `autopilot_yield_clear_hook.py`, the `.yielded-waiting` marker protocol, and the stale-marker watchdog are retired; the only remaining kill path is a dumb per-session wall-clock cap.
- A 2-PRD batch drains unattended with zero SIGINT/SIGKILL deliveries and zero "PHASE THRASH"/"without a signal" notifications.
- The PRD 00013 metrics append keeps working (signal field becomes `phase_end`-derived).
- Usage-limit handling survives: a limit-hit session is detected from the captured session output and the wrapper sleeps until reset (current behavior, simpler source).
- An operator can watch the live session (`tail -f` the log tee), pause the loop at the next session boundary (`touch $_ap_dir/pause-requested`), take over interactively (`/run-autopilot` resumes from the same `state.json`), and question a finished session (`claude --resume`); the runbook lives in the skill's Resuming section.

## Functional Decomposition

### Capability: Prove headless viability (spike gate)

#### Feature: Run a headless probe session

- **Description**: Verify `claude -p` supports everything a phase session needs before converting anything.
- **Inputs**: A scratch git repo with a trivial 1-task PRD; the current `/run-autopilot` skill.
- **Outputs**: `dev/local/tmp/00014-headless-spike.md` recording, with pasted output: (a) a `-p` session invokes a skill, (b) dispatches an Agent subagent and a background Bash and receives both results before emitting its final message, (c) a Stop-hook exit-2 block re-prompts the model in `-p` mode, (d) the process exits cleanly at turn end with `state.json` advanced.
- **Behavior**: If any of (a)-(d) fails, STOP the PRD and report the failure verbatim - the remaining features are void and the PRD moves to `dev/local/prds/stalled/` with the spike file as evidence. Do not work around a failed spike.

### Capability: Wrapper-owned orchestration

#### Feature: Launch sessions headless and decide from state

- **Description**: Replace the interactive launch + signal-file read with a headless launch + state read.
- **Inputs**: `~/.config/bash/plugins/development.plugin.bash`, `autoclaude` loop body.
- **Outputs**: Launch becomes `WARDEN_UNATTENDED=1 claude -p --permission-mode auto --model <model> "/run-autopilot"` with stdout/stderr teed to `$_ap_dir/last-session.log`. After exit, the wrapper reads `state.json` and branches, in order: (1) `pause_reason` set or `phase == "paused"` → notify ⚠️ with `pause_reason.detail`, stop loop; (2) `stall_reason.stalled == "subagent_prompt_overrun"` → print replan note, continue; (3) `next_phase == ""` → archive `state.json` to `reports/{batch_id}-state-final.json`, notify ✅ drained, stop loop; (4) `next_phase` non-empty → continue; (5) `state.json` missing or unreadable → usage-limit check against `last-session.log`, else notify ⚠️ died, stop loop.
- **Behavior**: The signal file is neither written nor read anywhere. `_AUTOPILOT_LOOP` export, memory circuit-breaker, orphan cleanup, and notify calls stay. The PRD 00013 metrics append is updated to source `signal` from the branch taken (`continue|paused|done|died`).

#### Feature: Cap session wall-clock

- **Description**: The one remaining kill path: a hung session (stuck tool, hung child CLI) dies at a hard cap.
- **Inputs**: The `_autopilot_loop_watchdog` sidecar in the same plugin file.
- **Outputs**: The marker/staleness logic is replaced by: if the `claude -p` child is still alive after `_AUTOPILOT_SESSION_MAX` (default 7200s), SIGTERM, then SIGKILL after 60s. `test_autoclaude_watchdog.sh` rewritten to the cap contract.
- **Behavior**: No marker files, no transcript parsing, no SIGINT-first etiquette - a capped session is a died session and takes branch (5).

#### Feature: Detect usage limits from session output

- **Description**: Keep the auto-wait-and-resume behavior with a simpler source.
- **Inputs**: `scripts/detect_usage_limit.py`, the wrapper's empty-signal branch.
- **Outputs**: The wrapper greps `last-session.log` for the usage-limit banner and extracts the reset time (extend `detect_usage_limit.py` to accept a log-file path argument; keep the transcript path as fallback). Wait-and-continue semantics and `_AUTOPILOT_LIMIT_WAIT_MAX` unchanged.
- **Behavior**: A limit-hit `-p` session exits on its own (no sidecar reap needed); the wrapper sleeps until reset + 120s and continues.

#### Feature: Operator interaction contract

- **Description**: Headless removes mid-turn chat; this defines how a human watches, pauses, and takes over an unattended batch. All interaction happens at session boundaries - the only safe point in either architecture (mid-turn interjection into an orchestrator was never reliable; it is what the review phases and batch-end review exist for).
- **Inputs**: `autoclaude` loop body; `~/.claude/skills/run-autopilot/SKILL.md` "### Resuming" section.
- **Outputs**: Four documented affordances: (a) **Watch**: `tail -f $_ap_dir/last-session.log` (the launch tee) is the live view of the running turn. (b) **Pause**: at the top of every iteration the wrapper checks `$_ap_dir/pause-requested`; if present it removes the marker, notifies "paused by operator", and exits the loop with state intact - `touch`ing that file is the sanctioned "let me in" signal, honored at the next session boundary. (c) **Take over**: with the loop stopped (pause file, or Ctrl-C on the wrapper), run `/run-autopilot` interactively in a normal session - resume-by-artifact reads the same `state.json`, and full interactive semantics (questions, PAUSEs) apply because `$_AUTOPILOT_LOOP` is unset; restart `autoclaude` afterwards to go unattended again. (d) **Forensics**: `claude --resume <session-id>` (id captured in `last-session.log`) reopens a finished headless conversation for questioning; harmless by construction - sessions are disposable and `state.json` plus the artifacts are the only orchestration contract, so a resumed chat cannot fork the loop.
- **Behavior**: A running `-p` turn is never interrupted except by the wall-clock cap. The skill's Resuming section gains this runbook as the operator-interaction contract.

### Capability: Skill-side contract update

#### Feature: Rewrite the Session Loop contract

- **Description**: The skill stops describing signals and Stop-hook choreography; hand-off = write state, print banner, end turn.
- **Inputs**: `~/.claude/skills/run-autopilot/SKILL.md` - "## Session Loop" section, the three hand-off sub-sections (Phase 3, Phase 5, Phase 7/8), Phase 9 step 10 and batch-end, "### Resuming" stale-signal cleanup, Error Handling pause rows; `~/.claude/CLAUDE.md` Workflow bullet 4 (its signal-file mechanism sentences).
- **Outputs**: Every "the Stop hook reads next_phase and writes the signal" passage becomes "end the turn; the loop wrapper reads `state.json` and relaunches". The stale-signal delete in Resuming is dropped (no signal file exists). Batch-end review in loop mode becomes non-interactive: write the deferred JSON and the batch report, set `next_phase: ""`, print the summary banner, END - and notify the user to run `/run-autopilot review-batch` interactively. A new entry point `/run-autopilot review-batch` runs the existing chunked batch-end presentation against the newest `deferred/{batch_id}-deferred.json`. In `~/.claude/CLAUDE.md` Workflow bullet 4, the signal-mechanics sentences (write `next` to the signal file, Stop hook auto-exits) are updated to end-turn semantics so the standing instruction never mandates deleted machinery - PRD 00015 rewrites bullets 3-4 wholesale right after; this edit only keeps the mechanics truthful if 00015 stalls.
- **Behavior**: Interactive (non-loop) semantics are untouched: the same state writes happen, the user re-invokes manually. The "STOP at a real hand-off, never STOP idle" discipline stays (an idle end-of-turn in `-p` just ends the session; the wrapper relaunches and the skill resumes by artifact - self-healing instead of thrash-halting).

#### Feature: Retire the Stop-hook orchestration machinery

- **Description**: Delete what the process model now does for free.
- **Inputs**: `scripts/autopilot_stop_hook.py`, `scripts/test_autopilot_stop_hook.py`, `scripts/autopilot_yield_clear_hook.py`, `scripts/test_autopilot_yield_clear_hook.py`, their `settings.json` hook registrations, `hooks/notify.py` (imports autopilot detectors for suppression).
- **Outputs**: The four autopilot hook/test files deleted; `settings.json` Stop/PostToolUse registrations for them removed; `notify.py` suppression simplified to its `_AUTOPILOT_LOOP`-ancestor check only (no transcript/bg-task detector imports). `review_coverage_hook.py` (the in-session quality gate) STAYS registered - it is a review-completeness gate, not orchestration, and the spike proved exit-2 works in `-p`.
- **Behavior**: `resume_target.py`, `test_autopilot_resume.py`, lifecycle/cap-rotation tests, and `autopilot_context_cap_hook.py` stay (resume-by-artifact and cap rotation are state semantics, not signal semantics; the cap hook's rotation write still works - the wrapper's branch (4) picks it up). Remaining test suite green after deletions.

## Structural Decomposition

### Repository Structure

```
~/.config/bash/plugins/development.plugin.bash        # Maps to: Wrapper-owned orchestration (all three features)
~/.claude/skills/run-autopilot/SKILL.md               # Maps to: Session Loop contract rewrite
~/.claude/skills/run-autopilot/scripts/               # Maps to: retirement (stop hook, yield hook + tests), detect_usage_limit.py extension
~/.claude/settings.json                               # Maps to: hook deregistration
~/.claude/hooks/notify.py                             # Maps to: suppression simplification
dev/local/tmp/00014-headless-spike.md                 # Maps to: spike gate evidence
```

### Module: autoclaude wrapper

- **Maps to capability**: Wrapper-owned orchestration
- **Responsibility**: Launch, decide, cap, wait-on-limit; sole owner of loop control flow
- **Exports**: state-branch decision table; `_AUTOPILOT_SESSION_MAX`

### Module: run-autopilot skill

- **Maps to capability**: Skill-side contract update
- **Responsibility**: State writes at hand-offs; `review-batch` entry point; no signal prose
- **Exports**: `next_phase`/`pause_reason`/`stall_reason` as the complete wrapper contract

### Module: hooks

- **Maps to capability**: Retire the Stop-hook orchestration machinery
- **Responsibility**: Only in-session quality gates remain registered
- **Exports**: none (deletions)

## Dependency Graph

### Foundation Layer (Phase 0)

- **spike**: independent; gates everything

### Core Layer (Phase 1)

- **wrapper conversion**: depends on [spike]
- **session cap**: depends on [wrapper conversion]
- **usage-limit source**: depends on [wrapper conversion]
- **operator pause + runbook**: depends on [wrapper conversion]

### Integration Layer (Phase 2)

- **SKILL contract rewrite**: depends on [wrapper conversion]
- **hook retirement**: depends on [SKILL contract rewrite] (nothing may reference the hook when it goes)
- **verification**: depends on all

## Implementation Phases

Premise rule: before each edit, re-verify the anchor still exists (`rg -n "autopilot_stop_hook" ~/.claude/settings.json ~/.claude/skills/run-autopilot/SKILL.md`; the wrapper still launches interactive `claude` and reads a signal file). PRD 00013 lands first and its metrics append must survive every wrapper edit here.

### Phase 0: Spike

**Tasks**:

- [ ] Run the headless probe (no deps) - Acceptance: spike file records (a)-(d) with pasted output; any failure → PRD stalled with evidence, no further tasks

**Exit Criteria**: All four probe points pass.

### Phase 1: Wrapper

**Tasks**:

- [ ] Convert launch + decision table (depends on: spike) - Acceptance: `claude -p` launch with tee; five-branch state read replaces signal read; signal file unreferenced in the plugin file; metrics line still written on every branch; `bash -n` clean
- [ ] Replace watchdog with session cap (depends on: launch) - Acceptance: sidecar kills only past `_AUTOPILOT_SESSION_MAX`; marker logic gone; `test_autoclaude_watchdog.sh` rewritten and green
- [ ] Extend detect_usage_limit.py to log-file input (depends on: launch) - Acceptance: given a log with the banner, prints reset epoch; transcript fallback intact; `test_detect_usage_limit.py` extended and green
- [ ] Pause file + operator runbook (depends on: launch) - Acceptance: touching `pause-requested` stops the loop at the next boundary with a notification and intact state (marker consumed); Resuming section documents watch/pause/take-over/forensics; wrapper test covers the pause-file branch

**Exit Criteria**: Wrapper never reads or writes a signal file; loop decisions come from state.json.

### Phase 2: Skill and hooks

**Tasks**:

- [ ] Rewrite Session Loop + hand-off prose, add review-batch entry (depends on: Phase 1) - Acceptance: `rg -n "signal" skills/run-autopilot/SKILL.md` shows no signal-file protocol references; three hand-off sections describe end-turn semantics; `review-batch` entry documented; batch-end loop path is non-interactive with ntfy hand-off; CLAUDE.md Workflow bullet 4 no longer describes the signal-file mechanism
- [ ] Retire stop/yield hooks and simplify notify.py (depends on: prose rewrite) - Acceptance: four files deleted; settings.json registrations removed; notify.py has no run-autopilot imports; remaining pytest suite in `skills/run-autopilot/scripts/` green with count pasted
- [ ] End-to-end drain (depends on: all) - Acceptance: a scratch 2-PRD batch drains via `autoclaude` unattended; `loop-metrics.jsonl` shows one line per session; zero ⚠️ notifications; evidence pasted

**Exit Criteria**: Success metrics all hold.

## Test Strategy

### Critical Scenarios

- **Happy path**: build → review → blind → doubt → done across sessions → Expected: wrapper relaunches on branch (4) each time, drains on branch (3)
- **Edge case**: session pauses (`pause_reason` set) → Expected: branch (1), ⚠️ notification names the site, loop stops, state preserved
- **Edge case**: usage limit mid-batch → Expected: branch (5) detects banner in log, sleeps, resumes; batch completes
- **Edge case**: hung child CLI in a session → Expected: session-max kill → branch (5) died path, loud
- **Edge case**: operator touches `pause-requested` mid-batch → Expected: current turn finishes, wrapper stops with a paused-by-operator notification, state intact; interactive `/run-autopilot` resumes from the same state
- **Error case**: state.json corrupted → Expected: branch (5) loud stop; state left for inspection

## Risks

- **Headless unknowns**: `-p` behavior with background tasks/hook-blocking is spike-gated; a failed spike stalls the PRD instead of shipping a broken loop.
- **Interactive regression**: manual `/run-autopilot` must stay working; the skill's state writes are shared, only loop prose changes. Covered by the resume tests that stay.
- **PRDs 00043/00044** (queued restructures) reference the stop hook's prose; they run later by sequence and re-derive their migration maps at execution time.
- **Repo specifics**: `$HOME` work-tree of bare repo `~/.buvis`; no CHANGELOG entries.
