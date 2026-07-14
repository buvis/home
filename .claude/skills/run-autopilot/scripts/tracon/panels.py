from __future__ import annotations

import time
from collections.abc import Sequence

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.console import Group

from . import model
from .discovery import LoopRow, Status
from .model import fmt_dur
from .stream import AgentTracker, SessionUsage

PHASES = ("build", "review", "done")


def fmt_tok(n: int) -> str:
    if n < 1000:
        return str(n)
    if n < 1000000:
        return f"{n / 1000:.1f}k"
    return f"{n / 1000000:.1f}M"


def phase_strip(state: model.LoopState) -> Text:
    current = state.phase or state.next_phase or "—"

    if current not in PHASES:
        parts = []
        for i, p in enumerate(PHASES):
            if i > 0:
                parts.append(" ─ ")
            parts.append(("○ " + p, "dim"))

        t = Text.assemble(*parts)
        if current == "paused":
            t.stylize("bold yellow")
        else:
            t.stylize("dim")
        t.append(f" · {current}")
    else:
        parts = []
        for p in PHASES:
            if parts:
                parts.append(" ─ ")

            if p in state.phases_completed:
                mark = "✓"
                style = ""
            elif p == current:
                mark = "●"
                style = "bold cyan"
            else:
                mark = "○"
                style = "dim"

            if style:
                parts.append((f"{mark} {p}", style))
            else:
                parts.append(f"{mark} {p}")

        t = Text.assemble(*parts)

    if state.needs_attention:
        t.stylize("bold red")

    return t


def agents_row(tracker: AgentTracker) -> Text | None:
    lanes = tracker.live_lanes()
    tasks = tracker.live_tasks()
    combined = lanes + tasks
    if not combined:
        return None

    t = Text("agents ")
    for i, lane in enumerate(combined):
        if i > 0:
            t.append(" · ")
        if lane.kind == "local_agent":
            t.append(f"⟨{lane.label}⟩", style=lane.color)
            if lane.n > 0 or lane.last:
                t.append(f" ⚒{lane.last}×{lane.n}")
        else:
            t.append(f"{lane.label} ▷{lane.status}", style=lane.color)

    return t


def head_rows(agents: Text | None) -> int:
    return 5 if agents is not None else 4


def _row_head(state: model.LoopState) -> Text:
    row1 = Text(no_wrap=True, overflow="ellipsis")
    task = (
        f"{state.tasks_completed}/{state.tasks_total}"
        if state.tasks_completed is not None and state.tasks_total is not None
        else "—"
    )
    cycle = (
        f"{state.cycle}/{state.rework_cap}"
        if state.cycle is not None and state.rework_cap is not None
        else "—"
    )
    phase = state.phase or state.next_phase or "—"
    row1.append(f"{phase} · {state.prd_name} · task {task} · {cycle}")

    gs = model.guards(state)
    if gs:
        g_texts = [f"{label}: {detail}" for label, detail in gs]
        row1.append(" · " + ", ".join(g_texts))

    if state.needs_attention:
        row1.append(" · ⚠ needs attention")
    return row1


def _row_progress(
    rows: Sequence[model.MetricsRow],
    status: Status,
    prd_counts: tuple[int, int],
    batch_id: str,
    session_start: float | None,
    now: float,
    usage: SessionUsage,
) -> Text:
    row3 = Text(no_wrap=True, overflow="ellipsis")
    backlog, wip = prd_counts
    sess_count = len(rows)

    last = model.last_row(rows)
    b_start = model.batch_start_ts(batch_id, rows)

    if b_start is None:
        elapsed_str = "—"
    else:
        end_ts = now if status.in_flight else (last.ts_end if last else None)
        elapsed_str = "—" if end_ts is None else fmt_dur(end_ts - b_start)

    active_secs = sum(r.wall_secs for r in rows)
    if status.in_flight and session_start is not None:
        active_secs += now - session_start

    cost = sum(r.cost_usd for r in rows)

    row3.append(f"{backlog} backlog · {wip} wip · {sess_count} sessions · {elapsed_str} elapsed · {fmt_dur(active_secs)} active · ${cost:.2f} cost")

    if status.in_flight and usage.session_cost > 0:
        row3.append(f" +${usage.session_cost:.2f} live")

    return row3


def _row_usage(usage: SessionUsage, status: Status) -> Text:
    row4 = Text(no_wrap=True, overflow="ellipsis")
    up, cached, out = usage.totals()
    row4.append(f"session {usage.model} · tok ↑{fmt_tok(up)} ⤓{fmt_tok(cached)} ↓{fmt_tok(out)} · ctx {fmt_tok(usage.context_size())} · ")
    row4.append(status.label, style=status.style)
    return row4


def build_head(
    state: model.LoopState,
    rows: Sequence[model.MetricsRow],
    usage: SessionUsage,
    status: Status,
    prd_counts: tuple[int, int],
    batch_id: str,
    root_name: str,
    session_start: float | None,
    agents: Text | None = None,
    now: float | None = None,
    wrapper: bool = False,
) -> Panel:
    if now is None:
        now = time.time()

    row1 = _row_head(state)
    if wrapper:
        row1.append(" · ⟳ wrapper")

    row2 = phase_strip(state)
    row2.no_wrap = True
    row2.overflow = "ellipsis"

    row3 = _row_progress(rows, status, prd_counts, batch_id, session_start, now, usage)
    row4 = _row_usage(usage, status)

    lines = [row1, row2, row3, row4]
    if agents is not None:
        agents.no_wrap = True
        agents.overflow = "ellipsis"
        lines.insert(2, agents)

    return Panel(Group(*lines), title=root_name)


def fleet_cells(row: LoopRow) -> tuple:
    prd = row.prd if len(row.prd) <= 44 else row.prd[:43] + "…"
    cost_t = Text(f"${row.cost:.2f}")
    if row.live_cost > 0:
        cost_t.append(f" +${row.live_cost:.2f}", style="dim")

    name = f"⟳ {row.name}" if row.wrapper else row.name

    return (
        name,
        Text(row.status.label, style=row.status.style),
        row.phase,
        prd,
        row.task,
        row.cycle,
        cost_t,
        str(row.sessions),
    )


def fleet_table(rows: Sequence[LoopRow]) -> Table:
    table = Table(box=None, show_header=True)
    table.add_column("project")
    table.add_column("status")
    table.add_column("phase")
    table.add_column("prd")
    table.add_column("task")
    table.add_column("cycle")
    table.add_column("cost")
    table.add_column("sessions", justify="right")

    sorted_rows = sorted(rows, key=lambda r: (r.status.rank, r.name))

    for r in sorted_rows:
        table.add_row(*fleet_cells(r))

    return table
