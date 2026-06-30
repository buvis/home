"""Tests for autopilot_yield_clear_hook.py.

Covers exactly the 6 acceptance criteria from the hook spec:
1. Removes .yielded-waiting when present and cwd is inside an autopilot run.
2. No-op (no error) when the marker is absent.
3. No-op when cwd is not under any autopilot dir (resolver returns None).
4. An OSError from unlink does not propagate out of main().
5. A matcher-less registration entry is present in settings.json PostToolUse.
6. settings.json parses as valid JSON.

Stdlib-only unittest. Run via:
    python3 test_autopilot_yield_clear_hook.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

# Same-dir import — add the scripts directory so `import autopilot_yield_clear_hook` resolves.
sys.path.insert(0, str(Path(__file__).parent))

import autopilot_yield_clear_hook

_SETTINGS_PATH = Path(__file__).resolve().parents[3] / "settings.json"
_YIELD_CLEAR_HOOK_CMD = (
    "python3 ~/.claude/skills/run-autopilot/scripts/autopilot_yield_clear_hook.py"
)
_MARKER_NAME = ".yielded-waiting"


def _make_autopilot_tree(root: Path) -> Path:
    """Create dev/local/autopilot/ under root; return the autopilot dir."""
    autopilot = root / "dev" / "local" / "autopilot"
    autopilot.mkdir(parents=True)
    return autopilot


class YieldClearHookBehaviorTests(unittest.TestCase):
    """Behavior tests: real temp tree, real chdir, assertions on file existence."""

    def setUp(self) -> None:
        self._orig_cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        self._root = Path(self._tmp.name)
        self._autopilot_dir = _make_autopilot_tree(self._root)
        os.chdir(self._root)

    def tearDown(self) -> None:
        os.chdir(self._orig_cwd)
        self._tmp.cleanup()

    def test_removes_marker_when_present(self) -> None:
        """AC1: .yielded-waiting is deleted when it exists and cwd is under autopilot."""
        marker = self._autopilot_dir / _MARKER_NAME
        marker.write_text("")
        self.assertTrue(marker.exists())

        autopilot_yield_clear_hook.main()

        self.assertFalse(marker.exists(), "marker must be removed after main()")

    def test_no_op_when_marker_absent(self) -> None:
        """AC2: main() does not raise when the marker file is absent."""
        marker = self._autopilot_dir / _MARKER_NAME
        self.assertFalse(marker.exists())

        autopilot_yield_clear_hook.main()  # must not raise

        self.assertFalse(marker.exists())

    def test_unlink_oserror_does_not_propagate(self) -> None:
        """AC4: an OSError raised by unlink must not escape main()."""
        marker = self._autopilot_dir / _MARKER_NAME
        marker.write_text("")

        with unittest.mock.patch.object(Path, "unlink", side_effect=OSError("blocked")):
            autopilot_yield_clear_hook.main()  # must not raise


class YieldClearHookNoAutopilotDirTests(unittest.TestCase):
    """Tests for the case where cwd has no autopilot ancestor."""

    def setUp(self) -> None:
        self._orig_cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        # Plain temp dir — no dev/local/autopilot/ anywhere in the tree.
        os.chdir(self._tmp.name)

    def tearDown(self) -> None:
        os.chdir(self._orig_cwd)
        self._tmp.cleanup()

    def test_no_op_when_not_under_autopilot_dir(self) -> None:
        """AC3: main() does not raise when the dir-resolver returns None."""
        autopilot_yield_clear_hook.main()  # must not raise


class YieldClearHookRegistrationTests(unittest.TestCase):
    """Registration tests: settings.json must be valid and contain the hook."""

    def test_settings_json_is_valid(self) -> None:
        """AC6: settings.json parses as valid JSON."""
        json.loads(_SETTINGS_PATH.read_text())

    def test_yield_clear_hook_registered_matcher_less_in_post_tool_use(self) -> None:
        """AC5: command is present in a matcher-less PostToolUse entry.

        Matcher-less means: no 'matcher' key, or matcher == "".
        """
        data = json.loads(_SETTINGS_PATH.read_text())
        for entry in data.get("hooks", {}).get("PostToolUse", []):
            matcher = entry.get("matcher")
            if matcher is not None and matcher != "":
                continue  # Entry has a real matcher — not matcher-less.
            for hook in entry.get("hooks", []):
                if hook.get("command") == _YIELD_CLEAR_HOOK_CMD:
                    return  # Found a matcher-less entry with the correct command.
        self.fail(
            f"{_YIELD_CLEAR_HOOK_CMD!r} not found as a matcher-less entry "
            "in hooks.PostToolUse (no 'matcher' key or matcher == '')"
        )


if __name__ == "__main__":
    unittest.main()
