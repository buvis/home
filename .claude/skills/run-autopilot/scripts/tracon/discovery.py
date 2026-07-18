"""Status classification and loop/registry discovery for tracon.

Stdlib-only: no rich, no textual, no tracon.panels. Classifies a loop's
on-disk state into a display Status, assembles a LoopRow for a single loop
root, and discovers loop roots from the gita repo registry.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from . import model
from .model import LoopState, MetricsRow

GITA_REGISTRY = Path.home() / ".config/gita/repos.csv"
LOOPS_DIR = Path(os.environ.get("_AUTOPILOT_LOOPS_DIR") or Path.home() / ".claude" / "autopilot-loops")
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
    wrapper: bool = False


@dataclass(frozen=True)
class Wrapper:
    pid: int
    root: Path
    started_at: str


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_registry(loops_dir: Path | None = None) -> list[Wrapper]:
    loops_dir = LOOPS_DIR if loops_dir is None else loops_dir
    try:
        paths = list(loops_dir.glob("*.json"))
    except OSError:
        return []

    wrappers: list[Wrapper] = []
    for path in paths:
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        pid = data.get("pid")
        root = data.get("root")
        if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0 or not isinstance(root, str):
            continue
        started_at = data.get("started_at")
        wrappers.append(
            Wrapper(pid=pid, root=Path(root), started_at=started_at if isinstance(started_at, str) else "")
        )
    return wrappers


def wrapper_alive(root: Path, loops_dir: Path | None = None) -> bool:
    resolved_root = root.resolve()
    return any(
        wrapper.root.resolve() == resolved_root and pid_alive(wrapper.pid)
        for wrapper in read_registry(loops_dir=loops_dir)
    )


def _fmt_clock(ts: float | None) -> str:
    return dt.datetime.fromtimestamp(ts or 0.0).strftime("%H:%M")


_LIMIT_CACHE: dict[Path, tuple[float, int | None]] = {}


def limit_reset(log_path: Path, log_mtime: float | None) -> int | None:
    """Reset epoch when the log tail ends in a usage-limit banner, else None.

    Cached per (path, mtime): during the wrapper's limit sleep the log is
    static, so the tick loop must not rescan it every 0.5s."""
    if log_mtime is None:
        return None
    hit = _LIMIT_CACHE.get(log_path)
    if hit is not None and hit[0] == log_mtime:
        return hit[1]
    scripts_dir = str(Path(__file__).resolve().parents[1])
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import detect_usage_limit

    reset = detect_usage_limit.detect_from_log(log_path)
    _LIMIT_CACHE[log_path] = (log_mtime, reset)
    return reset


def limit_wait_status(
    status: Status, log_path: Path, log_mtime: float | None, wrapper: bool, now: float
) -> Status:
    """Upgrade idle-under-a-live-wrapper to a limit-wait countdown.

    The wrapper sleeps inline until the usage-limit reset, appending no
    metrics row, so classify() reads the gap as idle/died. A live wrapper
    plus a future reset in the log tail proves the loop is waiting, not
    dead. needs_attention (rank 0) stays on top."""
    if not wrapper or status.in_flight or status.rank == 0:
        return status
    reset = limit_reset(log_path, log_mtime)
    if reset is None or reset <= now:
        return status
    label = f"⏳ limit-wait {model.fmt_dur(reset - now)} → {_fmt_clock(float(reset))}"
    return Status(label=label, style="yellow", rank=1, in_flight=False)


ORPHAN_FRESH_SECS = 86400.0


def pause_pending_status(status: Status, root: Path, wrapper: bool) -> Status:
    """Suffix the status while a pause-requested marker awaits a live wrapper.

    Pressing p only touches the marker; the wrapper acts on it at session
    end. Without the chip the keypress looks like it did nothing. With no
    wrapper alive the marker is inert — showing it would just pile onto the
    paused/orphaned indicators."""
    if not wrapper:
        return status
    if not (root / "dev" / "local" / "autopilot" / "pause-requested").exists():
        return status
    return Status(
        label=f"{status.label} · ⏸ pause requested",
        style=status.style,
        rank=status.rank,
        in_flight=status.in_flight,
    )


def orphan_status(
    status: Status,
    state: LoopState,
    wrapper: bool,
    last_end: float | None,
    log_mtime: float | None,
    now: float,
) -> Status:
    """Loud warning when work is queued but nothing will relaunch it.

    A wrapper that dies mid-batch (closed terminal, crash, breaker) leaves
    next_phase set with no autoclaude to act on it — classify() renders
    that as a dim idle/no-log row, which reads as fine. Only the dim
    non-terminal statuses (rank >= 3) are upgraded: died/paused keep their
    own deliberate labels, drained batches have next_phase == "". Fresh
    orphans (< 24h) are bold; long-parked ones keep their age visible."""
    if wrapper or status.in_flight or status.rank < 3:
        return status
    if state.next_phase not in ("build", "review", "done"):
        return status
    anchor = last_end if last_end is not None else log_mtime
    age = f" {model.fmt_dur(now - anchor)}" if anchor is not None else ""
    fresh = anchor is not None and now - anchor < ORPHAN_FRESH_SECS
    style = "bold red" if fresh else "red"
    return Status(label=f"⚠ orphaned{age} · run autoclaude", style=style, rank=1, in_flight=False)


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

    wrapper = wrapper_alive(root)
    status = classify(state, rows, log_mtime, now)
    status = limit_wait_status(status, log_path, log_mtime, wrapper, now)
    last = model.last_row(rows)
    status = orphan_status(
        status, state, wrapper, last.ts_end if last is not None else None, log_mtime, now
    )
    status = pause_pending_status(status, root, wrapper)
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
        wrapper=wrapper,
    )


def discover_loops(registry: Path = GITA_REGISTRY, loops_dir: Path | None = None) -> list[Path]:
    home = Path.home() / ".claude"
    candidates = [home]

    try:
        text = registry.read_text()
    except OSError:
        text = None

    if text is not None:
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

    for wrapper in read_registry(loops_dir=loops_dir):
        if pid_alive(wrapper.pid) and wrapper.root not in candidates:
            candidates.append(wrapper.root)

    result: list[Path] = []
    seen: set[Path] = set()
    for root in candidates:
        if not (root / "dev" / "local" / "autopilot").is_dir():
            continue
        resolved = root.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(root)

    return result
