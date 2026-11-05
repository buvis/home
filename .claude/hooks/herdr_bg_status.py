#!/usr/bin/env python3
"""Stop hook: keep herdr-core status "working" while background tasks run.

Claude Code reports idle/done over OSC 7501 when a turn ends, even with
background shells or agents still running. When the Stop input lists running
background tasks, write our own root `working` report to the terminal after
Claude's turn-end report lands. Claude only re-reports on change, so ours
holds until the next turn (a finished background task starts one).
"""

import json
import os
import sys
import time

# ponytail: fixed delay to land after Claude's own turn-end report; raise if
# herdr still shows idle with background work. Ceiling: a task killed without
# a new turn leaves "working" until the next prompt.
DELAY_S = 0.6
REPORT = "\x1b]7501;state=working:app=claude-code\x07"


def has_running_tasks(hook_input: dict) -> bool:
    return any(
        t.get("status") in (None, "running", "pending")
        for t in hook_input.get("background_tasks") or []
    )


def main() -> None:
    if not os.environ.get("HC_TERMINAL_ID"):
        return
    try:
        hook_input = json.load(sys.stdin)
    except ValueError:
        return
    if hook_input.get("hook_event_name") != "Stop" or not has_running_tasks(hook_input):
        return
    # Hooks run without a controlling tty (and the sandbox denies ps), so
    # write to the pty path the login shell exported as GPG_TTY.
    tty_path = os.environ.get("GPG_TTY", "")
    if not tty_path.startswith("/dev/"):
        print(
            "herdr_bg_status: GPG_TTY not set, cannot reach the terminal",
            file=sys.stderr,
        )
        return
    time.sleep(DELAY_S)
    try:
        with open(tty_path, "w") as tty:
            tty.write(REPORT)
    except OSError as exc:
        print(f"herdr_bg_status: cannot write {tty_path}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
