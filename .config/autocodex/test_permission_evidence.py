from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

import driver
from test_anthropic_routes import kiro_events, parsed


@pytest.mark.parametrize(
    "denial",
    [
        {"_meta": {"kiro": {"policyDenial": {"effect": "deny", "capability": "fs_read"}}}},
        {
            "rawOutput": {
                "message": "Output:\nThe permission request failed before it was answered, so this call did not run; the user did not reject it.\n\nExit Code: -1"
            }
        },
    ],
)
def test_tool_denial_survives_successful_finish(denial: dict) -> None:
    rows = kiro_events()
    rows.insert(
        -1,
        {
            "type": "sessionUpdate",
            "data": {
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "status": "failed",
                    **denial,
                }
            },
        },
    )
    events = parsed("kiro", rows)
    assert events.permission_denied
    assert not events.success


def test_stderr_denial_overrides_zero_exit(tmp_path: Path) -> None:
    script = tmp_path / "backend.py"
    script.write_text(
        "import json,sys\n"
        "sys.stderr.write('[denied] tool permission approval is not supported in non-interactive mode. Use --trust-all-tools to auto-approve.\\n')\n"
        f"rows = {kiro_events()!r}\n"
        "for row in rows: print(json.dumps(row))\n"
    )
    result = driver.run_process(
        [sys.executable, str(script)],
        "",
        tmp_path,
        dict(os.environ),
        tmp_path / "raw",
        30,
        provider="kiro",
    )
    assert result.returncode == 0
    assert result.events.permission_denied
    assert not result.ok


def test_success_cannot_override_permission_flag(tmp_path: Path) -> None:
    events = driver.Events("kiro", success=True, permission_denied=True)
    assert not driver.Result(0, tmp_path / "raw", events, False).ok


def test_file_contents_mentioning_denial_are_not_policy_events() -> None:
    rows = kiro_events()
    rows.insert(
        -1,
        {
            "type": "sessionUpdate",
            "data": {
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "status": "completed",
                    "rawOutput": {
                        "message": "The permission request failed before it was answered"
                    },
                }
            },
        },
    )
    assert parsed("kiro", rows).success


def test_denial_stops_routes_and_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import create_autospec

    events = parsed("kiro", kiro_events("\n".join(f"D{n}: pass" for n in range(1, 6))))
    driver.check_permission_stderr(
        events, b"[denied] tool permission approval is not supported in non-interactive mode."
    )
    run = create_autospec(
        driver.run_process, return_value=driver.Result(0, tmp_path / "raw", events, False)
    )
    monkeypatch.setattr(driver, "run_process", run)
    monkeypatch.setenv("AUTOCODEX_ANTHROPIC_BACKENDS", "kiro,copilot,claude")
    prompt = tmp_path / "prompt"
    prompt.write_text("review")
    out = tmp_path / "out"
    assert driver.review(prompt, out, "opus", tmp_path, "claude") == 1
    assert run.call_count == 1
    assert not out.exists()
    assert not out.with_suffix(".receipt.json").exists()
