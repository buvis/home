#!/usr/bin/env python3
"""Sanctioned test for PRD 00051 review cycle 1 task #14, Item 4: importing
cli.records must not leave scripts/ on sys.path as a side effect.

The hazard it guards has shrunk twice and the assertion still holds. It was a
lazily-scoped insert -> import -> remove around `park_decision`, imported from
scripts/resume_target.py. PRD 00089 absorbed that function into cli/resume.py,
so records now reaches it as an ordinary package import and touches sys.path
nowhere at all. The test stays because the invariant is what matters, not the
mechanism: a future module-level `sys.path.insert(scripts_dir)` in records
would fail it again.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

_CLI_DIR = Path(__file__).resolve().parent
_SKILL_ROOT = _CLI_DIR.parent
_SCRIPTS_DIR = _SKILL_ROOT / "scripts"


class ImportHygieneTests(unittest.TestCase):
    def test_import_cli_records_does_not_leave_scripts_dir_on_sys_path(self) -> None:
        code = (
            "import sys; "
            f"sys.path.insert(0, {str(_SKILL_ROOT)!r}); "
            "import cli.records; "
            f"print({str(_SCRIPTS_DIR)!r} in sys.path)"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "False")


if __name__ == "__main__":
    unittest.main()
