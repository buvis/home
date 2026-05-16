#!/usr/bin/env python3
"""Aggregate tier-escalation metrics from autopilot state.json.

Usage:
    python3 tier_escalation_metrics.py [state.json]

If no path given, locates state.json via walk-up from cwd.
Output is plain text suitable for embedding in the Phase 9 per-PRD summary.

Exit codes: 0 on success, 1 on missing/unreadable state.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

TIERS = ("haiku", "sonnet", "opus")

# Ensure the scripts directory is on the path so _walk_up is importable when
# this script is invoked directly (e.g. python3 scripts/tier_escalation_metrics.py).
sys.path.insert(0, str(Path(__file__).parent))


def _load_state(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _find_state() -> Path | None:
    try:
        from _walk_up import find_autopilot_dir
        ap = find_autopilot_dir(Path.cwd())
        if ap:
            candidate = ap / "state.json"
            if candidate.exists():
                return candidate
    except ImportError:
        pass
    return None


def _compute(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """Return computed metrics dict from a tasks list."""
    total = len(tasks)
    by_tier: dict[str, int] = {t: 0 for t in TIERS}
    escalated: list[str] = []
    chains: dict[str, int] = {}
    rework_failed: list[str] = []

    for task in tasks:
        attempts: list[dict[str, Any]] = task.get("attempts") or []
        if not attempts:
            continue

        first = attempts[0]
        initial_tier = first.get("model") or "unknown"
        if initial_tier in by_tier:
            by_tier[initial_tier] += 1

        rework_attempts = [a for a in attempts if a.get("review_cycle") is not None]
        if not rework_attempts:
            continue

        task_id = task.get("id", "?")
        escalated.append(task_id)

        last_outcome = attempts[-1].get("outcome", "")
        if last_outcome == "rework_failed":
            rework_failed.append(task_id)

        rework_tier = rework_attempts[0].get("model") or "unknown"
        if initial_tier in TIERS and rework_tier in TIERS:
            chain = f"{initial_tier}→{rework_tier}"
            chains[chain] = chains.get(chain, 0) + 1

    total_sonnet_first = by_tier.get("sonnet", 0)
    sonnet_to_opus = chains.get("sonnet→opus", 0)
    s2o_rate = (
        round(sonnet_to_opus / total_sonnet_first * 100, 1)
        if total_sonnet_first > 0
        else 0.0
    )
    overall_rate = round(len(escalated) / total * 100, 1) if total > 0 else 0.0

    return {
        "total_tasks": total,
        "by_tier": by_tier,
        "escalated_count": len(escalated),
        "escalated_ids": escalated,
        "chains": chains,
        "rework_failed": rework_failed,
        "overall_rate": overall_rate,
        "sonnet_to_opus_rate": s2o_rate,
    }


def format_metrics(m: dict[str, Any]) -> str:
    lines: list[str] = []
    total = m["total_tasks"]
    lines.append(
        f"Tier escalation ({m['escalated_count']}/{total} tasks, {m['overall_rate']}%):"
    )
    tier_parts = ", ".join(
        f"{t}: {m['by_tier'][t]}" for t in TIERS if m["by_tier"].get(t, 0) > 0
    )
    if tier_parts:
        lines.append(f"  Initial tier split — {tier_parts}")
    chains = m.get("chains") or {}
    if chains:
        chain_str = ", ".join(f"{k}: {v}" for k, v in sorted(chains.items()))
        lines.append(f"  Escalation chains — {chain_str}")
    if m["rework_failed"]:
        lines.append(
            f"  Rework failed (exhausted) — tasks: {', '.join(m['rework_failed'])}"
        )
    s2o = m["sonnet_to_opus_rate"]
    target_ok = "OK" if s2o <= 2.0 else "OVER TARGET"
    lines.append(f"  sonnet→opus rate: {s2o}% (PRD-00025 target ≤2% — {target_ok})")
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) > 1:
        state_path = Path(sys.argv[1])
    else:
        state_path = _find_state()
        if state_path is None:
            print("tier_escalation_metrics: state.json not found", file=sys.stderr)
            sys.exit(1)

    state = _load_state(state_path)
    if state is None:
        print(f"tier_escalation_metrics: cannot read {state_path}", file=sys.stderr)
        sys.exit(1)

    tasks = state.get("tasks") or []
    tasks_with_attempts = [t for t in tasks if t.get("attempts")]
    if not tasks_with_attempts:
        print("Tier escalation: no attempt data recorded.")
        return

    m = _compute(tasks_with_attempts)
    print(format_metrics(m))


if __name__ == "__main__":
    main()
