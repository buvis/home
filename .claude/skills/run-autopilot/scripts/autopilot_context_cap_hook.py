#!/usr/bin/env python3
"""PostToolUse hook: abort autopilot Work tasks before they exceed 180K context.

Reads PostToolUse JSON on stdin (`session_id`, `transcript_path`), tails the
session transcript to find the most recent `message.usage`, and on overrun
emits an `additionalContext` envelope telling the model to abort cleanly.

Active only when `dev/local/autopilot/state.json` exists with `phase == "work"`.
One-shot per task via `.cap-fired` marker (cleared at task start).

Stdlib only. Self-contained — no `_common` import (this script lives outside
~/.claude/hooks/).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

USAGE_LIMIT = 180_000
TAIL_BYTES = 64 * 1024  # Read last 64KB; one usage line is well under 4KB.

AUTOPILOT_DIR = Path("dev") / "local" / "autopilot"
STATE_FILE = AUTOPILOT_DIR / "state.json"
MARKER_FILE = AUTOPILOT_DIR / ".cap-fired"
TASK_ABORT_LOG = AUTOPILOT_DIR / "task-abort"

ABORT_INSTRUCTIONS = (
    "Context cap reached (~180K tokens). Abort current task cleanly: commit "
    "any safe partial work, append the abort record to state.task_aborts "
    "(already done by hook), write 'task_aborted' to "
    "dev/local/autopilot/signal, then exit."
)


def _read_stdin() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _load_state() -> dict[str, Any] | None:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _latest_usage_total(transcript_path: Path) -> int | None:
    """Return the most recent `message.usage` token total, or None if absent."""
    try:
        size = transcript_path.stat().st_size
    except OSError:
        return None
    if size == 0:
        return None
    try:
        with transcript_path.open("rb") as f:
            offset = max(0, size - TAIL_BYTES)
            f.seek(offset)
            tail = f.read()
    except OSError:
        return None

    text = tail.decode("utf-8", errors="ignore")
    if offset > 0:
        newline = text.find("\n")
        if newline == -1:
            return None
        text = text[newline + 1 :]

    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        total = (
            int(usage.get("input_tokens", 0) or 0)
            + int(usage.get("cache_read_input_tokens", 0) or 0)
            + int(usage.get("cache_creation_input_tokens", 0) or 0)
        )
        return total
    return None


def _in_progress_task_id(state: dict[str, Any]) -> str:
    tasks = state.get("tasks")
    if isinstance(tasks, list):
        for task in tasks:
            if isinstance(task, dict) and task.get("status") == "in_progress":
                task_id = task.get("id")
                if isinstance(task_id, str) and task_id:
                    return task_id
    return "unknown"


def _atomic_write_state(state: dict[str, Any]) -> None:
    tmp = STATE_FILE.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(state, indent=2))
        os.replace(tmp, STATE_FILE)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass


def _append_task_abort_log(entry: dict[str, Any]) -> None:
    try:
        with TASK_ABORT_LOG.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def _emit_abort_envelope() -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": ABORT_INSTRUCTIONS,
        }
    }
    print(json.dumps(payload))


def main() -> None:
    stdin = _read_stdin()
    transcript_path_str = stdin.get("transcript_path")
    if not isinstance(transcript_path_str, str) or not transcript_path_str:
        return

    state = _load_state()
    if not state or state.get("phase") != "work":
        return

    if MARKER_FILE.exists():
        return

    transcript_path = Path(transcript_path_str)
    total = _latest_usage_total(transcript_path)
    if total is None or total <= USAGE_LIMIT:
        return

    try:
        MARKER_FILE.touch()
    except OSError:
        return

    task_id = _in_progress_task_id(state)
    abort_entry = {
        "task_id": task_id,
        # The transcript usage line carries no turn counter, so we cannot
        # derive the actual turn. -1 signals "unknown" (matches the
        # work-skill subagent_prompt_overrun convention) rather than the
        # misleading "first turn" that 0 implied previously.
        "turn": -1,
        "total_input_tokens": total,
        "cause": "context_overrun",
    }
    _append_task_abort_log(abort_entry)

    aborts = state.get("task_aborts")
    if not isinstance(aborts, list):
        aborts = []
    aborts.append(abort_entry)
    state["task_aborts"] = aborts
    _atomic_write_state(state)

    _emit_abort_envelope()


if __name__ == "__main__":
    main()
