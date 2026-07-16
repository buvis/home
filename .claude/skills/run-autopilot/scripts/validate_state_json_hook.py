#!/usr/bin/env python3
"""PostToolUse hook: catch a Write/Edit that leaves autopilot state.json unparseable.

2026-07-16 (ddb): a headless autopilot session appended a literal `</content>`
line — harness-tag bleed — to its state.json write. The corruption sat on disk
until session exit, where the autoclaude wrapper's `jq -e` check turned a
healthy PAUSE hand-off into `died (state.json unreadable)` and halted the
loop. The wrapper can only detect this after the session (and its context) is
gone; this hook detects it at the write, while the model can still fix it:
exit 2 feeds the parse error straight back to the session.

Fires only when the edited path ends with dev/local/autopilot/state.json.
Stdlib only. Self-contained — no `_common` import (this script lives outside
~/.claude/hooks/). A failure of the hook itself never blocks writes to
unrelated files.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not path.endswith("dev/local/autopilot/state.json"):
        return 0
    try:
        with open(path, encoding="utf-8") as fh:
            json.load(fh)
    except FileNotFoundError:
        return 0
    except Exception as err:
        print(
            f"state.json is not valid JSON after this write: {err}. "
            "At session exit the autoclaude wrapper will misread this as "
            "'died (state.json unreadable)' and halt the loop. Rewrite the "
            "ENTIRE file as pure JSON — no trailing text, no harness wrapper "
            "tags like </content>.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
