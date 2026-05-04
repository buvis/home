#!/usr/bin/env python3
"""Stop hook for autopilot session loop.

When ./dev/local/autopilot/signal exists, autopilot is done with the current
PRD. Walks up the process tree to find the claude process and SIGINTs it so
the shell wrapper loop can restart with a fresh session.

Stdlib only. Self-contained — no _common import (this script lives outside
~/.claude/hooks/).
"""

import os
import signal
import subprocess
import sys
from pathlib import Path

PS_TIMEOUT_SEC = 2
SIGNAL_FILE = Path("dev") / "local" / "autopilot" / "signal"


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
        if comm and "claude" in comm:
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
    if not SIGNAL_FILE.is_file():
        return
    find_and_signal_claude(os.getppid())


if __name__ == "__main__":
    main()
