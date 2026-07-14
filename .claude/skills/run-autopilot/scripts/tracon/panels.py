from __future__ import annotations

import time
from typing import Sequence

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.console import Group

from tracon import model
from tracon.discovery import LoopRow, Status
from tracon.stream import AgentTracker, SessionUsage

PHASES = ("build", "review", "done")


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


def fmt_tok(n: int) -> str:
    if n < 1000:
        return str(n)
    if n < 1000000:
        return f"{n / 1000:.1f}k"
    return f"{n / 1000000:.1f}M"


def phase_strip(state: model.LoopState) -> Text:
    current = state.phase or state.next_phase

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
        t.append(f"⟨{lane.label}⟩", style=lane.color)
        if lane.n > 0 or lane.last:
            t.append(f" ⚒{lane.last}×{lane.n}")

    return t


def head_rows(agents: Text | None) -> int:
    return 5 if agents is not None else 4


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
) -> Panel:
    if now is None:
        now = time.time()

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
    row1.append(
        f"{state.phase or state.next_phase} · {state.prd_name} · task {task} · {cycle}"
    )

    gs = model.guards(state)
    if gs:
        g_texts = [f"{label}: {detail}" for label, detail in gs]
        row1.append(" · " + ", ".join(g_texts))

    if state.needs_attention:
        row1.append(" · ⚠ needs attention")

    row2 = phase_strip(state)
    row2.no_wrap = True
    row2.overflow = "ellipsis"

    row3 = Text(no_wrap=True, overflow="ellipsis")
    backlog, wip = prd_counts
    sess_count = len(rows)

    last = model.last_row(rows)
    b_start = model.batch_start_ts(batch_id, rows)

    if b_start is None:
        elapsed_str = "—"
    else:
        # `last` is None when the batch has written no metrics row yet, and
        # last.ts_end is None on a partially-written final line: elapsed has no
        # end to measure to. Unknown, never a crash on the 0.5s tick.
        end_ts = now if status.in_flight else (last.ts_end if last else None)
        elapsed_str = "—" if end_ts is None else fmt_dur(end_ts - b_start)

    active_secs = sum(r.wall_secs for r in rows)
    if status.in_flight and session_start is not None:
        active_secs += now - session_start

    cost = sum(r.cost_usd for r in rows)

    row3.append(f"{backlog} backlog · {wip} wip · {sess_count} sessions · {elapsed_str} elapsed · {fmt_dur(active_secs)} active · ${cost:.2f} cost")

    if status.in_flight and usage.session_cost > 0:
        row3.append(f" +${usage.session_cost:.2f} live")

    row4 = Text(no_wrap=True, overflow="ellipsis")
    up, cached, out = usage.totals()
    row4.append(f"session {usage.model} · tok ↑{fmt_tok(up)} ⤓{fmt_tok(cached)} ↓{fmt_tok(out)} · ctx {fmt_tok(usage.context_size())} · ")
    row4.append(status.label, style=status.style)

    lines = [row1, row2, row3, row4]
    if agents is not None:
        agents.no_wrap = True
        agents.overflow = "ellipsis"
        lines.insert(2, agents)

    return Panel(Group(*lines), title=root_name)


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
        prd = r.prd if len(r.prd) <= 44 else r.prd[:43] + "…"
        cost_t = Text(f"${r.cost:.2f}")
        if r.live_cost > 0:
            cost_t.append(f" +${r.live_cost:.2f}", style="dim")

        table.add_row(
            r.name,
            Text(r.status.label, style=r.status.style),
            r.phase,
            prd,
            r.task,
            r.cycle,
            cost_t,
            str(r.sessions),
        )

    return table
