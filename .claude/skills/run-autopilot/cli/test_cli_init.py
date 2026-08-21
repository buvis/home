#!/usr/bin/env python3
"""Tests for cli/__main__.py's `init` subcommand: create-state wiring, the
exit-7 re-run guard, and the exit-11 missing-parent-dir diagnostic.

Split out of test_cli.py to keep it under the project's 800-line ceiling;
see test_cli.py's module docstring for the rest of the CLI subcommand test
map (stall/park/reset-prd/defer/restore, exits 5/9/10, and the cwd
independence matrix all stay there).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI_DIR = Path(__file__).resolve().parent
CLI_MAIN = CLI_DIR / "__main__.py"


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI_MAIN), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )


def _fresh_dir(testcase: unittest.TestCase) -> Path:
    tmp = tempfile.TemporaryDirectory()
    testcase.addCleanup(tmp.cleanup)
    return Path(tmp.name)


class _TempDirTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = _fresh_dir(self)


class InitTests(_TempDirTestCase):
    def test_creates_state_with_prd_phase_and_next_phase_fields(self) -> None:
        state_path = self.root / "state.json"

        proc = _run(
            ["init", "--state", str(state_path), "--prd", "00004-feature-x.md"],
            cwd=self.root,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        content = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(content["prd"], "00004-feature-x.md")
        self.assertEqual(content["phase"], "build")
        self.assertEqual(content["next_phase"], "build")

    def test_rerun_on_existing_state_exits_7_and_leaves_state_byte_unchanged(
        self,
    ) -> None:
        state_path = self.root / "state.json"
        args = ["init", "--state", str(state_path), "--prd", "00004-feature-x.md"]
        first = _run(args, cwd=self.root)
        self.assertEqual(first.returncode, 0, first.stderr)
        before = state_path.read_bytes()

        second = _run(args, cwd=self.root)

        self.assertEqual(second.returncode, 7)
        self.assertEqual(state_path.read_bytes(), before)

    def test_missing_state_parent_dir_exits_11_naming_the_directory_and_fix(
        self,
    ) -> None:
        state_path = self.root / "no-such-dir" / "state.json"

        proc = _run(
            ["init", "--state", str(state_path), "--prd", "00004-feature-x.md"],
            cwd=self.root,
        )

        # A crash from an uncaught exception exits 1, not 11 - pinning
        # returncode to exactly 11 rules that out.
        self.assertEqual(proc.returncode, 11)
        self.assertIn(str(state_path.parent), proc.stderr)
        self.assertIn("Phase 0 creates the lifecycle dirs", proc.stderr)


if __name__ == "__main__":
    unittest.main()
