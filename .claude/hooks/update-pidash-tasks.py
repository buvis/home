#!/usr/bin/env python3
"""PostToolUse hook for TaskUpdate — syncs task status to dev/local/autopilot/state.json."""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pidash_session import mirror_to_session_dir

LOG = Path.home() / ".claude" / "hooks" / "pidash-hook.log"

_PREFIX_RE = re.compile(r"^\[(?:C\d+|DOUBT)\]\s*")


def log(msg: str) -> None:
    with LOG.open("a") as f:
        f.write(msg + "\n")


def _strip_task_prefix(name: str) -> str:
    """Strip [C1], [C2], [DOUBT] etc. prefixes from task names."""
    return _PREFIX_RE.sub("", name)


def find_task_title(hook_input: dict) -> str:
    """Extract task title from tool_response (may be JSON or text)."""
    resp = hook_input.get("tool_response", "")
    if isinstance(resp, dict):
        return resp.get("title", "") or resp.get("name", "")
    if isinstance(resp, str):
        try:
            parsed = json.loads(resp)
            if isinstance(parsed, dict):
                return parsed.get("title", "") or parsed.get("name", "")
        except (json.JSONDecodeError, ValueError):
            pass
    return ""


def _normalize_tasks(tasks: list) -> list[dict]:
    """Convert string tasks to dicts so matching works."""
    result = []
    for t in tasks:
        if isinstance(t, str):
            result.append({"name": t, "status": "pending"})
        elif isinstance(t, dict):
            result.append(t)
    return result


def _norm(s: str) -> str:
    return s.replace("\u2013", "-").replace("\u2014", "-").strip().lower()


def _name_matches(task_name: str, candidate: str) -> bool:
    """Match task names, ignoring [C{n}]/[DOUBT] prefixes and unicode dashes."""
    tn = _norm(task_name)
    cn = _norm(candidate)
    if tn == cn:
        return True
    tn_base = _norm(_strip_task_prefix(task_name))
    cn_base = _norm(_strip_task_prefix(candidate))
    return tn_base == cn_base


def main() -> None:
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    tool_input = hook_input.get("tool_input", {})
    task_id = tool_input.get("id", "")
    new_status = tool_input.get("status", "")
    if not task_id or not new_status:
        return

    state_file = Path("dev/local/autopilot/state.json")
    if not state_file.is_file():
        return

    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    tasks = state.get("tasks", [])
    if not tasks:
        return

    # Normalize string tasks to dicts
    tasks = _normalize_tasks(tasks)
    state["tasks"] = tasks

    # Strategy 1: match by ID
    updated = False
    for task in tasks:
        if task.get("id") == task_id:
            task["status"] = new_status
            updated = True
            break

    # Strategy 2: match by title from tool_response
    if not updated:
        title = find_task_title(hook_input)
        if title:
            for task in tasks:
                if task.get("name") and _name_matches(task["name"], title):
                    task["status"] = new_status
                    task["id"] = task_id
                    updated = True
                    break

    # Strategy 3: match by title substring in tool_response text
    if not updated:
        resp_text = str(hook_input.get("tool_response", ""))
        for task in tasks:
            name = task.get("name", "")
            if not name:
                continue
            if name in resp_text or _strip_task_prefix(name) in resp_text:
                task["status"] = new_status
                task["id"] = task_id
                updated = True
                break

    # Strategy 4: match by title from tool_input
    if not updated:
        input_title = tool_input.get("title", "") or tool_input.get("name", "")
        if input_title:
            for task in tasks:
                if task.get("name") and _name_matches(task["name"], input_title):
                    task["status"] = new_status
                    task["id"] = task_id
                    updated = True
                    break

    if not updated:
        log(f"NO MATCH id={task_id} status={new_status}")
        log(f"  tool_input={json.dumps(tool_input)[:300]}")
        log(f"  tool_response={str(hook_input.get('tool_response', ''))[:300]}")
        log(f"  tasks={json.dumps([t.get('name','') for t in tasks])[:300]}")
        return

    completed = sum(1 for t in tasks if t.get("status") == "completed")
    state["tasks_completed"] = completed
    state["tasks_total"] = len(tasks)

    try:
        state_file.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass

    mirror_to_session_dir(hook_input, state)


if __name__ == "__main__":
    main()
