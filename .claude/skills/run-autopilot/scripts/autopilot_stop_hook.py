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
- Write to <autopilot_dir>/signal, UNLESS already present with the same value.
- Call find_and_signal_claude(os.getppid()) to auto-exit.

Stdlib only. Self-contained — no _common import (this script lives outside
~/.claude/hooks/).
"""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from _walk_up import find_autopilot_dir

PS_TIMEOUT_SEC = 2


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

    # Write signal (idempotent: skip rewrite if value matches).
    signal_path = autopilot_dir / "signal"
    try:
        if signal_path.exists() and signal_path.read_text().strip() == computed:
            pass  # already correct; leave file untouched
        else:
            signal_path.write_text(computed)
    except OSError:
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
