"""Tests for tracon/screens.py — lazy-import guard, Collector, Textual pilot.

The lazy-import guard and `Collector` run under bare `python3 -m pytest` (no
textual). The Textual pilot test self-skips via `pytest.importorskip`.
"""

from __future__ import annotations

import asyncio
import importlib
import json
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
