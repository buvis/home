#!/usr/bin/env python3
"""Compute adaptive watchdog deadline in seconds for a dispatch type.

Usage:
    python3 dispatch_deadline.py <dispatch_type> [log-path]

Prints an integer seconds value to stdout.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _dispatch_log import find_dispatch_log, load_entries, percentile


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 1:
        print("Usage: python3 dispatch_deadline.py <dispatch_type> [log-path]", file=sys.stderr)
        sys.exit(1)
    dispatch_type = args[0]
    log_path = Path(args[1]) if len(args) > 1 else find_dispatch_log()

    entries = load_entries(log_path)
    durations = [
        float(e["duration_s"])
        for e in entries
        if e.get("outcome") == "completed"
        and e.get("dispatch_type") == dispatch_type
        and e.get("duration_s") is not None
    ]

    if len(durations) < 5:
        print(900)
        return

    deadline = int(max(300, min(900, percentile(durations, 95) * 2)))
    print(deadline)


if __name__ == "__main__":
    main()
