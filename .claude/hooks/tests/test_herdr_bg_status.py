"""herdr_bg_status: report `working` to herdr only while background tasks run."""

import json
import os
import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "herdr_bg_status.py"
_WORKING = "\x1b]7501;state=working:app=claude-code\x07"


def _run(payload: str, tty: Path) -> str:
    """Run the hook with GPG_TTY pointing at a temp file standing in for the pty."""
    tty.write_text("")
    fd = os.open(tty, os.O_RDWR)
    try:
        env = {**os.environ, "HC_TERMINAL_ID": "t1", "GPG_TTY": f"/dev/fd/{fd}"}
        subprocess.run(
            [sys.executable, str(_SCRIPT)],
            input=payload,
            text=True,
            env=env,
            check=True,
            pass_fds=(fd,),
        )
    finally:
        os.close(fd)
    return tty.read_text()


def test_reports_working_while_background_task_runs(tmp_path: Path) -> None:
    payload = (
        '{"hook_event_name":"Stop","background_tasks":[{"id":"b1","status":"running"}]}'
    )
    assert _run(payload, tmp_path / "tty") == _WORKING


def _stop(*commands: str) -> str:
    tasks = [
        {"id": f"b{i}", "type": "shell", "status": "running", "command": c}
        for i, c in enumerate(commands)
    ]
    return json.dumps({"hook_event_name": "Stop", "background_tasks": tasks})


def test_reports_blocked_when_only_waiting_for_warrant(tmp_path: Path) -> None:
    payload = _stop("~/bin/warrant wait 20261110-ab12")
    assert _run(payload, tmp_path / "tty") == _WORKING.replace("working", "blocked")


def test_reports_working_when_real_work_runs_beside_a_warrant_wait(
    tmp_path: Path,
) -> None:
    payload = _stop("~/bin/warrant wait 20261110-ab12", "uv run pytest")
    assert _run(payload, tmp_path / "tty") == _WORKING


def test_stays_silent_without_background_tasks(tmp_path: Path) -> None:
    payload = '{"hook_event_name":"Stop","background_tasks":[]}'
    assert _run(payload, tmp_path / "tty") == ""
