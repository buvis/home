from __future__ import annotations

import datetime as dt
import time
from collections.abc import Sequence

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.console import Group

from . import model
from .discovery import LoopRow, Status
from .model import fmt_dur
from .stream import AgentTracker, Lane, SessionUsage

PHASES = ("build", "review", "done")


def fmt_tok(n: int) -> str:
    if n < 1000:
        return str(n)
    if n < 1000000:
        return f"{n / 1000:.1f}k"
    return f"{n / 1000000:.1f}M"


def _strip_nodes(nodes: list[tuple[str, str]]) -> Text:
    parts: list = []
    for name, phase_state in nodes:
        if parts:
            parts.append(" ─ ")
        if phase_state == "done":
            parts.append(f"✓ {name}")
        elif phase_state == "current":
            parts.append((f"● {name}", "bold cyan"))
        else:
            parts.append(("○ " + name, "dim"))
    return Text.assemble(*parts)


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
    elif current == "build":
        # Expand build into its sub-steps; the first unfinished one is live.
        steps = model.build_steps_done(state)
        sub_current = next((s for s in model.BUILD_STEPS if not steps[s]), "work")
        nodes = [
            (s, "done" if steps[s] else ("current" if s == sub_current else "pending"))
            for s in model.BUILD_STEPS
        ]
        nodes += [("review", "pending"), ("done", "pending")]
        t = _strip_nodes(nodes)
    elif current == "review" and (lenses := model.review_lenses(state)):
        # Expand review into its lens sub-steps (stamped by the review skill
        # at dispatch); lenses run in parallel, so several can be current.
        nodes = [("build", "done")]
        nodes += [(n, "current" if s == "running" else "done") for n, s in lenses]
        nodes.append(("done", "pending"))
        t = _strip_nodes(nodes)
    else:
        # Collapsed strip; phases before the current gate are positionally
        # done (phases_completed only ever records "review").
        idx = PHASES.index(current)
        nodes = []
        for i, p in enumerate(PHASES):
            if p in state.phases_completed or i < idx:
                nodes.append((p, "done"))
            elif p == current:
                nodes.append((p, "current"))
            else:
                nodes.append((p, "pending"))
        t = _strip_nodes(nodes)

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
    # Phase lives on the phase strip (row 2) only — repeating it here made
    # the two rows read as two different facts.
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
    row1.append(f"{state.prd_name} · task {task} · cycle {cycle}")

    gs = model.guards(state)
    if gs:
        g_texts = [f"{label}: {detail}" for label, detail in gs]
        row1.append(" · " + ", ".join(g_texts))

    # needs_attention renders once, as the row-4 status (classify rank 0)
    # plus the red phase strip — not as a third marker here.

    task_name = model.current_task_name(state)
    if task_name:
        row1.append(f" ▸ {task_name}", style="dim")
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

    # "batch <stamp>" scopes everything after it: sessions, elapsed, active
    # and cost all cover the current batch, surviving interrupts/resumes.
    batch_stamp = (
        f"batch {dt.datetime.fromtimestamp(b_start).strftime('%m-%d %H:%M')} · "
        if b_start is not None
        else ""
    )
    row3.append(f"{backlog} backlog · {wip} wip · {batch_stamp}{sess_count} sessions · {elapsed_str} elapsed · {fmt_dur(active_secs)} active · ${cost:.2f} cost")

    if cost > 0 and active_secs >= 600:
        row3.append(f" · ${cost / active_secs * 3600:.2f}/h")

    if status.in_flight and usage.session_cost > 0:
        row3.append(f" +${usage.session_cost:.2f} live")

    return row3


def _row_usage(usage: SessionUsage, status: Status) -> Text:
    row4 = Text(no_wrap=True, overflow="ellipsis")
    up, cached, out = usage.totals()
    tilde = "~" if usage.out_estimated else ""
    row4.append(f"session {usage.model} · in ↑{fmt_tok(up)} · cache ⤓{fmt_tok(cached)} · out ↓{tilde}{fmt_tok(out)} · ")
    ctx = usage.context_size()
    row4.append(f"ctx {fmt_tok(ctx)}/{fmt_tok(model.USAGE_CAP)}")
    pct = ctx * 100 // model.USAGE_CAP
    pct_style = "bold red" if pct >= 95 else "yellow" if pct >= 80 else "dim"
    row4.append(f" {pct}%", style=pct_style)
    row4.append(" · ")
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
) -> Panel:
    if now is None:
        now = time.time()

    row1 = _row_head(state)

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


LANE_TITLES = {
    "in_progress": ("in progress", "bold cyan"),
    "pending": ("pending", "bold"),
    "completed": ("completed", "bold green"),
}


def lane_body(lane: str, tasks: Sequence[dict]) -> Text:
    title, style = LANE_TITLES[lane]
    t = Text()
    t.append(f"{title} ({len(tasks)})\n", style=style)
    for task in tasks:
        name = str(task.get("name") or task.get("id") or "?")
        t.append(f"\n• {name}")
        meta = []
        tier = task.get("model")
        if isinstance(tier, str) and tier:
            meta.append(tier)
        attempts = task.get("attempts")
        if isinstance(attempts, list) and attempts:
            meta.append(f"×{len(attempts)}")
            last = attempts[-1] if isinstance(attempts[-1], dict) else {}
            impl = last.get("implementor")
            if isinstance(impl, str) and impl and impl != "claude":
                meta.append(impl)
        if meta:
            t.append(f"  [{' · '.join(meta)}]", style="dim")
    return t


def agents_head(state: model.LoopState, root_name: str) -> Panel:
    return Panel(
        Group(_row_head(state), phase_strip(state)), title=f"{root_name} · agents"
    )


def _lane_detail(t: Text, lane: Lane) -> None:
    head_style = "dim" if lane.done else lane.color
    t.append("\n✓ " if lane.done else "\n● ", style=head_style)
    t.append(lane.desc or lane.label, style=head_style)

    meta = ["agent" if lane.kind == "local_agent" else "bash"]
    if lane.agent_type:
        meta.append(lane.agent_type)
    if lane.kind == "local_bash":
        meta.append("done" if lane.done else (lane.status or "running"))
    t.append(f"  [{' · '.join(meta)}]", style="dim")

    if lane.activity and not lane.done:
        t.append(f"\n    ↳ {lane.activity}")
    stats = []
    if lane.last:
        stats.append(f"⚒ {lane.last}×{lane.n}")
    if lane.tokens:
        stats.append(f"{fmt_tok(lane.tokens)} tok")
    if lane.dur_ms:
        stats.append(fmt_dur(lane.dur_ms / 1000))
    if stats:
        t.append(f"\n    {' · '.join(stats)}", style="dim")


def agents_body(tracker: AgentTracker) -> Text:
    lanes = tracker.lanes()
    if not lanes:
        return Text("no subagent or background-task activity this session", style="dim")
    live = [lane for lane in lanes if not lane.done]
    done = [lane for lane in lanes if lane.done]
    t = Text()
    t.append(f"running ({len(live)})\n", style="bold cyan")
    for lane in live:
        _lane_detail(t, lane)
    if done:
        t.append(f"\n\nfinished ({len(done)})\n", style="bold")
        for lane in done:
            _lane_detail(t, lane)
    return t


def tasks_head(state: model.LoopState, root_name: str) -> Panel:
    lines = [_row_head(state), phase_strip(state)]
    rc = state.raw.get("review_cycles")
    if isinstance(rc, list) and rc and isinstance(rc[-1], dict):
        last = rc[-1]
        t = Text(no_wrap=True, overflow="ellipsis")
        t.append(
            f"review cycle {last.get('cycle', '?')}: {last.get('issues_found', '?')} issues"
            f" · {last.get('follow_up_tasks', '?')} follow-ups · {last.get('deferred', '?')} deferred"
        )
        lines.append(t)
    return Panel(Group(*lines), title=f"{root_name} · tasks")


def fleet_cells(row: LoopRow) -> tuple:
    prd = row.prd if len(row.prd) <= 44 else row.prd[:43] + "…"
    cost_t = Text(f"${row.cost:.2f}")
    if row.live_cost > 0:
        cost_t.append(f" +${row.live_cost:.2f}", style="dim")

    return (
        row.name,
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
