"""Transcript clerical-overhead metrics report.

Reads a Claude Code session transcript (JSONL) and reports counts of
clerical/bookkeeping tool calls made during a build session: TaskCreate
turns, statectl Bash invocations, prompt-authoring Write calls, and
completed tasks (TaskUpdate status=completed).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from collections.abc import Iterable
from pathlib import Path

_PROMPT_WRITE_GLOBS = (
    "*/dev/local/tmp/*prompt*",
    "*/dev/local/tmp/dispatch-*",
)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report clerical-overhead metrics from a build transcript.",
    )
    parser.add_argument("transcript", help="Path to the transcript JSONL file.")
    return parser.parse_args(argv)


def _is_statectl_call(command: str) -> bool:
    return command.startswith("python3") and "statectl.py" in command


def _is_prompt_authoring_write(file_path: str) -> bool:
    return any(fnmatch.fnmatch(file_path, pattern) for pattern in _PROMPT_WRITE_GLOBS)


def _classify_content_blocks(
    content: list[object],
) -> tuple[bool, int, int, list[object], int]:
    """Classify one assistant turn's content blocks.

    Returns (turn_has_taskcreate, statectl_calls, prompt_write_calls,
    completed_task_ids, completed_tasks_without_id).
    """
    turn_has_taskcreate = False
    statectl_calls = 0
    prompt_write_calls = 0
    completed_task_ids: list[object] = []
    completed_tasks_without_id = 0

    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_use":
            continue
        name = block.get("name")
        tool_input = block.get("input", {})
        if name == "TaskCreate":
            turn_has_taskcreate = True
        elif name == "Bash":
            if _is_statectl_call(tool_input.get("command", "")):
                statectl_calls += 1
        elif name == "Write":
            if _is_prompt_authoring_write(tool_input.get("file_path", "")):
                prompt_write_calls += 1
        elif name == "TaskUpdate":
            if tool_input.get("status") == "completed":
                task_id = tool_input.get("taskId")
                if task_id:
                    completed_task_ids.append(task_id)
                else:
                    completed_tasks_without_id += 1

    return (
        turn_has_taskcreate,
        statectl_calls,
        prompt_write_calls,
        completed_task_ids,
        completed_tasks_without_id,
    )


def _classify_lines(lines: Iterable[str]) -> tuple[int, int, int, int, bool, int]:
    """Stream-classify transcript lines.

    Returns (taskcreate_turns, statectl_calls, prompt_write_calls,
    completed_tasks, any_parseable, malformed_line_count).
    """
    taskcreate_turns = 0
    statectl_calls = 0
    prompt_write_calls = 0
    completed_task_ids: set[object] = set()
    completed_tasks_without_id = 0
    any_parseable = False
    malformed_line_count = 0

    for raw_line in lines:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            entry = json.loads(raw_line)
        except json.JSONDecodeError:
            malformed_line_count += 1
            continue
        any_parseable = True

        if entry.get("type") != "assistant":
            continue
        content = entry.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue

        has_taskcreate, calls, writes, ids, no_id = _classify_content_blocks(content)
        statectl_calls += calls
        prompt_write_calls += writes
        completed_task_ids.update(ids)
        completed_tasks_without_id += no_id
        if has_taskcreate:
            taskcreate_turns += 1

    completed_tasks = len(completed_task_ids) + completed_tasks_without_id
    return (
        taskcreate_turns,
        statectl_calls,
        prompt_write_calls,
        completed_tasks,
        any_parseable,
        malformed_line_count,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    transcript_path = Path(args.transcript)

    try:
        handle = transcript_path.open()
    except FileNotFoundError:
        print(f"error: transcript file not found: {transcript_path}", file=sys.stderr)
        return 1
    except IsADirectoryError:
        print(f"error: not a file: {transcript_path}", file=sys.stderr)
        return 1
    except PermissionError:
        print(f"error: permission denied: {transcript_path}", file=sys.stderr)
        return 1

    with handle as f:
        (
            taskcreate_turns,
            statectl_calls,
            prompt_write_calls,
            completed_tasks,
            any_parseable,
            malformed_line_count,
        ) = _classify_lines(f)

    if not any_parseable:
        print(f"error: no parseable JSON lines in {transcript_path}", file=sys.stderr)
        return 2

    ratio = (statectl_calls / completed_tasks) if completed_tasks else 0.0

    print(f"TaskCreate turns: {taskcreate_turns}")
    print(f"statectl calls: {statectl_calls}")
    print(f"statectl calls per completed task: {ratio:.2f}")
    print(f"prompt-authoring Write calls: {prompt_write_calls}")
    print(f"completed tasks: {completed_tasks}")

    if malformed_line_count > 0:
        print(
            f"warning: skipped {malformed_line_count} unparseable line(s) "
            f"in {transcript_path}",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
