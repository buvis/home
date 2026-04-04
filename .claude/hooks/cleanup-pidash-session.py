#!/usr/bin/env python3
"""Stop hook — marks session as stopped in ~/.pidash/sessions/."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pidash_session import SESSIONS_DIR, read_hook_input, write_session_file


def main() -> None:
    hook_input = read_hook_input()
    raw_id = hook_input.get("session_id")
    if not raw_id:
        return
    session_id = Path(raw_id).name  # strip directory components
    if not session_id:
        return

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    target = SESSIONS_DIR / f"{session_id}.json"
    now = datetime.now(timezone.utc).isoformat()

    if target.is_file():
        try:
            state = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = {}
    else:
        state = {
            "session_id": session_id,
            "cwd": hook_input.get("cwd", ""),
        }

    state.setdefault("session_id", session_id)
    state.setdefault("cwd", hook_input.get("cwd", ""))
    state["phase"] = "stopped"
    state["stopped_at"] = now
    state["updated_at"] = now

    write_session_file(target, state)


if __name__ == "__main__":
    main()
