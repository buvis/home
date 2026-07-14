"""Tests for tracon/stream.py — the live session-log follower and event tracker."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from rich.text import Text

from tracon import stream


# --- fixtures grounded in the real captured event shapes --------------------
# (see /tmp/tracon-event-fixtures.jsonl; field names/values below mirror it)


def _real_assistant_event() -> dict[str, Any]:
    """The real assistant/usage shape captured from a live headless session."""
    return {
        "type": "assistant",
        "parent_tool_use_id": None,
        "message": {
            "id": "msg_011Cd1SM4ENG5oza6W5Ag3bu",
            "model": "claude-opus-4-8",
            "usage": {
                "input_tokens": 2,
                "cache_creation_input_tokens": 42117,
                "cache_read_input_tokens": 17592,
                "output_tokens": 1,
            },
        },
    }


def _assistant_event(
    message_id: str,
    *,
    input_tokens: int,
    cache_read_input_tokens: int,
    cache_creation_input_tokens: int,
    output_tokens: int,
    parent_tool_use_id: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "assistant",
        "parent_tool_use_id": parent_tool_use_id,
        "message": {
            "id": message_id,
            "usage": {
                "input_tokens": input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "output_tokens": output_tokens,
            },
        },
    }


def _system_init_event(**overrides: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": "system",
        "subtype": "init",
        "model": "claude-opus-4-8",
        "claude_code_version": "2.1.208",
        "permissionMode": "auto",
    }
    event.update(overrides)
    return event


def _rate_limit_event() -> dict[str, Any]:
    return {
        "type": "rate_limit_event",
        "rate_limit_info": {
            "status": "allowed_warning",
            "resetsAt": 1784451600,
            "rateLimitType": "seven_day",
            "utilization": 0.56,
            "isUsingOverage": False,
        },
        "uuid": "035a2650-c403-4a6a-8628-889250c21e55",
        "session_id": "f538d9ca-0153-4873-88e5-f8977593f111",
    }


def _thinking_tokens_event() -> dict[str, Any]:
    return {
        "type": "system",
        "subtype": "thinking_tokens",
        "estimated_tokens": 50,
        "estimated_tokens_delta": 50,
        "uuid": "b621f567-1587-411f-a2ae-b28897a25873",
        "session_id": "f538d9ca-0153-4873-88e5-f8977593f111",
    }


def _user_tool_result_event(tool_use_id: str) -> dict[str, Any]:
    return {
        "type": "user",
        "parent_tool_use_id": None,
        "message": {"content": [{"type": "tool_result", "tool_use_id": tool_use_id}]},
    }


def _task_started(
    task_id: str,
    tool_use_id: str,
    description: str,
    task_type: str,
    *,
    subagent_type: str | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": "system",
        "subtype": "task_started",
        "task_id": task_id,
        "tool_use_id": tool_use_id,
        "description": description,
        "task_type": task_type,
    }
    if subagent_type is not None:
        event["subagent_type"] = subagent_type
    return event


def _task_progress(task_id: str, last_tool_name: str, tool_uses: int) -> dict[str, Any]:
    return {
        "type": "system",
        "subtype": "task_progress",
        "task_id": task_id,
        "last_tool_name": last_tool_name,
        "usage": {"tool_uses": tool_uses},
    }


def _task_updated(task_id: str, status: str) -> dict[str, Any]:
    return {
        "type": "system",
        "subtype": "task_updated",
        "task_id": task_id,
        "patch": {"status": status},
    }


def _task_notification(task_id: str, status: str) -> dict[str, Any]:
    return {
        "type": "system",
        "subtype": "task_notification",
        "task_id": task_id,
        "status": status,
    }


def _background_tasks_changed(tasks: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "type": "system",
        "subtype": "background_tasks_changed",
        "tasks": tasks,
    }


# --- LogTail: bounded first attach -------------------------------------------


def test_log_tail_first_attach_replays_whole_small_file(tmp_path: Path) -> None:
    path = tmp_path / "last-session.log"
    path.write_text("A\nB\nC\n")
    log_tail = stream.LogTail(path, tail_bytes=1_000_000)
    assert log_tail.session_start is None
    lines, reset = log_tail.read_new()
    assert lines == ["A", "B", "C"]
    assert reset is False
    assert log_tail.session_start is None


def test_log_tail_first_attach_bounded_window_discards_partial_first_line(
    tmp_path: Path,
) -> None:
    numbered_lines = [f"L{i:04d}" for i in range(200)]
    content = "\n".join(numbered_lines) + "\n"
    path = tmp_path / "last-session.log"
    path.write_text(content)

    # size=1200, tail_bytes=27 -> offset=1173 lands 3 bytes into line "L0195",
    # which must be discarded as a partial fragment, never replayed as a line.
    log_tail = stream.LogTail(path, tail_bytes=27)
    lines, reset = log_tail.read_new()

    assert reset is False
    assert lines == ["L0196", "L0197", "L0198", "L0199"]
    assert log_tail.session_start is None


# --- LogTail: session_reset triggers -----------------------------------------


def test_log_tail_in_place_truncation_triggers_session_reset(tmp_path: Path) -> None:
    path = tmp_path / "last-session.log"
    path.write_text("A\nB\nC\n")
    log_tail = stream.LogTail(path, tail_bytes=1_000_000)
    lines1, reset1 = log_tail.read_new()
    assert lines1 == ["A", "B", "C"]
    assert reset1 is False
    assert log_tail.session_start is None

    path.write_text("X\nY\n")  # tee truncates the same inode in place for a fresh session
    lines2, reset2 = log_tail.read_new()
    assert lines2 == ["X", "Y"]
    assert reset2 is True
    assert log_tail.session_start is not None


def test_log_tail_inode_swap_triggers_session_reset(tmp_path: Path) -> None:
    path = tmp_path / "last-session.log"
    path.write_text("A\nB\n")
    log_tail = stream.LogTail(path, tail_bytes=1_000_000)
    lines1, reset1 = log_tail.read_new()
    assert lines1 == ["A", "B"]
    assert reset1 is False

    replacement = tmp_path / "last-session.log.new"
    replacement.write_text("Q\nR\nS\n")
    replacement.replace(path)  # atomic rename swaps the inode, unlike in-place truncation

    lines2, reset2 = log_tail.read_new()
    assert lines2 == ["Q", "R", "S"]
    assert reset2 is True


def test_log_tail_file_disappearance_triggers_session_reset_without_raising(
    tmp_path: Path,
) -> None:
    path = tmp_path / "last-session.log"
    path.write_text("A\nB\n")
    log_tail = stream.LogTail(path, tail_bytes=1_000_000)
    lines1, _ = log_tail.read_new()
    assert lines1 == ["A", "B"]

    path.unlink()
    lines2, reset2 = log_tail.read_new()
    assert lines2 == []
    assert reset2 is True


# --- LogTail: partial trailing line buffering --------------------------------


def test_log_tail_partial_trailing_line_buffered_until_completed(tmp_path: Path) -> None:
    path = tmp_path / "last-session.log"
    path.write_text("A\n")
    log_tail = stream.LogTail(path, tail_bytes=1_000_000)
    lines1, _ = log_tail.read_new()
    assert lines1 == ["A"]

    with path.open("a") as f:
        f.write("partial-no-newline-yet")
    lines2, _ = log_tail.read_new()
    assert lines2 == []

    with path.open("a") as f:
        f.write(" now-complete\nC\n")
    lines3, _ = log_tail.read_new()
    assert lines3 == ["partial-no-newline-yet now-complete", "C"]


# --- SessionUsage: token totals dedupe and aggregation -----------------------


def test_totals_dedupe_uses_real_captured_assistant_event_shape() -> None:
    usage = stream.SessionUsage()
    event = _real_assistant_event()
    usage.feed(event)
    usage.feed(event)  # same message.id fed twice must count once
    assert usage.totals() == (2, 42117 + 17592, 1)


def test_totals_sums_tokens_across_distinct_message_ids() -> None:
    usage = stream.SessionUsage()
    usage.feed(
        _assistant_event(
            "msg_1",
            input_tokens=10,
            cache_read_input_tokens=5,
            cache_creation_input_tokens=0,
            output_tokens=3,
        )
    )
    usage.feed(
        _assistant_event(
            "msg_2",
            input_tokens=1,
            cache_read_input_tokens=2,
            cache_creation_input_tokens=4,
            output_tokens=7,
        )
    )
    assert usage.totals() == (11, 11, 10)


def test_context_size_reflects_only_the_last_fed_message() -> None:
    usage = stream.SessionUsage()
    usage.feed(
        _assistant_event(
            "msg_1",
            input_tokens=100,
            cache_read_input_tokens=50,
            cache_creation_input_tokens=25,
            output_tokens=1,
        )
    )
    usage.feed(
        _assistant_event(
            "msg_2",
            input_tokens=2,
            cache_read_input_tokens=3,
            cache_creation_input_tokens=4,
            output_tokens=1,
        )
    )
    assert usage.context_size() == 2 + 3 + 4


# --- SessionUsage: cost and model --------------------------------------------


def test_session_cost_zero_until_first_result_event() -> None:
    usage = stream.SessionUsage()
    usage.feed(_system_init_event())
    usage.feed(_real_assistant_event())
    assert usage.session_cost == 0.0


def test_session_cost_latest_result_event_wins_over_earlier_ones() -> None:
    usage = stream.SessionUsage()
    usage.feed({"type": "result", "subtype": "success", "total_cost_usd": 1.11})
    usage.feed({"type": "result", "subtype": "success", "total_cost_usd": 2.22})
    assert usage.session_cost == 2.22


def test_model_comes_from_system_init_event() -> None:
    usage = stream.SessionUsage()
    usage.feed(_system_init_event(model="claude-sonnet-5"))
    assert usage.model == "claude-sonnet-5"


def test_session_usage_reset_clears_totals_cost_and_model() -> None:
    usage = stream.SessionUsage()
    usage.feed(_system_init_event())
    usage.feed(_real_assistant_event())
    usage.feed({"type": "result", "subtype": "success", "total_cost_usd": 9.99})
    usage.reset()
    assert usage.totals() == (0, 0, 0)
    assert usage.session_cost == 0.0
    assert usage.model == ""


# --- AgentTracker: task_started / task_progress ------------------------------


def test_task_started_local_agent_registers_live_lane_with_defaults() -> None:
    tracker = stream.AgentTracker()
    description = "Fix the flaky test suite across three modules"
    tracker.feed(
        _task_started("t1", "tool_1", description, "local_agent", subagent_type="general-purpose")
    )
    lanes = tracker.live_lanes()
    assert len(lanes) == 1
    lane = lanes[0]
    assert lane.task_id == "t1"
    assert lane.tool_use_id == "tool_1"
    assert lane.kind == "local_agent"
    assert lane.label == description[:20]
    assert lane.color in stream.LANE_COLORS
    assert lane.last == ""
    assert lane.n == 0
    assert lane.done is False
    assert tracker.live_tasks() == []


def test_task_progress_updates_last_tool_name_and_tool_use_count() -> None:
    tracker = stream.AgentTracker()
    tracker.feed(_task_started("t1", "tool_1", "desc", "local_agent"))
    tracker.feed(_task_progress("t1", "Edit", 4))
    lane = tracker.live_lanes()[0]
    assert lane.last == "Edit"
    assert lane.n == 4


# --- AgentTracker: local_bash background tasks -------------------------------


def test_task_started_local_bash_registers_as_background_task_not_agent_lane() -> None:
    tracker = stream.AgentTracker()
    tracker.feed(_task_started("t2", "tool_2", "codex review", "local_bash"))
    assert tracker.live_lanes() == []
    tasks = tracker.live_tasks()
    assert len(tasks) == 1
    assert tasks[0].task_id == "t2"
    assert tasks[0].kind == "local_bash"
    assert tasks[0].done is False


def test_background_tasks_changed_empty_list_retires_running_task() -> None:
    tracker = stream.AgentTracker()
    tracker.feed(_task_started("t2", "tool_2", "codex review", "local_bash"))
    assert len(tracker.live_tasks()) == 1
    tracker.feed(_background_tasks_changed([]))
    assert tracker.live_tasks() == []


def test_background_tasks_changed_membership_retires_absent_keeps_present() -> None:
    tracker = stream.AgentTracker()
    tracker.feed(_task_started("t2", "tool_2", "codex review", "local_bash"))
    tracker.feed(_task_started("t3", "tool_3", "gemini review", "local_bash"))
    tracker.feed(
        _background_tasks_changed(
            [{"task_id": "t3", "task_type": "local_bash", "description": "gemini review"}]
        )
    )
    remaining_ids = {lane.task_id for lane in tracker.live_tasks()}
    assert remaining_ids == {"t3"}


def test_background_tasks_changed_registers_a_task_id_not_seen_before() -> None:
    tracker = stream.AgentTracker()
    tracker.feed(
        _background_tasks_changed(
            [{"task_id": "t9", "task_type": "local_bash", "description": "unseen reviewer"}]
        )
    )
    live = tracker.live_tasks()
    assert len(live) == 1
    assert live[0].task_id == "t9"
    assert live[0].kind == "local_bash"


# --- AgentTracker: retirement via task_updated / task_notification ----------


def test_task_updated_terminal_status_retires_lane() -> None:
    tracker = stream.AgentTracker()
    tracker.feed(_task_started("t1", "tool_1", "desc", "local_agent"))
    tracker.feed(_task_updated("t1", "completed"))
    assert tracker.live_lanes() == []


def test_task_notification_terminal_status_retires_lane() -> None:
    tracker = stream.AgentTracker()
    tracker.feed(_task_started("t1", "tool_1", "desc", "local_agent"))
    tracker.feed(_task_notification("t1", "failed"))
    assert tracker.live_lanes() == []


def test_user_event_real_capture_shape_retires_matching_lane() -> None:
    tracker = stream.AgentTracker()
    real_tool_use_id = "toolu_01QdpjgEiiyhe78B28venMV2"
    tracker.feed(_task_started("t1", real_tool_use_id, "desc", "local_agent"))
    assert len(tracker.live_lanes()) == 1
    tracker.feed(_user_tool_result_event(real_tool_use_id))
    assert tracker.live_lanes() == []


# --- AgentTracker: auto-registration and tag_for -----------------------------


def test_unknown_parent_tool_use_id_auto_registers_agent_lane() -> None:
    tracker = stream.AgentTracker()
    tracker.feed(
        _assistant_event(
            "msg_a",
            input_tokens=1,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
            output_tokens=1,
            parent_tool_use_id="tool_unknown",
        )
    )
    lanes = tracker.live_lanes()
    assert len(lanes) == 1
    assert lanes[0].kind == "local_agent"
    assert re.fullmatch(r"agent\d+", lanes[0].label)

    tag = tracker.tag_for(
        _assistant_event(
            "msg_b",
            input_tokens=1,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
            output_tokens=1,
            parent_tool_use_id="tool_unknown",
        )
    )
    assert tag == (lanes[0].label, lanes[0].color)


def test_tag_for_none_event_returns_none() -> None:
    tracker = stream.AgentTracker()
    assert tracker.tag_for(None) is None


def test_tag_for_unmapped_parent_tool_use_id_returns_none() -> None:
    tracker = stream.AgentTracker()
    tracker.feed(_task_started("t1", "tool_1", "desc", "local_agent"))
    event = _assistant_event(
        "msg_c",
        input_tokens=1,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
        output_tokens=1,
        parent_tool_use_id="some-other-tool-id",
    )
    assert tracker.tag_for(event) is None


# --- AgentTracker: unknown events are ignored, never crash -------------------


def test_rate_limit_event_type_is_ignored_no_lane_no_crash() -> None:
    tracker = stream.AgentTracker()
    tracker.feed(_rate_limit_event())
    assert tracker.live_lanes() == []
    assert tracker.live_tasks() == []


def test_unknown_system_subtype_is_ignored_no_lane_no_crash() -> None:
    tracker = stream.AgentTracker()
    tracker.feed(_thinking_tokens_event())
    assert tracker.live_lanes() == []
    assert tracker.live_tasks() == []


def test_agent_tracker_reset_clears_all_lanes() -> None:
    tracker = stream.AgentTracker()
    tracker.feed(_task_started("t1", "tool_1", "desc", "local_agent"))
    tracker.feed(_task_started("t2", "tool_2", "bash desc", "local_bash"))
    tracker.reset()
    assert tracker.live_lanes() == []
    assert tracker.live_tasks() == []


# --- AgentTracker: parallel-reviewer attribution (pinned product metric) ----


def test_three_concurrent_reviewers_produce_three_distinct_live_entries_and_colors() -> None:
    tracker = stream.AgentTracker()
    tracker.feed(_task_started("bash-1", "tool_bash_1", "codex doubt review", "local_bash"))
    tracker.feed(_task_started("bash-2", "tool_bash_2", "gemini blind review", "local_bash"))
    tracker.feed(_task_started("agent-1", "tool_agent_1", "consensus reviewer", "local_agent"))

    live_tasks = tracker.live_tasks()
    live_lanes = tracker.live_lanes()
    all_live = live_tasks + live_lanes

    assert len(live_tasks) == 2
    assert len(live_lanes) == 1
    assert len(all_live) == 3
    assert len({lane.task_id for lane in all_live}) == 3
    colors = {lane.color for lane in all_live}
    assert len(colors) == 3
    assert colors <= set(stream.LANE_COLORS)


# --- render_line: renders, and fails open on bad input -----------------------


def test_render_line_valid_system_init_event_renders_transformed_summary() -> None:
    event = _system_init_event()
    raw = json.dumps(event)
    result = stream.render_line(raw, event)
    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], Text)
    plain = result[0].plain
    assert "claude-opus-4-8" in plain
    assert "2.1.208" in plain
    assert plain != raw


def test_render_line_none_event_passes_through_raw() -> None:
    raw = '{"type": "assistant", "message": {"content": [{"type": "text", "text": "hello"}]}}'
    result = stream.render_line(raw, None)
    assert len(result) == 1
    assert isinstance(result[0], Text)
    assert result[0].plain == raw


def test_render_line_unparseable_raw_line_passes_through_when_event_is_none() -> None:
    raw = "not json at all {{{ garbage output from a wrapper banner"
    result = stream.render_line(raw, None)
    assert len(result) == 1
    assert result[0].plain == raw


def test_render_line_falls_back_to_raw_when_delegate_raises() -> None:
    # render_stream.render()'s _render_assistant does
    # (event.get("message") or {}).get("content"); a string "message" value
    # makes that .get(...) raise AttributeError -- render_line must catch it.
    event = {"type": "assistant", "parent_tool_use_id": None, "message": "not-a-dict"}
    raw = json.dumps(event)
    result = stream.render_line(raw, event)
    assert len(result) == 1
    assert isinstance(result[0], Text)
    assert result[0].plain == raw


# --- module-level interface pins --------------------------------------------


def test_lane_colors_tuple_matches_spec() -> None:
    assert stream.LANE_COLORS == ("magenta", "blue", "green", "yellow", "red", "bright_cyan")
