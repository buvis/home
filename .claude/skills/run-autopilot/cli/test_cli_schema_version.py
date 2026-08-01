#!/usr/bin/env python3
"""Tests for cli/__main__.py's schema-version handling on `reset-prd` and
`stall`:

  - an old-schema state (schema_version below current) warns on stderr but
    proceeds with the subcommand's normal effects, and the written state.json
    is re-stamped to the current schema version.
  - a future-schema state (schema_version above current) is refused with
    exit 6, BEFORE any effect: state.json byte-unchanged, no PRD moved, no
    deferred file created.
  - an unstamped state (no "schema_version" key at all) keeps today's silent
    -adopt behavior: normal exit, no version warning on stderr.

Runs the CLI as a real subprocess, mirroring test_cli.py's helpers and
fixture shapes. Library-level schema.version_status()/validate() semantics
are covered by test_schema.py; state.init()/state.restore() stamping is
covered by test_state.py. This file binds only the CLI-level warn/refuse
/silent-adopt wiring on reset-prd and stall.
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

# Pinned by the task brief: schema.SCHEMA_VERSION == 1 today.
CURRENT_VERSION = 1
OLD_VERSION = 0
FUTURE_VERSION = 99


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI_MAIN), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )


def _minimal_state(**overrides) -> dict:
    """A schema-valid state, shaped like test_cli.py's _minimal_state."""
    base = {
        "prd": "00004-feature-x.md",
        "phase": "build",
        "next_phase": "build",
        "cycle": 2,
        "tasks": [{"id": "t1", "name": "x", "status": "in_progress"}],
        "batch": {"id": "202607300000", "completed_prds": [], "parks_consecutive": 1},
    }
    base.update(overrides)
    return base


def _write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj), encoding="utf-8")


def _fresh_dir(testcase: unittest.TestCase) -> Path:
    tmp = tempfile.TemporaryDirectory()
    testcase.addCleanup(tmp.cleanup)
    return Path(tmp.name)


class _TempDirTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = _fresh_dir(self)


class _StallFixtureTestCase(_TempDirTestCase):
    PRD = "00004-feature-x.md"

    def setUp(self) -> None:
        super().setUp()
        self.autopilot_dir = self.root / "autopilot"
        self.autopilot_dir.mkdir()
        self.state_path = self.autopilot_dir / "state.json"
        self.prds_dir = self.root / "prds"
        (self.prds_dir / "wip").mkdir(parents=True)

    def _stall_args(self) -> list[str]:
        return [
            "stall",
            "--state", str(self.state_path),
            "--prd", self.PRD,
            "--site", "design_gate",
            "--detail", "detail text",
            "--prds", str(self.prds_dir),
        ]


class ResetPrdOldSchemaWarnsAndProceedsTest(_TempDirTestCase):
    def test_reset_prd_on_v0_state_exits_0_warns_on_stderr_and_restamps(self) -> None:
        state_path = self.root / "state.json"
        _write_json(state_path, _minimal_state(schema_version=OLD_VERSION))

        proc = _run(["reset-prd", "--state", str(state_path)], cwd=self.root)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("old-schema", proc.stderr)
        self.assertIn("v0", proc.stderr)
        self.assertIn("v1", proc.stderr)
        self.assertEqual(len(proc.stderr.splitlines()), 1)

        content = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(content["cycle"], 1)
        self.assertEqual(content["phase"], "build")
        self.assertNotIn("tasks", content)
        self.assertEqual(content["schema_version"], CURRENT_VERSION)


class StallOldSchemaWarnsAndProceedsTest(_StallFixtureTestCase):
    def test_stall_on_v0_state_exits_0_warns_on_stderr_and_restamps(self) -> None:
        (self.prds_dir / "wip" / self.PRD).write_text("prd body", encoding="utf-8")
        _write_json(self.state_path, _minimal_state(schema_version=OLD_VERSION))

        proc = _run(self._stall_args(), cwd=self.root)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("old-schema", proc.stderr)
        self.assertIn("v0", proc.stderr)
        self.assertIn("v1", proc.stderr)
        self.assertEqual(len(proc.stderr.splitlines()), 1)

        self.assertFalse((self.prds_dir / "wip" / self.PRD).exists())
        self.assertTrue((self.prds_dir / "hold" / self.PRD).exists())
        deferred_path = self.autopilot_dir / "deferred" / "202607300000-deferred.json"
        items = json.loads(deferred_path.read_text(encoding="utf-8"))["items"]
        self.assertEqual(len(items), 1)

        content = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(content["schema_version"], CURRENT_VERSION)


class ResetPrdFutureSchemaRefusedTest(_TempDirTestCase):
    def test_reset_prd_on_v99_state_exits_6_before_any_effect(self) -> None:
        state_path = self.root / "state.json"
        _write_json(state_path, _minimal_state(schema_version=FUTURE_VERSION))
        before = state_path.read_bytes()

        proc = _run(["reset-prd", "--state", str(state_path)], cwd=self.root)

        self.assertEqual(proc.returncode, 6)
        self.assertEqual(state_path.read_bytes(), before)
        self.assertIn("future", proc.stderr)
        self.assertEqual(len(proc.stderr.splitlines()), 1)


class StallFutureSchemaRefusedTest(_StallFixtureTestCase):
    def test_stall_on_v99_state_exits_6_before_any_effect(self) -> None:
        (self.prds_dir / "wip" / self.PRD).write_text("prd body", encoding="utf-8")
        _write_json(self.state_path, _minimal_state(schema_version=FUTURE_VERSION))
        before = self.state_path.read_bytes()

        proc = _run(self._stall_args(), cwd=self.root)

        self.assertEqual(proc.returncode, 6)
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertTrue((self.prds_dir / "wip" / self.PRD).exists())
        self.assertFalse((self.prds_dir / "hold" / self.PRD).exists())
        self.assertFalse((self.autopilot_dir / "deferred").exists())
        self.assertIn("future", proc.stderr)
        self.assertEqual(len(proc.stderr.splitlines()), 1)


class ResetPrdUnstampedStateSilentAdoptTest(_TempDirTestCase):
    def test_reset_prd_on_unstamped_state_exits_0_with_no_version_warning(self) -> None:
        state_path = self.root / "state.json"
        _write_json(state_path, _minimal_state())  # no "schema_version" key at all

        proc = _run(["reset-prd", "--state", str(state_path)], cwd=self.root)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("old-schema", proc.stderr)
        self.assertNotIn("future", proc.stderr)


if __name__ == "__main__":
    unittest.main()
