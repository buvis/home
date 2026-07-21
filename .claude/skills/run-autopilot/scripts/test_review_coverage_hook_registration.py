"""Contract test: review_coverage_hook.py must be wired as a Stop route in
hooks/dispatch.py's ROUTES table (PRD 00071 moved the per-handler Stop
registrations out of settings.json into ROUTES, so settings.json no longer
names this script). The retired orchestration hooks (PRD 00014) must not be
registered in settings.json or in ROUTES.

The coverage Stop hook is a backstop — if it is wired nowhere, a session ending
at a review handoff with incomplete coverage would not be blocked. The stop and
yield-clear hooks were deleted with the headless-loop conversion; a resurrected
registration would point at a nonexistent script on every Stop. This test
fails loud if either invariant breaks, or if settings.json is malformed.

Stdlib-only unittest.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

_CLAUDE_DIR = Path(__file__).resolve().parents[3]
_SETTINGS_PATH = _CLAUDE_DIR / "settings.json"
_HOOKS_DIR = _CLAUDE_DIR / "hooks"

_COVERAGE_HOOK_NAME = "review_coverage_hook.py"
_RETIRED_HOOKS = ("autopilot_stop_hook.py", "autopilot_yield_clear_hook.py")


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


def _load_dispatch():
    """Import hooks/dispatch.py by absolute path so dispatch.ROUTES can be
    inspected without relying on hooks/ already being on sys.path."""
    if "dispatch" in sys.modules:
        return sys.modules["dispatch"]
    if str(_HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_DIR))  # dispatch.py does `from _common import ...`
    spec = importlib.util.spec_from_file_location("dispatch", str(_HOOKS_DIR / "dispatch.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["dispatch"] = mod
    spec.loader.exec_module(mod)
    return mod


def _dispatch_route_basenames(event: str | None = None) -> list[str]:
    """Basenames of dispatch.ROUTES handler paths, optionally filtered to one
    event ("PreToolUse" / "PostToolUse" / "Stop")."""
    dispatch = _load_dispatch()
    return [Path(r.path).name for r in dispatch.ROUTES if event is None or r.event == event]


class ReviewCoverageHookRegistrationTests(unittest.TestCase):
    def test_settings_json_is_valid(self) -> None:
        # Must parse — a malformed settings.json breaks the harness.
        json.loads(_SETTINGS_PATH.read_text())

    def test_coverage_hook_registered_as_stop_route(self) -> None:
        self.assertIn(
            _COVERAGE_HOOK_NAME,
            _dispatch_route_basenames("Stop"),
            "review_coverage_hook.py must be wired as a Stop route in "
            "hooks/dispatch.py's ROUTES table; the coverage Stop hook is a "
            "backstop - if it is wired nowhere, a session ending at a "
            "review handoff with incomplete coverage would not be blocked",
        )

    def test_retired_orchestration_hooks_not_registered(self) -> None:
        # PRD 00014 deleted these scripts; a registration would fail every Stop.
        route_basenames = _dispatch_route_basenames()
        for retired in _RETIRED_HOOKS:
            for cmd in _hook_commands():
                self.assertNotIn(
                    retired,
                    cmd,
                    f"{retired} was retired by PRD 00014 and must not be "
                    "registered in settings.json",
                )
            self.assertNotIn(
                retired,
                route_basenames,
                f"{retired} was retired by PRD 00014 and must not be "
                "registered in hooks/dispatch.py's ROUTES table",
            )


if __name__ == "__main__":
    unittest.main()
