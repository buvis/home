# Add An Idle Watchdog To The Autopilot Loop

> Source: 2026-06-23 halt-surface audit (jink 00025 reviewer-strand investigation). Closes the idle-deadlock class the Stop hook structurally cannot bound.
> Target: `run-autopilot` skill (`scripts/autopilot_stop_hook.py` + NEW `scripts/autopilot_yield_clear_hook.py` + `settings.json`) + the `autoclaude` wrapper (`~/.config/bash/plugins/development.plugin.bash`).
> **Priority: HIGH** - the only remaining way the loop hangs silently instead of failing loud.
> **Amended 2026-06-29** (design review). The original v1 prescribed a raw `.heartbeat` touched on PostToolUse + a wrapper that backgrounds `claude` and polls `find -mmin`. Design review found that mechanism (a) rests on unverified backgrounding of the interactive `claude` TUI (SIGTTIN-stop / EOF-exit), and (b) keys on time-since-last-tool-completion, which cannot tell an actively-working session from a yielded-and-waiting one and so contradicts the "never kill active work" metric. This amendment replaces it with: a **yield discriminator** (the Stop hook stamps `.yielded-waiting` only when it abstains because a background task is in flight; a matcher-less PostToolUse hook clears it on any tool use), a **foreground-unchanged `claude` + sidecar watchdog** (no backgrounding of the TUI), and a **SIGINT→SIGKILL** kill path. A second design-review pass (on the revised design) added two corrections now folded in: the marker clear must live in a **NEW matcher-less PostToolUse hook** (`autopilot_yield_clear_hook.py`), not the existing context-cap hook whose matcher excludes `Edit`/`Write`/`MultiEdit`/`TaskUpdate` (so the clear would miss edit-only turns and false-kill active work); and the sidecar must capture its own `$BASHPID` outside any command substitution and confirm the target's `comm == claude` before signalling (a naive `pgrep | grep -v -x "$BASHPID" | head -n1` resolves the watchdog's own pid). The context-cap hook is left untouched.

## Overview

### Problem Statement
The Stop hook keeps a session alive (abstains: no signal, no SIGINT) while a background task is in flight, relying on the harness to re-invoke the model with a `<task-notification>` on completion. That is correct when the task completes. But the Stop hook fires ONCE per yield and cannot re-check during idle, so if a background task ORPHANS (hangs, never emits its notification) no re-invoke ever comes: the session idles at its prompt forever and the `while true` wrapper blocks indefinitely (`autopilot_stop_hook.py` `_pending_background_task` `:314`, `_waiting_on_async` `:474` — both abstain with no wall-clock bound). Every prior fix is transcript pattern-matching; none bounds a task that simply never reports. No watchdog exists (`dispatch_deadline.py` is absent from this skill).

### Target Users
The operator running an unattended `autoclaude` batch who must not return to find the loop silently wedged on a hung reviewer/test instead of having advanced or failed loud.

### Success Metrics
- A session whose Stop hook has been ABSTAINING (yielded, waiting on a background task with no re-invocation) for more than N minutes while `claude` is still alive is SIGINT-killed (escalating to SIGKILL), converting an eternal idle into the existing loud `''`-signal halt ("Backlog NOT drained").
- A session that is actively making tool calls, running a foreground tool, or thinking is NEVER killed, regardless of total elapsed time. This is **structural**, not threshold-tuned: the idle signal (`.yielded-waiting`) exists only between an abstaining yield and the next tool use, so active work carries no idle signal at all.
- `claude`'s launch is byte-identical to today (foreground, full TTY); only a sidecar watchdog process is added. No backgrounding of the interactive TUI.
- The kill reuses the existing SIGINT → empty-signal → wrapper `*)`/`''` halt path; no new halt semantics.

### Non-Goals
- A fixed total-runtime cap (would kill legitimately-long active phases).
- Distinguishing a *legitimately slow* background task from an *orphaned* one **before** N elapses. This is irreducible: while a background task is in flight and has not re-invoked, a slow-but-alive task and a dead one have an identical signature. N must therefore sit above the longest legitimate background-task wait, and any task that can legitimately exceed N must carry its own internal watchdog (as `codex_review_run.py` already does). The watchdog only bounds the wait into a clean halt; it does not diagnose or restart the hung task.
- Backgrounding the `claude` TUI, or any change to how `claude` is invoked.
- A long-running daemon. The watchdog is a per-session sidecar that lives and dies with its `claude`.

## Functional Decomposition

### Capability: Yield discriminator
A single on-disk marker, `<autopilot_dir>/.yielded-waiting`, whose presence-and-age means "the session yielded waiting on a background task that has not re-invoked." It is the ONLY thing the wrapper needs to `stat`; it is never parsed.

#### Feature: Stop-hook yield stamp
- **Description**: stamp `.yielded-waiting` exactly when the Stop hook abstains because a background task is in flight.
- **Inputs**: the Stop event; the resolved autopilot dir (the hook already resolves it via `find_autopilot_dir`); the abstain decision (`_pending_background_task` / `_waiting_on_async` true → main() returns with no signal, no auto-exit).
- **Outputs**: `<autopilot_dir>/.yielded-waiting` mtime = the time of this abstaining yield.
- **Behavior**: at each abstain return point in `autopilot_stop_hook.py::main()` (the in-flight-Agent path `:706` and the auto-backgrounded-Bash/wakeup path `:692`), `(<autopilot_dir>/".yielded-waiting").touch()` before returning, inside try/except (fail-open — a touch failure must never change the hook's signal decision). The hook only stamps on the abstain paths; on a real hand-off (signal written + auto-exit) and on `phase == "paused"` it does NOT stamp. A true orphan triggers exactly one abstain → one stamp → frozen mtime → the wrapper fires at N. A normal yield is re-stamped on each subsequent abstain (mtime tracks the latest yield).

#### Feature: PostToolUse activity clear
- **Description**: delete `.yielded-waiting` on every tool use, so an active (re-invoked) session carries no idle signal.
- **Inputs**: the PostToolUse event; the resolved autopilot dir.
- **Outputs**: `<autopilot_dir>/.yielded-waiting` removed.
- **Behavior**: a NEW matcher-less PostToolUse hook `autopilot_yield_clear_hook.py` resolves the autopilot dir (`find_autopilot_dir(Path.cwd())`, like the cap hook) and `(<autopilot_dir>/".yielded-waiting").unlink(missing_ok=True)` inside try/except (fail-open). It MUST be matcher-less: the existing `autopilot_context_cap_hook.py` matcher (`Bash|Read|Grep|Glob|Agent|WebFetch|WebSearch|mcp__.*`) excludes `Edit`/`Write`/`MultiEdit`/`TaskUpdate`, so hosting the clear there would miss edit-only turns and let the marker go stale during active work → a false-positive kill. A tool use means the model is active, not idle-waiting, so the idle clock is cleared; the next abstaining yield (if any) re-stamps it. Registered in `settings.json` `hooks.PostToolUse` with an empty matcher, alongside the existing matcher-less `clear-pidash-attention.py` / `observe_tool.py`. The context-cap hook is left untouched.

### Capability: Wrapper-side idle kill
#### Feature: Foreground claude + sidecar watchdog
- **Description**: keep `claude` in the foreground exactly as today; add a background sidecar that polls `.yielded-waiting` and kills only an idle-waiting session.
- **Inputs**: the `.yielded-waiting` file, the wrapper pid, an idle threshold N (minutes), a poll interval S (seconds), a SIGKILL-escalation count K (stale polls after the first SIGINT).
- **Outputs**: SIGINT (then SIGKILL) to the `claude` session when idle-waiting longer than N.
- **Behavior**: in `autoclaude` (`development.plugin.bash`), before launching `claude`, `rm -f "$_ap_dir/.yielded-waiting"` (a stale marker from the prior session's last yield must not arm the watchdog against a fresh session). Launch `claude ...` UNCHANGED in the foreground. Alongside it, run a backgrounded sidecar `_autopilot_loop_watchdog` that (1) resolves the foreground `claude` pid as the child of the wrapper (`pgrep -P "$wrapper_pid"`, excluding its own `$BASHPID`/matching the `claude` invocation), and (2) every S seconds, while that pid is alive, if `.yielded-waiting` exists and is older than N minutes (`find "$_ap_dir/.yielded-waiting" -mmin +N` non-empty), sends `kill -INT`; if it remains alive and stale for K further polls, escalates to `kill -KILL`. When `claude` exits (on its own STOP, or from the watchdog's signal), the wrapper stops the sidecar (`kill "$_wd_pid"`), then reads the loop signal exactly as today. A watchdog SIGINT/SIGKILL mid-phase leaves no signal → the existing `''` case fails loud.

## Structural Decomposition

### Files
```
~/.claude/skills/run-autopilot/scripts/autopilot_stop_hook.py             # + .yielded-waiting touch on each abstain return
~/.claude/skills/run-autopilot/scripts/autopilot_yield_clear_hook.py      # NEW: matcher-less PostToolUse hook, unlinks .yielded-waiting
~/.claude/settings.json                                                   # register the clear hook (matcher-less PostToolUse entry)
~/.config/bash/plugins/development.plugin.bash                            # autoclaude: foreground claude + sidecar idle-poll
~/.claude/skills/run-autopilot/scripts/test_autopilot_stop_hook.py        # + stamp-on-abstain tests
~/.claude/skills/run-autopilot/scripts/test_autopilot_yield_clear_hook.py # NEW: clear-on-PostToolUse tests
~/.claude/skills/run-autopilot/scripts/test_autoclaude_watchdog.sh        # NEW: stub-claude sidecar poll tests
```

### Module: Stop hook (Stop)
- **Responsibility**: stamp `.yielded-waiting` iff it abstains because a background task is in flight. Fail-open — a touch failure must never alter the signal decision or block auto-exit. Must NOT stamp on a real hand-off or on `phase == "paused"`.

### Module: yield-clear hook (matcher-less PostToolUse)
- **Responsibility**: clear `.yielded-waiting` on EVERY tool use (matcher-less so it covers Edit/Write/TaskUpdate, which the cap hook's matcher omits). Self-contained, stdlib-only, lives in `scripts/` so `_walk_up` imports. Fail-open — an unlink failure must never block a tool call.

### Module: autoclaude wrapper
- **Responsibility**: bound idle without changing how `claude` is launched. Distinguish idle-waiting (marker present + stale) from busy (marker absent or fresh) from done (claude exited). Identify and signal the correct `claude` pid; never signal a bystander.

## Dependency Graph

### Foundation Layer (Phase 0)
- **yield stamp + activity clear**: no deps on each other beyond sharing the marker filename. Without them the wrapper has nothing to poll.

### Core Layer (Phase 1)
- **sidecar watchdog**: depends on [Phase 0].

### Integration Layer (Phase 2)
- **threshold tuning (N, S, K)**: depends on [Phase 1].

## Implementation Phases

### Phase 0: Yield discriminator
**Goal**: `.yielded-waiting` exists exactly while the session is yielded-waiting on a background task, and is cleared the moment the model is active again.
**Tasks**:
- [ ] In `autopilot_stop_hook.py::main()`, at BOTH abstain return points (in-flight Agent `:706`; auto-backgrounded Bash / scheduled wakeup `:692`), `(<autopilot_dir>/".yielded-waiting").touch()` inside try/except before returning. Do NOT stamp on the hand-off paths (signal written) or `phase == "paused"` (no deps) — Acceptance: a unit test asserts `.yielded-waiting` is created when `main()` abstains on an in-flight Agent dispatch and on an auto-backgrounded Bash; asserts it is NOT created on a `next`/`done`/`task_aborted` hand-off nor on `phase == "paused"`; asserts a `touch` raising `OSError` does not change the computed signal.
- [ ] Add NEW matcher-less PostToolUse hook `autopilot_yield_clear_hook.py` (stdlib only, in `scripts/`): resolve `find_autopilot_dir(Path.cwd())`, return if None, else `(<autopilot_dir>/".yielded-waiting").unlink(missing_ok=True)` inside try/except; register it in `settings.json` `hooks.PostToolUse` with an empty matcher (no deps) — Acceptance: a unit test asserts the marker is removed when present and is a no-op when absent or when cwd is not under an autopilot dir; asserts an `unlink` raising `OSError` does not propagate; a registration test asserts the matcher-less entry is present in `settings.json`. The clear MUST be matcher-less (not in the cap hook) so it fires on `Edit`/`Write`/`MultiEdit`/`TaskUpdate`.
**Exit Criteria**: stamp appears only on an abstaining yield; clear runs on every tool use (all tool kinds) in every phase; both fail-open.

### Phase 1: Sidecar watchdog
**Goal**: the wrapper kills only an idle-waiting session, without changing how `claude` is launched.
**Tasks**:
- [ ] In `autoclaude`, hoist the `_ap_dir` resolution above the launch, `rm -f "$_ap_dir/.yielded-waiting"` before launch, keep the `claude ...` launch byte-identical in the FOREGROUND, run a backgrounded `_autopilot_loop_watchdog` that resolves the foreground `claude` pid as the wrapper's direct child whose `comm == claude` — capturing `local _self="$BASHPID"` as the FIRST statement (outside any `$(...)`) and excluding it, NOT `pgrep | grep -v -x "$BASHPID" | head -n1` (which resolves the watchdog's own pid) — and, while it is alive, polls every S sec: if `find "$_ap_dir/.yielded-waiting" -mmin +N` is non-empty `kill -INT`, escalating to `kill -KILL` after K further stale polls; on `claude` exit, `kill "$_wd_pid"` and read the signal as today (depends on: Phase 0) — Acceptance: a stub test asserts the sidecar resolves the intended child (comm match) and never itself or a bystander sibling; with a pre-aged `.yielded-waiting`, the watchdog SIGINTs then (after K polls) SIGKILLs it and the wrapper falls into the existing `''` halt; with no `.yielded-waiting` (or a fresh one) the stub is NEVER signaled and runs to completion; the `claude` launch line and the signal read/delete lines are byte-identical to the current wrapper; a one-time real-`claude` smoke test confirms the sidecar resolves and signals the actual `claude` pid and signals no bystander.
- [ ] Update the `autoclaude` INT/TERM traps so a user Ctrl-C also tears down the foreground `claude` and the sidecar (the existing `_autopilot_loop_cleanup` only HUPs PPID=1 orphans) (depends on: prior task) — Acceptance: a test or documented manual check confirms Ctrl-C during a run does not leave an orphaned `claude` or sidecar.
**Exit Criteria**: idle-waiting killed (with guaranteed termination), active survives, `claude` invocation and signal handling unchanged, no orphaned children on abort.

### Phase 2: Thresholds
**Goal**: N, S, K are safe for the longest legitimate quiet stretch.
**Tasks**:
- [ ] Set N, S, K from observed waits, env-overridable, documented inline: N defaults to 20 min (comfortably above the longest legitimate background-task wait — codex/doubt runs are silent for minutes and carry their own internal watchdog; `codex_review_run.py` notes long silent model turns are normal), S=60 s (`find -mmin` granularity is whole minutes), K=2 stale polls before SIGKILL (`_AUTOPILOT_IDLE_MINS` / `_AUTOPILOT_POLL_SECS` / `_AUTOPILOT_KILL_AFTER`) (depends on: Phase 1) — Acceptance: N/S/K and their rationale are documented in the wrapper; a known-good doubt-phase run does not trip the watchdog.
**Exit Criteria**: no false kills on real workloads.

## Test Strategy
- **Idle-waiting → kill**: `.yielded-waiting` present and frozen > N while the (stub) process is alive → SIGINT, then SIGKILL after K stale polls → `''` halt.
- **Active → survive**: `.yielded-waiting` absent (cleared by a tool use) or fresh → never signaled, even past N total elapsed.
- **Stamp only on abstain**: Stop-hook `main()` creates `.yielded-waiting` on the in-flight-Agent and auto-backgrounded-Bash abstains, and NOT on `next`/`done`/`task_aborted` hand-offs or `phase == "paused"`.
- **Clear before the build gate**: a PostToolUse in a non-`build` phase removes `.yielded-waiting`.
- **Fail-open**: a `touch` (stop hook) or `unlink` (cap hook) raising must not change the signal decision, block the tool, or break the cap logic.
- **Stale cross-session marker**: a `.yielded-waiting` left by the prior session is removed by the wrapper before launch, so it cannot arm the watchdog against a fresh session.
- **Pid targeting**: the sidecar signals the real `claude` and never a bystander (stub test for the discovery predicate + one-time real-`claude` smoke test).
- **Done → clean**: `claude` exits normally → the wrapper stops the sidecar and reads the real signal, no spurious kill.

## Risks
- **Threshold too low** → kills a legitimately-quiet-but-alive background wait. Mitigation: N comfortably above the longest observed legitimate wait (20 min); tasks that can legitimately exceed N must carry their own internal watchdog (codex does). The yield discriminator already removes the foreground-tool / active-work false positives that a raw heartbeat would have had.
- **`find -mmin` is BSD/macOS-dependent.** This box is darwin 25.5; BSD `find` supports `-mmin`. The Phase 1 stub test pre-ages the marker and asserts staleness, so it fails loud if `-mmin` is unsupported. Portable fallback if ever needed: `stat -f %m` vs `date +%s`.
- **Sidecar pid mis-targeting** → signals a bystander or never finds `claude` (silent false negative). Mitigation: scope discovery to direct children of the wrapper pid and match the `claude` invocation; the one-time real-`claude` smoke test is the gate; if discovery proves unreliable, fall back to the existing `_AUTOPILOT_LOOP` env-marker scan that `_autopilot_loop_cleanup` already uses.
- **`claude` ignores a single SIGINT** (debounced double-Ctrl-C exit) → Mitigation: the SIGKILL escalation after K stale polls guarantees termination regardless.
- **`.yielded-waiting` contends with the atomic state write**. Mitigation: separate file, `touch`/`unlink` only, never read by the hooks, fail-open.
- **Wrapper bash regression breaks the loop**. Mitigation: stub-`claude` tests for the sidecar logic before landing; keep `claude`'s launch byte-identical (foreground); preserve the existing `while true`/signal-case structure; the only structural change is hoisting `_ap_dir` and adding the sidecar around the launch.
