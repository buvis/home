#!/usr/bin/env python3
"""Compute adaptive watchdog deadline in seconds for a dispatch type.

Usage:
    python3 dispatch_deadline.py <dispatch_type> [log-path]

Prints an integer seconds value to stdout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))


def _percentile(data: list[float], pct: float) -> float:
    """Nearest-rank percentile (copied from dispatch_health_metrics.py for consistency)."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    n = len(sorted_data)
    rank = int(pct / 100 * n)
    rank = min(rank, n - 1)
    return sorted_data[rank]


def _load_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def _find_log() -> Path:
    try:
        from _walk_up import find_autopilot_dir
        ap = find_autopilot_dir(Path.cwd())
        if ap:
            return ap / "dispatch-log.jsonl"
    except ImportError:
        pass
    return Path("dispatch-log.jsonl")


def main() -> None:
    args = sys.argv[1:]
    dispatch_type = args[0]
    log_path = Path(args[1]) if len(args) > 1 else _find_log()

    entries = _load_entries(log_path)
    durations = [
        float(e["duration_s"])
        for e in entries
        if e.get("outcome") == "completed" and e.get("dispatch_type") == dispatch_type
    ]

    if len(durations) < 5:
        print(900)
        return

    deadline = int(max(300, min(900, _percentile(durations, 95) * 2)))
    print(deadline)


if __name__ == "__main__":
    main()
