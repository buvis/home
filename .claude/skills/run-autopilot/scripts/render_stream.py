#!/usr/bin/env python3
"""Render `claude -p --output-format stream-json --verbose` for humans.

Stdin filter for the autoclaude loop terminal: upstream `tee` keeps the raw
JSONL in last-session.log — which stays load-bearing (detect_usage_limit.py
greps it, the loop-metrics line parses its final result event) — while this
script shapes what the operator sees.

Contract:
- JSON events become one-line summaries: tool calls, assistant text, tool
  errors, session init, final result. Noise (hook lifecycle, thinking,
  token counters, rate-limit pings) is dropped BY DESIGN; it stays in the
  raw log.
- Subagent events (parent_tool_use_id set) show tool calls only, dimmed and
  tagged with a stable per-lane ⟨label⟩ (from the spawning Task description;
  ⟨agentN⟩ fallback); subagent prose is noise at loop-watching altitude.
- Non-JSON lines (merged stderr, wrapper banners) pass through verbatim.
- Never breaks the session: a line that fails to render passes through
  raw, and a dead stdout (closed terminal) switches to draining stdin so
  tee/claude upstream never see SIGPIPE.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

_RESET = "\033[0m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"

_color_enabled = False

# First string field that names what a tool call is about, checked in order.
_SUMMARY_KEYS = (
    "description",
    "file_path",
    "pattern",
    "skill",
    "command",
    "prompt",
    "url",
    "query",
)

# Lane registry: parent_tool_use_id -> (label, ansi color). Registered when a
# top-level Task/Agent tool_use appears; unknown parents self-register as
# ⟨agentN⟩ so a stream joined mid-run still lane-tags (PRD 00063 Phase 0).
_AGENT_TOOLS = frozenset({"Task", "Agent"})
_LANE_COLORS = (
    "\033[35m",
    "\033[33m",
    "\033[36m",
    "\033[32m",
    "\033[34m",
    "\033[95m",
    "\033[93m",
    "\033[96m",
)
_lanes: dict[str, tuple[str, str]] = {}


def _register_lane(block_id: str, description: str) -> None:
    if block_id in _lanes:
        return
    label = _trunc(description, 24) if description.strip() else f"agent{len(_lanes) + 1}"
    _lanes[block_id] = (label, _LANE_COLORS[len(_lanes) % len(_LANE_COLORS)])


def _lane(parent_id: str) -> str:
    if parent_id not in _lanes:
        _register_lane(parent_id, "")
    label, color = _lanes[parent_id]
    return _c(color, f"⟨{label}⟩")


def _c(code: str, text: str) -> str:
    return f"{code}{text}{_RESET}" if _color_enabled else text


def _stamp() -> str:
    return _c(_DIM, time.strftime("%H:%M:%S"))


def _trunc(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _tool_summary(tool_input: Any) -> str:
    if not isinstance(tool_input, dict):
        return ""
    for key in _SUMMARY_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    for value in tool_input.values():
        if isinstance(value, str) and value:
            return value
    return ""


def _result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            block.get("text", "") for block in content if isinstance(block, dict)
        )
    return ""


def _render_assistant(event: dict[str, Any]) -> list[str]:
    subagent = bool(event.get("parent_tool_use_id"))
    content = (event.get("message") or {}).get("content")
    if not isinstance(content, list):
        return []
    lines: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "tool_use":
            name = str(block.get("name", "?"))
            summary = _trunc(_tool_summary(block.get("input")))
            if subagent:
                tail = f"↳ {name}"
                if summary:
                    tail += f" · {summary}"
                lane = _lane(str(event.get("parent_tool_use_id")))
                lines.append(
                    f"{_c(_DIM, time.strftime('%H:%M:%S'))} {lane} {_c(_DIM, tail)}"
                )
            else:
                if name in _AGENT_TOOLS and isinstance(block.get("id"), str):
                    lane_input = block.get("input")
                    desc = (
                        lane_input.get("description", "")
                        if isinstance(lane_input, dict)
                        else ""
                    )
                    _register_lane(block["id"], desc if isinstance(desc, str) else "")
                line = f"{_stamp()} {_c(_CYAN, '⚒ ' + name)}"
                if summary:
                    line += f" · {summary}"
                lines.append(line)
        elif btype == "text" and not subagent:
            text = str(block.get("text", "")).strip()
            if text:
                lines.extend("  " + part for part in text.splitlines())
    return lines


def _render_tool_results(event: dict[str, Any]) -> list[str]:
    content = (event.get("message") or {}).get("content")
    if not isinstance(content, list):
        return []
    parent_id = event.get("parent_tool_use_id")
    prefix = f"{_lane(str(parent_id))} " if parent_id else ""
    lines: list[str] = []
    for block in content:
        if (
            isinstance(block, dict)
            and block.get("type") == "tool_result"
            and block.get("is_error")
        ):
            detail = _trunc(_result_text(block.get("content"))) or "tool error"
            lines.append(f"{_stamp()} {prefix}{_c(_RED, '✗ ' + detail)}")
    return lines


def _render_result(event: dict[str, Any]) -> list[str]:
    is_error = bool(event.get("is_error"))
    color = _RED if is_error else _GREEN
    mark = _c(color, "■ " + str(event.get("subtype", "result")))
    secs = int(event.get("duration_ms") or 0) // 1000
    parts = [f"{secs}s", f"{event.get('num_turns', '?')} turns"]
    cost = event.get("total_cost_usd")
    if isinstance(cost, (int, float)):
        parts.append(f"${cost:.2f}")
    output_tokens = (event.get("usage") or {}).get("output_tokens")
    if isinstance(output_tokens, int):
        parts.append(f"{output_tokens} tok out")
    lines = [f"{_stamp()} {mark} · " + " · ".join(parts)]
    denials = event.get("permission_denials")
    if isinstance(denials, list) and denials:
        lines.append(
            f"{_stamp()} {_c(_YELLOW, f'⚠ {len(denials)} permission denial(s)')}"
        )
    return lines


def render(event: dict[str, Any]) -> list[str]:
    etype = event.get("type")
    if etype == "system":
        if event.get("subtype") == "init":
            return [
                f"{_stamp()} {_c(_GREEN, '▶')} claude "
                f"{event.get('claude_code_version', '?')}"
                f" · {event.get('model', '?')}"
                f" · {event.get('permissionMode', '?')}"
            ]
        return []
    if etype == "assistant":
        return _render_assistant(event)
    if etype == "user":
        return _render_tool_results(event)
    if etype == "result":
        return _render_result(event)
    return []


def main() -> int:
    global _color_enabled
    _color_enabled = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(errors="replace")
    dead_stdout = False
    for raw in sys.stdin:
        if dead_stdout:
            continue  # drain so tee/claude upstream never see SIGPIPE
        line = raw.rstrip("\n")
        try:
            event = json.loads(line)
            out = render(event) if isinstance(event, dict) else [line]
        except Exception:  # fail-open viewer: the raw line IS the fallback
            out = [line]
        try:
            for rendered in out:
                print(rendered, flush=True)
        except OSError:
            dead_stdout = True
    if dead_stdout:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
