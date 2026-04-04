#!/usr/bin/env python3
"""Shared helper for mirroring autopilot state to ~/.pidash/sessions/."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SESSIONS_DIR = Path.home() / ".pidash" / "sessions"


def read_hook_input() -> dict:
    """Read and parse JSON from stdin. Returns empty dict on any failure."""
    try:
        if sys.stdin.isatty():
            return {}
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError, OSError):
        return {}


def mirror_to_session_dir(hook_input: dict, state: dict) -> None:
    """Write session state to ~/.pidash/sessions/{session_id}.json.

    Skips silently if session_id is missing from hook_input.
    """
    raw_id = hook_input.get("session_id")
    if not raw_id:
        return
    session_id = Path(raw_id).name  # strip directory components
    if not session_id:
        return

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    merged = dict(state)
    merged["session_id"] = session_id
    merged["cwd"] = hook_input.get("cwd", "")
    merged["updated_at"] = datetime.now(timezone.utc).isoformat()

    write_session_file(SESSIONS_DIR / f"{session_id}.json", merged)


def write_session_file(target: Path, data: dict) -> None:
    """Atomically write JSON data to target path."""
    tmp_path = ""
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=target.parent, suffix=".tmp", prefix=f"{target.stem}."
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, target)
    except OSError:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
