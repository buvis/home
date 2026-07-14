"""Tests for tracon/screens.py — lazy-import guard, Collector, Textual pilot.

The lazy-import guard and `Collector` run under bare `python3 -m pytest` (no
textual). The Textual pilot test self-skips via `pytest.importorskip`.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from rich.text import Text

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _write_lines(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n")
    return path


def _metrics_line(**overrides: Any) -> str:
    row = {
        "ts_start": 1000.0,
        "ts_end": 1100.0,
        "wall_secs": 100,
        "prd": "00061-x.md",
        "batch": "B1",
        "phase_launched": "build",
        "phase_end": "build",
        "signal": "continue",
        "model": "opus",
        "cost_usd": 1.5,
        "tokens_out": 100,
    }
    row.update(overrides)
    return json.dumps(row)


def _init_event() -> str:
    return json.dumps({"type": "system", "subtype": "init", "model": "claude-opus-4-8"})


def _make_loop(root: Path, *, batch_id: str = "B1", log_lines: list[str] | None = None) -> Path:
    """A fake loop root: state.json + loop-metrics.jsonl + last-session.log.

    `log_lines=[]` gives an existing but EMPTY log — an idle loop that has not
    started writing yet.
    """
    autopilot_dir = root / "dev" / "local" / "autopilot"
    autopilot_dir.mkdir(parents=True)
    state = {
        "prd": "00061-x.md",
        "phase": "build",
        "next_phase": "review",
        "tasks_total": 6,
        "tasks_completed": 2,
        "batch": {"id": batch_id},
        "needs_attention": False,
    }
    (autopilot_dir / "state.json").write_text(json.dumps(state))
    _write_lines(autopilot_dir / "loop-metrics.jsonl", [_metrics_line(batch=batch_id)])
    if log_lines is None:
        log_lines = [_init_event()]
    (autopilot_dir / "last-session.log").write_text(
        "".join(line + "\n" for line in log_lines)
    )
    return root


# --- the lazy-import guard: the headline contract of this module ------------


def test_importing_screens_does_not_import_textual() -> None:
    """textual is imported ONLY inside build_app(); a bare import of the
    module must leave textual out of sys.modules (--once needs no textual)."""
    sys.modules.pop("textual", None)
    sys.modules.pop("tracon.screens", None)
    importlib.import_module("tracon.screens")
    assert "textual" not in sys.modules


def test_module_constants_match_the_spec() -> None:
    from tracon import screens

    assert screens.LOG_KEEP == 5000
    assert screens.DETAIL_TICK == 0.5
    assert screens.FLEET_TICK == 2.0


# --- Collector: the only per-tick I/O, runs under bare python3 --------------


def test_collector_snapshot_reflects_state_metrics_and_prd_counts_on_disk(
    tmp_path: Path,
) -> None:
    from tracon import screens
    from tracon.discovery import Status

    root = _make_loop(tmp_path)
    collector = screens.Collector(root)

    state, rows, status, counts = collector.snapshot()

    assert state.prd_name == "00061-x"
    assert (state.tasks_completed, state.tasks_total) == (2, 6)
    assert len(rows) == 1 and rows[0].batch == "B1"
    assert isinstance(status, Status)
    assert counts == (0, 0)  # no backlog/wip dirs written


def test_collector_feed_parses_json_once_and_returns_event_and_texts(
    tmp_path: Path,
) -> None:
    from tracon import screens

    collector = screens.Collector(_make_loop(tmp_path))
    raw = _init_event()

    event, texts = collector.feed(raw)

    assert event == json.loads(raw)
    assert texts and all(isinstance(t, Text) for t in texts)


def test_collector_feed_fails_open_on_non_json_line(tmp_path: Path) -> None:
    from tracon import screens

    collector = screens.Collector(_make_loop(tmp_path))

    event, texts = collector.feed("not json at all")

    assert event is None
    assert [t.plain for t in texts] == ["not json at all"]


def test_collector_poll_returns_lines_appended_since_the_last_call(
    tmp_path: Path,
) -> None:
    from tracon import screens

    root = _make_loop(tmp_path)
    log_path = root / "dev" / "local" / "autopilot" / "last-session.log"
    collector = screens.Collector(root)

    first_lines, _ = collector.poll()
    assert first_lines == [_init_event()]

    second_event = _metrics_line(ts_end=1200.0)
    with log_path.open("a") as f:
        f.write(second_event + "\n")

    second_lines, _ = collector.poll()
    assert second_lines == [second_event]


# --- run_once: the rich-only smoke path (no textual) -------------------------


def test_run_once_header_shows_the_session_model_from_the_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """run_once must feed the polled lines into SessionUsage/AgentTracker BEFORE
    building the head panel. Building the head first renders an empty session
    model and zero tokens while the very log it just read carries both."""
    from tracon import screens

    root = _make_loop(tmp_path)
    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [root])

    assert screens.run_once(root) == 0

    out = capsys.readouterr().out
    assert "session claude-opus-4-8" in out
    assert "session  · tok" not in out


# --- run_once picks the loop root CONTAINING the cwd --------------------------


def _panel_title_present(out: str, name: str) -> bool:
    """True if `name` appears as a box-bordered rich Panel TITLE in `out`
    (Panel renders titles as `───── name ─────`). fleet_table renders with
    box=None, so a name that appears ONLY in the fleet table (never chosen as
    the detail target) will not match this."""
    return re.search(r"[─]+\s+" + re.escape(name) + r"\s+[─]+", out) is not None


def test_run_once_selects_the_loop_root_when_cwd_is_inside_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """cwd = a subdirectory INSIDE a loop repo -- that repo's root is the
    detail target, not a fallback to ~/.claude."""
    from tracon import screens

    root = _make_loop(tmp_path / "inner-repo")
    sibling = _make_loop(tmp_path / "sibling-repo")
    # isolate from the real machine: the current bug DOES take the fallback
    # branch here, and it must not read this machine's real ~/.claude.
    _make_loop(tmp_path / "fakehome" / ".claude")

    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [root, sibling])
    monkeypatch.setattr(screens.Path, "cwd", lambda: root / "src")
    monkeypatch.setattr(screens.Path, "home", lambda: tmp_path / "fakehome")

    assert screens.run_once() == 0

    out = capsys.readouterr().out
    assert _panel_title_present(out, "inner-repo")
    assert not _panel_title_present(out, "sibling-repo")


def test_run_once_selects_the_loop_root_when_cwd_is_the_root_itself(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """cwd = a loop root exactly -- that root is selected."""
    from tracon import screens

    root = _make_loop(tmp_path / "exact-repo")
    sibling = _make_loop(tmp_path / "other-repo")
    # isolate from the real machine even though this sub-case is not expected
    # to hit the fallback branch (a future regression could route it there).
    _make_loop(tmp_path / "fakehome" / ".claude")

    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [root, sibling])
    monkeypatch.setattr(screens.Path, "cwd", lambda: root)
    monkeypatch.setattr(screens.Path, "home", lambda: tmp_path / "fakehome")

    assert screens.run_once() == 0

    out = capsys.readouterr().out
    assert _panel_title_present(out, "exact-repo")
    assert not _panel_title_present(out, "other-repo")


def test_run_once_falls_back_to_home_claude_when_no_root_contains_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """cwd = a directory ABOVE several loop roots (their shared parent) -- no
    discovered root CONTAINS cwd, so selection falls back to ~/.claude. The
    inverted predicate (`cwd in r.parents`) matches every loop root BELOW cwd
    instead and picks the first one -- this pins the fix."""
    from tracon import screens

    fleet_dir = tmp_path / "fleet"
    loop_x = _make_loop(fleet_dir / "loop-x")
    loop_y = _make_loop(fleet_dir / "loop-y")

    fake_home = tmp_path / "fakehome"
    fallback_root = _make_loop(fake_home / ".claude")

    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [loop_x, loop_y])
    monkeypatch.setattr(screens.Path, "cwd", lambda: fleet_dir)
    monkeypatch.setattr(screens.Path, "home", lambda: fake_home)

    assert screens.run_once() == 0

    out = capsys.readouterr().out
    assert _panel_title_present(out, fallback_root.name)
    assert not _panel_title_present(out, "loop-x")
    assert not _panel_title_present(out, "loop-y")


# --- Textual pilot smoke test: needs textual, skips cleanly without it ------


def test_dashboard_pilot_lists_loops_then_enter_and_f_drive_detail_screen(
    tmp_path: Path,
) -> None:
    pytest.importorskip("textual")
    from textual.widgets import DataTable, RichLog

    from tracon import screens

    root_a = _make_loop(tmp_path / "loop-a")
    root_b = _make_loop(tmp_path / "loop-b")

    async def _drive() -> None:
        app = screens.build_app([root_a, root_b])
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.screen.query_one(DataTable)
            assert table.row_count == 2

            await pilot.press("enter")
            await pilot.pause()
            log = app.screen.query_one(RichLog)
            assert log.max_lines == screens.LOG_KEEP

            before = log.auto_scroll
            await pilot.press("f")
            await pilot.pause()
            assert log.auto_scroll is not before

    asyncio.run(_drive())


def test_lines_written_after_attach_are_not_banner_ed_as_replay(
    tmp_path: Path,
) -> None:
    """Attaching to an idle loop and watching it start is the common workflow.
    Its first lines are LIVE, not pre-attach history: they must not arrive under
    the replay banner. Only content already in the log at the first poll may."""
    pytest.importorskip("textual")
    from textual.widgets import RichLog

    from tracon import screens

    root = _make_loop(tmp_path / "idle-loop", log_lines=[])  # log exists, empty
    log_path = root / "dev" / "local" / "autopilot" / "last-session.log"

    async def _drive() -> None:
        app = screens.build_app([root])  # single root -> auto-pushes DetailScreen
        async with app.run_test() as pilot:
            await pilot.pause()
            await asyncio.sleep(screens.DETAIL_TICK * 2)  # first poll: no lines
            await pilot.pause()

            with log_path.open("a") as f:  # the loop starts writing: LIVE
                f.write(_init_event() + "\n")

            await asyncio.sleep(screens.DETAIL_TICK * 3)
            await pilot.pause()

            log = app.screen.query_one(RichLog)
            written = "\n".join(strip.text for strip in log.lines)
            assert "claude-opus-4-8" in written  # the live line did land
            assert "replay" not in written  # ...and was never called history

    asyncio.run(_drive())


# --- the fleet dashboard re-discovers loops on every refresh ----------------


def test_refresh_discovers_a_loop_registered_after_boot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fleet list must come from a live discovery call on every refresh,
    not a `roots` list captured once at startup. A loop that appears after
    boot (a repo gets registered, or gains a dev/local/autopilot dir) must
    show up on the very next refresh, without restarting the app."""
    pytest.importorskip("textual")
    from textual.widgets import DataTable

    from tracon import screens

    root_a = _make_loop(tmp_path / "loop-a")
    root_b = _make_loop(tmp_path / "loop-b")
    root_c = tmp_path / "loop-c"  # registered only AFTER boot

    discovered = [root_a, root_b]
    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: list(discovered))

    async def _drive() -> None:
        app = screens.build_app([root_a, root_b])
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.screen.query_one(DataTable)
            assert table.row_count == 2

            _make_loop(root_c)
            discovered.append(root_c)
            app.screen.refresh_table()
            await pilot.pause()

            assert table.row_count == 3

    asyncio.run(_drive())


def test_forced_root_pins_dashboard_to_one_loop_without_rediscovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit --root/forced override pins the app to ONE loop: the
    dashboard behind it must show only that loop, never the full registry,
    even though discovery would return more loops."""
    pytest.importorskip("textual")
    from textual.widgets import DataTable

    from tracon import screens

    root_a = _make_loop(tmp_path / "loop-a")
    root_b = _make_loop(tmp_path / "loop-b")

    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [root_a, root_b])

    async def _drive() -> None:
        app = screens.build_app([root_a], forced=root_a)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("escape")  # pop the auto-pushed DetailScreen
            await pilot.pause()

            table = app.screen.query_one(DataTable)
            assert table.row_count == 1
            assert table.get_row_at(0)[0] == "loop-a"

    asyncio.run(_drive())


# --- the cursor follows the SELECTED LOOP, not the row index ----------------


def test_cursor_stays_on_the_selected_loop_when_sort_order_moves_it(
    tmp_path: Path,
) -> None:
    """'Cursor position survives refresh' means the cursor stays on the same
    LOOP after a refresh, even when the attention-first sort order changes
    and that loop moves to a different row index. Saving and restoring the
    integer cursor_row silently lands the cursor on whatever loop now sits
    at the OLD index -- a different loop."""
    pytest.importorskip("textual")
    from textual.widgets import DataTable

    from tracon import screens

    root_alpha = _make_loop(tmp_path / "alpha")
    root_beta = _make_loop(tmp_path / "beta")

    async def _drive() -> None:
        app = screens.build_app([root_alpha, root_beta])
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.screen.query_one(DataTable)

            # equal status rank at first -> alphabetical: alpha(0), beta(1)
            assert table.get_row_at(0)[0] == "alpha"
            assert table.get_row_at(1)[0] == "beta"

            table.move_cursor(row=1)  # select beta -- NOT the first row
            await pilot.pause()
            assert table.get_row_at(table.cursor_row)[0] == "beta"

            # beta now needs attention -> rank 0, must sort FIRST next refresh
            state_path = root_beta / "dev" / "local" / "autopilot" / "state.json"
            state = json.loads(state_path.read_text())
            state["needs_attention"] = True
            state_path.write_text(json.dumps(state))

            app.screen.refresh_table()
            await pilot.pause()

            # order flipped: beta(0), alpha(1) -- beta moved out from under the cursor
            assert table.get_row_at(0)[0] == "beta"
            assert table.get_row_at(1)[0] == "alpha"

            # cursor must still be ON beta, wherever it now sits -- not on
            # whatever loop now occupies the OLD row index (1).
            assert table.get_row_at(table.cursor_row)[0] == "beta"

    asyncio.run(_drive())


def test_dashboard_table_sorts_rows_by_status_rank_before_name(
    tmp_path: Path,
) -> None:
    """Both fleet views sort by (status.rank, name): a lower-rank status must
    sort before a higher-rank one even when its name is alphabetically
    later."""
    pytest.importorskip("textual")
    from textual.widgets import DataTable

    from tracon import screens

    root_alpha = _make_loop(tmp_path / "alpha")
    root_zeta = _make_loop(tmp_path / "zeta")

    state_path = root_zeta / "dev" / "local" / "autopilot" / "state.json"
    state = json.loads(state_path.read_text())
    state["needs_attention"] = True  # rank 0 -- must sort before "alpha"
    state_path.write_text(json.dumps(state))

    async def _drive() -> None:
        app = screens.build_app([root_alpha, root_zeta])
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.screen.query_one(DataTable)
            assert table.get_row_at(0)[0] == "zeta"
            assert table.get_row_at(1)[0] == "alpha"

    asyncio.run(_drive())


# --- the dashboard has an explicit empty state -------------------------------


def _dashboard_visible_text(screen: Any) -> str:
    """Best-effort text dump of everything a DashboardScreen renders: any
    Static/Label `.renderable`, plus every DataTable cell -- covers an
    empty-state message realized either as a separate widget or as a table
    row/placeholder."""
    from textual.widgets import DataTable

    parts: list[str] = []
    for widget in screen.query("*"):
        renderable = getattr(widget, "renderable", None)
        if renderable is not None:
            parts.append(str(renderable))
        if isinstance(widget, DataTable):
            for i in range(widget.row_count):
                for cell in widget.get_row_at(i):
                    parts.append(cell.plain if isinstance(cell, Text) else str(cell))
    return "\n".join(parts)


def test_dashboard_shows_an_explicit_empty_state_when_no_loops_are_discovered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With zero discovered loops the dashboard must show a visible
    empty-state message -- run_once already prints "No loops found." for
    this case; the app must not stay mute with a silently empty table."""
    pytest.importorskip("textual")
    from tracon import screens

    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [])

    async def _drive() -> None:
        app = screens.build_app([])
        async with app.run_test() as pilot:
            await pilot.pause()
            text = _dashboard_visible_text(app.screen)
            assert "no loops found" in text.lower()

    asyncio.run(_drive())


# --- one fleet row-builder, shared by both views ------------------------------


def test_dashboard_table_uses_fleet_cells_for_row_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DashboardScreen must build each row's cells via the shared
    panels.fleet_cells builder, not hand-duplicate the (rank, name) sort, the
    44-char prd truncation, and the cost chip logic that panels.fleet_table
    also builds -- one builder, so the two views cannot drift apart."""
    pytest.importorskip("textual")
    from tracon import screens

    root_a = _make_loop(tmp_path / "loop-a")
    root_b = _make_loop(tmp_path / "loop-b")

    calls: list[Any] = []
    original = screens.panels.fleet_cells

    def spy(row: Any) -> tuple:
        calls.append(row)
        return original(row)

    monkeypatch.setattr(screens.panels, "fleet_cells", spy)

    async def _drive() -> None:
        app = screens.build_app([root_a, root_b])
        async with app.run_test() as pilot:
            await pilot.pause()
            assert len(calls) == 2

    asyncio.run(_drive())
