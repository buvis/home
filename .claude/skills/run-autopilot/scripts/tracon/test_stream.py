"""Tests for tracon/stream.py — the live session-log follower and event tracker."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import pytest
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


def _task_progress(
    task_id: str,
    last_tool_name: str,
    tool_uses: int,
    *,
    description: str = "",
    total_tokens: int = 0,
    duration_ms: int = 0,
) -> dict[str, Any]:
    return {
        "type": "system",
        "subtype": "task_progress",
        "task_id": task_id,
        "description": description,
        "last_tool_name": last_tool_name,
        "usage": {
            "tool_uses": tool_uses,
            "total_tokens": total_tokens,
            "duration_ms": duration_ms,
        },
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


def _bg_bash_tool_use_event(tool_use_id: str, command: str) -> dict[str, Any]:
    """The assistant event carrying a backgrounded Bash tool_use block, as the
    stream emits it right before the matching task_started."""
    return {
        "type": "assistant",
        "parent_tool_use_id": None,
        "message": {
            "id": "msg_bash_launch",
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": "Bash",
                    "input": {"command": command, "run_in_background": True},
                }
            ],
        },
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


def test_log_tail_file_appearing_while_watched_sets_session_start(tmp_path: Path) -> None:
    # We were already polling (log file did not exist yet) when the session's log
    # appeared and started receiving lines -- we watched it begin, so session_start
    # must be set, unlike attaching to a log that already had content on first look.
    path = tmp_path / "last-session.log"
    log_tail = stream.LogTail(path, tail_bytes=1_000_000)
    assert log_tail.session_start is None

    lines1, reset1 = log_tail.read_new()  # path does not exist yet
    assert lines1 == []
    assert log_tail.session_start is None

    path.write_text("A\nB\n")
    lines2, reset2 = log_tail.read_new()

    assert lines2 == ["A", "B"]
    assert log_tail.session_start is not None
    assert abs(log_tail.session_start - time.time()) < 5


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
    # Header contract: tokens up(input + cache-creation) cached(cache-read) out(output).
    # cache_creation_input_tokens belongs in the "up" bucket, not "cached" -- it is new
    # context being written to the cache, not context served from it. The usage
    # snapshot's output_tokens (1 here) is a per-block placeholder and must NOT
    # surface as out — a content-less event contributes zero output.
    usage = stream.SessionUsage()
    event = _real_assistant_event()
    usage.feed(event)
    usage.feed(event)  # same message.id fed twice must count once
    assert usage.totals() == (2 + 42117, 17592, 0)


def test_totals_up_bucket_includes_cache_creation_not_cache_read() -> None:
    # input_tokens, cache_creation_input_tokens, and cache_read_input_tokens are all
    # distinct and non-zero here so the three buckets cannot be confused with each other.
    usage = stream.SessionUsage()
    usage.feed(
        _assistant_event(
            "msg_1",
            input_tokens=100,
            cache_read_input_tokens=20,
            cache_creation_input_tokens=7,
            output_tokens=3,
        )
    )
    up, cached, out = usage.totals()
    assert up == 100 + 7  # input_tokens + cache_creation_input_tokens
    assert cached == 20  # cache_read_input_tokens only
    assert out == 0  # snapshot output_tokens is a placeholder, never counted


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
    # up = (10+0) + (1+4) = 15; cached = 5 + 2 = 7; out = 0 (no content blocks)
    assert usage.totals() == (15, 7, 0)


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


# --- SessionUsage: output estimate anchored by result events ------------------


def _content_event(mid: str, block: dict[str, Any]) -> dict[str, Any]:
    event = _assistant_event(
        mid,
        input_tokens=1,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
        output_tokens=2,  # per-block snapshot placeholder — must be ignored
    )
    event["message"]["content"] = [block]
    return event


def test_out_estimates_from_emitted_chars_not_usage_snapshots() -> None:
    # Regression (out ↓145 bug): assistant usage.output_tokens is a per-block
    # snapshot; live out must come from emitted chars (~4 chars/token) instead.
    usage = stream.SessionUsage()
    usage.feed(_content_event("msg_1", {"type": "thinking", "thinking": "x" * 200}))
    usage.feed(_content_event("msg_1", {"type": "text", "text": "y" * 200}))
    _, _, out = usage.totals()
    assert out == 400 // 4
    assert usage.out_estimated is True


def test_out_counts_tool_use_input_chars() -> None:
    usage = stream.SessionUsage()
    usage.feed(_content_event("msg_1", {"type": "tool_use", "input": {"cmd": "a" * 78}}))
    _, _, out = usage.totals()
    assert out > 0


def test_result_event_anchors_exact_out_and_clears_estimate() -> None:
    usage = stream.SessionUsage()
    usage.feed(_content_event("msg_1", {"type": "text", "text": "x" * 400}))
    usage.feed({"type": "result", "subtype": "success", "usage": {"output_tokens": 5000}})
    assert usage.totals()[2] == 5000  # exact, estimate absorbed
    assert usage.out_estimated is False
    usage.feed(_content_event("msg_2", {"type": "text", "text": "y" * 400}))
    assert usage.totals()[2] == 5000 + 100  # estimating again past the anchor
    assert usage.out_estimated is True


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
    usage.feed(
        {"type": "result", "subtype": "success", "total_cost_usd": 9.99, "usage": {"output_tokens": 321}}
    )
    usage.reset()
    assert usage.totals() == (0, 0, 0)
    assert usage.session_cost == 0.0
    assert usage.model == ""
    assert usage.out_estimated is False


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


def test_task_progress_updates_activity_tokens_and_duration() -> None:
    """task_progress carries the live activity line and usage counters the
    agents detail screen shows; real captured shape has description plus
    usage.total_tokens / duration_ms alongside tool_uses."""
    tracker = stream.AgentTracker()
    tracker.feed(_task_started("t1", "tool_1", "desc", "local_agent"))
    tracker.feed(
        _task_progress(
            "t1",
            "Read",
            2,
            description="Reading review-prd-00067c1.md",
            total_tokens=36316,
            duration_ms=5792,
        )
    )
    lane = tracker.live_lanes()[0]
    assert lane.activity == "Reading review-prd-00067c1.md"
    assert lane.tokens == 36316
    assert lane.dur_ms == 5792


def test_bash_lane_captures_out_path_from_backgrounded_launch_command() -> None:
    """The launching Bash tool_use block is the only place the runner's -o
    output file appears; the lane must pick it up when task_started arrives
    with the same tool_use_id (real runner shape, quoted path)."""
    tracker = stream.AgentTracker()
    tracker.feed(
        _bg_bash_tool_use_event(
            "toolu_bob",
            'codex-run.sh -f "/tmp/bob prompt.md" -o "/tmp/bob output.txt" --emit-thread-id x',
        )
    )
    tracker.feed(_task_started("b1", "toolu_bob", "Bob (codex) review", "local_bash"))
    lane = tracker.live_tasks()[0]
    assert lane.out_path == "/tmp/bob output.txt"
    assert lane.started > 0


def test_bash_lane_without_output_flag_gets_empty_out_path() -> None:
    tracker = stream.AgentTracker()
    tracker.feed(_bg_bash_tool_use_event("toolu_q", "qwen-run.sh --preflight --approved-only"))
    tracker.feed(_task_started("q1", "toolu_q", "Qwen preflight probe", "local_bash"))
    assert tracker.live_tasks()[0].out_path == ""


def test_unparseable_launch_command_fails_open_to_empty_out_path() -> None:
    tracker = stream.AgentTracker()
    tracker.feed(_bg_bash_tool_use_event("toolu_x", 'runner.sh -o "/tmp/unbalanced'))
    tracker.feed(_task_started("x1", "toolu_x", "broken quoting", "local_bash"))
    assert tracker.live_tasks()[0].out_path == ""


def test_task_started_stores_full_description_and_agent_type() -> None:
    tracker = stream.AgentTracker()
    description = "Alice reviews work vs PRD and the design doc in detail"
    tracker.feed(
        _task_started("t1", "tool_1", description, "local_agent", subagent_type="general-purpose")
    )
    lane = tracker.live_lanes()[0]
    assert lane.desc == description  # untrimmed, unlike the 20-char label
    assert lane.agent_type == "general-purpose"


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


def test_background_tasks_changed_missing_status_key_fails_open_to_running() -> None:
    """Membership in the background_tasks_changed running set already means
    the task is live: an entry with no "status" key must fail open to
    "running", not leave lane.status empty (which panels.py would then render
    as a dangling `label ▷` marker with nothing after it)."""
    tracker = stream.AgentTracker()
    tracker.feed(
        _background_tasks_changed(
            [{"task_id": "t9", "task_type": "local_bash", "description": "no status field"}]
        )
    )
    lane = tracker.live_tasks()[0]
    assert lane.status == "running"


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


@pytest.mark.parametrize("status", ["in_progress", "running", "queued"])
def test_non_terminal_status_via_task_updated_keeps_lane_live(status: str) -> None:
    tracker = stream.AgentTracker()
    tracker.feed(_task_started("t1", "tool_1", "desc", "local_agent"))
    tracker.feed(_task_updated("t1", status))
    lanes = tracker.live_lanes()
    assert len(lanes) == 1
    assert lanes[0].task_id == "t1"
    assert lanes[0].done is False


@pytest.mark.parametrize("status", ["in_progress", "running", "queued"])
def test_non_terminal_status_via_task_notification_keeps_lane_live(status: str) -> None:
    tracker = stream.AgentTracker()
    tracker.feed(_task_started("t1", "tool_1", "desc", "local_agent"))
    tracker.feed(_task_notification("t1", status))
    lanes = tracker.live_lanes()
    assert len(lanes) == 1
    assert lanes[0].task_id == "t1"
    assert lanes[0].done is False


@pytest.mark.parametrize("status", ["completed", "failed", "stopped", "killed"])
def test_terminal_status_via_task_updated_retires_lane(status: str) -> None:
    tracker = stream.AgentTracker()
    tracker.feed(_task_started("t1", "tool_1", "desc", "local_agent"))
    tracker.feed(_task_updated("t1", status))
    assert tracker.live_lanes() == []


@pytest.mark.parametrize("status", ["completed", "failed", "stopped", "killed"])
def test_terminal_status_via_task_notification_retires_lane(status: str) -> None:
    tracker = stream.AgentTracker()
    tracker.feed(_task_started("t1", "tool_1", "desc", "local_agent"))
    tracker.feed(_task_notification("t1", status))
    assert tracker.live_lanes() == []


def test_launch_ack_tool_result_does_not_retire_task_started_agent_lane() -> None:
    """Background dispatch (parallel reviewers) acks the Agent tool_use
    IMMEDIATELY while the subagent keeps running. Captured sequence from a
    live review phase: background_tasks_changed listing the task, then
    task_started, then the user tool_result ack two lines later — followed by
    minutes of task_progress. The lane must survive the ack and retire only
    on a terminal task event, or the header never shows a running agent."""
    tracker = stream.AgentTracker()
    task_id = "a06358339df251993"
    tool_use_id = "toolu_018MmRop1BLEQ7stuTiX8U2c"
    tracker.feed(
        _background_tasks_changed(
            [
                {
                    "task_id": task_id,
                    "task_type": "local_agent",
                    "description": "Alice reviews work vs PRD",
                }
            ]
        )
    )
    tracker.feed(
        _task_started(
            task_id,
            tool_use_id,
            "Alice reviews work vs PRD",
            "local_agent",
            subagent_type="general-purpose",
        )
    )
    tracker.feed(_user_tool_result_event(tool_use_id))  # launch ack, not completion
    assert len(tracker.live_lanes()) == 1
    tracker.feed(_task_progress(task_id, "Read", 3))
    assert len(tracker.live_lanes()) == 1
    tracker.feed(_task_notification(task_id, "completed"))
    assert tracker.live_lanes() == []


def test_launch_ack_tool_result_does_not_retire_background_bash_lane() -> None:
    tracker = stream.AgentTracker()
    tracker.feed(
        _task_started(
            "b5pzlnyg5",
            "toolu_01GBXQkKxznMREg9spEUAbq9",
            "Bob (codex) doubt-lens review, background",
            "local_bash",
        )
    )
    tracker.feed(_user_tool_result_event("toolu_01GBXQkKxznMREg9spEUAbq9"))
    assert len(tracker.live_tasks()) == 1
    tracker.feed(_task_notification("b5pzlnyg5", "completed"))
    assert tracker.live_tasks() == []


def test_tool_result_still_retires_fallback_lane_registered_from_parent_id() -> None:
    """A lane known only from parent_tool_use_id attribution (no task
    lifecycle events — the synchronous-agent path) ends with its tool_result;
    that is the only completion signal such a lane will ever get."""
    tracker = stream.AgentTracker()
    tracker.feed(
        _assistant_event(
            "msg_a",
            input_tokens=1,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
            output_tokens=1,
            parent_tool_use_id="toolu_sync_agent",
        )
    )
    assert len(tracker.live_lanes()) == 1
    tracker.feed(_user_tool_result_event("toolu_sync_agent"))
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
