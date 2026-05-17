#!/usr/bin/env python3
"""Shared walk-up helper: locate the autopilot dir from cwd.

Used by autopilot hooks, scripts, and Bash callers (`--bash` entry) so the
walk-up pattern lives in one place. The pattern: starting from `start`,
resolve symlinks, then walk up the parent chain looking for a directory
named `dev/local/autopilot`. Return the resolved path to that directory if
found, None otherwise. Stop at filesystem root.

Why walk up: agents may `cd` into a subdirectory (or through a symlink)
during a session. A hard-coded relative `dev/local/autopilot/...` resolution
silently misses the dir. Hooks (and Bash one-liners that emit signal files)
must use the resolved absolute path.

Stdlib only. Self-contained — no other project imports.

Python API:
    from _walk_up import find_autopilot_dir
    autopilot_dir = find_autopilot_dir(Path.cwd())

Bash entry:
    autopilot_dir=$(python3 .../scripts/_walk_up.py --bash)
    # prints resolved dir to stdout; exits 0 on hit, 1 on miss
    # optional second arg: start directory (default cwd)
"""

from __future__ import annotations

import sys
from pathlib import Path

AUTOPILOT_REL_PATH = Path("dev") / "local" / "autopilot"


def find_autopilot_dir(start: Path) -> Path | None:
    """Walk up from `start` looking for dev/local/autopilot/.

    Returns the resolved path if found, None otherwise. Stops at filesystem
    root. Resolves symlinks via `Path.resolve()` so callers get a stable
    absolute path even when invoked through a symlinked cwd.
    """
    try:
        current = start.resolve()
    except OSError:
        return None
    while True:
        candidate = current / AUTOPILOT_REL_PATH
        try:
            if candidate.is_dir():
                return candidate
        except OSError:
            pass
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _main_bash() -> int:
    start_arg = sys.argv[2] if len(sys.argv) > 2 else None
    start = Path(start_arg) if start_arg else Path.cwd()
    result = find_autopilot_dir(start)
    if result is None:
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--bash":
        sys.exit(_main_bash())
    sys.stderr.write(
        "usage: _walk_up.py --bash [start_dir]\n"
        "       (or import find_autopilot_dir from Python)\n"
    )
    sys.exit(2)
