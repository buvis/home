"""Contract test: review_coverage_hook.py must be registered in settings.json's
Stop array, and the retired orchestration hooks (PRD 00014) must NOT be.

The coverage Stop hook is a backstop — if it is not registered, a session ending
at a review handoff with incomplete coverage would not be blocked. The stop and
yield-clear hooks were deleted with the headless-loop conversion; a resurrected
registration would point at a nonexistent script on every Stop. This test fails
loud if either invariant breaks or settings.json is malformed.

Stdlib-only unittest.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

_SETTINGS_PATH = Path(__file__).resolve().parents[3] / "settings.json"

_COVERAGE_HOOK_CMD = (
    "python3 ~/.claude/skills/run-autopilot/scripts/review_coverage_hook.py"
)
def _hook_commands() -> list[str]:
    data = json.loads(_SETTINGS_PATH.read_text())
    commands: list[str] = []
    for entries in data.get("hooks", {}).values():
        for entry in entries:
            for hook in entry.get("hooks", []):
                cmd = hook.get("command")
                if cmd is not None:
                    commands.append(cmd)
    return commands


def _stop_commands() -> list[str]:
    data = json.loads(_SETTINGS_PATH.read_text())
    commands: list[str] = []
    for entry in data.get("hooks", {}).get("Stop", []):
        for hook in entry.get("hooks", []):
            cmd = hook.get("command")
            if cmd is not None:
                commands.append(cmd)
    return commands


class ReviewCoverageHookRegistrationTests(unittest.TestCase):
    def test_settings_json_is_valid(self) -> None:
        # Must parse — a malformed settings.json breaks the harness.
        json.loads(_SETTINGS_PATH.read_text())

    def test_coverage_hook_registered_in_stop_array(self) -> None:
        self.assertIn(
            _COVERAGE_HOOK_CMD,
            _stop_commands(),
            "review_coverage_hook.py must be registered in hooks.Stop",
        )

    def test_retired_orchestration_hooks_not_registered(self) -> None:
        # PRD 00014 deleted these scripts; a registration would fail every Stop.
        for retired in ("autopilot_stop_hook.py", "autopilot_yield_clear_hook.py"):
            for cmd in _hook_commands():
                self.assertNotIn(
                    retired,
                    cmd,
                    f"{retired} was retired by PRD 00014 and must not be registered",
                )


if __name__ == "__main__":
    unittest.main()
