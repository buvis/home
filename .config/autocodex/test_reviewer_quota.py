from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import create_autospec

import pytest

import driver


def rejected(reset: object = 130, status: object = 429) -> driver.Events:
    events = driver.Events("claude")
    events.accept(
        json.dumps(
            {
                "type": "rate_limit_event",
                "rate_limit_info": {"status": "rejected", "resetsAt": reset},
            }
        ).encode()
    )
    events.accept(
        json.dumps(
            {
                "type": "result",
                "is_error": True,
                "api_error_status": status,
                "result": "Session limit",
            }
        ).encode()
    )
    return events


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    now = [100.0]
    monkeypatch.setattr(driver.time, "time", lambda: now[0])
    monkeypatch.setattr(driver.time, "monotonic", lambda: now[0])

    def sleep(seconds: float) -> None:
        assert 0 < seconds <= 60
        now[0] += seconds

    monkeypatch.setattr(driver.time, "sleep", sleep)
    monkeypatch.setenv("_AUTOPILOT_LIMIT_WAIT_MAX", "300")
    monkeypatch.setenv("AUTOCODEX_REVIEWER_STALL_TIMEOUT", "1800")
    return now


def runner(monkeypatch: pytest.MonkeyPatch, events: list[driver.Events]) -> object:
    pending = iter(events)

    def run(*args: object, **kwargs: object) -> driver.Result:
        event = next(pending)
        stem = args[4]
        assert isinstance(stem, Path)
        raw = stem.with_suffix(".jsonl")
        with raw.open("x") as file:
            file.write(event.text or event.error)
        stem.with_suffix(".stderr").touch()
        return driver.Result(0 if event.success else 1, raw, event, False)

    mock = create_autospec(driver.run_process, side_effect=run)
    monkeypatch.setattr(driver, "run_process", mock)
    return mock


def review(tmp_path: Path) -> int:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Review")
    return driver.review(prompt, tmp_path / "bob.md", "opus", tmp_path, "claude")


def success() -> driver.Events:
    return driver.Events("claude", success=True, text="\n".join(f"D{n}: pass" for n in range(1, 6)))


def test_quota_wait_retries_and_publishes_only_successful_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clock: list[float],
) -> None:
    run = runner(monkeypatch, [rejected(), success()])
    assert review(tmp_path) == 0
    assert clock[0] >= 130
    assert run.call_count == 2
    assert len(list(tmp_path.glob("*.jsonl"))) == 2
    receipt = json.loads((tmp_path / "bob.md.receipt.json").read_text())
    assert Path(receipt["raw"]).read_text() == success().text
    assert (tmp_path / "bob.md").read_text() == success().text


@pytest.mark.parametrize(
    "reset,status",
    [
        (None, 429),
        (True, 429),
        ("130", 429),
        (float("inf"), 429),
        (float("nan"), 429),
        (10**400, 429),
        (99, 429),
        (1000, 429),
        (130, 401),
        (130, "429"),
    ],
)
def test_unusable_or_unbounded_reset_does_not_retry_or_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clock: list[float],
    reset: object,
    status: object,
) -> None:
    run = runner(monkeypatch, [rejected(reset, status)])
    assert review(tmp_path) == 1
    assert clock[0] == 100
    assert run.call_count == 1
    assert not (tmp_path / "bob.md").exists()
    assert not (tmp_path / "bob.md.receipt.json").exists()


def test_repeated_expired_reset_does_not_spin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clock: list[float],
) -> None:
    run = runner(monkeypatch, [rejected(), rejected()])
    assert review(tmp_path) == 1
    assert run.call_count == 2
    assert not (tmp_path / "bob.md.receipt.json").exists()


def test_reviewer_uses_configured_stall_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clock: list[float],
) -> None:
    monkeypatch.setenv("AUTOCODEX_REVIEWER_STALL_TIMEOUT", "77")
    run = runner(monkeypatch, [success()])
    assert review(tmp_path) == 0
    assert run.call_count == 1
    assert run.call_args.args[5] == 77


def test_pause_during_wait_prevents_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clock: list[float],
) -> None:
    ap = tmp_path / "docs/dev/project-management/autopilot"
    ap.mkdir(parents=True)

    def pause(seconds: float) -> None:
        clock[0] += seconds
        (ap / "pause-requested").touch()

    monkeypatch.setattr(driver.time, "sleep", pause)
    run = runner(monkeypatch, [rejected()])
    assert review(tmp_path) == 1
    assert run.call_count == 1
    assert not (tmp_path / "bob.md.receipt.json").exists()


def test_incomplete_rubric_after_quota_retry_is_not_published(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clock: list[float],
) -> None:
    run = runner(monkeypatch, [rejected(), driver.Events("claude", success=True, text="D1: pass")])
    assert review(tmp_path) == 1
    assert run.call_count == 2
    assert not (tmp_path / "bob.md.receipt.json").exists()


def test_total_wait_budget_bounds_multiple_advancing_resets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clock: list[float],
) -> None:
    monkeypatch.setenv("_AUTOPILOT_LIMIT_WAIT_MAX", "60")
    run = runner(monkeypatch, [rejected(130), rejected(170)])
    assert review(tmp_path) == 1
    assert run.call_count == 2
    assert clock[0] == 135
    assert not (tmp_path / "bob.md.receipt.json").exists()


def test_elapsed_deadline_after_suspension_does_not_launch_another_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clock: list[float],
) -> None:
    def suspend(seconds: float) -> None:
        clock[0] += 1000

    monkeypatch.setattr(driver.time, "sleep", suspend)
    run = runner(monkeypatch, [rejected()])
    assert review(tmp_path) == 1
    assert run.call_count == 1


@pytest.mark.parametrize("info", [None, [], "rejected", {"status": "allowed", "resetsAt": 130}])
def test_latest_nonrejected_or_malformed_limit_clears_rejection(info: object) -> None:
    events = rejected()
    events.accept(json.dumps({"type": "rate_limit_event", "rate_limit_info": info}).encode())
    assert events.quota_reset is None


def test_reviewer_cli_waits_for_real_process_reset_and_retains_attempts(tmp_path: Path) -> None:
    fake = tmp_path / "fake-claude"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import json,pathlib,sys,time\n"
        "sys.stdin.read()\n"
        "counter=pathlib.Path('calls.jsonl')\n"
        "first=not counter.exists()\n"
        "with counter.open('a') as f: f.write(json.dumps({'at':time.time()})+'\\n')\n"
        "if first:\n"
        " print(json.dumps({'type':'rate_limit_event','rate_limit_info':"
        "{'status':'rejected','resetsAt':time.time()+0.1}}))\n"
        " print(json.dumps({'type':'result','is_error':True,'api_error_status':429,'result':'limit'}))\n"
        " sys.exit(1)\n"
        "print(json.dumps({'type':'result','is_error':False,'result':"
        "'\\n'.join(f'D{n}: pass' for n in range(1,6))}))\n"
    )
    fake.chmod(0o700)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Synthetic quota test")
    output = tmp_path / "bob.md"
    env = dict(os.environ, AUTOCODEX_CLAUDE_BIN=str(fake), _AUTOPILOT_LIMIT_WAIT_MAX="20")
    result = subprocess.run(
        [
            sys.executable,
            str(driver.HERE / "driver.py"),
            "--cd",
            str(tmp_path),
            "reviewer",
            "-f",
            str(prompt),
            "-o",
            str(output),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    calls = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert len(calls) == 2
    assert calls[1]["at"] - calls[0]["at"] >= 5
    assert len(list(tmp_path.glob("bob-*.jsonl"))) == 2
    receipt = json.loads(Path(str(output) + ".receipt.json").read_text())
    assert json.loads(Path(receipt["raw"]).read_text())["is_error"] is False
    assert "Claude quota exhausted; waiting until" in result.stdout
