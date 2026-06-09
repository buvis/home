"""Contract test: review_coverage_hook.py must be registered in settings.json's
Stop array alongside autopilot_stop_hook.py.

The coverage Stop hook is a backstop — if it is not registered, a session ending
at a review handoff with incomplete coverage would not be blocked. This test
fails loud if the registration is missing or settings.json is malformed.

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
_STOP_HOOK_CMD = (
    "python3 ~/.claude/skills/run-autopilot/scripts/autopilot_stop_hook.py"
)


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

    def test_autopilot_stop_hook_still_registered(self) -> None:
        # The new hook must be added alongside, not replace, the existing one.
        self.assertIn(
            _STOP_HOOK_CMD,
            _stop_commands(),
            "autopilot_stop_hook.py must remain registered in hooks.Stop",
        )


if __name__ == "__main__":
    unittest.main()
