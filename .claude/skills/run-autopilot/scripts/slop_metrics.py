#!/usr/bin/env python3
"""Compute the per-PRD bloat metric and emit it as a markdown block.

Bloat metric: net lines added by this PRD divided by the count of acceptance
criteria items in the PRD's ``## Implementation Phases`` section. Surfaces
unusual diff-size growth in the autopilot batch report.

Compares ``lines_per_AC`` against the rolling median across up to the last 5
``Lines per AC`` values found in batch reports under
``dev/local/autopilot/reports/``. Status labels:

- ``LOW`` — ratio < 1.5x median
- ``NORMAL`` — 1.5x ≤ ratio ≤ 2.5x
- ``HIGH`` — ratio > 2.5x
- ``INSUFFICIENT_DATA`` — fewer than 3 prior values

Informational only. Does not gate or trigger anything. Graceful degradation on
any missing input: exits zero and writes nothing when ``state.json`` is absent
or malformed, matching ``tier_escalation_metrics.py``.

Usage:
    python3 slop_metrics.py

Stdlib only.
"""

from __future__ import annotations

import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

AC_TASK_LINE_RE = re.compile(r"^\s*-\s*\[\s*\]\s*", re.M)
SHORTSTAT_INSERTIONS_RE = re.compile(r"(\d+)\s+insertions?\(\+\)")
SHORTSTAT_DELETIONS_RE = re.compile(r"(\d+)\s+deletions?\(-\)")
BLOAT_LINES_PER_AC_RE = re.compile(r"^-\s*Lines per AC:\s*([\d.]+)\s*$", re.M)

LOW_RATIO = 1.5
HIGH_RATIO = 2.5
SAMPLE_SIZE = 5
MIN_PRIOR_VALUES = 3


def count_acceptance_criteria(prd_text: str) -> int:
    """Return the number of ``- [ ]`` task lines under ``## Implementation Phases``.

    Returns 0 when the section is absent or contains no checkbox tasks.
    """
    start = prd_text.find("## Implementation Phases")
    if start == -1:
        return 0
    rest = prd_text[start + len("## Implementation Phases"):]
    next_section = re.search(r"^## ", rest, re.M)
    section = rest[:next_section.start()] if next_section else rest
    return len(AC_TASK_LINE_RE.findall(section))


def net_lines_added(work_start_sha: str) -> int | None:
    """Return ``insertions - deletions`` in ``<work_start_sha>..HEAD``.

    Returns ``None`` when the SHA is empty or ``git diff`` fails.
    """
    if not work_start_sha:
        return None
    try:
        result = subprocess.run(
            ["git", "diff", "--shortstat", f"{work_start_sha}..HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    ins_match = SHORTSTAT_INSERTIONS_RE.search(result.stdout)
    del_match = SHORTSTAT_DELETIONS_RE.search(result.stdout)
    insertions = int(ins_match.group(1)) if ins_match else 0
    deletions = int(del_match.group(1)) if del_match else 0
    return insertions - deletions


def collect_prior_lines_per_ac(reports_dir: Path) -> list[float]:
    """Return ``Lines per AC`` values from existing batch reports, newest first.

    Scans every ``*-report.md`` file in ``reports_dir`` ordered by modification
    time (newest first) and, within each file, extracts matches in reverse
    appearance order so the most recent PRD's value comes first.
    """
    if not reports_dir.is_dir():
        return []
    report_files = sorted(
        reports_dir.glob("*-report.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    values: list[float] = []
    for path in report_files:
        try:
            text = path.read_text()
        except OSError:
            continue
        matches = list(BLOAT_LINES_PER_AC_RE.finditer(text))
        for match in reversed(matches):
            try:
                values.append(float(match.group(1)))
            except ValueError:
                continue
    return values


def status_label(lines_per_ac: float, median: float) -> str:
    """Classify the ratio as LOW / NORMAL / HIGH."""
    if median <= 0:
        return "NORMAL"
    ratio = lines_per_ac / median
    if ratio < LOW_RATIO:
        return "LOW"
    if ratio > HIGH_RATIO:
        return "HIGH"
    return "NORMAL"


def find_prd_file(autopilot_dir: Path, prd_filename: str) -> Path | None:
    """Locate the PRD file in ``wip/``, ``done/``, or ``stalled/``.

    ``autopilot_dir`` is ``<repo>/dev/local/autopilot``; the prds directory is
    its sibling ``<repo>/dev/local/prds``.
    """
    prds_dir = autopilot_dir.parent / "prds"
    for subdir in ("wip", "done", "stalled"):
        candidate = prds_dir / subdir / prd_filename
        if candidate.is_file():
            return candidate
    return None


def render_block(
    lines_added: int,
    ac_count: int,
    lines_per_ac: float,
    sample: list[float],
) -> str:
    """Render the markdown block consumed by Phase 9 step 9."""
    lines = ["### Bloat metric"]
    lines.append(f"- Net lines added: {lines_added}")
    lines.append(f"- Acceptance criteria items: {ac_count}")
    lines.append(f"- Lines per AC: {lines_per_ac:.1f}")
    if len(sample) < MIN_PRIOR_VALUES:
        lines.append("- Median across last 5 PRDs: n/a")
        lines.append("- Status: INSUFFICIENT_DATA")
        return "\n".join(lines)
    median = statistics.median(sample)
    status = status_label(lines_per_ac, median)
    lines.append(f"- Median across last 5 PRDs: {median:.1f}")
    if median > 0:
        lines.append(f"- Status: {status} ({lines_per_ac / median:.1f}x median)")
    else:
        lines.append(f"- Status: {status}")
    return "\n".join(lines)


def main() -> int:
    try:
        from _walk_up import find_autopilot_dir
    except ImportError:
        return 0
    autopilot_dir = find_autopilot_dir(Path.cwd())
    if autopilot_dir is None:
        return 0
    try:
        state = json.loads((autopilot_dir / "state.json").read_text())
    except (OSError, ValueError):
        return 0
    prd_filename = state.get("prd")
    if not prd_filename:
        return 0
    prd_path = find_prd_file(autopilot_dir, prd_filename)
    if prd_path is None:
        return 0
    try:
        prd_text = prd_path.read_text()
    except OSError:
        return 0
    lines_added = net_lines_added(state.get("work_start_sha", ""))
    if lines_added is None:
        return 0
    ac_count = count_acceptance_criteria(prd_text)
    lines_per_ac = lines_added / max(1, ac_count)
    prior_values = collect_prior_lines_per_ac(autopilot_dir / "reports")
    sample = prior_values[:SAMPLE_SIZE]
    print(render_block(lines_added, ac_count, lines_per_ac, sample))
    return 0


if __name__ == "__main__":
    sys.exit(main())
