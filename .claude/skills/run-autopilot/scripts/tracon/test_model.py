"""Tests for tracon/model.py — the tolerant parse layer for autopilot artifacts."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from tracon import model


def _write_json(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(json.dumps(data))
    return path


def _write_lines(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n")
    return path


def _metrics_line(**overrides: Any) -> str:
    row = {
        "ts_start": 1783835237,
        "ts_end": 1783842444,
        "wall_secs": 7207,
        "prd": "00054-disambiguate-research-skill-triggers-v1.md",
        "batch": "202607120753",
        "phase_launched": "build",
        "phase_end": "build",
        "signal": "continue",
        "model": "claude-opus-4-8",
    }
    row.update(overrides)
    return json.dumps(row)


def _result_event(cost: float) -> str:
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "duration_ms": 1000,
            "num_turns": 3,
            "total_cost_usd": cost,
            "usage": {"output_tokens": 50},
        }
    )


# --- read_state: current-shape and legacy values ---------------------------


@pytest.mark.parametrize("phase", ["build", "review", "done", "paused"])
def test_read_state_phase_passes_through_current_shape_values(
    tmp_path: Path, phase: str
) -> None:
    path = _write_json(
        tmp_path / "state.json",
        {"prd": "00061-build-tracon-observer-v1.md", "phase": phase},
    )
    state = model.read_state(path)
    assert state.phase == phase
    assert state.prd == "00061-build-tracon-observer-v1.md"


def test_read_state_legacy_phase_stopped_passes_through_unchanged(
    tmp_path: Path,
) -> None:
    path = _write_json(tmp_path / "state.json", {"phase": "stopped"})
    state = model.read_state(path)
    assert state.phase == "stopped"


def test_read_state_phases_completed_list_becomes_tuple(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "state.json", {"phases_completed": ["build", "review"]}
    )
    state = model.read_state(path)
    assert state.phases_completed == ("build", "review")


# --- read_state: never-raise on bad input -----------------------------------


def test_read_state_survives_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{not valid json, dangling")
    state = model.read_state(path)
    assert state.exists is False


def test_read_state_survives_missing_file(tmp_path: Path) -> None:
    state = model.read_state(tmp_path / "does-not-exist.json")
    assert state.exists is False


def test_read_state_non_dict_top_level_is_treated_as_not_exists(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.json"
    path.write_text("[1, 2, 3]")
    state = model.read_state(path)
    assert state.exists is False


def test_read_state_survives_non_utf8_bytes(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_bytes(b'{"prd": "x.md", "phase": "\xff\xfebuild"}')
    state = model.read_state(path)
    assert state.exists is False


def test_read_state_partial_file_defaults_every_absent_field(
    tmp_path: Path,
) -> None:
    path = _write_json(tmp_path / "state.json", {})
    state = model.read_state(path)
    assert state.exists is True
    assert state.prd == ""
    assert state.phase == ""
    assert state.next_phase == ""
    assert state.phases_completed == ()
    assert state.cycle is None
    assert state.rework_cap is None
    assert state.tasks_total is None
    assert state.tasks_completed is None
    assert state.batch_id == ""
    assert state.needs_attention is False


def test_read_state_wrong_typed_cycle_coerces_to_none(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "state.json", {"cycle": "three"})
    state = model.read_state(path)
    assert state.cycle is None
    assert state.exists is True


# --- read_state: batch_id nested lookup -------------------------------------


def test_read_state_batch_id_comes_from_nested_batch_id(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "state.json", {"batch": {"id": "202607120753"}}
    )
    state = model.read_state(path)
    assert state.batch_id == "202607120753"


def test_read_state_batch_id_empty_when_batch_absent(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "state.json", {})
    state = model.read_state(path)
    assert state.batch_id == ""


def test_read_state_batch_id_empty_when_batch_not_a_dict(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "state.json", {"batch": "202607120753"})
    state = model.read_state(path)
    assert state.batch_id == ""


# --- LoopState.prd_name ------------------------------------------------------


def test_prd_name_strips_md_suffix(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "state.json",
        {"prd": "00061-build-tracon-observer-v1.md"},
    )
    state = model.read_state(path)
    assert state.prd_name == "00061-build-tracon-observer-v1"


def test_prd_name_defaults_to_em_dash_when_empty(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "state.json", {})
    state = model.read_state(path)
    assert state.prd_name == "—"


# --- read_metrics: batch sentinel three-way split ---------------------------


def test_read_metrics_batch_none_returns_every_row(tmp_path: Path) -> None:
    path = _write_lines(
        tmp_path / "loop-metrics.jsonl",
        [
            _metrics_line(batch="A"),
            _metrics_line(batch="B"),
            _metrics_line(batch="A"),
        ],
    )
    rows = model.read_metrics(path, batch=None)
    assert len(rows) == 3


def test_read_metrics_batch_id_filters_to_matching_rows_only(
    tmp_path: Path,
) -> None:
    path = _write_lines(
        tmp_path / "loop-metrics.jsonl",
        [
            _metrics_line(batch="A", phase_end="build"),
            _metrics_line(batch="B", phase_end="review"),
            _metrics_line(batch="A", phase_end="done"),
        ],
    )
    rows = model.read_metrics(path, batch="A")
    assert [r.batch for r in rows] == ["A", "A"]
    assert [r.phase_end for r in rows] == ["build", "done"]


def test_read_metrics_batch_empty_string_returns_empty_list(
    tmp_path: Path,
) -> None:
    path = _write_lines(
        tmp_path / "loop-metrics.jsonl",
        [_metrics_line(batch="A"), _metrics_line(batch="B")],
    )
    rows = model.read_metrics(path, batch="")
    assert rows == []


# --- read_metrics: never-raise and ordering ---------------------------------


def test_read_metrics_skips_unparseable_line_and_keeps_file_order(
    tmp_path: Path,
) -> None:
    path = _write_lines(
        tmp_path / "loop-metrics.jsonl",
        [
            _metrics_line(batch="A", phase_end="build"),
            "not json at all {{{",
            _metrics_line(batch="A", phase_end="done"),
        ],
    )
    rows = model.read_metrics(path, batch=None)
    assert [r.phase_end for r in rows] == ["build", "done"]


def test_read_metrics_survives_non_utf8_line(tmp_path: Path) -> None:
    path = tmp_path / "loop-metrics.jsonl"
    path.write_bytes(_metrics_line(phase_end="build").encode("utf-8") + b"\n\xff\xfe not utf8\n")
    rows = model.read_metrics(path, batch=None)
    assert isinstance(rows, list)


def test_read_metrics_survives_missing_file(tmp_path: Path) -> None:
    assert model.read_metrics(tmp_path / "nope.jsonl") == []


def test_read_metrics_defaults_absent_optional_fields(tmp_path: Path) -> None:
    line = json.dumps(
        {
            "prd": "00054-x.md",
            "batch": "202607120753",
            "phase_launched": "build",
            "phase_end": "build",
            "model": "claude-opus-4-8",
        }
    )
    path = _write_lines(tmp_path / "loop-metrics.jsonl", [line])
    rows = model.read_metrics(path, batch=None)
    assert len(rows) == 1
    row = rows[0]
    assert row.ts_start is None
    assert row.ts_end is None
    assert row.wall_secs == 0.0
    assert row.signal == ""
    assert row.cost_usd == 0.0
    assert row.tokens_out == 0


# --- last_row ----------------------------------------------------------------


def test_last_row_treats_missing_ts_end_as_zero_and_does_not_raise(
    tmp_path: Path,
) -> None:
    path = _write_lines(
        tmp_path / "loop-metrics.jsonl",
        [
            _metrics_line(phase_end="has-ts-end", ts_end=5000000),
            json.dumps(
                {
                    "prd": "00054-x.md",
                    "batch": "202607120753",
                    "phase_launched": "build",
                    "phase_end": "missing-ts-end",
                    "model": "claude-opus-4-8",
                }
            ),
        ],
    )
    rows = model.read_metrics(path, batch=None)
    row = model.last_row(rows)
    assert row is not None
    assert row.phase_end == "has-ts-end"


def test_last_row_returns_none_for_empty_list() -> None:
    assert model.last_row([]) is None


# --- batch_start_ts ------------------------------------------------------------


def test_batch_start_ts_takes_min_ts_start_from_rows(tmp_path: Path) -> None:
    path = _write_lines(
        tmp_path / "loop-metrics.jsonl",
        [
            _metrics_line(batch="202607120753", ts_start=1783842444),
            _metrics_line(batch="202607120753", ts_start=1783835237),
        ],
    )
    rows = model.read_metrics(path, batch="202607120753")
    assert model.batch_start_ts("202607120753", rows) == 1783835237


def test_batch_start_ts_falls_back_to_batch_id_stamp_when_no_rows(
    tmp_path: Path,
) -> None:
    batch = "202607120753"
    expected = dt.datetime.strptime(batch, "%Y%m%d%H%M").timestamp()
    assert model.batch_start_ts(batch, []) == expected


def test_batch_start_ts_returns_none_when_neither_rows_nor_stamp_work() -> None:
    assert model.batch_start_ts("not-a-stamp", []) is None


# --- guards --------------------------------------------------------------------


def test_guards_returns_empty_list_for_clean_state(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "state.json",
        {"prd": "00061-x.md", "phase": "build", "cycle": 1, "rework_cap": 3},
    )
    state = model.read_state(path)
    assert model.guards(state) == []


def test_guards_reports_every_present_field_in_declared_order(
    tmp_path: Path,
) -> None:
    path = _write_json(
        tmp_path / "state.json",
        {
            "stall_reason": {"stalled": "no runnable prd"},
            "cap_pause_reason": {"cycle": 3, "cap": 3},
            "pause_reason": {"site": "review", "detail": "waiting on doubt"},
            "thrash_halt": True,
            "phase_guard": "review",
            "cycle": 4,
            "rework_cap": 3,
        },
    )
    state = model.read_state(path)
    assert model.guards(state) == [
        ("stall", "no runnable prd"),
        ("cap-pause", "at cap"),
        ("paused", "review: waiting on doubt"),
        ("thrash", "halted"),
        ("guard", "phase"),
    ]


def test_guards_reports_present_when_guard_field_is_malformed(
    tmp_path: Path,
) -> None:
    path = _write_json(
        tmp_path / "state.json",
        {
            "stall_reason": "some string, not a dict",
            "cap_pause_reason": [1, 2, 3],
            "pause_reason": {"site": "review"},
        },
    )
    state = model.read_state(path)
    assert model.guards(state) == [
        ("stall", "present"),
        ("cap-pause", "present"),
        ("paused", "present"),
    ]


def test_guards_emit_no_standalone_cycle_guard_even_at_cap(
    tmp_path: Path,
) -> None:
    """Row 1 always renders `cycle x/y`; a bare at-cap counter here would
    print the same fact twice, and the acted-on case is cap-pause."""
    path = _write_json(tmp_path / "state.json", {"cycle": 3, "rework_cap": 3})
    state = model.read_state(path)
    assert model.guards(state) == []


# --- prd_counts ------------------------------------------------------------


def test_prd_counts_counts_md_files_in_backlog_and_wip(tmp_path: Path) -> None:
    backlog = tmp_path / "dev" / "local" / "prds" / "backlog"
    wip = tmp_path / "dev" / "local" / "prds" / "wip"
    backlog.mkdir(parents=True)
    wip.mkdir(parents=True)
    (backlog / "00060-a.md").write_text("a")
    (backlog / "00061-b.md").write_text("b")
    (backlog / "notes.txt").write_text("not markdown")
    (wip / "00062-c.md").write_text("c")
    assert model.prd_counts(tmp_path) == (2, 1)


def test_prd_counts_zero_for_empty_dirs(tmp_path: Path) -> None:
    backlog = tmp_path / "dev" / "local" / "prds" / "backlog"
    wip = tmp_path / "dev" / "local" / "prds" / "wip"
    backlog.mkdir(parents=True)
    wip.mkdir(parents=True)
    assert model.prd_counts(tmp_path) == (0, 0)


def test_prd_counts_zero_for_missing_dirs(tmp_path: Path) -> None:
    assert model.prd_counts(tmp_path) == (0, 0)


# --- scan_session_cost -------------------------------------------------------


def test_scan_session_cost_takes_latest_result_event(tmp_path: Path) -> None:
    path = _write_lines(
        tmp_path / "last-session.log",
        [
            json.dumps({"type": "system", "subtype": "init"}),
            _result_event(1.11),
            json.dumps({"type": "assistant", "message": {"content": []}}),
            _result_event(2.22),
        ],
    )
    assert model.scan_session_cost(path) == 2.22


def test_scan_session_cost_zero_when_no_result_event(tmp_path: Path) -> None:
    path = _write_lines(
        tmp_path / "last-session.log",
        [
            json.dumps({"type": "system", "subtype": "init"}),
            json.dumps({"type": "assistant", "message": {"content": []}}),
        ],
    )
    assert model.scan_session_cost(path) == 0.0


def test_scan_session_cost_missing_file_returns_zero(tmp_path: Path) -> None:
    assert model.scan_session_cost(tmp_path / "does-not-exist.log") == 0.0


def test_scan_session_cost_ignores_result_event_before_tail_window(
    tmp_path: Path,
) -> None:
    lines = [_result_event(99.0)]
    lines.extend(
        json.dumps({"type": "system", "subtype": "noise", "i": i, "pad": "x" * 50})
        for i in range(3000)
    )
    path = _write_lines(tmp_path / "last-session.log", lines)
    assert model.scan_session_cost(path, tail_bytes=2000) == 0.0


# --- fmt_dur: the one surviving duration formatter --------------------------
#
# model.fmt_dur is the sole duration formatter in the package (relocated from
# panels.fmt_dur; discovery's near-duplicate _fmt_age is retired). Below 60s
# it renders bare seconds, never zero-padded minutes.


def test_fmt_dur_seconds_render_bare_with_no_minute_padding() -> None:
    assert model.fmt_dur(9) == "9s"


def test_fmt_dur_minutes_under_an_hour_zero_pad_seconds() -> None:
    assert model.fmt_dur(303) == "5m03s"


def test_fmt_dur_an_hour_or_more_zero_pads_minutes() -> None:
    assert model.fmt_dur(7620) == "2h07m"


# --- module-level interface pins --------------------------------------------


def test_signals_tuple_matches_spec() -> None:
    assert model.SIGNALS == ("continue", "paused", "done", "died")


def test_tail_bytes_constant_matches_spec() -> None:
    assert model.TAIL_BYTES == 512 * 1024


def test_usage_cap_mirrors_the_context_cap_hook() -> None:
    """model.USAGE_CAP is a display copy of the rotation threshold; if the
    hook's cap moves, the ctx gauge must move with it."""
    import autopilot_context_cap_hook

    assert model.USAGE_CAP == autopilot_context_cap_hook.USAGE_CAP


# --- current_task_name -------------------------------------------------------


def _state_with_tasks(tmp_path: Path, tasks: Any) -> model.LoopState:
    return model.read_state(
        _write_json(tmp_path / "state.json", {"phase": "build", "tasks": tasks})
    )


def test_current_task_name_prefers_in_progress_over_pending(tmp_path: Path) -> None:
    state = _state_with_tasks(
        tmp_path,
        [
            {"id": "t-1", "name": "Done thing", "status": "completed"},
            {"id": "t-2", "name": "Queued thing", "status": "pending"},
            {"id": "t-3", "name": "Running thing", "status": "in_progress"},
        ],
    )
    assert model.current_task_name(state) == "Running thing"


def test_current_task_name_falls_back_to_first_pending(tmp_path: Path) -> None:
    state = _state_with_tasks(
        tmp_path,
        [
            {"id": "t-1", "name": "Done thing", "status": "completed"},
            {"id": "t-2", "name": "Queued thing", "status": "pending"},
        ],
    )
    assert model.current_task_name(state) == "Queued thing"


def test_build_steps_done_infers_each_step_from_its_artifact(
    tmp_path: Path,
) -> None:
    path = _write_json(
        tmp_path / "state.json",
        {
            "phase": "build",
            "batch": {"id": "B1", "catchup_completed_at": "2026-07-18T08:00:00Z"},
            "design_doc": "dev/local/designs/x-design.md",
            "tasks_total": 2,
            "tasks_completed": 1,
            "tasks": [
                {"id": "t1", "name": "A", "status": "completed"},
                {"id": "t2", "name": "B", "status": "in_progress"},
            ],
        },
    )
    state = model.read_state(path)
    assert model.build_steps_done(state) == {
        "catchup": True,
        "design": True,
        "plan": True,
        "work": False,
    }


def test_build_steps_done_counts_skip_modes_as_done(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "state.json", {"catchup_mode": "skipped", "design_mode": "skip"}
    )
    steps = model.build_steps_done(model.read_state(path))
    assert steps == {"catchup": True, "design": True, "plan": False, "work": False}


def test_build_steps_done_work_requires_every_task_completed(
    tmp_path: Path,
) -> None:
    path = _write_json(
        tmp_path / "state.json",
        {
            "tasks_total": 2,
            "tasks_completed": 2,
            "tasks": [
                {"id": "t1", "status": "completed"},
                {"id": "t2", "status": "completed"},
            ],
        },
    )
    assert model.build_steps_done(model.read_state(path))["work"] is True


def test_tasks_by_lane_groups_by_status_and_defaults_junk_to_pending(
    tmp_path: Path,
) -> None:
    path = _write_json(
        tmp_path / "state.json",
        {
            "tasks": [
                {"id": "t1", "name": "A", "status": "completed"},
                {"id": "t2", "name": "B", "status": "in_progress"},
                {"id": "t3", "name": "C", "status": "pending"},
                {"id": "t4", "name": "D", "status": "cancelled"},
                "junk",
            ]
        },
    )
    lanes = model.tasks_by_lane(model.read_state(path))
    assert [t["id"] for t in lanes["completed"]] == ["t1"]
    assert [t["id"] for t in lanes["in_progress"]] == ["t2"]
    assert [t["id"] for t in lanes["pending"]] == ["t3", "t4"]


def test_tasks_by_lane_empty_lanes_when_tasks_missing(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "state.json", {"phase": "build"})
    lanes = model.tasks_by_lane(model.read_state(path))
    assert lanes == {"in_progress": [], "pending": [], "completed": []}


def test_current_task_name_empty_when_tasks_absent_or_malformed(
    tmp_path: Path,
) -> None:
    assert model.current_task_name(_state_with_tasks(tmp_path, None)) == ""
    assert model.current_task_name(_state_with_tasks(tmp_path, "not-a-list")) == ""
    assert (
        model.current_task_name(
            _state_with_tasks(tmp_path, [{"status": "in_progress", "name": 7}, "junk"])
        )
        == ""
    )
