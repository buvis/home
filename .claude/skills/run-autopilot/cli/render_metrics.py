#!/usr/bin/env python3
"""cli/render_metrics.py - loop-metrics rendering (PRD 00107).

Pure functions over parsed `loop-metrics.jsonl` rows (PRD 00013 fields:
`prd`, `batch`, `phase_launched`, `wall_secs`; PRD 00018 adds `model` and
`cost_usd`). Two surfaces:

- `phase_table(rows)` - the per-PRD "### Loop Metrics" table the batch
  report embeds: one row per distinct `phase_launched` (first-appearance
  order) plus a Total row.
- `render_metrics(rows)` - the standalone `autopilot render metrics`
  summary: one row per PRD across the whole file.

Both render existing fields only; a row without `cost_usd` leaves the cell
blank rather than faking zeros (the wrapper omits the key when the session
carried no usage payload). `load_rows` skips malformed lines loud on
stderr - a metrics render must never fail its report.

`load_rows` returns SESSION rows only. Since PRD 00094 the review gate also
appends event rows (`{"event": "review_converged", ...}`) to the same file:
one per PRD, with no `wall_secs` and no `cost_usd`. Counting those as
sessions would inflate every Sessions and Total cell and open a bogus `?`
phase row, so any row carrying an `event` key is dropped here. Whatever
wants those rows reads them itself.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

NO_METRICS = "no loop metrics (manual run)"


def load_rows(path: Path) -> list[dict]:
    """Parse a jsonl metrics file into SESSION rows; missing file is [],
    malformed lines skip, and event rows (any row with an `event` key) are
    dropped - see the module docstring."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows = []
    for i, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            print(
                f"render_metrics: skipping malformed line {i} of {path}",
                file=sys.stderr,
            )
            continue
        if isinstance(row, dict) and "event" not in row:
            rows.append(row)
    return rows


def matching_rows(rows: list[dict], prd: str, batch_id: str) -> list[dict]:
    return [r for r in rows if r.get("prd") == prd and r.get("batch") == batch_id]


def _cost_cell(costs: list[float]) -> str:
    return f"{sum(costs):.2f}" if costs else ""


def phase_table(rows: list[dict]) -> str:
    """The per-PRD Loop Metrics table; NO_METRICS when rows is empty."""
    if not rows:
        return NO_METRICS
    phases: dict[str, list[dict]] = {}
    for row in rows:
        phases.setdefault(str(row.get("phase_launched", "?")), []).append(row)
    lines = [
        "| Launch phase | Sessions | Wall secs | Model | Cost USD |",
        "|--------------|----------|-----------|-------|----------|",
    ]
    for phase, group in phases.items():
        models = []
        for row in group:
            model = row.get("model")
            if model and model not in models:
                models.append(model)
        costs = [row["cost_usd"] for row in group if "cost_usd" in row]
        wall = sum(int(row.get("wall_secs", 0)) for row in group)
        lines.append(
            f"| {phase} | {len(group)} | {wall} | {', '.join(models)} | {_cost_cell(costs)} |",
        )
    total_wall = sum(int(row.get("wall_secs", 0)) for row in rows)
    total_costs = [row["cost_usd"] for row in rows if "cost_usd" in row]
    lines.append(
        f"| **Total** | {len(rows)} | {total_wall} | | {_cost_cell(total_costs)} |",
    )
    return "\n".join(lines)


def render_metrics(rows: list[dict]) -> str:
    """Whole-file summary, one row per PRD (first-appearance order)."""
    if not rows:
        return NO_METRICS
    prds: dict[str, list[dict]] = {}
    for row in rows:
        prds.setdefault(str(row.get("prd", "?")), []).append(row)
    lines = [
        "| PRD | Sessions | Wall secs | Cost USD |",
        "|-----|----------|-----------|----------|",
    ]
    for prd, group in prds.items():
        wall = sum(int(row.get("wall_secs", 0)) for row in group)
        costs = [row["cost_usd"] for row in group if "cost_usd" in row]
        lines.append(f"| {prd} | {len(group)} | {wall} | {_cost_cell(costs)} |")
    total_wall = sum(int(row.get("wall_secs", 0)) for row in rows)
    total_costs = [row["cost_usd"] for row in rows if "cost_usd" in row]
    lines.append(
        f"| **Total** | {len(rows)} | {total_wall} | {_cost_cell(total_costs)} |",
    )
    return "\n".join(lines)
