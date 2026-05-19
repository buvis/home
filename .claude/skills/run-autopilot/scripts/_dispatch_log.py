#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from _walk_up import find_autopilot_dir


def percentile(data: list[float], pct: float) -> float:
    """Nearest-rank percentile."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    n = len(sorted_data)
    rank = int(pct / 100 * n)
    rank = min(rank, n - 1)
    return sorted_data[rank]


def load_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def find_dispatch_log() -> Path:
    autopilot_dir = find_autopilot_dir(Path.cwd())
    if autopilot_dir:
        return autopilot_dir / "dispatch-log.jsonl"
    return Path("dispatch-log.jsonl")
