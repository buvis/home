#!/usr/bin/env python3
"""PostToolUse hook: track struggle signals for model escalation.

Reads a JSON payload from stdin after every tool call. Updates
~/.claude/dev/local/escalation-state.json with accumulated signals.
Exits 0 always (never blocks tool execution).

Python 3.10+, stdlib only.
"""

import json
import sys
from pathlib import Path

CONFIG_PATH = Path.home() / ".claude" / "escalation-config.json"
STATE_PATH = Path.home() / ".claude" / "dev" / "local" / "escalation-state.json"

DEFAULT_CONFIG: dict = {
    "same_file_edit_count": 3,
    "same_test_failure_count": 2,
    "consecutive_error_count": 3,
    "tool_calls_without_progress": 20,
    "score_threshold": 5,
    "cooldown_after_escalation": 10,
}

EDIT_TOOLS = {"Edit", "Write", "MultiEdit"}
TASK_TOOLS = {"TaskUpdate", "TaskCreate", "TaskList", "TaskGet"}

TEST_COMMANDS = (
    "pytest",
    "cargo test",
    "npm test",
    "vitest",
    "jest",
    "go test",
    "npx playwright",
)

ERROR_MARKERS = (
    "FAILED",
    "FAIL",
    "error",
    "traceback",
    "panicked",
    "exit code",
)


def load_config() -> dict:
    try:
        text = CONFIG_PATH.read_text(encoding="utf-8")
        data = json.loads(text)
        return {**DEFAULT_CONFIG, **data}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return DEFAULT_CONFIG.copy()


def empty_state(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "file_edits": {},
        "test_failures": {},
        "consecutive_errors": 0,
        "tool_calls_since_task_complete": 0,
        "struggle_score": 0,
        "escalation_count": 0,
        "cooldown_remaining": 0,
    }


def load_state(session_id: str) -> dict:
    try:
        text = STATE_PATH.read_text(encoding="utf-8")
        state = json.loads(text)
        if state.get("session_id") != session_id:
            return empty_state(session_id)
        return state
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return empty_state(session_id)


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.rename(STATE_PATH)


def is_test_command(command: str) -> bool:
    cmd = command.strip()
    return any(cmd.startswith(marker) or f" {marker}" in cmd for marker in TEST_COMMANDS)


def has_error_marker(response: str) -> bool:
    lower = response.lower()
    return any(marker.lower() in lower for marker in ERROR_MARKERS)


def is_escalation(tool_name: str, tool_input: dict) -> bool:
    if tool_name != "Agent":
        return False
    model = str(tool_input.get("model", "")).lower()
    prompt = str(tool_input.get("prompt", "")).lower()
    return "opus" in model or "escalat" in prompt


def is_task_completed(tool_name: str, tool_input: dict) -> bool:
    if tool_name != "TaskUpdate":
        return False
    return str(tool_input.get("status", "")).lower() == "completed"


def compute_score(state: dict, config: dict) -> int:
    score = 0

    for count in state["file_edits"].values():
        if count >= config["same_file_edit_count"]:
            score += 3

    for count in state["test_failures"].values():
        if count >= config["same_test_failure_count"]:
            score += 4

    if state["consecutive_errors"] >= config["consecutive_error_count"]:
        score += 3

    if state["tool_calls_since_task_complete"] >= config["tool_calls_without_progress"]:
        score += 2

    return score


def track_file_edit(state: dict, tool_input: dict) -> dict:
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return state
    edits = {**state["file_edits"], file_path: state["file_edits"].get(file_path, 0) + 1}
    return {**state, "file_edits": edits}


def track_test_failure(state: dict, tool_input: dict, tool_response: str) -> dict:
    command = tool_input.get("command", "")
    if not is_test_command(command) or not has_error_marker(tool_response):
        return state
    failures = {
        **state["test_failures"],
        command: state["test_failures"].get(command, 0) + 1,
    }
    return {**state, "test_failures": failures}


def track_consecutive_errors(state: dict, tool_name: str, tool_response: str) -> dict:
    if tool_name in TASK_TOOLS:
        return state
    if has_error_marker(tool_response):
        return {**state, "consecutive_errors": state["consecutive_errors"] + 1}
    return {**state, "consecutive_errors": 0}


def process_payload(payload: dict) -> None:
    session_id = payload.get("session_id", "")
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    tool_response = str(payload.get("tool_response", ""))

    if not isinstance(tool_input, dict):
        tool_input = {}

    config = load_config()
    state = load_state(session_id)

    # Decrement cooldown each call
    if state["cooldown_remaining"] > 0:
        state = {**state, "cooldown_remaining": state["cooldown_remaining"] - 1}

    # Detect escalation completion - reset signals, set cooldown
    if is_escalation(tool_name, tool_input):
        state = {
            **state,
            "file_edits": {},
            "test_failures": {},
            "consecutive_errors": 0,
            "tool_calls_since_task_complete": 0,
            "escalation_count": state["escalation_count"] + 1,
            "cooldown_remaining": config["cooldown_after_escalation"],
            "struggle_score": 0,
        }
        save_state(state)
        return

    # Track file edits
    if tool_name in EDIT_TOOLS:
        state = track_file_edit(state, tool_input)

    # Track test failures (Bash tool only)
    if tool_name == "Bash":
        state = track_test_failure(state, tool_input, tool_response)

    # Track consecutive errors (skip task tools)
    state = track_consecutive_errors(state, tool_name, tool_response)

    # Track tool calls since last task completion
    state = {**state, "tool_calls_since_task_complete": state["tool_calls_since_task_complete"] + 1}

    # Reset progress counter on task completion
    if is_task_completed(tool_name, tool_input):
        state = {**state, "tool_calls_since_task_complete": 0}

    # Compute and store score
    score = compute_score(state, config)
    state = {**state, "struggle_score": score}

    save_state(state)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, OSError):
        sys.exit(0)

    try:
        process_payload(payload)
    except Exception:
        pass  # Never block tool execution

    sys.exit(0)


if __name__ == "__main__":
    main()
