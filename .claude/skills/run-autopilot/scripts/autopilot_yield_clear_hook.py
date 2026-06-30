#!/usr/bin/env python3
"""PostToolUse hook: clear the autopilot idle-watchdog yield marker on ANY tool use.

A tool use means the autopilot session is active (the harness re-invoked the model after a
background task completed), not idle-waiting on an orphaned task. Removing
<autopilot_dir>/.yielded-waiting resets the idle clock; the Stop hook re-stamps it on the
next abstaining yield. Registered matcher-less so it fires on every tool — Edit/Write/
TaskUpdate included — which the cap hook's restricted matcher does not. Fail-open and
self-contained (stdlib only; lives in scripts/ so `_walk_up` is importable, like the cap
hook)."""
from __future__ import annotations

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
