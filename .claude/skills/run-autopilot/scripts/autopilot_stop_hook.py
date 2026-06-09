#!/usr/bin/env python3
"""Stop hook for autopilot session loop.

When dev/local/autopilot/signal exists in any ancestor of cwd, autopilot is
done with the current PRD. Walks up the process tree to find the claude
process and SIGINTs it so the shell wrapper loop can restart with a fresh
session.

Walking up from cwd is mandatory: the agent may `cd` into a subdirectory
during the session, so a hard-coded relative `dev/local/autopilot/signal`
silently misses the signal. (Observed 2026-05-11.) The walk-up itself lives
in the shared `_walk_up.find_autopilot_dir` helper; this hook only appends
`signal` to the discovered dir.

Stdlib only. Self-contained — no _common import (this script lives outside
~/.claude/hooks/).
"""

import os
import signal
import subprocess
import sys
from pathlib import Path

from _walk_up import find_autopilot_dir

PS_TIMEOUT_SEC = 2


def find_signal_file(start: Path) -> Path | None:
    """Walk up from `start` looking for dev/local/autopilot/signal.

    Delegates the walk-up to the shared `_walk_up.find_autopilot_dir` helper,
    then checks for the `signal` file in the discovered autopilot dir.
    Returns the path if found, None otherwise.
    """
    autopilot_dir = find_autopilot_dir(start)
    if autopilot_dir is None:
        return None
    candidate = autopilot_dir / "signal"
    try:
        return candidate if candidate.is_file() else None
    except OSError:
        return None


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


def main() -> None:
    _drain_stdin()
    if find_signal_file(Path.cwd()) is None:
        return
    find_and_signal_claude(os.getppid())


if __name__ == "__main__":
    main()
