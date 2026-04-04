#!/usr/bin/env python3
"""PreToolUse hook: block tool calls when struggle threshold is exceeded.

Reads a JSON payload from stdin before every tool call. Exits 0 to allow
or 2 to block. Never raises - parse failures always allow the tool call.

Python 3.10+, stdlib only.
"""

import json
import sys
from pathlib import Path

CONFIG_PATH = Path.home() / ".claude" / "escalation-config.json"
STATE_PATH = Path.home() / ".claude" / "dev" / "local" / "escalation-state.json"

DEFAULT_THRESHOLD = 5

# Tools always allowed regardless of score
ALWAYS_ALLOWED = {
    "Read",
    "Grep",
    "Glob",
    "TaskCreate",
    "TaskUpdate",
    "TaskList",
    "TaskGet",
    "TaskOutput",
    "TaskStop",
    "AskUserQuestion",
}


def load_threshold() -> int:
    try:
        text = CONFIG_PATH.read_text(encoding="utf-8")
        data = json.loads(text)
        return int(data.get("score_threshold", DEFAULT_THRESHOLD))
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return DEFAULT_THRESHOLD


def load_state() -> dict | None:
    try:
        text = STATE_PATH.read_text(encoding="utf-8")
        return json.loads(text)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def is_allowed_skill(tool_name: str, tool_input: dict) -> bool:
    if tool_name != "Skill":
        return False
    skill = str(tool_input.get("skill", "")).lower()
    return "escalat" in skill


def is_allowed_agent(tool_name: str, tool_input: dict) -> bool:
    if tool_name != "Agent":
        return False
    model = str(tool_input.get("model", "")).lower()
    prompt = str(tool_input.get("prompt", "")).lower()
    return "opus" in model or "escalat" in prompt


def determine_trigger(state: dict) -> str:
    file_edits: dict = state.get("file_edits", {})
    test_failures: dict = state.get("test_failures", {})
    consecutive_errors: int = state.get("consecutive_errors", 0)
    tool_calls: int = state.get("tool_calls_since_task_complete", 0)

    has_file_signals = any(c >= 3 for c in file_edits.values())
    has_test_signals = any(c >= 2 for c in test_failures.values())
    has_error_signals = consecutive_errors >= 3
    has_no_progress = tool_calls >= 20

    file_or_test = has_file_signals or has_test_signals or has_error_signals

    if file_or_test:
        return "struggle-repeated-failure"
    if has_no_progress:
        return "struggle-no-progress"
    return "struggle-repeated-failure"


def format_signals(state: dict) -> list[str]:
    signals: list[str] = []

    file_edits: dict = state.get("file_edits", {})
    for path, count in file_edits.items():
        if count >= 3:
            signals.append(f"file edited {count}x: {path}")

    test_failures: dict = state.get("test_failures", {})
    for command, count in test_failures.items():
        if count >= 2:
            signals.append(f"test failed {count}x: {command}")

    consecutive_errors: int = state.get("consecutive_errors", 0)
    if consecutive_errors >= 3:
        signals.append(f"consecutive errors: {consecutive_errors}")

    tool_calls: int = state.get("tool_calls_since_task_complete", 0)
    if tool_calls >= 20:
        signals.append(f"tool calls without progress: {tool_calls}")

    return signals


def build_block_message(score: int, trigger: str, signals: list[str]) -> str:
    lines = [
        f"Struggle score {score} has reached threshold. Escalation required.",
        f"Suggested trigger: {trigger}",
    ]
    if signals:
        lines.append("Active signals:")
        lines.extend(f"  - {s}" for s in signals)
    return "\n".join(lines)


def check(tool_name: str, tool_input: dict) -> None:
    """Exit 0 to allow or 2 to block. Never returns on block."""
    if tool_name in ALWAYS_ALLOWED:
        sys.exit(0)

    if is_allowed_skill(tool_name, tool_input):
        sys.exit(0)

    if is_allowed_agent(tool_name, tool_input):
        sys.exit(0)

    state = load_state()
    if state is None:
        sys.exit(0)

    score: int = state.get("struggle_score", 0)
    cooldown: int = state.get("cooldown_remaining", 0)
    threshold = load_threshold()

    if score < threshold or cooldown > 0:
        sys.exit(0)

    trigger = determine_trigger(state)
    signals = format_signals(state)
    message = build_block_message(score, trigger, signals)
    sys.stderr.write(message + "\n")
    sys.exit(2)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, OSError):
        sys.exit(0)

    tool_name = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input", {})
    if not isinstance(tool_input, dict):
        tool_input = {}

    try:
        check(tool_name, tool_input)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
