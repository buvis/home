#!/usr/bin/env python3
"""PostToolUse hook for Agent — syncs task status to dev/local/autopilot/state.json.

Safety net for when subagents call TaskUpdate internally (hooks don't fire
inside subagents). Parses the Agent's response text for task completion
and in-progress markers and updates the state file.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pidash_session import mirror_to_session_dir

_PREFIX_RE = re.compile(r"^\[(?:C\d+|DOUBT)\]\s*")


def _normalize(s: str) -> str:
    """Normalize unicode dashes and whitespace for comparison."""
    return s.replace("\u2013", "-").replace("\u2014", "-").strip().lower()


def _strip_prefix(name: str) -> str:
    """Strip [C1], [DOUBT] etc. prefixes."""
    return _PREFIX_RE.sub("", name)


def _names_match(task_name: str, candidate: str) -> bool:
    """Match names, ignoring [C{n}]/[DOUBT] prefixes."""
    tn = _normalize(task_name)
    cn = _normalize(candidate)
    if tn == cn or tn in cn or cn in tn:
        return True
    tn_base = _normalize(_strip_prefix(task_name))
    cn_base = _normalize(_strip_prefix(candidate))
    if tn_base and cn_base and (tn_base in cn_base or cn_base in tn_base):
        return True
    return tn_base == cn_base


def _extract_task_markers(text: str) -> tuple[list[str], list[str]]:
    """Extract completed and in-progress task names from agent response text."""
    completed = []
    in_progress = []
    for line in text.splitlines():
        stripped = line.strip()
        # Completed: ✓ Task Name, ✅ Task Name, - [x] Task Name
        if re.match(r"^[✓✅]\s+", stripped):
            name = re.sub(r"^[✓✅]\s+", "", stripped)
            completed.append(name)
        elif re.match(r"^-\s+\[x\]\s+", stripped, re.IGNORECASE):
            name = re.sub(r"^-\s+\[x\]\s+", "", stripped, flags=re.IGNORECASE)
            completed.append(name)
        # In progress: ■ Task Name, ▸ Task Name, 🔄 Task Name, ⏳ Task Name
        elif re.match(r"^[■▸🔄⏳]\s+", stripped):
            name = re.sub(r"^[■▸🔄⏳]\s+", "", stripped)
            in_progress.append(name)
    return completed, in_progress


def main() -> None:
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    response_text = str(hook_input.get("tool_response", ""))
    if not response_text:
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
    for i, t in enumerate(tasks):
        if isinstance(t, str):
            tasks[i] = {"name": t, "status": "pending"}
    state["tasks"] = tasks

    completed_names, in_progress_names = _extract_task_markers(response_text)
    if not completed_names and not in_progress_names:
        return

    updated = False
    for task in tasks:
        task_name = task.get("name", "")
        if not task_name:
            continue

        # Check completed markers
        if task.get("status") != "completed":
            for comp_name in completed_names:
                if _names_match(task_name, comp_name):
                    task["status"] = "completed"
                    updated = True
                    break

        # Check in-progress markers (only upgrade from pending)
        if task.get("status") == "pending":
            for ip_name in in_progress_names:
                if _names_match(task_name, ip_name):
                    task["status"] = "in_progress"
                    updated = True
                    break

    if not updated:
        return

    completed_count = sum(1 for t in tasks if t.get("status") == "completed")
    state["tasks_completed"] = completed_count
    state["tasks_total"] = len(tasks)

    try:
        state_file.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass

    mirror_to_session_dir(hook_input, state)


if __name__ == "__main__":
    main()
