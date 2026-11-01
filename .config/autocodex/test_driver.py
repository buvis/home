from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, create_autospec

import pytest

import driver


@pytest.mark.parametrize(
    ("tier", "expected"),
    [
        ("sonnet", "gpt-6.1-sol"),
        ("claude-opus-5[1m]", "gpt-6.1-sol"),
        ("haiku", "gpt-6-luna"),
        ("gpt-5.6-terra", "gpt-5.6-terra"),
    ],
)
def test_model_roles(tier: str, expected: str) -> None:
    assert driver.codex_model(tier, {}) == expected


def test_unknown_claude_model_refused() -> None:
    with pytest.raises(ValueError):
        driver.codex_model("claude-fable-5", {})


def test_fast_track_handoff_is_detected() -> None:
    assert driver.is_fast_track_handoff(
        Path("docs/dev/project-management/plans/fast-track-handoffs/00004/rework-11.md")
    )
    assert not driver.is_fast_track_handoff(Path("scope.md"))
    assert not driver.is_fast_track_handoff(None)


def test_driver_uses_codex_native_flags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(driver.sys, "platform", "linux")
    argv = driver.codex_argv("codex", "gpt-6.1-sol", "high", tmp_path)
    assert argv[:3] == ["codex", "exec", "--json"]
    assert "--approve-for-me" in argv
    assert argv[-1] == "-"
    assert "--permission-mode" not in argv
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv
    assert "resume" not in argv


@pytest.mark.parametrize(
    ("status", "error", "protected"),
    [(1, 0, True), (0, 0, False), (-1, 1, False), (2, 0, False), (1, 1, False)],
)
def test_codex_sandbox_selection_requires_verified_seatbelt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    error: int,
    protected: bool,
) -> None:
    monkeypatch.setattr(driver.sys, "platform", "darwin")

    def check(_pid: int, operation: bytes | None, filter_type: int) -> int:
        ctypes.set_errno(error)
        return status

    probe = create_autospec(check, side_effect=check)
    library = create_autospec(ctypes.CDLL, return_value=SimpleNamespace(sandbox_check=probe))
    monkeypatch.setattr(ctypes, "CDLL", library)
    ctypes.set_errno(99)

    argv = driver.codex_argv("codex", "gpt-6.1-sol", "high", tmp_path)

    library.assert_called_once_with("/usr/lib/libsandbox.dylib", use_errno=True)
    probe.assert_called_once_with(os.getpid(), None, 0)
    assert probe.argtypes == [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    assert probe.restype is ctypes.c_int
    assert ("--approve-for-me" not in argv) is protected
    assert ("--sandbox" in argv) is protected
    if protected:
        assert argv[argv.index("--sandbox") + 1] == "danger-full-access"
        assert 'approval_policy="on-request"' in argv
        assert 'approvals_reviewer="auto_review"' in argv
        assert "--ask-for-approval" not in argv  # exec does not accept this flag.
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_non_darwin_does_not_probe_or_disable_native_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    monkeypatch.setattr(driver.sys, "platform", platform)
    library = create_autospec(ctypes.CDLL)
    monkeypatch.setattr(ctypes, "CDLL", library)
    argv = driver.codex_argv("codex", "gpt-6.1-sol", "low", tmp_path)
    library.assert_not_called()
    assert "--approve-for-me" in argv
    assert "danger-full-access" not in argv


@pytest.mark.parametrize("error", [OSError("probe unavailable"), AttributeError("missing symbol")])
def test_seatbelt_probe_error_preserves_native_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    monkeypatch.setattr(driver.sys, "platform", "darwin")
    library = create_autospec(ctypes.CDLL, side_effect=error)
    monkeypatch.setattr(ctypes, "CDLL", library)
    argv = driver.codex_argv("codex", "gpt-6.1-sol", "low", tmp_path)
    library.assert_called_once()
    assert "--approve-for-me" in argv
    assert "danger-full-access" not in argv


def test_gpt_reviewer_uses_the_shared_sandbox_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(driver.sys, "platform", "darwin")
    probe = Mock(return_value=1)
    monkeypatch.setattr(
        ctypes,
        "CDLL",
        create_autospec(ctypes.CDLL, return_value=SimpleNamespace(sandbox_check=probe)),
    )
    result = driver.Result(0, tmp_path / "raw.jsonl", driver.Events("codex", success=True), False)
    process = create_autospec(driver.run_process, return_value=result)
    monkeypatch.setattr(driver, "run_process", process)
    assert (
        driver.run_reviewer("review", tmp_path / "review.md", "gpt-6.1-sol", tmp_path, "codex")
        is result
    )
    argv = process.call_args.args[0]
    assert argv[argv.index("--sandbox") + 1] == "danger-full-access"
    assert 'approval_policy="on-request"' in argv
    assert 'approvals_reviewer="auto_review"' in argv


def test_external_reviewer_is_claude() -> None:
    argv = driver.claude_argv("claude", "opus")
    assert argv[0] == "claude"
    assert argv[argv.index("--permission-prompts") + 1] == "none"
    assert "--dangerously-skip-permissions" not in argv


@pytest.mark.parametrize(
    "events",
    [
        [{"type": "turn.failed", "error": {"message": "quota"}}],
        [{"type": "item.completed", "item": {"type": "agent_message", "text": "done"}}],
        [{"type": "turn.completed"}, {"type": "turn.failed"}],
    ],
)
def test_exit_zero_without_successful_terminal_event_fails(events: list[dict]) -> None:
    result = driver.Events("codex")
    for event in events:
        result.accept(json.dumps(event).encode())
    assert not result.success


def test_tolerant_events_preserve_real_completion() -> None:
    result = driver.Events("codex")
    result.accept(b"not json")
    result.accept(b"[]")
    result.accept(b'{"type":"future.event","value":42}')
    result.accept(
        b'{"type":"item.completed","item":{"type":"agent_message","text":"quota test passed"}}'
    )
    result.accept(b'{"type":"turn.completed","usage":{"output_tokens":9}}')
    assert result.success
    assert result.text == "quota test passed"
    assert result.usage == {"output_tokens": 9}


def test_claude_failure_is_not_a_success() -> None:
    result = driver.Events("claude")
    result.accept(b'{"type":"result","is_error":true,"result":"failed"}')
    assert not result.success


def test_real_process_captures_raw_and_stderr(tmp_path: Path) -> None:
    code = 'import sys; print("noise"); print(\'{"type":"turn.completed"}\'); print("diagnostic",file=sys.stderr)'
    result = driver.run_process(
        [sys.executable, "-c", code],
        "prompt",
        tmp_path,
        dict(os.environ),
        tmp_path / "run",
        5,
        provider="codex",
    )
    assert result.ok
    assert result.log.read_bytes().startswith(b"noise\n")
    assert result.log.with_suffix(".stderr").read_text() == "diagnostic\n"


def test_nonzero_process_cannot_certify_completion(tmp_path: Path) -> None:
    code = 'print(\'{"type":"turn.completed"}\'); raise SystemExit(7)'
    result = driver.run_process(
        [sys.executable, "-c", code],
        "",
        tmp_path,
        dict(os.environ),
        tmp_path / "run",
        5,
        provider="codex",
    )
    assert not result.ok
    assert result.returncode == 7


def test_stall_timeout_kills_child_group(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    code = (
        "import subprocess,time,pathlib,sys; "
        'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(90)"]); '
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid)); time.sleep(90)"
    )
    started = time.monotonic()
    result = driver.run_process(
        [sys.executable, "-c", code],
        "",
        tmp_path,
        dict(os.environ),
        tmp_path / "run",
        0.3,
        provider="codex",
        grace=0.1,
    )
    assert result.stalled
    assert "no substantive activity" in result.events.error
    assert time.monotonic() - started < 5
    child = int(pid_file.read_text())
    status = subprocess.run(["ps", "-o", "stat=", "-p", str(child)], capture_output=True, text=True)
    assert not status.stdout.strip() or status.stdout.strip().startswith("Z")


def test_stall_timeout_is_bounded_when_child_keeps_stdout_open(tmp_path: Path) -> None:
    code = (
        "import subprocess,sys; "
        'subprocess.Popen([sys.executable,"-c","import time; time.sleep(90)"]); '
        'print(\'{"type":"turn.completed"}\')'
    )
    result = driver.run_process(
        [sys.executable, "-c", code],
        "",
        tmp_path,
        dict(os.environ),
        tmp_path / "run",
        0.3,
        provider="codex",
        grace=0.1,
    )
    assert not result.ok
    assert result.stalled


def test_substantive_events_keep_a_long_session_alive(tmp_path: Path) -> None:
    code = """
import json
import time

for item in range(6):
    print(json.dumps({"type": "item.completed", "item": {
        "id": f"item_{item}", "type": "command_execution", "status": "completed"
    }}), flush=True)
    time.sleep(0.08)
print(json.dumps({"type": "turn.completed"}), flush=True)
"""
    result = driver.run_process(
        [sys.executable, "-c", code],
        "",
        tmp_path,
        dict(os.environ),
        tmp_path / "run",
        0.15,
        provider="codex",
        grace=0.1,
    )
    assert result.ok
    assert not result.stalled


def test_wait_churn_does_not_hide_a_stall(tmp_path: Path) -> None:
    code = """
import json
import time

while True:
    print(json.dumps({"type": "item.completed", "item": {
        "id": "wait", "type": "collab_tool_call", "tool": "wait", "status": "completed"
    }}), flush=True)
    time.sleep(0.04)
"""
    result = driver.run_process(
        [sys.executable, "-c", code],
        "",
        tmp_path,
        dict(os.environ),
        tmp_path / "run",
        0.2,
        provider="codex",
        grace=0.1,
    )
    assert result.stalled


def test_workspace_changes_keep_a_waiting_session_alive(tmp_path: Path) -> None:
    marker = tmp_path / "subagent-work"
    code = f"""
import json
import pathlib
import time

marker = pathlib.Path({str(marker)!r})
for item in range(6):
    marker.write_text(str(item))
    print(json.dumps({{"type": "item.completed", "item": {{
        "id": "wait", "type": "collab_tool_call", "tool": "wait", "status": "completed"
    }}}}), flush=True)
    time.sleep(0.08)
print(json.dumps({{"type": "turn.completed"}}), flush=True)
"""
    result = driver.run_process(
        [sys.executable, "-c", code],
        "",
        tmp_path,
        dict(os.environ),
        tmp_path / "run",
        0.15,
        provider="codex",
        grace=0.1,
    )
    assert result.ok
    assert not result.stalled


def test_claude_reviewer_environment_preserves_guards() -> None:
    env = {"_AUTOPILOT_LOOP": "123", "CODEX_SESSION_ID": "host", "AUTOPILOT_DISPATCH_DEPTH": "1"}
    output = driver.reviewer_env(env)
    assert "_AUTOPILOT_LOOP" not in output
    assert output["CODEX_SESSION_ID"] == "host"
    assert output["AUTOPILOT_DISPATCH_DEPTH"] == "1"
    assert output["CLAUDE_NESTED"] == "1"


def test_bob_missing_rubric_is_not_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Review")
    output = tmp_path / "review.md"
    output.write_text("prior evidence")
    events = driver.Events("claude")
    events.accept(b'{"type":"result","is_error":false,"result":"looks good"}')
    result = driver.Result(0, tmp_path / "raw.jsonl", events, False)
    monkeypatch.setattr(driver, "run_process", lambda *args, **kwargs: result)
    assert driver.review(prompt, output, "opus", tmp_path, "claude") != 0
    assert output.read_text() == "prior evidence"
