"""Status classification and loop/registry discovery for tracon.

Stdlib-only: no rich, no textual, no tracon.panels. Classifies a loop's
on-disk state into a display Status, assembles a LoopRow for a single loop
root, and discovers loop roots from the gita repo registry.
"""

from __future__ import annotations

import csv
import datetime as dt
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from . import model
from .model import LoopState, MetricsRow

GITA_REGISTRY = Path.home() / ".config/gita/repos.csv"
LIVE_WINDOW = 20.0
IN_FLIGHT_SLACK = 2.0


@dataclass(frozen=True)
class Status:
    label: str
    style: str
    rank: int
    in_flight: bool


@dataclass(frozen=True)
class LoopRow:
    root: Path
    name: str
    status: Status
    phase: str
    prd: str
    task: str
    cycle: str
    cost: float
    live_cost: float
    sessions: int


def _fmt_clock(ts: float | None) -> str:
    return dt.datetime.fromtimestamp(ts or 0.0).strftime("%H:%M")


def classify(
    state: LoopState, rows: Sequence[MetricsRow], log_mtime: float | None, now: float
) -> Status:
    last = model.last_row(rows)
    in_flight = log_mtime is not None and (
        last is None or log_mtime > (last.ts_end or 0.0) + IN_FLIGHT_SLACK
    )
    live = in_flight and (now - log_mtime) < LIVE_WINDOW
    quiet = in_flight and not live

    if state.needs_attention:
        return Status(label="⚠ attention", style="bold red", rank=0, in_flight=in_flight)
    if live:
        return Status(label="● live", style="green", rank=2, in_flight=in_flight)
    if quiet:
        age = model.fmt_dur(now - log_mtime)
        return Status(label=f"◐ quiet {age}", style="yellow", rank=2, in_flight=in_flight)
    if last is not None:
        if last.signal == "died":
            clock = _fmt_clock(last.ts_end)
            return Status(label=f"■ died {clock}", style="bold red", rank=1, in_flight=in_flight)
        if last.signal == "paused":
            clock = _fmt_clock(last.ts_end)
            return Status(label=f"⏸ paused {clock}", style="yellow", rank=1, in_flight=in_flight)
        if last.signal == "done":
            clock = _fmt_clock(last.ts_end)
            return Status(label=f"✔ drained {clock}", style="dim", rank=4, in_flight=in_flight)
    if not state.exists:
        return Status(label="○ no state", style="dim", rank=5, in_flight=in_flight)
    if log_mtime is None:
        return Status(label="○ no log", style="dim", rank=3, in_flight=in_flight)
    age = model.fmt_dur(now - log_mtime)
    return Status(label=f"○ idle {age}", style="dim", rank=3, in_flight=in_flight)


def loop_status(root: Path, now: float | None = None) -> LoopRow:
    if now is None:
        now = time.time()
    autopilot_dir = root / "dev" / "local" / "autopilot"
    state = model.read_state(autopilot_dir / "state.json")
    rows = model.read_metrics(autopilot_dir / "loop-metrics.jsonl", state.batch_id)

    log_path = autopilot_dir / "last-session.log"
    try:
        log_mtime: float | None = log_path.stat().st_mtime
    except OSError:
        log_mtime = None

    status = classify(state, rows, log_mtime, now)
    live_cost = model.scan_session_cost(log_path) if status.in_flight else 0.0

    if state.tasks_completed is not None and state.tasks_total is not None:
        task = f"{state.tasks_completed}/{state.tasks_total}"
    else:
        task = "—"

    if state.cycle is not None and state.rework_cap is not None:
        cycle = f"{state.cycle}/{state.rework_cap}"
    else:
        cycle = "—"

    return LoopRow(
        root=root,
        name=root.name,
        status=status,
        phase=state.phase or state.next_phase or "—",
        prd=state.prd_name,
        task=task,
        cycle=cycle,
        cost=sum(row.cost_usd for row in rows),
        live_cost=live_cost,
        sessions=len(rows),
    )


def discover_loops(registry: Path = GITA_REGISTRY) -> list[Path]:
    home = Path.home() / ".claude"
    try:
        text = registry.read_text()
    except OSError:
        return [home] if (home / "dev" / "local" / "autopilot").is_dir() else []

    candidates = [home]
    for row in csv.reader(text.splitlines()):
        if not row:
            continue
        col1 = row[0].strip()
        if not col1:
            continue
        path = Path(col1)
        if not path.is_absolute():
            continue
        if path not in candidates:
            candidates.append(path)

    return [root for root in candidates if (root / "dev" / "local" / "autopilot").is_dir()]
