#!/usr/bin/env python3
"""Tests for cli/policy.py (F5, the loop task ceiling) and the `autopilot
check-plan` subcommand that exposes it.

Two layers, matching the rest of the suite: the pure function is exercised
in-process, and the exit-code contract (0 under, 3 over) is pinned as a real
CLI process exit via subprocess, the way test_cli.py pins exits 5/9/10.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cli import policy

CLI_MAIN = Path(__file__).resolve().parent / "__main__.py"


def _state_with_tasks(count: int) -> dict:
    """A schema-valid state carrying `count` tasks, shaped like test_cli.py's
    _minimal_state."""
    return {
        "prd": "00004-feature-x.md",
        "phase": "build",
        "next_phase": "build",
        "cycle": 1,
        "tasks": [
            {"id": f"t{i}", "name": f"task {i}", "status": "pending"}
            for i in range(count)
        ],
    }


class PlanOverCeilingTests(unittest.TestCase):
    """The pure decision: the count comes from the snapshot, and the
    comparison is strictly greater-than."""

    def test_under_ceiling_is_not_over(self) -> None:
        over, count = policy.plan_over_ceiling(_state_with_tasks(14))
        self.assertFalse(over)
        self.assertEqual(count, 14)

    def test_exactly_at_ceiling_is_not_over(self) -> None:
        over, count = policy.plan_over_ceiling(_state_with_tasks(15))
        self.assertFalse(over, "the ceiling itself is allowed; only above it stalls")
        self.assertEqual(count, 15)

    def test_one_over_ceiling_is_over(self) -> None:
        over, count = policy.plan_over_ceiling(_state_with_tasks(16))
        self.assertTrue(over)
        self.assertEqual(count, 16)

    def test_ceiling_is_fifteen(self) -> None:
        self.assertEqual(policy.LOOP_TASK_CEILING, 15)

    def test_explicit_ceiling_overrides_the_default(self) -> None:
        over, _count = policy.plan_over_ceiling(_state_with_tasks(16), ceiling=20)
        self.assertFalse(over)

    def test_absent_tasks_field_counts_zero(self) -> None:
        over, count = policy.plan_over_ceiling({"prd": "x.md"})
        self.assertFalse(over, "nothing planned yet is not oversized")
        self.assertEqual(count, 0)

    def test_non_list_tasks_counts_zero_instead_of_raising(self) -> None:
        over, count = policy.plan_over_ceiling({"tasks": "not-a-list"})
        self.assertFalse(over)
        self.assertEqual(count, 0)

    def test_does_not_mutate_the_state_it_reads(self) -> None:
        state = _state_with_tasks(3)
        before = json.dumps(state, sort_keys=True)
        policy.plan_over_ceiling(state)
        self.assertEqual(json.dumps(state, sort_keys=True), before)


class CheckPlanCliTests(unittest.TestCase):
    """The exit-code contract as a real process exit."""

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CLI_MAIN), *args],
            capture_output=True,
            text=True,
        )

    def _write_state(self, tmp: Path, count: int) -> Path:
        state_path = tmp / "state.json"
        state_path.write_text(json.dumps(_state_with_tasks(count)), encoding="utf-8")
        return state_path

    def test_under_ceiling_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self._write_state(Path(tmp), 15)
            result = self._run(["check-plan", "--state", str(state_path)])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_over_ceiling_exits_three_and_names_both_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self._write_state(Path(tmp), 16)
            result = self._run(["check-plan", "--state", str(state_path)])
        self.assertEqual(result.returncode, 3)
        self.assertIn("16", result.stderr)
        self.assertIn("15", result.stderr)
        self.assertIn("oversized_plan", result.stderr)

    def test_ceiling_flag_is_honored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self._write_state(Path(tmp), 16)
            result = self._run(
                ["check-plan", "--state", str(state_path), "--ceiling", "20"]
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_parser_exposes_no_count_flag(self) -> None:
        """The count must never be suppliable by the caller being gated."""
        with tempfile.TemporaryDirectory() as tmp:
            state_path = self._write_state(Path(tmp), 16)
            result = self._run(
                ["check-plan", "--state", str(state_path), "--count", "3"]
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--count", result.stderr)

    def test_missing_state_fails_loud_rather_than_passing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "state.json"
            result = self._run(["check-plan", "--state", str(missing)])
        self.assertEqual(result.returncode, 2)
        self.assertIn("check-plan failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
