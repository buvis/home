from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import create_autospec

import pytest

import anthropic_routes
import driver


def kiro_events(text: str = "D1: pass", model: str = "claude-opus-5.5") -> list[dict]:
    return [
        {
            "type": "sessionUpdate",
            "data": {
                "sessionId": "review",
                "update": {
                    "sessionUpdate": "config_option_update",
                    "configOptions": [
                        {"id": "model", "currentValue": model},
                        {"id": "effortLevel", "currentValue": "xhigh"},
                    ],
                },
            },
        },
        {
            "type": "sessionUpdate",
            "data": {
                "update": {
                    "_meta": {
                        "kiro": {
                            "kind": "turn_start",
                        }
                    }
                }
            },
        },
        {
            "type": "runFinished",
            "data": {
                "status": "success",
                "stopReason": "end_turn",
                "finalText": text,
                "finalTextTruncated": False,
            },
        },
    ]


def parsed(provider: str, rows: list[dict]) -> driver.Events:
    events = driver.Events(provider)
    for row in rows:
        events.accept(json.dumps(row).encode())
    return events


def test_kiro_result_retains_identity() -> None:
    events = parsed("kiro", kiro_events())
    assert events.success
    assert events.text == "D1: pass"
    assert events.models == {"claude-opus-5.5"}
    assert events.efforts == {"xhigh"}


@pytest.mark.parametrize("status,truncated", [("error", False), ("success", True)])
def test_kiro_partial_result_cannot_certify(status: str, truncated: bool) -> None:
    rows = kiro_events()
    rows[-1]["data"].update(status=status, finalTextTruncated=truncated)
    assert not parsed("kiro", rows).success


def test_copilot_quota_is_not_success() -> None:
    events = parsed(
        "copilot",
        [
            {
                "type": "model.call_failure",
                "data": {
                    "statusCode": 402,
                    "errorCode": "quota_exceeded",
                    "errorMessage": "monthly quota",
                },
            },
            {"type": "result", "exitCode": 1},
        ],
    )
    assert events.api_status == 402
    assert not events.success


def test_copilot_result_retains_identity() -> None:
    events = parsed(
        "copilot",
        [
            {"type": "user.message", "data": {"responsesReasoning": {"effort": "xhigh"}}},
            {"type": "model.call_start", "data": {"model": "claude-opus-5.5"}},
            {"type": "assistant.message", "data": {"content": "D1: pass"}},
            {"type": "result", "exitCode": 0, "sessionId": "review"},
        ],
    )
    assert events.success
    assert events.text == "D1: pass"
    assert events.models == {"claude-opus-5.5"}
    assert events.efforts == {"xhigh"}


def test_quota_tries_alternative_before_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUTOCODEX_ANTHROPIC_BACKENDS", "claude,kiro,copilot")
    quota = driver.Events("claude", api_status=429, quota_reset=driver.time.time() + 3600)
    available = parsed("kiro", kiro_events())
    run = create_autospec(
        driver.run_process,
        side_effect=[
            driver.Result(1, tmp_path / "claude.jsonl", quota, False),
            driver.Result(0, tmp_path / "kiro.jsonl", available, False),
        ],
    )
    wait = create_autospec(driver.wait_for_reviewer_quota, return_value=False)
    monkeypatch.setattr(driver, "run_process", run)
    monkeypatch.setattr(driver, "wait_for_reviewer_quota", wait)
    result = driver.run_reviewer("review", tmp_path / "out", "opus", tmp_path, "claude")
    assert result.ok
    assert [call.kwargs["provider"] for call in run.call_args_list] == ["claude", "kiro"]
    wait.assert_not_called()


def test_permission_failure_does_not_change_launcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUTOCODEX_ANTHROPIC_BACKENDS", "claude,kiro,copilot")
    failed = driver.Result(
        1, tmp_path / "raw", driver.Events("claude", error="permission denied"), False
    )
    run = create_autospec(driver.run_process, return_value=failed)
    monkeypatch.setattr(driver, "run_process", run)
    assert driver.run_reviewer("review", tmp_path / "out", "opus", tmp_path, "claude") == failed
    assert run.call_count == 1


def test_wrong_model_cannot_publish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOCODEX_ANTHROPIC_BACKENDS", "kiro")
    text = "\n".join(f"D{n}: pass" for n in range(1, 6))
    wrong = parsed("kiro", kiro_events(text, "gpt-6.1-sol"))
    run = create_autospec(
        driver.run_process, return_value=driver.Result(0, tmp_path / "raw", wrong, False)
    )
    monkeypatch.setattr(driver, "run_process", run)
    prompt = tmp_path / "prompt"
    prompt.write_text("review")
    assert driver.review(prompt, tmp_path / "out", "opus", tmp_path, "claude") == 1
    assert not (tmp_path / "out.receipt.json").exists()


def test_default_routes_prefer_available_alternatives() -> None:
    assert anthropic_routes.backends({}) == ["kiro", "copilot", "claude"]


@pytest.mark.parametrize("value", ["auto", "kiro,kiro", "", "unknown"])
def test_invalid_route_configuration_is_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        anthropic_routes.backends({"AUTOCODEX_ANTHROPIC_BACKENDS": value})


def test_model_override_cannot_change_tier() -> None:
    with pytest.raises(ValueError):
        anthropic_routes.concrete_model(
            "opus", {"AUTOCODEX_ANTHROPIC_OPUS_MODEL": "claude-haiku-5.5"}
        )


@pytest.mark.parametrize("route", ["kiro", "copilot"])
def test_alternate_review_process_and_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    import sys

    text = "\n".join(f"D{n}: pass" for n in range(1, 6))
    rows = (
        kiro_events(text)
        if route == "kiro"
        else [
            {"type": "user.message", "data": {"responsesReasoning": {"effort": "xhigh"}}},
            {"type": "model.call_start", "data": {"model": "claude-opus-5.5"}},
            {"type": "assistant.message", "data": {"content": text}},
            {"type": "result", "exitCode": 0, "sessionId": "review"},
        ]
    )
    fake = tmp_path / "backend"
    fake.write_text(
        f"#!{sys.executable}\nimport json,sys,pathlib\n"
        "assert '--model' in sys.argv and 'claude-opus-5.5' in sys.argv\n"
        "assert 'xhigh' in sys.argv\n"
        "assert sys.stdin.read() == ''\n"
        "assert sys.argv[-1] == 'Review with `quotes` and $literal'\n"
        f"rows={rows!r}\nfor row in rows: print(json.dumps(row))\n"
    )
    fake.chmod(0o700)
    monkeypatch.setenv("AUTOCODEX_ANTHROPIC_BACKENDS", route)
    monkeypatch.setenv(f"AUTOCODEX_{route.upper()}_BIN", str(fake))
    prompt = tmp_path / "prompt"
    prompt.write_text("Review with `quotes` and $literal")
    out = tmp_path / "review.md"
    assert driver.review(prompt, out, "opus", tmp_path, "claude") == 0
    receipt = json.loads((tmp_path / "review.md.receipt.json").read_text())
    assert receipt["provider"] == route
    assert receipt["model_provider"] == "anthropic"
    assert receipt["model"] == "claude-opus-5.5"
    assert receipt["effort"] == "xhigh"
    assert out.read_text() == text
    # The completion gate must accept authentic alternative evidence and reject tampering.
    sys.path.insert(0, str(driver.skill_root()))
    import adapter

    stamp = f"autocodex_bob_anthropic_receipt: {out}.receipt.json"
    assert adapter.bob_gap(stamp, tmp_path, 1, "", provider="anthropic") is None
    receipt["model"] = "claude-opus-5"
    Path(str(out) + ".receipt.json").write_text(json.dumps(receipt))
    assert "model/effort" in adapter.bob_gap(stamp, tmp_path, 1, "", provider="anthropic")


def test_missing_cli_tries_next_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOCODEX_ANTHROPIC_BACKENDS", "kiro,claude")
    done = driver.Result(0, tmp_path / "raw", driver.Events("claude", success=True), False)
    run = create_autospec(driver.run_process, side_effect=[FileNotFoundError(), done])
    monkeypatch.setattr(driver, "run_process", run)
    assert driver.run_reviewer("review", tmp_path / "out", "opus", tmp_path, "claude") == done
    assert run.call_count == 2


def test_pause_prevents_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pause = tmp_path / "docs/dev/project-management/autopilot/pause-requested"
    pause.parent.mkdir(parents=True)
    pause.touch()
    run = create_autospec(driver.run_process)
    monkeypatch.setattr(driver, "run_process", run)
    with pytest.raises(ValueError, match="operator pause"):
        driver.run_reviewer("review", tmp_path / "out", "opus", tmp_path, "claude")
    run.assert_not_called()
