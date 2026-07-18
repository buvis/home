"""Tests for tracon/panels.py — rich rendering layer (no file I/O, no re-classification)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console
from rich.text import Text

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from tracon import model, panels
from tracon.discovery import LoopRow, Status
from tracon.stream import AgentTracker


# --- fixture builders (mirrors test_discovery.py conventions) ---------------


def _state(**overrides: Any) -> model.LoopState:
    base: dict[str, Any] = dict(
        prd="00061-x.md",
        phase="build",
        next_phase="",
        phases_completed=(),
        cycle=1,
        rework_cap=3,
        tasks_total=6,
        tasks_completed=2,
        batch_id="B1",
        needs_attention=False,
        exists=True,
        raw={},
    )
    base.update(overrides)
    return model.LoopState(**base)


def _mrow(**overrides: Any) -> model.MetricsRow:
    base: dict[str, Any] = dict(
        ts_start=1000.0,
        ts_end=1100.0,
        wall_secs=100.0,
        prd="00061-x.md",
        batch="B1",
        phase_launched="build",
        phase_end="build",
        signal="continue",
        model="opus",
        cost_usd=2.5,
        tokens_out=100,
    )
    base.update(overrides)
    return model.MetricsRow(**base)


def _loop_row(**overrides: Any) -> LoopRow:
    base: dict[str, Any] = dict(
        root=Path("/tmp/repo"),
        name="repo",
        status=Status(label="○ idle", style="dim", rank=3, in_flight=False),
        phase="build",
        prd="00061-x.md",
        task="2/6",
        cycle="1/3",
        cost=10.0,
        live_cost=0.0,
        sessions=1,
    )
    base.update(overrides)
    return LoopRow(**base)


class _Usage:
    """Tiny stub exposing the SessionUsage attributes build_head reads."""

    def __init__(
        self,
        model: str = "opus",
        session_cost: float = 0.0,
        totals: tuple[int, int, int] = (0, 0, 0),
        context: int = 0,
    ) -> None:
        self.model = model
        self.session_cost = session_cost
        self._totals = totals
        self._context = context

    def totals(self) -> tuple[int, int, int]:
        return self._totals

    def context_size(self) -> int:
        return self._context


def _head(**overrides: Any):
    kwargs: dict[str, Any] = dict(
        state=_state(),
        rows=[_mrow()],
        usage=_Usage(),
        status=Status(label="◐ quiet 5m00s", style="yellow", rank=2, in_flight=True),
        prd_counts=(42, 17),
        batch_id="B1",
        root_name="myrepo",
        session_start=None,
        agents=None,
        now=2000.0,
    )
    kwargs.update(overrides)
    return panels.build_head(**kwargs)


def _render(renderable: Any) -> str:
    console = Console(width=200, record=True)
    console.print(renderable)
    return console.export_text()


def _iter_texts(renderable: Any):
    """Walk Panel/Group/Text trees, yielding every Text leaf found."""
    if isinstance(renderable, Text):
        yield renderable
        return
    children = getattr(renderable, "renderables", None)
    if children is not None:
        for child in children:
            yield from _iter_texts(child)
        return
    child = getattr(renderable, "renderable", None)
    if child is not None:
        yield from _iter_texts(child)


def _styles_containing(text: Text, needle: str) -> list:
    return [span for span in text.spans if needle in str(span.style)]


# --- fmt_dur boundaries -------------------------------------------------------


def test_fmt_dur_seconds_only_under_one_minute() -> None:
    assert panels.fmt_dur(9) == "9s"
    assert panels.fmt_dur(59) == "59s"


def test_fmt_dur_minutes_and_seconds_under_one_hour() -> None:
    assert panels.fmt_dur(60) == "1m00s"
    assert panels.fmt_dur(725) == "12m05s"
    assert panels.fmt_dur(3599) == "59m59s"


def test_fmt_dur_hours_and_minutes_at_or_above_one_hour() -> None:
    assert panels.fmt_dur(3600) == "1h00m"
    assert panels.fmt_dur(14520) == "4h02m"


def test_fmt_dur_clamps_negative_to_zero() -> None:
    assert panels.fmt_dur(-5) == "0s"


# --- fmt_tok boundaries --------------------------------------------------------


def test_fmt_tok_raw_integer_under_one_thousand() -> None:
    assert panels.fmt_tok(812) == "812"
    assert panels.fmt_tok(999) == "999"


def test_fmt_tok_thousands_tier() -> None:
    assert panels.fmt_tok(1000) == "1.0k"
    assert panels.fmt_tok(45300) == "45.3k"


def test_fmt_tok_millions_tier() -> None:
    assert panels.fmt_tok(1000000) == "1.0M"
    assert panels.fmt_tok(1200000) == "1.2M"


# --- build_head: headline in-flight gating, pinned from both sides -----------


def test_elapsed_advances_when_quiet_but_in_flight() -> None:
    status = Status(label="◐ quiet 5m00s", style="yellow", rank=2, in_flight=True)
    rendered = _render(
        _head(
            rows=[_mrow(ts_start=1000.0, ts_end=1100.0, wall_secs=100.0)],
            status=status,
            now=2000.0,
            session_start=None,
        )
    )
    # elapsed = now(2000) - batch_start(1000) = 1000s -> "16m40s", NOT
    # last.ts_end(1100) - batch_start(1000) = 100s -> "1m40s".
    assert panels.fmt_dur(1000) in rendered
    assert "16m40s" in rendered


def test_active_slice_included_when_quiet_but_in_flight() -> None:
    status = Status(label="◐ quiet 5m00s", style="yellow", rank=2, in_flight=True)
    rendered = _render(
        _head(
            rows=[_mrow(ts_start=1000.0, ts_end=1100.0, wall_secs=100.0)],
            status=status,
            now=2000.0,
            session_start=1500.0,
        )
    )
    # active = wall_secs(100) + (now(2000) - session_start(1500)) = 600s -> "10m00s".
    assert "10m00s" in rendered


def test_cost_chip_shown_when_quiet_but_in_flight() -> None:
    status = Status(label="◐ quiet 5m00s", style="yellow", rank=2, in_flight=True)
    rendered = _render(
        _head(
            rows=[_mrow(cost_usd=2.5)],
            status=status,
            usage=_Usage(session_cost=5.5),
            now=2000.0,
        )
    )
    assert "+$5.50 live" in rendered


def test_elapsed_pinned_to_last_ts_end_when_terminal() -> None:
    status = Status(label="✔ drained 10:00", style="dim", rank=4, in_flight=False)
    rendered = _render(
        _head(
            rows=[_mrow(ts_start=1000.0, ts_end=1100.0, wall_secs=100.0)],
            status=status,
            now=9999.0,
            session_start=1500.0,
        )
    )
    # elapsed = last.ts_end(1100) - batch_start(1000) = 100s -> "1m40s", never
    # jumping to `now`.
    assert "1m40s" in rendered


def test_active_slice_excluded_when_terminal() -> None:
    status = Status(label="✔ drained 10:00", style="dim", rank=4, in_flight=False)
    rendered = _render(
        _head(
            rows=[_mrow(ts_start=1000.0, ts_end=1100.0, wall_secs=100.0)],
            status=status,
            now=9999.0,
            session_start=1500.0,
        )
    )
    # active = wall_secs(100) only, no (now - session_start) slice added.
    assert "1m40s" in rendered
    assert "2h" not in rendered  # a bug that added (now - session_start) here
    # would produce a much larger, distinct duration than 100s.


def test_cost_chip_absent_when_terminal() -> None:
    status = Status(label="✔ drained 10:00", style="dim", rank=4, in_flight=False)
    rendered = _render(
        _head(
            rows=[_mrow(cost_usd=2.5)],
            status=status,
            usage=_Usage(session_cost=5.5),
            now=2000.0,
        )
    )
    assert "+$" not in rendered


def test_cost_chip_omitted_when_session_cost_zero_while_in_flight() -> None:
    status = Status(label="● live", style="green", rank=2, in_flight=True)
    rendered = _render(
        _head(
            rows=[_mrow(cost_usd=2.5)],
            status=status,
            usage=_Usage(session_cost=0.0),
            now=2000.0,
        )
    )
    assert "+$" not in rendered


def test_active_runtime_excludes_live_slice_when_session_start_is_none() -> None:
    status = Status(label="● live", style="green", rank=2, in_flight=True)
    rendered = _render(
        _head(
            rows=[_mrow(ts_start=1000.0, ts_end=1100.0, wall_secs=100.0)],
            status=status,
            now=5000.0,
            session_start=None,
        )
    )
    # active = wall_secs(100) only -> "1m40s". elapsed = now(5000) -
    # batch_start(1000) = 4000s -> "1h06m", a distinct value, so finding
    # "1m40s" pins the active field specifically.
    assert "1m40s" in rendered


def test_elapsed_renders_em_dash_when_unknown() -> None:
    status = Status(label="○ no log", style="dim", rank=3, in_flight=False)
    rendered = _render(
        _head(
            rows=[],
            status=status,
            batch_id="not-a-timestamp",
            now=2000.0,
        )
    )
    assert "—" in rendered


def test_elapsed_survives_known_batch_start_with_no_metrics_rows() -> None:
    """A batch whose id parses as a timestamp but which has written no metrics
    row yet, while NOT in flight (no log): batch_start is known, but `last` is
    None, so there is no end timestamp to measure to. Elapsed is unknown, not a
    crash -- the header renders on a 0.5s tick and must never raise."""
    status = Status(label="○ no log", style="dim", rank=3, in_flight=False)
    rendered = _render(
        _head(
            rows=[],
            status=status,
            batch_id="202607120753",  # parses via the "%Y%m%d%H%M" fallback
            now=2000.0,
        )
    )
    assert "—" in rendered


def test_elapsed_survives_last_row_missing_ts_end() -> None:
    """A partially-written final metrics line carries no ts_end. Not in flight,
    so elapsed would measure to that missing timestamp: unknown, not a crash."""
    status = Status(label="○ idle", style="dim", rank=3, in_flight=False)
    rendered = _render(
        _head(
            rows=[_mrow(ts_start=1000.0, ts_end=None)],
            status=status,
            batch_id="B1",
            now=2000.0,
        )
    )
    assert "—" in rendered


def test_row1_renders_em_dash_for_unknown_task_and_cycle_counts() -> None:
    """A stateless or partial loop has None task/cycle counts. The header must
    not print the literal string "None/None" at the operator."""
    rendered = _render(
        _head(
            state=_state(
                tasks_total=None, tasks_completed=None, cycle=None, rework_cap=None
            )
        )
    )
    assert "None" not in rendered


def test_row1_renders_labeled_em_dash_placeholders_on_empty_state() -> None:
    """With an empty/absent LoopState (a missing or malformed state.json),
    row 1 must render labeled "—" placeholders rather than empty fields or
    dangling separators, and phase_strip's own trailing `" · " + current`
    suffix (row 2) must not dangle with nothing after it. Phase itself is
    row 2's job — row 1 must not repeat it."""
    state = _state(
        prd="",
        phase="",
        next_phase="",
        phases_completed=(),
        cycle=None,
        rework_cap=None,
        tasks_total=None,
        tasks_completed=None,
        needs_attention=False,
        raw={},
    )
    panel = _head(state=state)
    texts = list(_iter_texts(panel))

    row1 = texts[0]
    assert row1.plain == "— · task — · cycle —"

    row2 = texts[1]
    assert row2.plain.endswith(" · —")


# --- build_head: backlog/wip come from the injected tuple, never disk --------


def test_backlog_and_wip_render_from_injected_prd_counts() -> None:
    rendered = _render(_head(prd_counts=(42, 17)))
    assert "42" in rendered
    assert "17" in rendered


# --- build_head: row 3 batch stamp and burn rate ------------------------------


def test_row3_names_the_batch_scope_with_its_start_stamp() -> None:
    """sessions/elapsed/active/cost are batch totals that survive interrupts;
    the `batch <stamp>` prefix is what tells the operator when they reset."""
    import datetime as _dt

    stamp = _dt.datetime.fromtimestamp(1000.0).strftime("%m-%d %H:%M")
    rendered = _render(_head(rows=[_mrow(ts_start=1000.0)]))
    assert f"batch {stamp}" in rendered


def test_row3_omits_batch_stamp_when_start_unknown() -> None:
    rendered = _render(_head(rows=[], batch_id="not-a-timestamp"))
    assert "batch " not in rendered


def test_row3_shows_hourly_burn_rate_once_active_time_is_meaningful() -> None:
    rendered = _render(_head(rows=[_mrow(wall_secs=3600.0, cost_usd=36.0)]))
    assert "$36.00/h" in rendered


def test_row3_omits_burn_rate_under_ten_active_minutes() -> None:
    rendered = _render(_head(rows=[_mrow(wall_secs=100.0, cost_usd=2.5)]))
    assert "/h" not in rendered


# --- build_head: row 4 labeled token counters and ctx gauge -------------------


def test_row4_labels_each_token_counter_and_shows_ctx_percent() -> None:
    """`tok ↑x ⤓y ↓z` read as three unnamed arrows (⤓ and ↓ are near-identical
    glyphs); each counter now carries a word, and ctx shows the cap + percent."""
    usage = _Usage(totals=(1_300_000, 44_100_000, 2_500), context=491_700)
    rendered = _render(_head(usage=usage))
    assert "in ↑1.3M" in rendered
    assert "cache ⤓44.1M" in rendered
    assert "out ↓2.5k" in rendered
    assert "ctx 491.7k/500.0k" in rendered
    assert "98%" in rendered


def test_row4_ctx_percent_turns_red_near_the_rotation_cap() -> None:
    panel = _head(usage=_Usage(context=491_700))
    row4 = list(_iter_texts(panel))[3]
    assert _styles_containing(row4, "bold red")


def test_row4_ctx_percent_stays_dim_when_far_from_the_cap() -> None:
    idle = Status(label="○ idle", style="dim", rank=3, in_flight=False)
    panel = _head(usage=_Usage(context=100_000), status=idle)
    row4 = list(_iter_texts(panel))[3]
    assert not _styles_containing(row4, "red")
    assert not _styles_containing(row4, "yellow")


# --- build_head: row 1 fields --------------------------------------------------


def test_needs_attention_marker_shown_when_true() -> None:
    rendered = _render(_head(state=_state(needs_attention=True)))
    assert "⚠ needs attention" in rendered


def test_needs_attention_marker_absent_when_false() -> None:
    rendered = _render(_head(state=_state(needs_attention=False)))
    assert "⚠ needs attention" not in rendered


def test_guard_detail_shown_when_guards_present() -> None:
    rendered = _render(_head(state=_state(raw={"thrash_halt": True})))
    assert "thrash" in rendered


def test_no_guard_text_when_guards_absent() -> None:
    rendered = _render(_head(state=_state(raw={})))
    assert "thrash" not in rendered


def test_row1_shows_task_progress_and_labeled_cycle_fraction() -> None:
    rendered = _render(
        _head(state=_state(tasks_completed=2, tasks_total=6, cycle=1, rework_cap=3))
    )
    assert "task 2/6" in rendered
    assert "cycle 1/3" in rendered


def test_row1_does_not_repeat_the_phase_shown_on_the_phase_strip() -> None:
    """Phase is rendered exactly once, on row 2's phase strip. The old row-1
    `build · <prd>` prefix read as a separate fact from the strip below it."""
    panel = _head(state=_state(phase="review"))
    texts = list(_iter_texts(panel))
    assert "review" not in texts[0].plain
    assert "review" in texts[1].plain


def test_row1_appends_current_task_name_from_state_tasks() -> None:
    raw = {
        "tasks": [
            {"id": "t-1", "name": "Add validation endpoint", "status": "completed"},
            {"id": "t-2", "name": "Write integration tests", "status": "in_progress"},
            {"id": "t-3", "name": "Update docs", "status": "pending"},
        ]
    }
    rendered = _render(_head(state=_state(raw=raw)))
    assert "▸ Write integration tests" in rendered


def test_row1_omits_task_name_marker_when_state_has_no_tasks() -> None:
    rendered = _render(_head(state=_state(raw={})))
    assert "▸" not in rendered


def test_status_label_rendered_verbatim_without_recomputation() -> None:
    status = Status(label="☯ totally-custom-label", style="magenta", rank=9, in_flight=False)
    rendered = _render(_head(status=status))
    assert "☯ totally-custom-label" in rendered


# --- build_head: rows are no_wrap with ellipsis overflow ----------------------


def test_header_rows_are_no_wrap_with_ellipsis_overflow() -> None:
    panel = _head()
    texts = list(_iter_texts(panel))
    assert texts, "expected at least one Text renderable inside the header panel"
    for text in texts:
        assert text.no_wrap is True
        assert text.overflow == "ellipsis"


# --- head_rows: content-row count ---------------------------------------------


def test_head_rows_without_agents_is_four() -> None:
    assert panels.head_rows(None) == 4


def test_head_rows_with_agents_is_five() -> None:
    assert panels.head_rows(Text("agents foo")) == 5


# --- PHASES constant ------------------------------------------------------------


def test_phases_constant_matches_spec() -> None:
    assert panels.PHASES == ("build", "review", "done")


# --- phase_strip ----------------------------------------------------------------


def test_phase_strip_marks_completed_current_and_pending_gates() -> None:
    state = _state(phase="review", next_phase="", phases_completed=("build",))
    text = panels.phase_strip(state)
    plain = text.plain

    assert "✓" in plain
    assert "●" in plain
    assert "○" in plain
    assert plain.index("build") < plain.index("review") < plain.index("done")
    assert _styles_containing(text, "cyan")


def test_phase_strip_precedence_uses_phase_over_next_phase() -> None:
    # phase="" is falsy -> current phase must resolve via `phase or next_phase`
    # to next_phase="done". A buggy implementation using phase="" directly
    # would fall into the unknown-phase branch and never mark a current gate.
    state = _state(phase="", next_phase="done", phases_completed=())
    text = panels.phase_strip(state)
    assert _styles_containing(text, "cyan")


def test_phase_strip_unknown_phase_paused_renders_bold_yellow_with_raw_suffix() -> None:
    state = _state(phase="paused", next_phase="", phases_completed=())
    text = panels.phase_strip(state)
    assert " · paused" in text.plain
    assert not _styles_containing(text, "cyan")
    assert _styles_containing(text, "yellow")


def test_phase_strip_unknown_phase_legacy_stopped_does_not_crash_or_mark_current() -> None:
    state = _state(phase="stopped", next_phase="", phases_completed=())
    text = panels.phase_strip(state)
    assert " · stopped" in text.plain
    assert not _styles_containing(text, "cyan")
    assert not _styles_containing(text, "yellow")


def test_phase_strip_attention_forces_bold_red_style() -> None:
    state = _state(phase="build", next_phase="", phases_completed=(), needs_attention=True)
    text = panels.phase_strip(state)
    assert _styles_containing(text, "red")


# --- agents_row -------------------------------------------------------------


def test_agents_row_returns_none_when_nothing_live() -> None:
    tracker = AgentTracker()
    assert panels.agents_row(tracker) is None


def test_agents_row_lists_background_bash_task_alongside_agent_lane() -> None:
    tracker = AgentTracker()
    tracker.feed(
        {
            "type": "system",
            "subtype": "task_started",
            "task_id": "t1",
            "tool_use_id": "tu1",
            "description": "build task",
            "task_type": "local_agent",
        }
    )
    tracker.feed(
        {
            "type": "system",
            "subtype": "task_progress",
            "task_id": "t1",
            "last_tool_name": "Read",
            "usage": {"tool_uses": 12},
        }
    )
    tracker.feed(
        {
            "type": "system",
            "subtype": "background_tasks_changed",
            "tasks": [
                {"task_id": "bg1", "task_type": "local_bash", "description": "design review"}
            ],
        }
    )

    text = panels.agents_row(tracker)
    assert text is not None
    plain = text.plain

    assert "agents" in plain
    assert "build task" in plain
    assert "⚒Read×12" in plain
    assert "design review" in plain


def test_agents_row_renders_background_task_as_summary_and_status_glyph_not_agent_shape() -> None:
    """Agent lanes (kind="local_agent") and background-task lanes
    (kind="local_bash") are different kinds of live work and must render
    differently, or a running background reviewer is indistinguishable from a
    subagent lane. Agents keep the existing `⟨label⟩ ⚒tool×n` shape;
    background tasks render as `summary ▷status` -- no angle brackets, the
    task's summary followed by the ▷ glyph and its status. Background-task
    lanes are registered by AgentTracker._apply_background_tasks from
    background_tasks_changed events, whose entries carry a status; Lane must
    expose that status for agents_row to read (natural field name: `status`)."""
    tracker = AgentTracker()
    tracker.feed(
        {
            "type": "system",
            "subtype": "task_started",
            "task_id": "t1",
            "tool_use_id": "tu1",
            "description": "build task",
            "task_type": "local_agent",
        }
    )
    tracker.feed(
        {
            "type": "system",
            "subtype": "task_progress",
            "task_id": "t1",
            "last_tool_name": "Read",
            "usage": {"tool_uses": 12},
        }
    )
    tracker.feed(
        {
            "type": "system",
            "subtype": "background_tasks_changed",
            "tasks": [
                {
                    "task_id": "bg1",
                    "task_type": "local_bash",
                    "description": "design review",
                    "status": "running",
                }
            ],
        }
    )

    text = panels.agents_row(tracker)
    assert text is not None
    plain = text.plain

    assert "⟨build task⟩ ⚒Read×12" in plain
    assert "design review ▷running" in plain
    assert "⟨design review⟩" not in plain


def test_agents_row_background_task_missing_status_renders_running_not_dangling_marker() -> None:
    """A background_tasks_changed entry with no "status" key must still fail
    open to "running" and render `label ▷running` -- never a dangling `▷`
    with nothing after it. Membership in the running set already means the
    task is live, so a missing status is not the same as an unknown one."""
    tracker = AgentTracker()
    tracker.feed(
        {
            "type": "system",
            "subtype": "background_tasks_changed",
            "tasks": [
                {
                    "task_id": "bg1",
                    "task_type": "local_bash",
                    "description": "design review",
                    # no "status" key
                }
            ],
        }
    )

    text = panels.agents_row(tracker)
    assert text is not None
    plain = text.plain

    assert "design review ▷running" in plain
    assert "▷ " not in plain  # no dangling marker followed by the " · " separator
    assert not plain.rstrip().endswith("▷")  # no dangling marker at the end of the row


# --- fleet_table --------------------------------------------------------------


def test_fleet_table_shows_live_cost_chip_only_when_positive() -> None:
    rows = [
        _loop_row(name="alpha", cost=10.0, live_cost=2.5),
        _loop_row(name="beta", cost=5.0, live_cost=0.0),
    ]
    text = _render(panels.fleet_table(rows))
    assert "+$2.50" in text
    assert "+$0.00" not in text


def test_fleet_table_sorts_by_status_rank_then_name() -> None:
    rows = [
        _loop_row(name="zeta", status=Status(label="x", style="", rank=2, in_flight=False)),
        _loop_row(name="alpha", status=Status(label="x", style="", rank=1, in_flight=False)),
        _loop_row(name="beta", status=Status(label="x", style="", rank=1, in_flight=False)),
    ]
    text = _render(panels.fleet_table(rows))
    assert text.index("alpha") < text.index("beta") < text.index("zeta")


def test_fleet_table_truncates_prd_to_44_chars() -> None:
    long_prd = "P" * 60
    rows = [_loop_row(prd=long_prd)]
    text = _render(panels.fleet_table(rows))
    assert long_prd not in text
    assert long_prd[:20] in text


def test_fleet_table_headers_include_all_named_columns() -> None:
    rows = [_loop_row()]
    text = _render(panels.fleet_table(rows)).lower()
    for column in ("project", "status", "phase", "prd", "task", "cycle", "cost", "sessions"):
        assert column in text


# --- fleet_cells: the shared row-builder behind both fleet views -------------


def test_fleet_cells_returns_the_eight_columns_in_order() -> None:
    row = _loop_row(
        name="myrepo",
        status=Status(label="● live", style="green", rank=2, in_flight=True),
        phase="build",
        prd="00061-x.md",
        task="2/6",
        cycle="1/3",
        cost=10.0,
        live_cost=0.0,
        sessions=3,
    )

    cells = panels.fleet_cells(row)

    assert len(cells) == 8
    project, status, phase, prd, task, cycle, cost, sessions = cells
    assert project == "myrepo"
    assert isinstance(status, Text) and status.plain == "● live"
    assert phase == "build"
    assert prd == "00061-x.md"
    assert task == "2/6"
    assert cycle == "1/3"
    assert isinstance(cost, Text) and cost.plain == "$10.00"
    assert sessions == "3"


def test_fleet_cells_project_is_a_plain_string_not_rich_text() -> None:
    cells = panels.fleet_cells(_loop_row(name="myproj"))
    assert cells[0] == "myproj"
    assert isinstance(cells[0], str) and not isinstance(cells[0], Text)


def test_fleet_cells_status_text_carries_the_rows_style() -> None:
    row = _loop_row(status=Status(label="⚠ attention", style="bold red", rank=0, in_flight=False))
    status_cell = panels.fleet_cells(row)[1]
    assert isinstance(status_cell, Text)
    assert status_cell.plain == "⚠ attention"
    assert status_cell.style == "bold red"


def test_fleet_cells_prd_untouched_at_exactly_44_chars() -> None:
    prd = "P" * 44
    cells = panels.fleet_cells(_loop_row(prd=prd))
    assert cells[3] == prd


def test_fleet_cells_prd_truncates_to_43_chars_plus_ellipsis_at_45_chars() -> None:
    prd = "P" * 45
    cells = panels.fleet_cells(_loop_row(prd=prd))
    assert cells[3] == "P" * 43 + "…"
    assert len(cells[3]) == 44


def test_fleet_cells_cost_chip_present_when_live_cost_positive() -> None:
    cost_cell = panels.fleet_cells(_loop_row(cost=10.0, live_cost=2.5))[6]
    assert isinstance(cost_cell, Text)
    assert cost_cell.plain == "$10.00 +$2.50"
    assert _styles_containing(cost_cell, "dim")


def test_fleet_cells_cost_chip_absent_when_live_cost_zero() -> None:
    cost_cell = panels.fleet_cells(_loop_row(cost=5.0, live_cost=0.0))[6]
    assert cost_cell.plain == "$5.00"


def test_fleet_cells_sessions_is_the_stringified_count() -> None:
    cells = panels.fleet_cells(_loop_row(sessions=7))
    assert cells[7] == "7"
    assert isinstance(cells[7], str)


# --- fleet_table: must delegate to fleet_cells, never rebuild cells itself ---


def test_fleet_table_delegates_row_construction_to_fleet_cells(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fleet_table and the Textual dashboard build the SAME cells today by
    duplicating the (rank, name) sort, the 44-char prd truncation, and the
    cost chip logic in two places. They must share one builder -- fleet_cells
    -- so the views cannot silently drift apart."""
    rows = [_loop_row(name="alpha"), _loop_row(name="beta")]
    calls: list[LoopRow] = []
    original = panels.fleet_cells

    def spy(row: LoopRow) -> tuple:
        calls.append(row)
        return original(row)

    monkeypatch.setattr(panels, "fleet_cells", spy)

    panels.fleet_table(rows)

    assert len(calls) == 2
    assert {r.name for r in calls} == {"alpha", "beta"}


# --- fleet_cells: wrapper-alive badge on the project cell -------------------


def test_fleet_cells_project_cell_carries_wrapper_marker_when_wrapper_alive() -> None:
    row = _loop_row(name="myrepo", wrapper=True)
    cells = panels.fleet_cells(row)
    assert cells[0] == "⟳ myrepo"
    assert isinstance(cells[0], str) and not isinstance(cells[0], Text)


def test_fleet_cells_project_cell_plain_when_wrapper_not_alive() -> None:
    row = _loop_row(name="myrepo", wrapper=False)
    cells = panels.fleet_cells(row)
    assert cells[0] == "myrepo"


# --- build_head: wrapper-alive chip ------------------------------------------


def test_build_head_shows_wrapper_chip_when_wrapper_alive() -> None:
    rendered = _render(_head(wrapper=True))
    assert "⟳ wrapper" in rendered


def test_build_head_omits_wrapper_chip_when_wrapper_not_alive() -> None:
    rendered = _render(_head(wrapper=False))
    assert "⟳ wrapper" not in rendered
