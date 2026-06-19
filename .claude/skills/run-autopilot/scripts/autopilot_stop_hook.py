#!/usr/bin/env python3
"""Stop hook for autopilot session loop.

Reads state.json and $_AUTOPILOT_LOOP, then COMPUTES and WRITES the loop
signal. Auto-exits by SIGINTing the claude parent process so the shell wrapper
loop can restart with a fresh session.

Decision table (first match wins):
1. $_AUTOPILOT_LOOP unset/empty -> no signal, no auto-exit.
2. dev/local/autopilot dir not found -> no signal, no auto-exit.
3. state.json absent or corrupt -> no signal, no auto-exit (fail open).
4. state["phase"] == "paused" -> no signal, no auto-exit.
5. stall_reason.stalled == "subagent_prompt_overrun" -> signal = "task_aborted".
6. next_phase == "" (empty string) -> signal = "done".
7. next_phase is a non-empty string -> signal = "next".
8. Otherwise -> no signal, no auto-exit (fail open).

After computing a signal (cases 5-7):
- Consult the review-coverage gate. If a review surface just completed but its
  coverage is incomplete, the gate blocks: write NO signal and do NOT auto-exit,
  so the session stays alive for review_coverage_hook.py (same Stop event) to
  inject its blocking feedback and let the model finish the review. Without this
  the SIGINT below killed the session before it could act on that feedback, the
  coverage hook deleted the signal, and the loop reported "ended without a
  signal" (observed 2026-06-11 and 2026-06-12).
- Otherwise write to <autopilot_dir>/signal, UNLESS already present with the
  same value, then call find_and_signal_claude(os.getppid()) to auto-exit.

Stdlib only, plus the sibling review_coverage_hook module for the shared gate
decision (both live in this scripts/ dir). No _common import (this script
lives outside ~/.claude/hooks/).
"""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from _walk_up import find_autopilot_dir

try:
    # Sibling module in this scripts/ dir. Shared so the signal hook and the
    # coverage hook never disagree about a review handoff. If it cannot be
    # imported, fall open (gate_blocks=None -> hand-off proceeds as before).
    from review_coverage_hook import gate_blocks
except ImportError:
    gate_blocks = None

try:
    # Reuse the cap hook's atomic state writer (temp + os.replace) so both hooks
    # persist state.json the same way and never drift. If it cannot be imported,
    # the phase-thrash guard simply does not persist (fail open, no worse than
    # before the guard existed).
    from autopilot_context_cap_hook import _atomic_write_state
except ImportError:
    _atomic_write_state = None

PS_TIMEOUT_SEC = 2

# A review/build phase that hands off "next" with no forward progress this many
# consecutive times is a thrash, not progress (blind-review async-dispatch loop,
# observed 2026-06-17 on PRD 00157: 18 dead restarts, ~885k output tokens, zero
# progress). At the limit the hook withholds the signal so the wrapper loop
# exits cleanly — the same halt a PAUSE uses.
PHASE_THRASH_LIMIT = 3


def _progress_key(state: dict) -> str:
    """Fingerprint of forward progress across a hand-off. Two consecutive "next"
    hand-offs with the same key means the phase advanced nothing — a thrash. Any
    real step (phase/cycle change, a phase or task completing, a replan or cap
    rotation, a new review cycle) changes the key and resets the counter."""
    return "|".join(
        str(x)
        for x in (
            state.get("phase", ""),
            state.get("next_phase", ""),
            len(state.get("phases_completed") or []),
            state.get("tasks_completed", 0),
            state.get("cycle", 0),
            state.get("replan_count") or 0,
            len(state.get("cap_rotations") or []),
            len(state.get("review_cycles") or []),
        )
    )


def _drain_stdin() -> None:
    """Stop hooks always receive a JSON payload on stdin. Discard it."""
    try:
        sys.stdin.read()
    except OSError:
        pass


def _ps(args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["ps", *args],
            capture_output=True,
            text=True,
            timeout=PS_TIMEOUT_SEC,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def comm_for(pid: int) -> str:
    return _ps(["-p", str(pid), "-o", "comm="])


def parent_of(pid: int) -> int:
    raw = _ps(["-o", "ppid=", "-p", str(pid)])
    if not raw.isdigit():
        return 0
    return int(raw)


def find_and_signal_claude(start_pid: int) -> bool:
    pid = start_pid
    while pid > 1:
        comm = comm_for(pid)
        if comm and os.path.basename(comm) == "claude":
            try:
                os.kill(pid, signal.SIGINT)
            except OSError:
                return False
            return True
        next_pid = parent_of(pid)
        if next_pid <= 0 or next_pid == pid:
            break
        pid = next_pid
    return False


def _compute_signal(state: dict) -> str | None:
    """Return the signal string, or None if no signal should be written."""
    if state.get("phase") == "paused":
        return None
    stall = state.get("stall_reason")
    if isinstance(stall, dict) and stall.get("stalled") == "subagent_prompt_overrun":
        return "task_aborted"
    next_phase = state.get("next_phase")
    if next_phase == "":
        return "done"
    if next_phase:
        return "next"
    return None


def main() -> None:
    _drain_stdin()

    # Step 1: check _AUTOPILOT_LOOP.
    loop_val = os.environ.get("_AUTOPILOT_LOOP", "")
    if not loop_val:
        return

    # Step 2: locate autopilot dir.
    autopilot_dir = find_autopilot_dir(Path.cwd())
    if autopilot_dir is None:
        return

    # Step 3: read and parse state.json (fail open on missing/corrupt).
    state_path = autopilot_dir / "state.json"
    try:
        state: dict = json.loads(state_path.read_text())
    except (OSError, json.JSONDecodeError):
        return

    # Steps 4-8: compute signal.
    computed = _compute_signal(state)
    if computed is None:
        return

    # Defer to the review-coverage gate before signaling. When a review
    # surface just completed but its coverage is incomplete, the session must
    # stay alive so the model can finish the review — review_coverage_hook.py
    # (same Stop event) emits the block + feedback. Writing the signal and
    # SIGINTing here would kill the session before it could act on that
    # feedback, and the coverage hook's signal deletion would leave the loop
    # reporting "ended without a signal" (observed 2026-06-11 and 2026-06-12).
    # gate_blocks is phase-aware: it returns (False, ...) for non-review phases,
    # so build/PRD-to-PRD/task_aborted hand-offs are unaffected. Fail open on
    # any gate error — the coverage hook runs the same gate and likewise won't
    # block, so the hand-off proceeds without a race.
    if gate_blocks is not None:
        try:
            blocked, _ = gate_blocks(autopilot_dir, state)
        except Exception as exc:
            sys.stderr.write(
                f"autopilot stop hook: review gate check errored ({exc}); "
                "proceeding with hand-off (fail open)\n"
            )
            blocked = False
        if blocked:
            return

    # Phase-thrash circuit-breaker (the "next" hand-off only). A phase that
    # re-enters with no forward progress PHASE_THRASH_LIMIT times is stuck: the
    # 2026-06-17 blind-review loop dispatched an async reviewer and yielded
    # before the result landed, so "blind" never reached phases_completed and
    # the loop re-ran it 18 times (~885k output tokens, zero progress). On trip,
    # withhold the signal — the wrapper sees no signal and exits its loop
    # cleanly (same halt as a PAUSE) — and record the stall for the user.
    # "done"/"task_aborted" are out of scope: batch end and the replan_count cap
    # bound those on their own.
    if computed == "next":
        guard = state.get("phase_guard") or {}
        key = _progress_key(state)
        count = guard.get("count", 0) + 1 if guard.get("key") == key else 1
        state["phase_guard"] = {"key": key, "count": count}
        tripped = count >= PHASE_THRASH_LIMIT
        if tripped:
            state["needs_attention"] = True
            state["thrash_halt"] = {
                "phase": state.get("phase", ""),
                "next_phase": state.get("next_phase", ""),
                "repeats": count,
            }
        if _atomic_write_state is not None:
            _atomic_write_state(autopilot_dir, state)
        if tripped:
            sys.stderr.write(
                "autopilot stop hook: PHASE THRASH — phase "
                f"\"{state.get('phase', '')}\" handed off \"next\" {count}x with "
                "no progress. Withholding the loop signal and halting "
                "(needs_attention set, thrash_halt recorded in state.json). The "
                "phase is not advancing; inspect before re-running.\n"
            )
            # Exit the session WITHOUT writing a signal: claude exits, the
            # wrapper reads an empty signal, hits its `*)` case ("NOT drained")
            # and breaks the loop. SIGINT (not a passive return) makes the
            # unattended loop halt deterministically instead of idling on a live
            # session.
            find_and_signal_claude(os.getppid())
            return

    # Write signal (idempotent: skip rewrite if value matches).
    signal_path = autopilot_dir / "signal"
    if signal_path.exists() and signal_path.read_text().strip() == computed:
        pass  # already correct; leave file untouched
    else:
        signal_path.write_text(computed)

    # Batch end: delete state.json after emitting "done" so the next batch
    # starts from a clean slate (no stale phases_completed -> no skipped
    # reviews). This is the durable-marker cleanup the model used to do by
    # deleting state itself; the hook owns it now.
    if computed == "done":
        try:
            state_path.unlink()
        except OSError:
            pass

    find_and_signal_claude(os.getppid())


if __name__ == "__main__":
    main()
