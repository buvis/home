"""Tests for autopilot_stop_hook.find_signal_file.

Covers the walk-up logic added 2026-05-11: the hook can be invoked with cwd
in a subdirectory after the agent `cd`s during a session. The relative
`dev/local/autopilot/signal` lookup used to silently miss the signal in
that case, leaving the loop wedged.

Stdlib-only unittest. Imports the module directly (no subprocess).
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOOK_PATH = Path(__file__).parent / "autopilot_stop_hook.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "autopilot_stop_hook_under_test", HOOK_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load_module()


class FindSignalFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _write_signal(self, parent: Path) -> Path:
        sig_dir = parent / "dev" / "local" / "autopilot"
        sig_dir.mkdir(parents=True, exist_ok=True)
        sig = sig_dir / "signal"
        sig.write_text("next\n")
        return sig

    def test_finds_signal_at_cwd(self) -> None:
        sig = self._write_signal(self.root)
        result = hook.find_signal_file(self.root)
        self.assertIsNotNone(result)
        self.assertEqual(result.resolve(), sig.resolve())

    def test_finds_signal_at_parent(self) -> None:
        # Simulates the observed bug: agent cd'd into a subdir,
        # signal lives at the project root.
        sig = self._write_signal(self.root)
        subdir = self.root / "skills" / "run-autopilot" / "scripts"
        subdir.mkdir(parents=True)
        result = hook.find_signal_file(subdir)
        self.assertIsNotNone(result)
        self.assertEqual(result.resolve(), sig.resolve())

    def test_finds_signal_deep_ancestor(self) -> None:
        sig = self._write_signal(self.root)
        deep = self.root / "a" / "b" / "c" / "d" / "e"
        deep.mkdir(parents=True)
        result = hook.find_signal_file(deep)
        self.assertIsNotNone(result)
        self.assertEqual(result.resolve(), sig.resolve())

    def test_no_signal_anywhere_returns_none(self) -> None:
        subdir = self.root / "no" / "signal" / "here"
        subdir.mkdir(parents=True)
        self.assertIsNone(hook.find_signal_file(subdir))

    def test_signal_in_sibling_does_not_match(self) -> None:
        sibling = self.root / "sibling"
        sibling.mkdir()
        self._write_signal(sibling)
        other = self.root / "other"
        other.mkdir()
        self.assertIsNone(hook.find_signal_file(other))

    def test_prefers_nearest_ancestor(self) -> None:
        # Signal at root and at intermediate — nearest (intermediate) wins.
        self._write_signal(self.root)
        intermediate = self.root / "inner"
        intermediate.mkdir()
        nearer_sig = self._write_signal(intermediate)
        deep = intermediate / "x" / "y"
        deep.mkdir(parents=True)
        result = hook.find_signal_file(deep)
        self.assertEqual(result.resolve(), nearer_sig.resolve())


class FindAndSignalClaudeProcessMatchTests(unittest.TestCase):
    """The Stop hook walks the process tree to SIGINT the claude process.

    The match must be an EXACT process basename, not a substring: a sibling
    helper named `claude-helper` (or any `*claude*`) must not be mistaken for
    the loop's claude process and killed.
    """

    def _run(self, comms, parents, start_pid):
        killed: list[int] = []
        with mock.patch.object(hook, "comm_for", lambda pid: comms.get(pid, "")), \
                mock.patch.object(hook, "parent_of", lambda pid: parents.get(pid, 0)), \
                mock.patch.object(hook.os, "kill", lambda pid, sig: killed.append(pid)):
            result = hook.find_and_signal_claude(start_pid)
        return result, killed

    def test_substring_claude_not_matched(self) -> None:
        # 'claude-helper' must NOT be treated as the claude process.
        result, killed = self._run(
            comms={100: "claude-helper", 50: "bash", 1: "init"},
            parents={100: 50, 50: 1},
            start_pid=100,
        )
        self.assertFalse(result)
        self.assertEqual(killed, [])

    def test_exact_claude_matched(self) -> None:
        result, killed = self._run(
            comms={100: "node", 50: "claude", 1: "init"},
            parents={100: 50, 50: 1},
            start_pid=100,
        )
        self.assertTrue(result)
        self.assertEqual(killed, [50])

    def test_full_path_comm_basename_matched(self) -> None:
        # Some `ps` variants print a full path in comm; basename must match.
        result, killed = self._run(
            comms={100: "/usr/local/bin/claude", 1: "init"},
            parents={100: 1},
            start_pid=100,
        )
        self.assertTrue(result)
        self.assertEqual(killed, [100])


if __name__ == "__main__":
    unittest.main()
