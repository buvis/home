#!/usr/bin/env python3
"""Notification hook for permission_prompt — sets needs_attention in prd-cycle.json."""

import json
from pathlib import Path


def main() -> None:
    state_file = Path(".local/autopilot/state.json")
    if not state_file.is_file():
        return
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        state["needs_attention"] = True
        state_file.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    except (json.JSONDecodeError, OSError):
        pass


if __name__ == "__main__":
    main()
