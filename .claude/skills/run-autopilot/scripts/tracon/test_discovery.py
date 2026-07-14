"""Tests for tracon/discovery.py — status classification and loop/registry discovery."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from tracon import discovery, model


def _state(**overrides: Any) -> model.LoopState:
    base: dict[str, Any] = dict(
        prd="00061-x.md",
        phase="build",
        next_phase="",
        phases_completed=(),
        cycle=None,
        rework_cap=None,
        tasks_total=None,
        tasks_completed=None,
        batch_id="",
        needs_attention=False,
        exists=True,
        raw={},
    )
    base.update(overrides)
    return model.LoopState(**base)


def _row(**overrides: Any) -> model.MetricsRow:
    base: dict[str, Any] = dict(
        ts_start=1000.0,
        ts_end=1000.0,
        wall_secs=10.0,
        prd="00061-x.md",
        batch="202607120753",
        phase_launched="build",
        phase_end="build",
        signal="continue",
        model="opus",
        cost_usd=1.0,
        tokens_out=100,
    )
    base.update(overrides)
    return model.MetricsRow(**base)


def _write_json(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(json.dumps(data))
    return path


def _write_lines(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n")
    return path


def _metrics_line(**overrides: Any) -> str:
    row = {
        "ts_start": 1000.0,
        "ts_end": 1000.0,
        "wall_secs": 10,
        "prd": "00061-x.md",
        "batch": "202607120753",
        "phase_launched": "build",
        "phase_end": "build",
        "signal": "continue",
        "model": "opus",
        "cost_usd": 1.0,
        "tokens_out": 100,
    }
    row.update(overrides)
    return json.dumps(row)


def _result_event(cost: float) -> str:
    return json.dumps({"type": "result", "subtype": "success", "total_cost_usd": cost})


# --- classify: truth table, rows 1-9 (evaluated in contract order) ----------


def test_attention_wins_over_every_other_condition() -> None:
    status = discovery.classify(
        _state(needs_attention=True), rows=[], log_mtime=None, now=1000.0
    )
    assert status.label == "⚠ attention"
    assert status.rank == 0


def test_live_when_in_flight_and_log_written_within_live_window() -> None:
    last = _row(ts_end=1000.0, signal="continue")
    status = discovery.classify(_state(), rows=[last], log_mtime=1006.0, now=1010.0)
    assert status.label.startswith("● live")
    assert status.rank == 2
    assert status.in_flight is True


def test_quiet_when_log_newer_than_last_ts_end_even_if_last_signal_died() -> None:
    last = _row(ts_end=1000.0, signal="died")
    status = discovery.classify(_state(), rows=[last], log_mtime=1005.0, now=1030.0)
    assert status.label.startswith("◐ quiet")
    assert status.rank == 2
    assert not status.label.startswith("■")


def test_died_when_log_fresh_but_predates_ts_end_plus_slack() -> None:
    """LIVE_WINDOW alone cannot establish in-flight: a session that died 3s
    ago still has a log mtime well inside the 20s live window, but it must
    render died, not live, because it never wrote *after* its own ts_end."""
    last = _row(ts_end=1000.0, signal="died")
    status = discovery.classify(_state(), rows=[last], log_mtime=1000.3, now=1003.3)
    assert status.in_flight is False
    assert status.label.startswith("■ died")
    assert status.rank == 1


def test_paused_when_last_signal_paused_and_not_in_flight() -> None:
    last = _row(ts_end=1000.0, signal="paused")
    status = discovery.classify(_state(), rows=[last], log_mtime=1000.5, now=5000.0)
    assert status.label.startswith("⏸ paused")
    assert status.rank == 1


def test_drained_when_last_signal_done_and_not_in_flight() -> None:
    last = _row(ts_end=1000.0, signal="done")
    status = discovery.classify(_state(), rows=[last], log_mtime=1000.5, now=5000.0)
    assert status.label.startswith("✔ drained")
    assert status.rank == 4


def test_no_state_wins_over_no_log_when_both_absent() -> None:
    status = discovery.classify(
        _state(exists=False, needs_attention=False), rows=[], log_mtime=None, now=1000.0
    )
    assert status.label == "○ no state"
    assert status.rank == 5


def test_missing_log_renders_dedicated_no_log_status_not_idle() -> None:
    """Row 8 of the truth table: state present, no session log at all
    (log_mtime is None) renders the dedicated `○ no log` status - distinct
    from `○ idle {age}` (row 9), which requires a log to compute an age
    from."""
    status = discovery.classify(
        _state(exists=True, needs_attention=False), rows=[], log_mtime=None, now=1000.0
    )
    assert status.label == "○ no log"
    assert status.rank == 3


def test_idle_when_terminal_and_in_flight_conditions_are_exhausted() -> None:
    last = _row(ts_end=1000.0, signal="continue")
    status = discovery.classify(
        _state(exists=True, needs_attention=False),
        rows=[last],
        log_mtime=1000.5,
        now=5000.0,
    )
    assert status.label.startswith("○ idle")
    assert status.rank == 3


def test_idle_age_suffix_uses_fmt_dur_shape_not_zero_padded_minutes() -> None:
    """Age suffixes render via model.fmt_dur, not a discovery-local formatter:
    9 whole seconds must render `9s`, never `0m09s`."""
    last = _row(ts_end=1000.0, signal="continue")
    status = discovery.classify(
        _state(exists=True, needs_attention=False),
        rows=[last],
        log_mtime=1000.5,
        now=1009.5,
    )
    assert status.label == "○ idle 9s"


# --- classify: headline in-flight cases --------------------------------------


def test_empty_metrics_rows_with_stale_but_present_log_is_quiet_not_idle() -> None:
    """No session has ever completed a row, but the log exists: `last is None`
    alone must establish in-flight, never fall through to idle."""
    status = discovery.classify(_state(), rows=[], log_mtime=1000.0, now=1030.0)
    assert status.label.startswith("◐ quiet")
    assert status.rank == 2
    assert status.in_flight is True


def test_in_flight_log_with_missing_state_file_is_live_not_no_state() -> None:
    status = discovery.classify(
        _state(exists=False, needs_attention=False), rows=[], log_mtime=1000.0, now=1001.0
    )
    assert status.label.startswith("● live")
    assert status.rank == 2
    assert status.in_flight is True


def test_in_flight_is_independent_of_attention_label() -> None:
    last = _row(ts_end=1000.0, signal="continue")
    status = discovery.classify(
        _state(needs_attention=True), rows=[last], log_mtime=1006.0, now=1030.0
    )
    assert status.label == "⚠ attention"
    assert status.rank == 0
    assert status.in_flight is True


# --- classify: IN_FLIGHT_SLACK boundary, pinned from both sides -------------


def test_slack_boundary_just_under_two_seconds_is_terminal_signal() -> None:
    """A log written 1.9s after ts_end - inside the 2s truncation-guard
    slack - does not establish in-flight, so a died session at that instant
    still renders its terminal signal, not quiet."""
    last = _row(ts_end=1000.0, signal="died")
    status = discovery.classify(_state(), rows=[last], log_mtime=1001.9, now=1001.9)
    assert status.in_flight is False
    assert status.label.startswith("■ died")


def test_slack_boundary_just_over_two_seconds_is_in_flight_quiet() -> None:
    """A log written 2.1s after ts_end - past the 2s slack - establishes
    in-flight. Once the session has gone quiet past LIVE_WINDOW it renders
    `◐ quiet`, never the previous session's terminal signal."""
    last = _row(ts_end=1000.0, signal="died")
    status = discovery.classify(_state(), rows=[last], log_mtime=1002.1, now=1030.0)
    assert status.in_flight is True
    assert status.label.startswith("◐ quiet")


def test_exact_slack_boundary_is_not_in_flight() -> None:
    """The slack comparison is strict `>`, not `>=`: a log written at
    exactly last.ts_end + IN_FLIGHT_SLACK does not establish in-flight, so a
    died session at exactly that instant still renders its terminal signal.
    This is the only boundary test that discriminates `>` from `>=` - a
    write a fraction of a second to either side agrees under both
    operators, so it can't catch the operator flipping back to `>=`."""
    last = _row(ts_end=1000.0, signal="died")
    log_mtime = last.ts_end + discovery.IN_FLIGHT_SLACK
    status = discovery.classify(_state(), rows=[last], log_mtime=log_mtime, now=log_mtime)
    assert status.in_flight is False
    assert status.label.startswith("■ died")


# --- classify: rank ordering -------------------------------------------------


def test_rank_orders_attention_above_died_even_when_name_sorts_earlier() -> None:
    attention_status = discovery.classify(
        _state(needs_attention=True), rows=[], log_mtime=None, now=1000.0
    )
    died_status = discovery.classify(
        _state(needs_attention=False),
        rows=[_row(ts_end=1000.0, signal="died")],
        log_mtime=None,
        now=1000.0,
    )
    entries = [("aaa-died-repo", died_status), ("zzz-attention-repo", attention_status)]
    ordered = sorted(entries, key=lambda e: (e[1].rank, e[0]))
    assert ordered[0][0] == "zzz-attention-repo"


# --- loop_status: end-to-end against a fake loop root ------------------------


def test_loop_status_end_to_end_populates_row_cells_from_current_batch(
    tmp_path: Path,
) -> None:
    autopilot_dir = tmp_path / "dev" / "local" / "autopilot"
    autopilot_dir.mkdir(parents=True)
    _write_json(
        autopilot_dir / "state.json",
        {
            "prd": "00061-build-tracon-observer-v1.md",
            "phase": "build",
            "next_phase": "review",
            "tasks_total": 6,
            "tasks_completed": 2,
            "batch": {"id": "202607120753"},
            "needs_attention": False,
        },
    )
    _write_lines(
        autopilot_dir / "loop-metrics.jsonl",
        [
            _metrics_line(batch="202607120753", ts_end=1000.0, cost_usd=1.5),
            _metrics_line(batch="202607120753", ts_end=2000.0, cost_usd=2.5),
            _metrics_line(batch="OLDBATCH", ts_end=500.0, cost_usd=100.0, signal="done"),
        ],
    )
    # No last-session.log: log_mtime is None, so in_flight is trivially False
    # and live_cost must be 0.0 regardless of the batch's cost/session data.

    row = discovery.loop_status(tmp_path, now=3000.0)

    assert row.phase == "build"
    assert row.prd == "00061-build-tracon-observer-v1"
    assert row.task == "2/6"
    assert row.cost == pytest.approx(4.0)
    assert row.sessions == 2
    assert row.live_cost == 0.0


def test_loop_status_phase_falls_back_to_next_phase_when_phase_empty(
    tmp_path: Path,
) -> None:
    autopilot_dir = tmp_path / "dev" / "local" / "autopilot"
    autopilot_dir.mkdir(parents=True)
    _write_json(
        autopilot_dir / "state.json",
        {"prd": "x.md", "phase": "", "next_phase": "review"},
    )
    row = discovery.loop_status(tmp_path, now=1000.0)
    assert row.phase == "review"


def test_loop_status_phase_falls_back_to_em_dash_when_both_empty(
    tmp_path: Path,
) -> None:
    autopilot_dir = tmp_path / "dev" / "local" / "autopilot"
    autopilot_dir.mkdir(parents=True)
    _write_json(
        autopilot_dir / "state.json",
        {"prd": "x.md", "phase": "", "next_phase": ""},
    )
    row = discovery.loop_status(tmp_path, now=1000.0)
    assert row.phase == "—"


def test_loop_status_live_cost_populated_only_when_in_flight(tmp_path: Path) -> None:
    autopilot_dir = tmp_path / "dev" / "local" / "autopilot"
    autopilot_dir.mkdir(parents=True)
    _write_json(
        autopilot_dir / "state.json",
        {"prd": "x.md", "phase": "build", "batch": {"id": "B1"}},
    )
    _write_lines(
        autopilot_dir / "loop-metrics.jsonl",
        [_metrics_line(batch="B1", ts_end=1000.0, cost_usd=1.0)],
    )
    log_path = _write_lines(
        autopilot_dir / "last-session.log", [_result_event(7.77)]
    )
    # ts_end + IN_FLIGHT_SLACK = 1002.0; write the log after that -> in flight,
    # and within LIVE_WINDOW of `now` -> live.
    os.utime(log_path, (1006.0, 1006.0))

    row = discovery.loop_status(tmp_path, now=1007.0)

    assert row.status.in_flight is True
    assert row.live_cost == pytest.approx(7.77)


# --- discover_loops: registry handling ---------------------------------------


def test_missing_registry_returns_empty_when_home_claude_lacks_autopilot_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The degrade path is filtered too: a missing registry falls back to
    ~/.claude as the sole candidate, but that candidate still has to clear
    the same dev/local/autopilot filter as every other root."""
    fake_home = tmp_path / "home-bare"
    (fake_home / ".claude").mkdir(parents=True)
    monkeypatch.setattr(discovery.Path, "home", classmethod(lambda cls: fake_home))

    result = discovery.discover_loops(registry=tmp_path / "does-not-exist.csv")

    assert result == []


def test_missing_registry_returns_home_claude_when_autopilot_dir_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home-active"
    autopilot_dir = fake_home / ".claude" / "dev" / "local" / "autopilot"
    autopilot_dir.mkdir(parents=True)
    monkeypatch.setattr(discovery.Path, "home", classmethod(lambda cls: fake_home))

    result = discovery.discover_loops(registry=tmp_path / "does-not-exist.csv")

    assert result == [fake_home / ".claude"]


def test_discover_loops_skips_blank_and_relative_column_one_rows(
    tmp_path: Path,
) -> None:
    root_valid = tmp_path / "validrepo"
    (root_valid / "dev" / "local" / "autopilot").mkdir(parents=True)
    registry = tmp_path / "repos.csv"
    registry.write_text(
        "\n"
        "relative/path,badname,,\n"
        f"{root_valid},validrepo,,\n"
    )

    result = discovery.discover_loops(registry=registry)

    assert root_valid in result
    assert not any(str(p) == "relative/path" for p in result)


def test_discover_loops_drops_root_without_autopilot_dir(tmp_path: Path) -> None:
    root_no_autopilot = tmp_path / "bare-repo"
    root_no_autopilot.mkdir()
    registry = tmp_path / "repos.csv"
    registry.write_text(f"{root_no_autopilot},barerepo,,\n")

    result = discovery.discover_loops(registry=registry)

    assert root_no_autopilot not in result


def test_registry_row_with_quoted_comma_path_is_parsed_via_csv_module(
    tmp_path: Path,
) -> None:
    """The registry is real CSV, not line.split(',', 1): a quoted first
    column containing a comma must yield the full path, not a truncated
    prefix up to the first comma."""
    root_with_comma = tmp_path / "my,repo"
    (root_with_comma / "dev" / "local" / "autopilot").mkdir(parents=True)
    registry = tmp_path / "repos.csv"
    registry.write_text(f'"{root_with_comma}",name,flags\n')

    result = discovery.discover_loops(registry=registry)

    assert root_with_comma in result


# --- module-level interface pins --------------------------------------------


def test_live_window_constant_matches_spec() -> None:
    assert discovery.LIVE_WINDOW == 20.0


def test_in_flight_slack_constant_matches_spec() -> None:
    assert discovery.IN_FLIGHT_SLACK == 2.0


def test_discovery_has_no_separate_age_formatter() -> None:
    """fmt_dur is the sole duration formatter, living in model.py; discovery
    must not carry its own near-duplicate."""
    assert not hasattr(discovery, "_fmt_age")


def test_gita_registry_constant_matches_spec() -> None:
    assert discovery.GITA_REGISTRY == Path.home() / ".config/gita/repos.csv"


# --- loop_status: batch-scoped read isolates foreign-batch data -------------
#
# Contract: loop_status performs ONE read_metrics(path, state.batch_id) call
# and feeds those rows to BOTH classify(...) and the cost/sessions cells. A
# loop with no state.json has batch_id == "", and read_metrics(path, "")
# is a sentinel for "no rows at all" -- never "all rows". These tests fail
# against an implementation that passes read_metrics(path, batch=None) (all
# batches) to classify while scoping cost/sessions separately.


def test_loop_status_with_no_state_ignores_foreign_batch_cost_and_signal(
    tmp_path: Path,
) -> None:
    """No state.json means batch_id == "" -> read_metrics(path, "") == [].
    A foreign, already-finished batch's non-zero cost must not surface on
    a stateless loop, and its `done` signal must not render `drained`
    instead of `no state`."""
    autopilot_dir = tmp_path / "dev" / "local" / "autopilot"
    autopilot_dir.mkdir(parents=True)
    _write_lines(
        autopilot_dir / "loop-metrics.jsonl",
        [_metrics_line(batch="OLDBATCH", ts_end=500.0, cost_usd=100.0, signal="done")],
    )
    # No state.json, no last-session.log.

    row = discovery.loop_status(tmp_path, now=1000.0)

    assert row.status.label == "○ no state"
    assert row.status.rank == 5
    assert row.cost == 0.0
    assert row.sessions == 0


def test_loop_status_with_no_state_and_in_flight_log_is_never_drained_or_no_state(
    tmp_path: Path,
) -> None:
    """Same foreign-batch fixture as above, plus a log written after the
    foreign batch's ts_end: `last is None` (scoped rows are empty) still
    establishes in-flight from the log alone. An in-flight session outranks
    a missing state file, and the foreign batch's `done` signal must not
    outrank it either."""
    autopilot_dir = tmp_path / "dev" / "local" / "autopilot"
    autopilot_dir.mkdir(parents=True)
    _write_lines(
        autopilot_dir / "loop-metrics.jsonl",
        [_metrics_line(batch="OLDBATCH", ts_end=500.0, cost_usd=100.0, signal="done")],
    )
    log_path = _write_lines(autopilot_dir / "last-session.log", [_result_event(0.0)])
    os.utime(log_path, (1000.0, 1000.0))

    row = discovery.loop_status(tmp_path, now=1010.0)

    assert row.status.in_flight is True
    assert row.status.label.startswith("● live")
    assert row.status.rank == 2
