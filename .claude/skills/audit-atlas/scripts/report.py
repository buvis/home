#!/usr/bin/env python3
"""audit-atlas report generator (PRD 00046).

Scans ~/.claude/cartographer/projects/*/ (or argv[1]) and the instincts
projects list (~/.claude/instincts/projects.json, or argv[2]) and prints the
aggregates the audit-atlas skill interprets: fresh-atlas coverage, staleness
distribution, atlas sizes, and layer population/enrichment.

Read-only. Empty/missing input prints the sections with zero counts and
exits 0; a malformed atlas.json is counted, not fatal.
"""
from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECTS_ROOT = Path.home() / ".claude" / "cartographer" / "projects"
INSTINCTS_PATH = Path.home() / ".claude" / "instincts" / "projects.json"
FRESH_MAX_AGE_DAYS = 14
ACTIVE_WINDOW_DAYS = 30
MD_BUDGET_BYTES = 5120


def _parse_ts(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def load_atlases(root: Path) -> tuple[list[dict], int]:
    """Return (atlas records, malformed count)."""
    if not root.is_dir():
        return [], 0
    records: list[dict] = []
    malformed = 0
    for d in sorted(root.iterdir()):
        atlas_json = d / "atlas.json"
        if not atlas_json.is_file():
            continue
        try:
            data = json.loads(atlas_json.read_text(errors="replace"))
        except (OSError, json.JSONDecodeError):
            malformed += 1
            continue
        surveyed = _parse_ts(data.get("surveyed_at"))
        if surveyed is not None and surveyed.tzinfo is None:
            surveyed = surveyed.replace(tzinfo=timezone.utc)
        md = d / "atlas.md"
        records.append({
            "hash": d.name,
            "surveyed_at": surveyed,
            "flag": (d / "staleness.flag").exists(),
            "json_bytes": atlas_json.stat().st_size,
            "md_bytes": md.stat().st_size if md.is_file() else 0,
            "layers": data.get("layers") or {},
            "degraded": bool(data.get("degraded")),
            "enriched": any([
                data.get("naming"),
                data.get("error_style"),
                data.get("forbidden_imports"),
                data.get("dependency_edges"),
            ]),
        })
    return records, malformed


def load_active_hashes(path: Path) -> set[str]:
    try:
        entries = json.loads(path.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError):
        return set()
    cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVE_WINDOW_DAYS)
    active: set[str] = set()
    for entry in entries if isinstance(entries, list) else []:
        ts = _parse_ts(entry.get("last_active"))
        if ts is not None and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts is not None and ts >= cutoff:
            active.add(str(entry.get("hash")))
    return active


def is_fresh(record: dict, now: datetime) -> bool:
    if record["flag"]:
        return False
    surveyed = record["surveyed_at"]
    if surveyed is None:
        return False
    return (now - surveyed) < timedelta(days=FRESH_MAX_AGE_DAYS)


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECTS_ROOT
    instincts = Path(sys.argv[2]) if len(sys.argv) > 2 else INSTINCTS_PATH
    records, malformed = load_atlases(root)
    active = load_active_hashes(instincts)
    now = datetime.now(timezone.utc)

    print(f"projects root: {root}")
    if not records:
        print("LOW: no atlases found")
    print(f"total atlases: {len(records)} (malformed: {malformed})")

    fresh = [r for r in records if is_fresh(r, now)]
    stale = [r for r in records if not is_fresh(r, now)]
    print("\n=== Fresh-atlas coverage ===")
    print(f"fresh: {len(fresh)}, stale: {len(stale)}")
    fresh_pct = 100 * len(fresh) / len(records) if records else 0.0
    print(f"fresh_pct: {fresh_pct:.1f}%")
    active_with_atlas = [r for r in records if r["hash"] in active]
    active_fresh = [r for r in active_with_atlas if is_fresh(r, now)]
    if active:
        active_fresh_pct = 100 * len(active_fresh) / len(active)
        print(f"active repos: {len(active)}; "
              f"active_fresh_pct: {active_fresh_pct:.1f}% (target >80%)")
    else:
        print("active repos: 0 (no instincts data); active_fresh_pct: n/a")

    print("\n=== Staleness distribution ===")
    for r in records:
        age = "n/a" if r["surveyed_at"] is None else f"{(now - r['surveyed_at']).days}d"
        status = "Fresh" if is_fresh(r, now) else "Stale"
        flag = "flag" if r["flag"] else "no-flag"
        print(f"  {r['hash']}: age {age}, {status}, {flag}")

    print("\n=== Atlas size ===")
    over_budget = [r for r in records if r["md_bytes"] > MD_BUDGET_BYTES]
    if records:
        print(f"median atlas.json: {int(statistics.median(r['json_bytes'] for r in records))} bytes")
        print(f"median atlas.md: {int(statistics.median(r['md_bytes'] for r in records))} bytes")
    else:
        print("median atlas.json: 0 bytes\nmedian atlas.md: 0 bytes")
    print(f"over 5KB budget: {len(over_budget)}")
    for r in over_budget:
        print(f"  {r['hash']}: atlas.md {r['md_bytes']} bytes")

    print("\n=== Layer population ===")
    under_enriched = [r for r in records if not r["enriched"]]
    degraded = [r for r in records if r["degraded"]]
    for r in records:
        layers = r["layers"]
        total = len(layers)
        populated = sum(1 for v in layers.values()
                        if isinstance(v, dict) and v.get("files"))
        pct = 100 * populated / total if total else 0.0
        note = " <-- under 80%" if pct < 80 else ""
        print(f"  {r['hash']}: {populated}/{total} layers populated ({pct:.0f}%){note}")
    print(f"under-enriched: {len(under_enriched)}")
    print(f"degraded (tree-sitter fallback): {len(degraded)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
