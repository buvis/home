"""Tests for skills/run-autopilot/scripts/autopilot_stop_hook.py.

Loaded via importlib because the hook lives outside ~/.claude/hooks/ and is
self-contained (no _common import). Covers stdin draining, signal-file gating,
parent-process traversal, and the SIGINT delivery path.
"""

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HOOK_PATH = (
    Path.home() / ".claude" / "skills" / "run-autopilot" / "scripts" / "autopilot_stop_hook.py"
)

# The hook imports sibling modules from its scripts/ dir (_walk_up, and the
# review_coverage_hook gate). Put that dir on sys.path so importlib can resolve
# them when this test runs from ~/.claude/hooks/tests/.
_SCRIPTS_DIR = str(HOOK_PATH.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


def _load_hook():
    spec = importlib.util.spec_from_file_location("autopilot_stop_hook", HOOK_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hook = _load_hook()


class TestParentOf(unittest.TestCase):
    def test_returns_int_when_ps_yields_digits(self) -> None:
        with patch.object(hook, "_ps", return_value="1234"):
            self.assertEqual(hook.parent_of(99), 1234)

    def test_returns_zero_when_ps_yields_garbage(self) -> None:
        with patch.object(hook, "_ps", return_value="not a pid"):
            self.assertEqual(hook.parent_of(99), 0)

    def test_returns_zero_when_ps_yields_empty(self) -> None:
        with patch.object(hook, "_ps", return_value=""):
            self.assertEqual(hook.parent_of(99), 0)


class TestCommFor(unittest.TestCase):
    def test_passes_through_ps_output(self) -> None:
        with patch.object(hook, "_ps", return_value="claude"):
            self.assertEqual(hook.comm_for(123), "claude")


class TestFindAndSignalClaude(unittest.TestCase):
    def test_signals_immediate_match(self) -> None:
        with patch.object(hook, "comm_for", return_value="claude"):
            with patch("os.kill") as kill:
                self.assertTrue(hook.find_and_signal_claude(500))
                kill.assert_called_once()
                args = kill.call_args[0]
                self.assertEqual(args[0], 500)

    def test_walks_up_until_claude(self) -> None:
        comms = {500: "node", 400: "bash", 300: "claude"}
        parents = {500: 400, 400: 300, 300: 1}
        with patch.object(hook, "comm_for", side_effect=lambda pid: comms.get(pid, "")):
            with patch.object(hook, "parent_of", side_effect=lambda pid: parents.get(pid, 0)):
                with patch("os.kill") as kill:
                    self.assertTrue(hook.find_and_signal_claude(500))
                    kill.assert_called_once()
                    self.assertEqual(kill.call_args[0][0], 300)

    def test_returns_false_when_no_match(self) -> None:
        with patch.object(hook, "comm_for", return_value="bash"):
            with patch.object(hook, "parent_of", side_effect=[400, 300, 1]):
                with patch("os.kill") as kill:
                    self.assertFalse(hook.find_and_signal_claude(500))
                    kill.assert_not_called()

    def test_stops_when_pid_does_not_advance(self) -> None:
        with patch.object(hook, "comm_for", return_value="bash"):
            with patch.object(hook, "parent_of", return_value=500):
                with patch("os.kill") as kill:
                    self.assertFalse(hook.find_and_signal_claude(500))
                    kill.assert_not_called()

    def test_returns_false_on_kill_oserror(self) -> None:
        with patch.object(hook, "comm_for", return_value="claude"):
            with patch("os.kill", side_effect=OSError("denied")):
                self.assertFalse(hook.find_and_signal_claude(500))


class TestEndToEnd(unittest.TestCase):
    def setUp(self) -> None:
        self.cwd = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.cwd)

    def _run(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HOOK_PATH)],
            input='{"hook_event_name":"Stop"}',
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(self.cwd),
        )

    def test_no_signal_file_is_noop(self) -> None:
        proc = self._run()
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(proc.stderr, "")

    def test_drains_stdin_without_error(self) -> None:
        proc = self._run()
        self.assertEqual(proc.returncode, 0)

    def test_with_signal_file_does_not_crash(self) -> None:
        signal_dir = self.cwd / "dev" / "local" / "autopilot"
        signal_dir.mkdir(parents=True)
        (signal_dir / "signal").write_text("", encoding="utf-8")
        proc = self._run()
        self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
