"""Tests for tracon/discovery.py — status classification and loop/registry discovery."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from tracon import discovery, model

WRAPPER_ALIVE_SCRIPT = SCRIPTS_DIR / "tracon_wrapper_alive.py"


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


# --- pid_alive: os.kill(pid, 0) probe, tolerant of permission errors --------


def test_pid_alive_true_for_live_process() -> None:
    assert discovery.pid_alive(os.getpid()) is True


def test_pid_alive_false_when_kill_raises_process_lookup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_lookup(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(discovery.os, "kill", raise_lookup)
    assert discovery.pid_alive(999999) is False


def test_pid_alive_true_when_kill_raises_permission_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A process owned by another user still answers os.kill(pid, 0) with
    PermissionError, not ProcessLookupError - the OS confirmed the pid
    exists, it just refused to let us signal it. That must read as alive."""

    def raise_perm(pid: int, sig: int) -> None:
        raise PermissionError

    monkeypatch.setattr(discovery.os, "kill", raise_perm)
    assert discovery.pid_alive(1) is True


def test_pid_alive_rejects_nonpositive_pid() -> None:
    """os.kill(pid, 0) targets a process GROUP for pid 0 and pid -1, so it
    reports success even though no such process exists. pid_alive must reject
    both before ever reaching os.kill, not just relay its return value."""
    assert discovery.pid_alive(0) is False
    assert discovery.pid_alive(-1) is False


# --- read_registry: tolerant parse of one-file-per-wrapper registry ---------


def test_read_registry_returns_empty_list_when_dir_absent(tmp_path: Path) -> None:
    result = discovery.read_registry(loops_dir=tmp_path / "does-not-exist")
    assert result == []


def test_read_registry_skips_non_json_file(tmp_path: Path) -> None:
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    (loops_dir / "12345.json").write_text("not json {")

    result = discovery.read_registry(loops_dir=loops_dir)

    assert result == []


def test_read_registry_skips_entry_missing_pid(tmp_path: Path) -> None:
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    _write_json(
        loops_dir / "orphan.json",
        {"root": str(tmp_path), "started_at": "2026-07-14T00:00:00Z"},
    )

    result = discovery.read_registry(loops_dir=loops_dir)

    assert result == []


def test_read_registry_skips_entry_missing_root(tmp_path: Path) -> None:
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    _write_json(
        loops_dir / "12345.json",
        {"pid": 12345, "started_at": "2026-07-14T00:00:00Z"},
    )

    result = discovery.read_registry(loops_dir=loops_dir)

    assert result == []


def test_read_registry_parses_valid_entry_into_wrapper(tmp_path: Path) -> None:
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    root = tmp_path / "myrepo"
    _write_json(
        loops_dir / "12345.json",
        {
            "pid": 12345,
            "root": str(root),
            "ap_dir": str(root / "dev/local/autopilot"),
            "started_at": "2026-07-14T00:00:00Z",
        },
    )

    result = discovery.read_registry(loops_dir=loops_dir)

    assert len(result) == 1
    wrapper = result[0]
    assert isinstance(wrapper, discovery.Wrapper)
    assert wrapper.pid == 12345
    assert isinstance(wrapper.pid, int)
    assert wrapper.root == root
    assert isinstance(wrapper.root, Path)
    assert wrapper.started_at == "2026-07-14T00:00:00Z"


def test_read_registry_rejects_nonpositive_pid() -> None:
    """A registry entry with pid 0 or a negative pid must never be treated as
    a live wrapper candidate: pid 0 and pid -1 both target process GROUPS
    under os.kill, so a bogus entry would otherwise read as alive forever."""
    loops_dir = discovery.LOOPS_DIR
    root = loops_dir / "myrepo"
    _write_json(
        loops_dir / "zero.json",
        {"pid": 0, "root": str(root), "started_at": "2026-07-14T00:00:00Z"},
    )
    _write_json(
        loops_dir / "negative.json",
        {"pid": -1, "root": str(root), "started_at": "2026-07-14T00:00:00Z"},
    )
    _write_json(
        loops_dir / "valid.json",
        {"pid": 12345, "root": str(root), "started_at": "2026-07-14T00:00:00Z"},
    )

    result = discovery.read_registry()

    pids = [wrapper.pid for wrapper in result]
    assert pids == [12345]


# --- wrapper_alive: registry membership AND liveness, root paths resolved ---


def test_wrapper_alive_true_when_registry_entry_matches_root_and_pid_live(
    tmp_path: Path,
) -> None:
    root = tmp_path / "myrepo"
    root.mkdir()
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    _write_json(
        loops_dir / "1.json",
        {"pid": os.getpid(), "root": str(root), "started_at": "2026-07-14T00:00:00Z"},
    )

    assert discovery.wrapper_alive(root, loops_dir=loops_dir) is True


def test_wrapper_alive_false_when_registry_pid_is_dead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "myrepo"
    root.mkdir()
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    _write_json(
        loops_dir / "1.json",
        {"pid": 999999, "root": str(root), "started_at": "2026-07-14T00:00:00Z"},
    )

    def raise_lookup(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(discovery.os, "kill", raise_lookup)

    assert discovery.wrapper_alive(root, loops_dir=loops_dir) is False


def test_wrapper_alive_false_when_no_registry_entry_exists(tmp_path: Path) -> None:
    root = tmp_path / "myrepo"
    root.mkdir()
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()

    assert discovery.wrapper_alive(root, loops_dir=loops_dir) is False


def test_wrapper_alive_false_when_entry_is_for_a_different_root(tmp_path: Path) -> None:
    root = tmp_path / "myrepo"
    root.mkdir()
    other_root = tmp_path / "otherrepo"
    other_root.mkdir()
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    _write_json(
        loops_dir / "1.json",
        {"pid": os.getpid(), "root": str(other_root), "started_at": "2026-07-14T00:00:00Z"},
    )

    assert discovery.wrapper_alive(root, loops_dir=loops_dir) is False


def test_wrapper_alive_resolves_symlinked_root_to_match_registry_entry(
    tmp_path: Path,
) -> None:
    """Repo roots can be symlinks: a registry entry recorded against the real
    path must still match a caller passing the symlink, so both sides
    compare after Path.resolve()."""
    real_root = tmp_path / "real-repo"
    real_root.mkdir()
    symlink_root = tmp_path / "symlinked-repo"
    symlink_root.symlink_to(real_root)
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    _write_json(
        loops_dir / "1.json",
        {"pid": os.getpid(), "root": str(real_root), "started_at": "2026-07-14T00:00:00Z"},
    )

    assert discovery.wrapper_alive(symlink_root, loops_dir=loops_dir) is True


def test_wrapper_alive_ignores_nonpositive_pid_entry(tmp_path: Path) -> None:
    """A registry entry for this exact root with pid 0 must never read as a
    live wrapper: os.kill(0, 0) succeeds because it targets the calling
    process's group, not because pid 0 is a real, live wrapper process."""
    root = tmp_path / "myrepo"
    root.mkdir()
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    _write_json(
        loops_dir / "1.json",
        {"pid": 0, "root": str(root), "started_at": "2026-07-14T00:00:00Z"},
    )

    assert discovery.wrapper_alive(root, loops_dir=loops_dir) is False


# --- loop_status: wrapper field reflects wrapper_alive for the loop root ----


def test_loop_status_wrapper_true_when_registry_entry_alive_for_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    autopilot_dir = tmp_path / "dev" / "local" / "autopilot"
    autopilot_dir.mkdir(parents=True)
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    _write_json(
        loops_dir / "1.json",
        {"pid": os.getpid(), "root": str(tmp_path), "started_at": "2026-07-14T00:00:00Z"},
    )
    monkeypatch.setattr(discovery, "LOOPS_DIR", loops_dir)

    row = discovery.loop_status(tmp_path, now=1000.0)

    assert row.wrapper is True


def test_loop_status_wrapper_false_when_registry_entry_pid_is_dead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A registry entry exists for this exact root, so this only exercises
    the negative path meaningfully if the pid-liveness check truly runs - a
    stub that always returns False would pass just as easily, but so would
    one that never calls wrapper_alive at all; pairing this with the
    true-case test above rules out both."""
    autopilot_dir = tmp_path / "dev" / "local" / "autopilot"
    autopilot_dir.mkdir(parents=True)
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    _write_json(
        loops_dir / "1.json",
        {"pid": 999999, "root": str(tmp_path), "started_at": "2026-07-14T00:00:00Z"},
    )
    monkeypatch.setattr(discovery, "LOOPS_DIR", loops_dir)

    def raise_lookup(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(discovery.os, "kill", raise_lookup)

    row = discovery.loop_status(tmp_path, now=1000.0)

    assert row.wrapper is False


# --- limit-wait: wrapper sleeping until the usage-limit reset ----------------


def _idle_status() -> discovery.Status:
    return discovery.Status(label="○ idle 5m00s", style="dim", rank=3, in_flight=False)


def test_limit_wait_status_upgrades_idle_with_countdown_and_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(discovery, "limit_reset", lambda path, mtime: 1600)
    out = discovery.limit_wait_status(
        _idle_status(), tmp_path / "log", 100.0, True, 1000.0
    )
    assert out.label.startswith("⏳ limit-wait 10m00s")
    assert out.style == "yellow"
    assert out.in_flight is False
    assert out.rank == 1


def test_limit_wait_status_keeps_original_without_a_live_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(discovery, "limit_reset", lambda path, mtime: 1600)
    idle = _idle_status()
    out = discovery.limit_wait_status(idle, tmp_path / "log", 100.0, False, 1000.0)
    assert out is idle


def test_limit_wait_status_keeps_original_when_in_flight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(discovery, "limit_reset", lambda path, mtime: 1600)
    live = discovery.Status(label="● live", style="green", rank=2, in_flight=True)
    out = discovery.limit_wait_status(live, tmp_path / "log", 100.0, True, 1000.0)
    assert out is live


def test_limit_wait_status_never_overrides_needs_attention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(discovery, "limit_reset", lambda path, mtime: 1600)
    attention = discovery.Status(
        label="⚠ attention", style="bold red", rank=0, in_flight=False
    )
    out = discovery.limit_wait_status(
        attention, tmp_path / "log", 100.0, True, 1000.0
    )
    assert out is attention


def test_limit_wait_status_ignores_a_reset_already_in_the_past(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(discovery, "limit_reset", lambda path, mtime: 900)
    idle = _idle_status()
    out = discovery.limit_wait_status(idle, tmp_path / "log", 100.0, True, 1000.0)
    assert out is idle


def test_limit_reset_caches_per_mtime_and_rescans_on_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tick loop calls this every 0.5s against a static log; the tail
    scan must run once per mtime, not once per tick."""
    import detect_usage_limit

    calls: list[Path] = []

    def fake_detect(path: Path) -> int:
        calls.append(path)
        return 1600

    monkeypatch.setattr(detect_usage_limit, "detect_from_log", fake_detect)
    log = tmp_path / "last-session.log"
    log.write_text("banner")

    assert discovery.limit_reset(log, 100.0) == 1600
    assert discovery.limit_reset(log, 100.0) == 1600
    assert len(calls) == 1
    assert discovery.limit_reset(log, 200.0) == 1600
    assert len(calls) == 2
    assert discovery.limit_reset(log, None) is None


def test_loop_status_shows_limit_wait_instead_of_died_while_wrapper_sleeps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A limit-hit session exits with the banner in its log; the wrapper
    sleeps until the reset, appending no metrics row. classify() alone reads
    that gap as died/idle — a live wrapper plus a future reset must render
    the loop as waiting, not dead."""
    autopilot_dir = tmp_path / "dev" / "local" / "autopilot"
    autopilot_dir.mkdir(parents=True)
    _write_json(
        autopilot_dir / "state.json", {"phase": "build", "batch": {"id": "B1"}}
    )
    log = autopilot_dir / "last-session.log"
    log.write_text("claude: usage limit reached — try again later\n")
    now = time.time()
    _write_lines(
        autopilot_dir / "loop-metrics.jsonl",
        [_metrics_line(batch="B1", ts_start=now - 100, ts_end=now, signal="died")],
    )
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    _write_json(
        loops_dir / "1.json",
        {"pid": os.getpid(), "root": str(tmp_path), "started_at": ""},
    )
    monkeypatch.setattr(discovery, "LOOPS_DIR", loops_dir)

    row = discovery.loop_status(tmp_path, now=now + 10)

    assert row.status.label.startswith("⏳ limit-wait")
    assert row.status.style == "yellow"


# --- orphaned: queued work with nothing alive to relaunch it -----------------


def test_orphan_status_upgrades_idle_to_loud_warning_with_age() -> None:
    out = discovery.orphan_status(
        _idle_status(), _state(next_phase="build"), False, 900.0, None, 1000.0
    )
    assert out.label == "⚠ orphaned 1m40s => run autoclaude"
    assert out.style == "bold red"
    assert out.rank == 1


def test_orphan_status_dims_to_plain_red_after_a_day() -> None:
    out = discovery.orphan_status(
        _idle_status(), _state(next_phase="review"), False, 1000.0, None, 1000.0 + 200000
    )
    assert out.style == "red"
    assert "55h33m" in out.label


def test_orphan_status_falls_back_to_log_mtime_for_the_age_anchor() -> None:
    out = discovery.orphan_status(
        _idle_status(), _state(next_phase="build"), False, None, 940.0, 1000.0
    )
    assert "1m00s" in out.label


def test_orphan_status_keeps_original_when_wrapper_alive() -> None:
    idle = _idle_status()
    out = discovery.orphan_status(
        idle, _state(next_phase="build"), True, 900.0, None, 1000.0
    )
    assert out is idle


@pytest.mark.parametrize("next_phase", ["", "paused"])
def test_orphan_status_keeps_original_when_no_work_is_queued(
    next_phase: str,
) -> None:
    """Drained batches (next_phase == "") and deliberate pauses are not
    orphans — warning on every parked loop would drown the real incident."""
    idle = _idle_status()
    out = discovery.orphan_status(
        idle, _state(next_phase=next_phase), False, 900.0, None, 1000.0
    )
    assert out is idle


def test_orphan_status_keeps_terminal_statuses_like_died() -> None:
    died = discovery.Status(label="■ died 10:00", style="bold red", rank=1, in_flight=False)
    out = discovery.orphan_status(
        died, _state(next_phase="build"), False, 900.0, None, 1000.0
    )
    assert out is died


def test_loop_status_marks_orphaned_when_wrapper_died_mid_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wrapper killed mid-batch (closed terminal, crash) leaves next_phase
    set and the last metrics signal non-terminal; without the warning that
    renders as a dim idle row that reads as fine."""
    autopilot_dir = tmp_path / "dev" / "local" / "autopilot"
    autopilot_dir.mkdir(parents=True)
    _write_json(
        autopilot_dir / "state.json",
        {"phase": "build", "next_phase": "build", "batch": {"id": "B1"}},
    )
    (autopilot_dir / "last-session.log").write_text("{}\n")
    now = time.time()
    _write_lines(
        autopilot_dir / "loop-metrics.jsonl",
        [_metrics_line(batch="B1", ts_start=now - 100, ts_end=now + 5, signal="continue")],
    )

    row = discovery.loop_status(tmp_path, now=now + 10)

    assert row.status.label.startswith("⚠ orphaned")
    assert row.status.style == "bold red"


def test_live_wrapper_pid_returns_registered_live_pid(tmp_path: Path) -> None:
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    _write_json(loops_dir / "1.json", {"pid": os.getpid(), "root": str(tmp_path)})

    assert discovery.live_wrapper_pid(tmp_path, loops_dir=loops_dir) == os.getpid()


def test_live_wrapper_pid_none_when_pid_dead_or_unregistered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    assert discovery.live_wrapper_pid(tmp_path, loops_dir=loops_dir) is None

    _write_json(loops_dir / "1.json", {"pid": 999999, "root": str(tmp_path)})

    def raise_lookup(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(discovery.os, "kill", raise_lookup)
    assert discovery.live_wrapper_pid(tmp_path, loops_dir=loops_dir) is None


# --- pause-requested: pending marker must be visible -------------------------


def test_pause_pending_status_suffixes_the_label_while_marker_exists(
    tmp_path: Path,
) -> None:
    autopilot_dir = tmp_path / "dev" / "local" / "autopilot"
    autopilot_dir.mkdir(parents=True)
    (autopilot_dir / "pause-requested").touch()
    idle = _idle_status()

    out = discovery.pause_pending_status(idle, tmp_path, True)

    assert out.label == "○ idle 5m00s · ⏸ pause requested"
    assert (out.style, out.rank, out.in_flight) == (idle.style, idle.rank, idle.in_flight)


def test_pause_pending_status_identity_without_marker(tmp_path: Path) -> None:
    idle = _idle_status()
    assert discovery.pause_pending_status(idle, tmp_path, True) is idle


def test_pause_pending_status_identity_when_no_wrapper_alive(
    tmp_path: Path,
) -> None:
    """With no live wrapper the marker is inert; the chip would only pile
    onto the paused/orphaned indicators."""
    autopilot_dir = tmp_path / "dev" / "local" / "autopilot"
    autopilot_dir.mkdir(parents=True)
    (autopilot_dir / "pause-requested").touch()
    idle = _idle_status()

    assert discovery.pause_pending_status(idle, tmp_path, False) is idle


# --- discover_loops: union of ~/.claude, gita CSV rows, live registry roots -


def test_discover_loops_includes_live_registry_root_absent_from_gita_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)  # no autopilot dir -> filtered
    monkeypatch.setattr(discovery.Path, "home", classmethod(lambda cls: fake_home))

    registry_root = tmp_path / "wrapper-only-repo"
    (registry_root / "dev" / "local" / "autopilot").mkdir(parents=True)

    gita_csv = tmp_path / "repos.csv"
    gita_csv.write_text("")

    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    _write_json(
        loops_dir / "1.json",
        {
            "pid": os.getpid(),
            "root": str(registry_root),
            "started_at": "2026-07-14T00:00:00Z",
        },
    )

    result = discovery.discover_loops(registry=gita_csv, loops_dir=loops_dir)

    assert registry_root in result


def test_discover_loops_dedups_root_present_in_both_gita_csv_and_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    monkeypatch.setattr(discovery.Path, "home", classmethod(lambda cls: fake_home))

    shared_root = tmp_path / "shared-repo"
    (shared_root / "dev" / "local" / "autopilot").mkdir(parents=True)

    gita_csv = tmp_path / "repos.csv"
    gita_csv.write_text(f"{shared_root},sharedrepo,,\n")

    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    _write_json(
        loops_dir / "1.json",
        {
            "pid": os.getpid(),
            "root": str(shared_root),
            "started_at": "2026-07-14T00:00:00Z",
        },
    )

    result = discovery.discover_loops(registry=gita_csv, loops_dir=loops_dir)

    assert result.count(shared_root) == 1


def test_discover_loops_excludes_dead_pid_registry_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    monkeypatch.setattr(discovery.Path, "home", classmethod(lambda cls: fake_home))

    dead_root = tmp_path / "dead-wrapper-repo"
    (dead_root / "dev" / "local" / "autopilot").mkdir(parents=True)

    gita_csv = tmp_path / "repos.csv"
    gita_csv.write_text("")

    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    _write_json(
        loops_dir / "1.json",
        {"pid": 999999, "root": str(dead_root), "started_at": "2026-07-14T00:00:00Z"},
    )

    def raise_lookup(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(discovery.os, "kill", raise_lookup)

    result = discovery.discover_loops(registry=gita_csv, loops_dir=loops_dir)

    assert dead_root not in result


def test_discover_loops_registry_root_survives_unreadable_gita_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pre-existing degrade path for a missing gita registry falls back
    to ~/.claude alone; a live wrapper-registry entry must still surface its
    root through that same fallback, not get dropped alongside the CSV."""
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)  # no autopilot dir -> filtered
    monkeypatch.setattr(discovery.Path, "home", classmethod(lambda cls: fake_home))

    registry_root = tmp_path / "wrapper-survives-repo"
    (registry_root / "dev" / "local" / "autopilot").mkdir(parents=True)

    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    _write_json(
        loops_dir / "1.json",
        {
            "pid": os.getpid(),
            "root": str(registry_root),
            "started_at": "2026-07-14T00:00:00Z",
        },
    )

    result = discovery.discover_loops(
        registry=tmp_path / "does-not-exist.csv", loops_dir=loops_dir
    )

    assert registry_root in result


def test_discover_loops_registry_root_without_autopilot_dir_is_filtered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    monkeypatch.setattr(discovery.Path, "home", classmethod(lambda cls: fake_home))

    bare_root = tmp_path / "bare-wrapper-repo"
    bare_root.mkdir()  # no dev/local/autopilot

    gita_csv = tmp_path / "repos.csv"
    gita_csv.write_text("")

    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    _write_json(
        loops_dir / "1.json",
        {"pid": os.getpid(), "root": str(bare_root), "started_at": "2026-07-14T00:00:00Z"},
    )

    result = discovery.discover_loops(registry=gita_csv, loops_dir=loops_dir)

    assert bare_root not in result


# --- tracon_wrapper_alive.py: subprocess guard over discovery.wrapper_alive -
#
# Thin CLI adapter: `python3 tracon_wrapper_alive.py <root>` exits 0 when a
# live wrapper owns <root>, 1 otherwise. It reads the registry via the
# _AUTOPILOT_LOOPS_DIR env var (discovery.LOOPS_DIR is resolved from that var
# at import time), so these tests run it as a real subprocess with that var
# set in `env`, rather than monkeypatching discovery in-process.


def _run_wrapper_alive_guard(root: Path, loops_dir: Path) -> subprocess.CompletedProcess[bytes]:
    env = dict(os.environ)
    env["_AUTOPILOT_LOOPS_DIR"] = str(loops_dir)
    return subprocess.run(
        [sys.executable, str(WRAPPER_ALIVE_SCRIPT), str(root)],
        env=env,
        capture_output=True,
    )


def test_exits_zero_when_live_wrapper_owns_root(tmp_path: Path) -> None:
    root = tmp_path / "myrepo"
    root.mkdir()
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    _write_json(
        loops_dir / "1.json",
        {"pid": os.getpid(), "root": str(root), "started_at": "2026-07-14T00:00:00Z"},
    )

    result = _run_wrapper_alive_guard(root, loops_dir)

    assert result.returncode == 0


def test_prints_incumbent_pid_on_stdout_when_alive(tmp_path: Path) -> None:
    """A refusing caller names the incumbent loop's pid, so the guard prints it
    on stdout (exit 0) — the plain/headless autoclaude path reads it to refuse a
    second loop by pid. PRD 00084 R1."""
    root = tmp_path / "myrepo"
    root.mkdir()
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    _write_json(
        loops_dir / "1.json",
        {"pid": os.getpid(), "root": str(root), "started_at": "2026-07-14T00:00:00Z"},
    )

    result = _run_wrapper_alive_guard(root, loops_dir)

    assert result.returncode == 0
    assert result.stdout.strip() == str(os.getpid()).encode()


def test_exits_one_when_no_registry_entry_for_root(tmp_path: Path) -> None:
    root = tmp_path / "myrepo"
    root.mkdir()
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()  # empty registry

    result = _run_wrapper_alive_guard(root, loops_dir)

    assert result.returncode == 1
    assert result.stdout.strip() == b""  # empty stdout → bash `[ -n "$pid" ]` reads absent


def test_exits_one_when_registry_entry_pid_is_dead(tmp_path: Path) -> None:
    root = tmp_path / "myrepo"
    root.mkdir()
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()

    # Spawn and wait out a real subprocess so its pid is guaranteed reaped,
    # rather than mocking os.kill (not possible across a subprocess boundary).
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    dead_pid = child.pid
    child.wait()

    _write_json(
        loops_dir / "1.json",
        {"pid": dead_pid, "root": str(root), "started_at": "2026-07-14T00:00:00Z"},
    )

    result = _run_wrapper_alive_guard(root, loops_dir)

    assert result.returncode == 1


def test_exits_one_for_nonexistent_root_without_crashing(tmp_path: Path) -> None:
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()

    result = _run_wrapper_alive_guard(Path("/nonexistent/root"), loops_dir)

    assert result.returncode == 1
    assert b"Traceback" not in result.stderr


def test_guard_is_read_only_leaves_registry_and_root_untouched(tmp_path: Path) -> None:
    root = tmp_path / "myrepo"
    root.mkdir()
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    entry_path = _write_json(
        loops_dir / "1.json",
        {"pid": os.getpid(), "root": str(root), "started_at": "2026-07-14T00:00:00Z"},
    )
    before_entry_text = entry_path.read_text()
    before_loops_names = sorted(p.name for p in loops_dir.iterdir())
    before_root_names = sorted(p.name for p in root.iterdir())

    _run_wrapper_alive_guard(root, loops_dir)

    assert sorted(p.name for p in loops_dir.iterdir()) == before_loops_names
    assert sorted(p.name for p in root.iterdir()) == before_root_names
    assert entry_path.read_text() == before_entry_text


def test_wrapper_alive_script_requires_root_arg() -> None:
    """Invoked with no <root> argument, the script must exit non-zero with a
    usage message on stderr - not raise an uncaught IndexError traceback from
    an unguarded sys.argv[1] access."""
    result = subprocess.run(
        [sys.executable, str(WRAPPER_ALIVE_SCRIPT)],
        cwd=SCRIPTS_DIR,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    stderr_lower = result.stderr.lower()
    assert "usage" in stderr_lower or "root" in stderr_lower
    assert "traceback" not in stderr_lower
    assert "indexerror" not in stderr_lower
