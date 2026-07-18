"""Tolerant, stdlib-only parse layer for autopilot on-disk artifacts.

Single parse point for the tracon package. Hard rule: never raise on a
real file. Missing file, malformed JSON, wrong-typed field, legacy shape
all fall back to sensible defaults instead of an exception.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SIGNALS = ("continue", "paused", "done", "died")
TAIL_BYTES = 512 * 1024
USAGE_CAP = 500_000  # ctx gauge denominator; mirrors autopilot_context_cap_hook.USAGE_CAP


@dataclass(frozen=True)
class MetricsRow:
    ts_start: float | None
    ts_end: float | None
    wall_secs: float
    prd: str
    batch: str
    phase_launched: str
    phase_end: str
    signal: str
    model: str
    cost_usd: float
    tokens_out: int


@dataclass(frozen=True)
class LoopState:
    prd: str
    phase: str
    next_phase: str
    phases_completed: tuple[str, ...]
    cycle: int | None
    rework_cap: int | None
    tasks_total: int | None
    tasks_completed: int | None
    batch_id: str
    needs_attention: bool
    exists: bool
    raw: dict[str, Any]

    @property
    def prd_name(self) -> str:
        if not self.prd:
            return "—"
        return self.prd.removesuffix(".md")


def _str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _int_or_default(value: Any, default: int = 0) -> int:
    result = _int_or_none(value)
    return default if result is None else result


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _float_or_default(value: Any, default: float = 0.0) -> float:
    result = _float_or_none(value)
    return default if result is None else result


def _tuple_of_str(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return ()


def _batch_id(batch: Any) -> str:
    if isinstance(batch, dict):
        bid = batch.get("id")
        if isinstance(bid, str):
            return bid
    return ""


def _empty_state() -> LoopState:
    return LoopState(
        prd="",
        phase="",
        next_phase="",
        phases_completed=(),
        cycle=None,
        rework_cap=None,
        tasks_total=None,
        tasks_completed=None,
        batch_id="",
        needs_attention=False,
        exists=False,
        raw={},
    )


def read_state(path: Path) -> LoopState:
    try:
        text = path.read_text()
    except (OSError, ValueError):
        return _empty_state()
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        return _empty_state()
    if not isinstance(data, dict):
        return _empty_state()
    return LoopState(
        prd=_str(data.get("prd")),
        phase=_str(data.get("phase")),
        next_phase=_str(data.get("next_phase")),
        phases_completed=_tuple_of_str(data.get("phases_completed")),
        cycle=_int_or_none(data.get("cycle")),
        rework_cap=_int_or_none(data.get("rework_cap")),
        tasks_total=_int_or_none(data.get("tasks_total")),
        tasks_completed=_int_or_none(data.get("tasks_completed")),
        batch_id=_batch_id(data.get("batch")),
        needs_attention=bool(data.get("needs_attention", False)),
        exists=True,
        raw=data,
    )


def _parse_json_object_line(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
    except (ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def _parse_metrics_row(data: dict[str, Any]) -> MetricsRow:
    return MetricsRow(
        ts_start=_float_or_none(data.get("ts_start")),
        ts_end=_float_or_none(data.get("ts_end")),
        wall_secs=_float_or_default(data.get("wall_secs")),
        prd=_str(data.get("prd")),
        batch=_str(data.get("batch")),
        phase_launched=_str(data.get("phase_launched")),
        phase_end=_str(data.get("phase_end")),
        signal=_str(data.get("signal")),
        model=_str(data.get("model")),
        cost_usd=_float_or_default(data.get("cost_usd")),
        tokens_out=_int_or_default(data.get("tokens_out")),
    )


def read_metrics(path: Path, batch: str | None = None) -> list[MetricsRow]:
    if batch == "":
        return []
    try:
        lines = path.read_text().splitlines()
    except (OSError, ValueError):
        return []
    rows: list[MetricsRow] = []
    for line in lines:
        data = _parse_json_object_line(line)
        if data is None:
            continue
        row = _parse_metrics_row(data)
        if batch is not None and row.batch != batch:
            continue
        rows.append(row)
    return rows


def last_row(rows: Sequence[MetricsRow]) -> MetricsRow | None:
    return max(rows, key=lambda row: row.ts_end if row.ts_end is not None else 0.0, default=None)


def batch_start_ts(batch: str, rows: Sequence[MetricsRow]) -> float | None:
    starts = [row.ts_start for row in rows if row.ts_start is not None]
    if starts:
        return min(starts)
    try:
        return dt.datetime.strptime(batch, "%Y%m%d%H%M").timestamp()
    except ValueError:
        return None


def guards(state: LoopState) -> list[tuple[str, str]]:
    raw = state.raw
    result: list[tuple[str, str]] = []

    if "stall_reason" in raw:
        v = raw["stall_reason"]
        if isinstance(v, dict) and "stalled" in v:
            result.append(("stall", str(v["stalled"])))
        else:
            result.append(("stall", "present"))

    if "cap_pause_reason" in raw:
        v = raw["cap_pause_reason"]
        if isinstance(v, dict) and "cycle" in v and "cap" in v:
            # row 1's `cycle x/y` counter already carries the numbers
            result.append(("cap-pause", "at cap"))
        else:
            result.append(("cap-pause", "present"))

    if "pause_reason" in raw:
        v = raw["pause_reason"]
        if isinstance(v, dict) and "site" in v and "detail" in v:
            result.append(("paused", f"{v['site']}: {v['detail']}"))
        else:
            result.append(("paused", "present"))

    if "thrash_halt" in raw:
        result.append(("thrash", "halted"))

    if "phase_guard" in raw:
        result.append(("guard", "phase"))

    # No standalone cycle-at-cap guard: row 1 always renders `cycle x/y`,
    # and the acted-on case surfaces as cap-pause above.
    return result


BUILD_STEPS = ("catchup", "design", "plan", "work")
LANES = ("in_progress", "pending", "completed")


def build_steps_done(state: LoopState) -> dict[str, bool]:
    """Which build sub-steps have finished, inferred from state artifacts:
    catchup by its batch stamp (or a skip mode), design by its doc (or a
    skip mode), plan by a task snapshot existing, work by all tasks done."""
    raw = state.raw
    batch = raw.get("batch") if isinstance(raw.get("batch"), dict) else {}
    tasks = raw.get("tasks") if isinstance(raw.get("tasks"), list) else []
    all_done = (
        bool(tasks)
        and state.tasks_total is not None
        and state.tasks_total > 0
        and state.tasks_completed is not None
        and state.tasks_completed >= state.tasks_total
    )
    return {
        "catchup": bool(batch.get("catchup_completed_at"))
        or raw.get("catchup_mode") in ("skip", "skipped"),
        "design": bool(raw.get("design_doc"))
        or raw.get("design_mode") in ("skip", "skipped"),
        "plan": bool(tasks),
        "work": all_done,
    }


def tasks_by_lane(state: LoopState) -> dict[str, list[dict[str, Any]]]:
    """Group the state.tasks snapshot into kanban lanes; unknown or missing
    statuses land in pending, junk entries are dropped."""
    lanes: dict[str, list[dict[str, Any]]] = {lane: [] for lane in LANES}
    tasks = state.raw.get("tasks")
    if not isinstance(tasks, list):
        return lanes
    for item in tasks:
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        lanes[status if status in lanes else "pending"].append(item)
    return lanes


def current_task_name(state: LoopState) -> str:
    """Name of the task being worked: first in_progress, else first pending."""
    tasks = state.raw.get("tasks")
    if not isinstance(tasks, list):
        return ""
    for wanted in ("in_progress", "pending"):
        for item in tasks:
            if isinstance(item, dict) and item.get("status") == wanted:
                return _str(item.get("name"))
    return ""


def prd_counts(root: Path) -> tuple[int, int]:
    backlog = root / "dev" / "local" / "prds" / "backlog"
    wip = root / "dev" / "local" / "prds" / "wip"
    return (len(list(backlog.glob("*.md"))), len(list(wip.glob("*.md"))))


def scan_session_cost(path: Path, tail_bytes: int = TAIL_BYTES) -> float:
    try:
        size = path.stat().st_size
    except OSError:
        return 0.0
    offset = max(0, size - tail_bytes)
    try:
        with path.open("rb") as f:
            f.seek(offset)
            chunk = f.read()
    except OSError:
        return 0.0
    lines = chunk.decode("utf-8", errors="ignore").split("\n")
    cost = 0.0
    for line in lines:
        data = _parse_json_object_line(line)
        if data is None:
            continue
        if data.get("type") == "result":
            c = data.get("total_cost_usd")
            if isinstance(c, (int, float)) and not isinstance(c, bool):
                cost = float(c)
    return cost


def fmt_dur(secs: float) -> str:
    if secs < 0:
        secs = 0
    secs = int(secs)
    if secs < 60:
        return f"{secs}s"
    mins = secs // 60
    s = secs % 60
    if mins < 60:
        return f"{mins}m{s:02}s"
    h = mins // 60
    m = mins % 60
    return f"{h}h{m:02}m"
