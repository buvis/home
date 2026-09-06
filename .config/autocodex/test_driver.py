from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import driver


@pytest.mark.parametrize(
    ("tier", "expected"),
    [
        ("sonnet", "gpt-5.6-sol"),
        ("claude-opus-5[1m]", "gpt-6-astra"),
        ("haiku", "gpt-5.6-luna"),
        ("gpt-5.6-terra", "gpt-5.6-terra"),
    ],
)
def test_model_roles(tier: str, expected: str) -> None:
    assert driver.codex_model(tier, {}) == expected


def test_unknown_claude_model_refused() -> None:
    with pytest.raises(ValueError):
        driver.codex_model("claude-fable-5", {})


def test_driver_uses_codex_native_flags(tmp_path: Path) -> None:
    argv = driver.codex_argv("codex", "gpt-5.6-sol", "high", tmp_path)
    assert argv[:3] == ["codex", "exec", "--json"]
    assert "--approve-for-me" in argv
    assert argv[-1] == "-"
    assert "--permission-mode" not in argv
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv
    assert "resume" not in argv


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


def test_wall_cap_kills_child_group(tmp_path: Path) -> None:
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
    assert result.capped
    assert time.monotonic() - started < 5
    child = int(pid_file.read_text())
    status = subprocess.run(["ps", "-o", "stat=", "-p", str(child)], capture_output=True, text=True)
    assert not status.stdout.strip() or status.stdout.strip().startswith("Z")


def test_timeout_is_bounded_when_child_keeps_stdout_open(tmp_path: Path) -> None:
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
    assert result.capped


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
