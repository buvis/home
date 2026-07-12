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
