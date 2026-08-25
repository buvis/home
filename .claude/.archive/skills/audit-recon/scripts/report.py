#!/usr/bin/env python3
"""audit-recon report generator (PRD 00046).

Reads ~/.claude/cartographer/audit.jsonl (or the path given as argv[1]),
keeps `phase == "recon"` events, and prints the aggregates the audit-recon
skill interprets: inject uniqueness per (repo x day), missing-atlas repos,
stale-at-inject rate, and the excerpt-size distribution.

Read-only. Never mutates the audit log. Empty/missing input prints the
sections with zero counts and exits 0; malformed lines are counted, not fatal.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

AUDIT_PATH = Path.home() / ".claude" / "cartographer" / "audit.jsonl"
EXCERPT_CAP_BYTES = 1024


def load_recon_events(path: Path) -> tuple[list[dict], int]:
    """Return (recon events, malformed line count)."""
    if not path.exists():
        return [], 0
    events: list[dict] = []
    malformed = 0
    with path.open(errors="replace") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if event.get("phase") == "recon":
                events.append(event)
    return events, malformed


def _day(event: dict) -> str:
    return str(event.get("ts") or "")[:10] or "<no-ts>"


def print_uniqueness(injects: list[dict]) -> None:
    print("\n=== Inject uniqueness (repo x day) ===")
    groups: Counter = Counter((e.get("repo_hash"), _day(e)) for e in injects)
    doubles = {k: c for k, c in groups.items() if c > 1}
    print(f"(repo x day) groups: {len(groups)}; double-inject groups: {len(doubles)}")
    for (repo, day), count in sorted(doubles.items(), key=lambda kv: -kv[1]):
        verdict = "THROTTLE BROKEN (>=3)" if count >= 3 else "within race tolerance (2)"
        print(f"  {repo} {day}: {count} injects — {verdict}")


def print_missing_atlas(events: list[dict]) -> None:
    print("\n=== Missing-atlas repos ===")
    missing = [e for e in events if e.get("decision") == "atlas-missing"]
    per_repo: dict[str, list[str]] = defaultdict(list)
    for e in missing:
        per_repo[e.get("repo_hash") or "<none>"].append(_day(e))
    print(f"repos needing /survey: {len(per_repo)}")
    for repo, days in sorted(per_repo.items(), key=lambda kv: -len(kv[1])):
        print(f"  {repo}: {len(days)} events, last day {max(days)}")


def print_stale_rate(injects: list[dict]) -> None:
    print("\n=== Stale-at-inject rate ===")
    stale = [e for e in injects if e.get("stale")]
    pct = 100 * len(stale) / len(injects) if injects else 0.0
    print(f"stale_pct: {pct:.1f}% ({len(stale)} of {len(injects)} injects)")
    per_repo: dict[str, list[str]] = defaultdict(list)
    for e in stale:
        per_repo[e.get("repo_hash") or "<none>"].append(_day(e))
    for repo, days in sorted(per_repo.items()):
        print(f"  {repo}: {len(days)} stale injects, last stale day {max(days)}")


def print_excerpt_sizes(injects: list[dict]) -> None:
    print("\n=== Excerpt-size distribution ===")
    sizes = [int(e.get("atlas_excerpt_bytes") or 0) for e in injects]
    if not sizes:
        print("  min: 0\n  median: 0\n  max: 0\n  at 1024-byte cap: 0")
        return
    at_cap = sum(1 for s in sizes if s == EXCERPT_CAP_BYTES)
    print(f"  min: {min(sizes)}")
    print(f"  median: {int(statistics.median(sizes))}")
    print(f"  max: {max(sizes)}")
    print(f"  at 1024-byte cap: {at_cap} injects")


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else AUDIT_PATH
    events, malformed = load_recon_events(path)
    injects = [e for e in events if e.get("decision") == "inject"]
    missing = [e for e in events if e.get("decision") == "atlas-missing"]

    print(f"audit log: {path}")
    if not events:
        print("LOW: no recon events recorded yet")
    print(f"recon events: {len(events)} (inject events: {len(injects)}, "
          f"atlas-missing events: {len(missing)}, malformed: {malformed})")

    print_uniqueness(injects)
    print_missing_atlas(events)
    print_stale_rate(injects)
    print_excerpt_sizes(injects)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
