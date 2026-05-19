#!/usr/bin/env python3
"""Aggregate dispatch-log.jsonl into a plain-text health report.

Usage:
    python3 dispatch_health_metrics.py [log-path]
    python3 dispatch_health_metrics.py --deadletter [log-path]

If no path given, locates dispatch-log.jsonl via walk-up from cwd.
A missing or empty log produces a zero-state report; exit 0 always.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))


def _load_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    entries: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def _find_log() -> Path | None:
    try:
        from _walk_up import find_autopilot_dir
        ap = find_autopilot_dir(Path.cwd())
        if ap:
            return ap / "dispatch-log.jsonl"
    except ImportError:
        pass
    return None


def _percentile(data: list[float], pct: float) -> float:
    """Nearest-rank percentile."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    n = len(sorted_data)
    rank = int(pct / 100 * n)
    rank = min(rank, n - 1)
    return sorted_data[rank]


def _default_report(entries: list[dict[str, Any]]) -> str:
    lines: list[str] = []

    total = len(entries)

    # Outcome counts
    outcome_counts: dict[str, int] = defaultdict(int)
    for e in entries:
        outcome_counts[e.get("outcome", "unknown")] += 1

    lines.append("Outcome counts:")
    if outcome_counts:
        for outcome, count in sorted(outcome_counts.items()):
            lines.append(f"  {outcome}: {count}")
    else:
        lines.append("  (none)")

    # Dispatch type counts
    type_counts: dict[str, int] = defaultdict(int)
    for e in entries:
        type_counts[e.get("dispatch_type", "unknown")] += 1

    lines.append("Dispatch type counts:")
    if type_counts:
        for dtype, count in sorted(type_counts.items()):
            lines.append(f"  {dtype}: {count}")
    else:
        lines.append("  (none)")

    # Hang rate
    hung_count = outcome_counts.get("hung", 0)
    hang_rate = round(hung_count / total * 100, 1) if total > 0 else 0.0
    lines.append(f"Hang rate: {hung_count}/{total} ({hang_rate}%)")

    # p50 and p95 per dispatch_type over completed dispatches
    durations_by_type: dict[str, list[float]] = defaultdict(list)
    for e in entries:
        if e.get("outcome") == "completed":
            dtype = e.get("dispatch_type", "unknown")
            dur = e.get("duration_s")
            if dur is not None:
                durations_by_type[dtype].append(float(dur))

    lines.append("Duration percentiles (completed dispatches only):")
    if durations_by_type:
        for dtype in sorted(durations_by_type.keys()):
            durs = durations_by_type[dtype]
            p50 = _percentile(durs, 50)
            p95 = _percentile(durs, 95)
            lines.append(f"  {dtype}: p50={p50:.1f}s  p95={p95:.1f}s")
    else:
        lines.append("  (no completed dispatches)")

    # Top recurring failure tasks
    failure_counts: dict[str, int] = defaultdict(int)
    for e in entries:
        if e.get("outcome") != "completed":
            failure_counts[e.get("task_name", "unknown")] += 1

    recurring = sorted(failure_counts.items(), key=lambda x: -x[1])

    lines.append("Top recurring failure tasks:")
    if recurring:
        for name, count in recurring:
            lines.append(f"  {name}: {count} failure(s)")
    else:
        lines.append("  (none)")

    return "\n".join(lines)


def _deadletter_report(entries: list[dict[str, Any]]) -> str:
    failed = [e for e in entries if e.get("outcome") != "completed"]

    # Group by task_name, newest-first within each group
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in failed:
        groups[e.get("task_name", "unknown")].append(e)

    lines: list[str] = []
    lines.append("Dead-letter queue (non-completed dispatches):")

    if not groups:
        lines.append("  (none)")
        return "\n".join(lines)

    for task_name in sorted(groups.keys()):
        task_entries = sorted(groups[task_name], key=lambda e: e.get("ts", ""), reverse=True)
        count = len(task_entries)
        flag = "  [recurring]" if count >= 3 else ""
        lines.append(f"  {task_name} ({count} failure(s)){flag}:")
        for e in task_entries:
            ts = e.get("ts", "?")
            outcome = e.get("outcome", "?")
            dtype = e.get("dispatch_type", "?")
            lines.append(f"    {ts}  {outcome}  {dtype}")

    return "\n".join(lines)


def main() -> None:
    args = sys.argv[1:]
    deadletter = False

    if args and args[0] == "--deadletter":
        deadletter = True
        args = args[1:]

    if args:
        log_path = Path(args[0])
    else:
        log_path = _find_log()
        if log_path is None:
            log_path = Path("dispatch-log.jsonl")

    entries = _load_entries(log_path)

    if deadletter:
        print(_deadletter_report(entries))
    else:
        print(_default_report(entries))


if __name__ == "__main__":
    main()
