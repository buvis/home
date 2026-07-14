"""Tests for render_stream.py — the loop-terminal stream-json renderer."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT = Path(__file__).with_name("render_stream.py")


def _run(lines: list[str]) -> str:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    return result.stdout


def _assistant(blocks: list[dict[str, Any]], parent: str | None = None) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "parent_tool_use_id": parent,
            "message": {"content": blocks},
        }
    )


def test_tool_use_shows_name_and_description() -> None:
    out = _run(
        [
            _assistant(
                [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "cargo test", "description": "Run tests"},
                    }
                ]
            )
        ]
    )
    assert "⚒ Bash · Run tests" in out


def test_tool_use_falls_back_to_command_without_description() -> None:
    out = _run(
        [
            _assistant(
                [{"type": "tool_use", "name": "Bash", "input": {"command": "ls -la"}}]
            )
        ]
    )
    assert "⚒ Bash · ls -la" in out


def test_assistant_text_renders_and_thinking_is_dropped() -> None:
    out = _run(
        [
            _assistant(
                [
                    {"type": "thinking", "thinking": "secret reasoning"},
                    {"type": "text", "text": "Phase build: task 3 of 7"},
                ]
            )
        ]
    )
    assert "Phase build: task 3 of 7" in out
    assert "secret reasoning" not in out


def test_subagent_shows_tools_but_not_prose() -> None:
    out = _run(
        [
            _assistant(
                [
                    {"type": "text", "text": "subagent narration"},
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "a.rs"}},
                ],
                parent="toolu_01",
            )
        ]
    )
    assert "↳ Edit · a.rs" in out
    assert "subagent narration" not in out


def test_tool_result_error_surfaces_and_success_is_silent() -> None:
    ok = json.dumps(
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "is_error": False, "content": "fine"}
                ]
            },
        }
    )
    bad = json.dumps(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "is_error": True,
                        "content": [{"type": "text", "text": "exit 1: boom"}],
                    }
                ]
            },
        }
    )
    out = _run([ok, bad])
    assert "fine" not in out
    assert "✗ exit 1: boom" in out


def test_result_event_shows_cost_turns_and_denials() -> None:
    out = _run(
        [
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "duration_ms": 93000,
                    "num_turns": 12,
                    "total_cost_usd": 1.2345,
                    "usage": {"output_tokens": 4567},
                    "permission_denials": [{"tool_name": "Bash"}],
                }
            )
        ]
    )
    assert "■ success · 93s · 12 turns · $1.23 · 4567 tok out" in out
    assert "⚠ 1 permission denial(s)" in out


def test_noise_events_are_dropped() -> None:
    out = _run(
        [
            json.dumps({"type": "system", "subtype": "hook_started", "hook_name": "x"}),
            json.dumps({"type": "system", "subtype": "thinking_tokens"}),
            json.dumps({"type": "rate_limit_event", "rate_limit_info": {}}),
        ]
    )
    assert out == ""


def test_init_event_shows_model_and_mode() -> None:
    out = _run(
        [
            json.dumps(
                {
                    "type": "system",
                    "subtype": "init",
                    "claude_code_version": "2.1.199",
                    "model": "claude-opus-4-8",
                    "permissionMode": "auto",
                }
            )
        ]
    )
    assert "▶ claude 2.1.199 · claude-opus-4-8 · auto" in out


def test_non_json_lines_pass_through_verbatim() -> None:
    out = _run(["plain stderr line", "{not valid json"])
    assert "plain stderr line\n" in out
    assert "{not valid json\n" in out


def _task_spawn(block_id: str, description: str) -> str:
    return _assistant(
        [
            {
                "type": "tool_use",
                "id": block_id,
                "name": "Task",
                "input": {"description": description, "prompt": "go"},
            }
        ]
    )


def test_subagent_lane_label_from_task_description() -> None:
    out = _run(
        [
            _task_spawn("toolu_A", "review bugs"),
            _assistant(
                [{"type": "tool_use", "name": "Edit", "input": {"file_path": "a.rs"}}],
                parent="toolu_A",
            ),
        ]
    )
    assert "⟨review bugs⟩" in out
    assert "↳ Edit · a.rs" in out


def test_unknown_parent_falls_back_to_agent_n() -> None:
    out = _run(
        [
            _assistant(
                [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}],
                parent="toolu_unseen",
            )
        ]
    )
    assert "⟨agent1⟩" in out


def test_lanes_are_distinct_and_stable_across_events() -> None:
    out = _run(
        [
            _task_spawn("toolu_A", "lane alpha"),
            _task_spawn("toolu_B", "lane beta"),
            _assistant(
                [{"type": "tool_use", "name": "Read", "input": {"file_path": "x"}}],
                parent="toolu_A",
            ),
            _assistant(
                [{"type": "tool_use", "name": "Read", "input": {"file_path": "y"}}],
                parent="toolu_B",
            ),
            _assistant(
                [{"type": "tool_use", "name": "Read", "input": {"file_path": "z"}}],
                parent="toolu_A",
            ),
        ]
    )
    assert out.count("⟨lane alpha⟩") == 2
    assert out.count("⟨lane beta⟩") == 1


def test_lane_color_stable_per_lane_and_distinct() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("render_stream_mod", SCRIPT)
    assert spec is not None and spec.loader is not None
    rs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rs)
    rs._color_enabled = True
    rs._lanes.clear()
    rs._register_lane("toolu_A", "alpha")
    rs._register_lane("toolu_B", "beta")
    a_first = rs._lane("toolu_A")
    b_first = rs._lane("toolu_B")
    a_second = rs._lane("toolu_A")
    assert a_first == a_second
    assert a_first != b_first
    assert a_first.split("⟨")[0] != b_first.split("⟨")[0]


def test_subagent_error_line_carries_lane() -> None:
    err = json.dumps(
        {
            "type": "user",
            "parent_tool_use_id": "toolu_A",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "is_error": True,
                        "content": [{"type": "text", "text": "boom"}],
                    }
                ]
            },
        }
    )
    out = _run([_task_spawn("toolu_A", "review bugs"), err])
    assert "⟨review bugs⟩" in out
    assert "✗ boom" in out


def test_parent_lines_carry_no_lane_brackets() -> None:
    out = _run(
        [
            _assistant(
                [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]
            )
        ]
    )
    assert "⟨" not in out
