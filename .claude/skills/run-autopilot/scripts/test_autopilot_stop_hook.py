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


if __name__ == "__main__":
    unittest.main()
