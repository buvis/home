#!/usr/bin/env python3
"""PostToolUse hook: clear .yielded-waiting on any tool use.

Tool activity means the session is active, not idle-waiting on an orphaned task.
Registered matcher-less so it fires on all tools. Fail-open."""
from pathlib import Path

from _walk_up import find_autopilot_dir


def main() -> None:
    autopilot_dir = find_autopilot_dir(Path.cwd())
    if autopilot_dir is None:
        return
    try:
        (autopilot_dir / ".yielded-waiting").unlink(missing_ok=True)
    except OSError:
        pass


if __name__ == "__main__":
    main()
