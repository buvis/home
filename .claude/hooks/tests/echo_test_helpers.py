"""Shared helpers for the cartographer-echo test family
(`test_cartographer_echo.py`, `test_echo_handle.py`, `test_echo_envelope.py`).

The hook is a hyphenated file, so it cannot be imported by name; every test
that needs it in-process loads it by path through `import_hook_module`, and
every end-to-end test drives it as a subprocess through `run_hook` with HOME
redirected to a tmp dir so the audit log and session-state I/O never touch
the real ~/.claude/.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import _lib_cartographer as lib
import pytest

HOOK = Path(__file__).resolve().parents[1] / "cartographer-echo.py"


def import_hook_module():
    """Import the hook by file path (hyphenated filename can't use `import`)."""
    spec = importlib.util.spec_from_file_location("cartographer_echo_mod", HOOK)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def run_hook(
    payload: dict,
    home: Path,
    cwd: Path | None = None,
    env_extra: dict | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "HOME": str(home)}
    # Force a fresh session-key resolution per test run.
    env.pop("CLAUDE_SESSION_ID", None)
    env.pop("CLAUDE_TRANSCRIPT_PATH", None)
    env.pop("CLAUDE_PROJECT_DIR", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd) if cwd else None,
        timeout=15,
    )


def read_audit(home: Path) -> list[dict]:
    log = home / ".local" / "share" / "agents" / "cartographer" / "audit.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


def isolate_hook_for_direct_call(
    monkeypatch: pytest.MonkeyPatch,
    home: Path,
) -> object:
    """Import the hook with HOME pointed at a tmp dir.

    No module eviction: the entry and the `_echo_*` helpers must share one
    `_lib_cartographer` instance (PRD 00158 review 1, finding 3). The one
    piece of lib state that depends on HOME is the once-per-process audit-dir
    sentinel, so reset it explicitly for the new HOME instead."""
    monkeypatch.setenv("HOME", str(home))
    lib._reset_ensure_dirs_for_tests()
    return import_hook_module()
