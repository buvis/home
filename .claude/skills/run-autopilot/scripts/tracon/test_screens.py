"""Tests for tracon/screens.py — lazy-import guard, Collector, Textual pilot.

The lazy-import guard and `Collector` run under bare `python3 -m pytest` (no
textual). The Textual pilot test self-skips via `pytest.importorskip`.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from rich.text import Text

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

_TEXTUAL_SKIP_REASON = (
    "PRD 00061 Phase 2 acceptance test: requires textual, run with "
    "`uv run --with textual --with rich --with pytest pytest .`"
)


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


def _load_tracon_cli() -> Any:
    """Load the top-level tracon.py CLI script under a distinct module name.

    `tracon.py` (this script) and the `tracon/` package share the name
    `tracon` on disk; a plain `import tracon` always resolves to the
    package (regular packages win over same-named modules on the same
    sys.path entry), so `main()` is only reachable by loading the file
    directly, by path, under a name that cannot collide.
    """
    path = SCRIPTS_DIR / "tracon.py"
    spec = importlib.util.spec_from_file_location("tracon_cli", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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


# --- exit codes: the wrapper branches on these (bare python3, no textual) ---


@pytest.mark.parametrize("code", [0, 130])
def test_run_app_propagates_the_apps_return_code(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    """run_app() must return app.return_code, NOT a hard-coded 0. The
    wrapper branches on 0 (detach, keep the loop running) vs. 130 (stop the
    loop). Note App.exit(return_code=...) sets App.return_code; App.run()'s
    own return value is a DIFFERENT attribute (return_value) -- that mix-up
    is the bug this pins."""
    from tracon import screens

    class _FakeApp:
        return_code = code

        def run(self) -> None:
            return None

    monkeypatch.setattr(screens, "build_app", lambda *a, **kw: _FakeApp())

    assert screens.run_app([]) == code


def test_main_returns_130_on_keyboard_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    """tracon.py's `except KeyboardInterrupt` must return 130 (the SIGINT
    convention), not swallow it as a clean 0 exit."""
    module = _load_tracon_cli()
    monkeypatch.setattr(sys, "argv", ["tracon.py"])
    monkeypatch.setattr(module.discovery, "discover_loops", lambda: [])

    def _raise(*args: Any, **kwargs: Any) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(module.screens, "run_app", _raise)

    assert module.main() == 130


def test_wrapper_pid_flag_is_forwarded_to_run_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """--wrapper-pid is a new CLI flag; main() must plumb its value through
    to run_app so the app can poll discovery.pid_alive for the wrapper that
    launched it."""
    module = _load_tracon_cli()
    monkeypatch.setattr(sys, "argv", ["tracon.py", "--wrapper-pid", "4242"])
    monkeypatch.setattr(module.discovery, "discover_loops", lambda: [])

    captured: dict[str, Any] = {}

    def _fake_run_app(*args: Any, **kwargs: Any) -> int:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return 0

    monkeypatch.setattr(module.screens, "run_app", _fake_run_app)

    assert module.main() == 0
    assert 4242 in captured["args"] or captured["kwargs"].get("wrapper_pid") == 4242


# --- Textual pilot smoke test: needs textual, skips cleanly without it ------


@pytest.mark.ui
def test_dashboard_pilot_lists_loops_then_enter_and_f_drive_detail_screen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("textual", reason=_TEXTUAL_SKIP_REASON)
    from textual.widgets import DataTable, RichLog

    from tracon import screens

    root_a = _make_loop(tmp_path / "loop-a")
    root_b = _make_loop(tmp_path / "loop-b")
    # isolate from the real machine: refresh_table re-discovers on every
    # tick, so without this the fleet tick would read this developer
    # machine's real gita registry instead of the temp fixture roots.
    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [root_a, root_b])

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


@pytest.mark.ui
def test_lines_written_after_attach_are_not_banner_ed_as_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Attaching to an idle loop and watching it start is the common workflow.
    Its first lines are LIVE, not pre-attach history: they must not arrive under
    the replay banner. Only content already in the log at the first poll may."""
    pytest.importorskip("textual", reason=_TEXTUAL_SKIP_REASON)
    from textual.widgets import RichLog

    from tracon import screens

    root = _make_loop(tmp_path / "idle-loop", log_lines=[])  # log exists, empty
    log_path = root / "dev" / "local" / "autopilot" / "last-session.log"
    # isolate from the real machine: DashboardScreen mounts underneath the
    # auto-pushed DetailScreen and re-discovers on every fleet tick.
    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [root])

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


@pytest.mark.ui
def test_refresh_discovers_a_loop_registered_after_boot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fleet list must come from a live discovery call on every refresh,
    not a `roots` list captured once at startup. A loop that appears after
    boot (a repo gets registered, or gains a dev/local/autopilot dir) must
    show up on the very next refresh, without restarting the app."""
    pytest.importorskip("textual", reason=_TEXTUAL_SKIP_REASON)
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


@pytest.mark.ui
def test_forced_root_dashboard_always_shows_the_full_discovered_fleet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CONTRACT REVERSAL (design gate, 2026-07-14): --root/forced now ONLY
    selects which loop gets the auto-attached DetailScreen -- the dashboard
    behind it is NEVER pinned to one loop. Escaping from the auto-attached
    detail screen must land on the FULL discovered fleet, not a one-row
    table: an autoclaude-launched tracon monitors the whole fleet, not just
    its own root."""
    pytest.importorskip("textual", reason=_TEXTUAL_SKIP_REASON)
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
            assert table.row_count == 2

    asyncio.run(_drive())


# --- the cursor follows the SELECTED LOOP, not the row index ----------------


@pytest.mark.ui
def test_cursor_stays_on_the_selected_loop_when_sort_order_moves_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """'Cursor position survives refresh' means the cursor stays on the same
    LOOP after a refresh, even when the attention-first sort order changes
    and that loop moves to a different row index. Saving and restoring the
    integer cursor_row silently lands the cursor on whatever loop now sits
    at the OLD index -- a different loop."""
    pytest.importorskip("textual", reason=_TEXTUAL_SKIP_REASON)
    from textual.widgets import DataTable

    from tracon import screens

    root_alpha = _make_loop(tmp_path / "alpha")
    root_beta = _make_loop(tmp_path / "beta")
    # isolate from the real machine: refresh_table() (called explicitly
    # below, and by the fleet tick) re-discovers on every call.
    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [root_alpha, root_beta])

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


@pytest.mark.ui
def test_dashboard_table_sorts_rows_by_status_rank_before_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both fleet views sort by (status.rank, name): a lower-rank status must
    sort before a higher-rank one even when its name is alphabetically
    later."""
    pytest.importorskip("textual", reason=_TEXTUAL_SKIP_REASON)
    from textual.widgets import DataTable

    from tracon import screens

    root_alpha = _make_loop(tmp_path / "alpha")
    root_zeta = _make_loop(tmp_path / "zeta")
    # isolate from the real machine: DashboardScreen re-discovers on mount
    # and on every fleet tick.
    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [root_alpha, root_zeta])

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


@pytest.mark.ui
def test_dashboard_shows_an_explicit_empty_state_when_no_loops_are_discovered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With zero discovered loops the dashboard must show a visible
    empty-state message -- run_once already prints "No loops found." for
    this case; the app must not stay mute with a silently empty table."""
    pytest.importorskip("textual", reason=_TEXTUAL_SKIP_REASON)
    from tracon import screens

    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [])

    async def _drive() -> None:
        app = screens.build_app([])
        async with app.run_test() as pilot:
            await pilot.pause()
            text = _dashboard_visible_text(app.screen)
            assert "no loops found" in text.lower()

    asyncio.run(_drive())


@pytest.mark.ui
def test_enter_on_empty_dashboard_does_not_crash_or_push_detail_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The zero-loop dashboard's placeholder row ("No loops found.") is backed
    by nothing -- `_roots` stays empty. Pressing Enter on it must be a
    harmless no-op: the product contract requires the degraded-discovery case
    to never crash, but `on_data_table_row_selected` indexes `self._roots`
    unconditionally, so this used to raise IndexError and would have pushed a
    DetailScreen for a root that does not exist."""
    pytest.importorskip("textual", reason=_TEXTUAL_SKIP_REASON)
    from textual.widgets import DataTable

    from tracon import screens

    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [])

    async def _drive() -> None:
        app = screens.build_app([])
        async with app.run_test() as pilot:
            await pilot.pause()
            stack_depth_before = len(app.screen_stack)

            await pilot.press("enter")
            await pilot.pause()

            assert len(app.screen_stack) == stack_depth_before  # no DetailScreen pushed
            assert app.screen.query_one(DataTable) is not None  # still on the dashboard

    asyncio.run(_drive())


# --- one fleet row-builder, shared by both views ------------------------------


@pytest.mark.ui
def test_dashboard_table_uses_fleet_cells_for_row_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DashboardScreen must build each row's cells via the shared
    panels.fleet_cells builder, not hand-duplicate the (rank, name) sort, the
    44-char prd truncation, and the cost chip logic that panels.fleet_table
    also builds -- one builder, so the two views cannot drift apart."""
    pytest.importorskip("textual", reason=_TEXTUAL_SKIP_REASON)
    from tracon import screens

    root_a = _make_loop(tmp_path / "loop-a")
    root_b = _make_loop(tmp_path / "loop-b")
    # isolate from the real machine: DashboardScreen re-discovers on mount
    # and on every fleet tick.
    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [root_a, root_b])

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


# --- key protocol: q detaches, ctrl+c stops the loop ------------------------


@pytest.mark.ui
def test_q_detaches_the_dashboard_with_return_code_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """q leaves the loop running: it is rebound from app.quit to
    app.detach, which must exit with return_code=0 so the wrapper knows to
    keep the loop alive."""
    pytest.importorskip("textual", reason=_TEXTUAL_SKIP_REASON)
    from tracon import screens

    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [])

    async def _drive() -> None:
        app = screens.build_app([])
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("q")
            await pilot.pause()
            assert app.return_code == 0

    asyncio.run(_drive())


@pytest.mark.ui
def test_q_detaches_the_detail_screen_with_return_code_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """q is rebound on BOTH screens, not just the dashboard."""
    pytest.importorskip("textual", reason=_TEXTUAL_SKIP_REASON)
    from textual.widgets import RichLog

    from tracon import screens

    root = _make_loop(tmp_path / "loop-a")
    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [root])

    async def _drive() -> None:
        app = screens.build_app([root])  # single root -> auto-pushes DetailScreen
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.screen.query_one(RichLog) is not None  # on the detail screen

            await pilot.press("q")
            await pilot.pause()
            assert app.return_code == 0

    asyncio.run(_drive())


@pytest.mark.ui
def test_ctrl_c_stops_the_loop_with_return_code_130(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ctrl+C arrives as a key event in Textual's raw mode, not a
    KeyboardInterrupt: TraconApp.action_quit is overridden to exit 130 so
    the wrapper stops the loop instead of treating it as a clean detach."""
    pytest.importorskip("textual", reason=_TEXTUAL_SKIP_REASON)
    from tracon import screens

    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [])

    async def _drive() -> None:
        app = screens.build_app([])
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+c")
            await pilot.pause()
            assert app.return_code == 130

    asyncio.run(_drive())


# --- p: tracon's only write, anywhere ----------------------------------------


@pytest.mark.ui
def test_p_on_detail_screen_writes_only_the_pause_requested_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """p is tracon's ONLY write, anywhere: on the detail screen it must
    touch <root>/dev/local/autopilot/pause-requested in the ATTACHED root,
    and nothing else lands in that directory."""
    pytest.importorskip("textual", reason=_TEXTUAL_SKIP_REASON)
    from tracon import screens

    root = _make_loop(tmp_path / "loop-a")
    autopilot_dir = root / "dev" / "local" / "autopilot"
    before = {p.name for p in autopilot_dir.iterdir()}
    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [root])

    async def _drive() -> None:
        app = screens.build_app([root])  # single root -> auto-pushes DetailScreen
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()

    asyncio.run(_drive())

    after = {p.name for p in autopilot_dir.iterdir()}
    assert after - before == {"pause-requested"}
    assert (autopilot_dir / "pause-requested").is_file()


@pytest.mark.ui
def test_p_on_dashboard_targets_the_selected_rows_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """p on the dashboard must target the SELECTED row's root, not the
    first-discovered or the alphabetically-first loop."""
    pytest.importorskip("textual", reason=_TEXTUAL_SKIP_REASON)
    from textual.widgets import DataTable

    from tracon import screens

    root_a = _make_loop(tmp_path / "loop-a")
    root_b = _make_loop(tmp_path / "loop-b")
    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [root_a, root_b])

    async def _drive() -> None:
        app = screens.build_app([root_a, root_b])
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.screen.query_one(DataTable)
            assert table.get_row_at(0)[0] == "loop-a"
            assert table.get_row_at(1)[0] == "loop-b"

            table.move_cursor(row=1)  # select loop-b, NOT the first row
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()

    asyncio.run(_drive())

    assert (root_b / "dev" / "local" / "autopilot" / "pause-requested").is_file()
    assert not (root_a / "dev" / "local" / "autopilot" / "pause-requested").exists()


@pytest.mark.ui
def test_p_write_failure_notifies_instead_of_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pause-requested write failure (e.g. an unwritable autopilot dir)
    must surface as a Textual notification, never an unhandled exception."""
    pytest.importorskip("textual", reason=_TEXTUAL_SKIP_REASON)
    from textual.widgets import RichLog

    from tracon import screens

    root = _make_loop(tmp_path / "loop-a")
    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [root])

    def _raise_touch(self: Path, *args: Any, **kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(screens.Path, "touch", _raise_touch)

    async def _drive() -> None:
        app = screens.build_app([root])
        async with app.run_test() as pilot:
            notifications: list[Any] = []
            app.notify = lambda *a, **kw: notifications.append((a, kw))

            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()

            assert notifications  # a notification fired, not an exception
            assert app.screen.query_one(RichLog) is not None  # app still alive

    asyncio.run(_drive())


# --- --wrapper-pid: the wrapper's own life is polled ------------------------


@pytest.mark.ui
def test_wrapper_pid_dead_transition_shows_banner_and_exits_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the wrapper that launched tracon dies, tracon must render a
    loop-exit banner naming the final signal from the last loop-metrics row
    (here "done" -> "drained", the same label discovery.classify already
    uses for this signal), then exit 3 -- an alive->dead TRANSITION, not
    just "started dead"."""
    pytest.importorskip("textual", reason=_TEXTUAL_SKIP_REASON)
    from tracon import screens

    root = _make_loop(tmp_path / "loop-a")
    metrics_path = root / "dev" / "local" / "autopilot" / "loop-metrics.jsonl"
    _write_lines(metrics_path, [_metrics_line(signal="done")])
    monkeypatch.setattr(screens.discovery, "discover_loops", lambda: [root])

    wrapper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])

    async def _drive() -> None:
        app = screens.build_app([root], wrapper_pid=wrapper.pid)
        async with app.run_test() as pilot:
            await pilot.pause()
            await asyncio.sleep(2.5)  # >= one poll tick while the wrapper is alive
            await pilot.pause()
            assert app.return_code is None  # still alive: no exit yet

            wrapper.terminate()
            wrapper.wait(timeout=5)  # reaped: the pid is now genuinely dead

            banner_seen = False
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline and app.return_code is None:
                await asyncio.sleep(0.2)
                await pilot.pause()
                if "drained" in _dashboard_visible_text(app.screen).lower():
                    banner_seen = True

            assert banner_seen
            assert app.return_code == 3

    try:
        asyncio.run(_drive())
    finally:
        if wrapper.poll() is None:
            wrapper.kill()
            wrapper.wait()


# --- --preflight: dependency check, not a startup proof ---------------------


@pytest.mark.ui
def test_preflight_flag_exits_zero_without_launching_the_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--preflight imports textual and rich and exits 0 -- a dependency
    check, NOT a startup proof: it must return before ever calling
    run_app()."""
    pytest.importorskip("textual", reason=_TEXTUAL_SKIP_REASON)
    module = _load_tracon_cli()
    monkeypatch.setattr(sys, "argv", ["tracon.py", "--preflight"])

    calls: list[Any] = []

    def _fake_run_app(*args: Any, **kwargs: Any) -> int:
        calls.append((args, kwargs))
        return 0

    monkeypatch.setattr(module.screens, "run_app", _fake_run_app)

    assert module.main() == 0
    assert calls == []
