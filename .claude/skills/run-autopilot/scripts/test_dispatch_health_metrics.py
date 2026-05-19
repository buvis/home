"""Tests for dispatch_health_metrics.py — CLI contract requirements.

Covers:
  - outcome counts and dispatch_type counts in default report
  - hang rate (hung / total)
  - p50 and p95 of duration_s per dispatch_type over completed dispatches
  - top recurring failure tasks (grouped by task_name)
  - empty log file → graceful zero-state report, exit 0
  - missing log file → graceful zero-state report, exit 0
  - log with only completed entries → hang rate 0
  - --deadletter mode: lists non-completed entries grouped by task_name, newest-first
  - --deadletter: flags recurring at exactly 3+ failures; not at 2
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT: Path = Path(__file__).parent / "dispatch_health_metrics.py"


def _run_script(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Invoke dispatch_health_metrics.py with the given CLI args."""
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        capture_output=True,
        text=True,
    )


def _jsonl_line(
    ts: str,
    prd: str,
    task_id: str,
    task_name: str,
    dispatch_type: str,
    model: str,
    outcome: str,
    duration_s: float,
    attempt: int,
) -> str:
    return json.dumps(
        {
            "ts": ts,
            "prd": prd,
            "task_id": task_id,
            "task_name": task_name,
            "dispatch_type": dispatch_type,
            "model": model,
            "outcome": outcome,
            "duration_s": duration_s,
            "attempt": attempt,
        }
    )


class TestDefaultReportOutcomeCounts(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.log = Path(self._tmpdir) / "dispatch-log.jsonl"

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_outcome_counts_present_in_report(self) -> None:
        # 2 completed, 1 hung — report must show counts BY outcome.
        # A line mentioning "completed" must also contain "2";
        # a line mentioning "hung" must also contain "1".
        entries = [
            _jsonl_line("2026-01-01T00:00:00Z", "prd-1", "t1", "task-alpha", "codex", "sonnet", "completed", 10.0, 1),
            _jsonl_line("2026-01-01T00:01:00Z", "prd-1", "t2", "task-beta", "gemini", "sonnet", "completed", 12.0, 1),
            _jsonl_line("2026-01-01T00:02:00Z", "prd-1", "t3", "task-gamma", "codex", "sonnet", "hung", 300.0, 1),
        ]
        self.log.write_text("\n".join(entries) + "\n")
        result = _run_script([str(self.log)])
        self.assertEqual(result.returncode, 0)
        lines = result.stdout.splitlines()

        completed_lines = [ln for ln in lines if "completed" in ln]
        self.assertTrue(completed_lines, "Report must contain a line with 'completed'")
        self.assertTrue(
            any("2" in ln for ln in completed_lines),
            f"Line(s) mentioning 'completed' must contain the count 2; got: {completed_lines}",
        )

        hung_lines = [ln for ln in lines if "hung" in ln]
        self.assertTrue(hung_lines, "Report must contain a line with 'hung'")
        self.assertTrue(
            any("1" in ln for ln in hung_lines),
            f"Line(s) mentioning 'hung' must contain the count 1; got: {hung_lines}",
        )

    def test_dispatch_type_counts_present_in_report(self) -> None:
        # 2 codex, 1 gemini — report must show counts BY dispatch_type.
        # A line mentioning "codex" must also contain "2";
        # a line mentioning "gemini" must also contain "1".
        entries = [
            _jsonl_line("2026-01-01T00:00:00Z", "prd-1", "t1", "task-alpha", "codex", "sonnet", "completed", 5.0, 1),
            _jsonl_line("2026-01-01T00:01:00Z", "prd-1", "t2", "task-beta", "codex", "sonnet", "completed", 8.0, 1),
            _jsonl_line("2026-01-01T00:02:00Z", "prd-1", "t3", "task-gamma", "gemini", "sonnet", "completed", 6.0, 1),
        ]
        self.log.write_text("\n".join(entries) + "\n")
        result = _run_script([str(self.log)])
        self.assertEqual(result.returncode, 0)
        lines = result.stdout.splitlines()

        codex_lines = [ln for ln in lines if "codex" in ln]
        self.assertTrue(codex_lines, "Report must contain a line with 'codex'")
        self.assertTrue(
            any("2" in ln for ln in codex_lines),
            f"Line(s) mentioning 'codex' must contain the count 2; got: {codex_lines}",
        )

        gemini_lines = [ln for ln in lines if "gemini" in ln]
        self.assertTrue(gemini_lines, "Report must contain a line with 'gemini'")
        self.assertTrue(
            any("1" in ln for ln in gemini_lines),
            f"Line(s) mentioning 'gemini' must contain the count 1; got: {gemini_lines}",
        )


class TestHangRate(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.log = Path(self._tmpdir) / "dispatch-log.jsonl"

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_hang_rate_counts_hung_outcomes(self) -> None:
        # 1 hung out of 4 total = 25%.
        # Wrong impl counting errors-as-hung would show a different value.
        # "25" must appear as a standalone number — "125" or "250" must not satisfy.
        import re

        entries = [
            _jsonl_line("2026-01-01T00:00:00Z", "prd-1", "t1", "task-a", "codex", "sonnet", "completed", 10.0, 1),
            _jsonl_line("2026-01-01T00:01:00Z", "prd-1", "t2", "task-b", "codex", "sonnet", "completed", 10.0, 1),
            _jsonl_line("2026-01-01T00:02:00Z", "prd-1", "t3", "task-c", "codex", "sonnet", "completed", 10.0, 1),
            _jsonl_line("2026-01-01T00:03:00Z", "prd-1", "t4", "task-d", "codex", "sonnet", "hung", 300.0, 1),
        ]
        self.log.write_text("\n".join(entries) + "\n")
        result = _run_script([str(self.log)])
        self.assertEqual(result.returncode, 0)
        found = False
        for ln in result.stdout.splitlines():
            if "hang" in ln.lower():
                self.assertRegex(
                    ln,
                    r"(^|[^0-9])25([^0-9]|$)",
                    "Hang rate line must show 25 (word-bounded) for 1/4 dispatches",
                )
                found = True
                break
        self.assertTrue(found, "Report must contain a hang rate line")

    def test_hang_rate_zero_when_no_hung_outcomes(self) -> None:
        # All completed — hang rate must be 0.
        entries = [
            _jsonl_line("2026-01-01T00:00:00Z", "prd-1", "t1", "task-a", "codex", "sonnet", "completed", 10.0, 1),
            _jsonl_line("2026-01-01T00:01:00Z", "prd-1", "t2", "task-b", "gemini", "sonnet", "completed", 12.0, 1),
        ]
        self.log.write_text("\n".join(entries) + "\n")
        result = _run_script([str(self.log)])
        self.assertEqual(result.returncode, 0)
        found = False
        for ln in result.stdout.splitlines():
            if "hang" in ln.lower():
                self.assertIn("0", ln, "Hang rate must be 0 when no hung outcomes")
                self.assertNotIn("50", ln)
                self.assertNotIn("100", ln)
                found = True
                break
        self.assertTrue(found, "Report must contain a hang rate line")


class TestPercentiles(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.log = Path(self._tmpdir) / "dispatch-log.jsonl"

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_p50_and_p95_labels_present_in_report(self) -> None:
        # 4 codex completed dispatches — p50 and p95 labels must appear.
        entries = [
            _jsonl_line("2026-01-01T00:00:00Z", "prd-1", "t1", "task-a", "codex", "sonnet", "completed", 10.0, 1),
            _jsonl_line("2026-01-01T00:01:00Z", "prd-1", "t2", "task-b", "codex", "sonnet", "completed", 20.0, 1),
            _jsonl_line("2026-01-01T00:02:00Z", "prd-1", "t3", "task-c", "codex", "sonnet", "completed", 30.0, 1),
            _jsonl_line("2026-01-01T00:03:00Z", "prd-1", "t4", "task-d", "codex", "sonnet", "completed", 40.0, 1),
        ]
        self.log.write_text("\n".join(entries) + "\n")
        result = _run_script([str(self.log)])
        self.assertEqual(result.returncode, 0)
        out_lower = result.stdout.lower()
        self.assertIn("p50", out_lower)
        self.assertIn("p95", out_lower)

    def test_p50_is_median_not_mean(self) -> None:
        # Skewed durations [10, 11, 12, 13, 100] for codex completed.
        # Median = 12.  Mean = 29.2.
        # A "p50 = mean" implementation reports ~29 and must fail.
        entries = [
            _jsonl_line("2026-01-01T00:00:00Z", "prd-1", "t1", "task-a", "codex", "sonnet", "completed", 10.0, 1),
            _jsonl_line("2026-01-01T00:01:00Z", "prd-1", "t2", "task-b", "codex", "sonnet", "completed", 11.0, 1),
            _jsonl_line("2026-01-01T00:02:00Z", "prd-1", "t3", "task-c", "codex", "sonnet", "completed", 12.0, 1),
            _jsonl_line("2026-01-01T00:03:00Z", "prd-1", "t4", "task-d", "codex", "sonnet", "completed", 13.0, 1),
            _jsonl_line("2026-01-01T00:04:00Z", "prd-1", "t5", "task-e", "codex", "sonnet", "completed", 100.0, 1),
        ]
        self.log.write_text("\n".join(entries) + "\n")
        result = _run_script([str(self.log)])
        self.assertEqual(result.returncode, 0)
        out_lower = result.stdout.lower()

        # Find the line(s) carrying the p50 value.
        p50_lines = [ln for ln in result.stdout.splitlines() if "p50" in ln.lower()]
        self.assertTrue(p50_lines, "Report must contain a p50 line")

        # Extract all numbers from p50 line(s) and verify the p50 value is the
        # median (near 12), not the mean (near 29).
        import re
        p50_numbers: list[float] = []
        for ln in p50_lines:
            p50_numbers.extend(float(m) for m in re.findall(r"\d+(?:\.\d+)?", ln))

        # At least one number on the p50 line must be in the median range [11, 13].
        near_median = [n for n in p50_numbers if 11 <= n <= 13]
        self.assertTrue(
            near_median,
            f"p50 value must be near the median (12), not the mean (29). "
            f"Numbers found on p50 line(s): {p50_numbers}",
        )
        # Confirm the mean (≈29) is NOT reported as the p50 value.
        near_mean = [n for n in p50_numbers if 25 <= n <= 34]
        self.assertFalse(
            near_mean,
            f"p50 value must not reflect the arithmetic mean (~29); "
            f"numbers found on p50 line(s): {p50_numbers}",
        )

    def test_percentiles_exclude_non_completed_dispatches(self) -> None:
        # 2 completed codex (10s, 20s) + 1 hung codex (9999s).
        # Wrong impl including hung in sample would show 9999 as p95.
        # Also: p95 must lie within [p50, max_completed=20] — not pinning
        # the exact interpolation method, just bounding the value.
        entries = [
            _jsonl_line("2026-01-01T00:00:00Z", "prd-1", "t1", "task-a", "codex", "sonnet", "completed", 10.0, 1),
            _jsonl_line("2026-01-01T00:01:00Z", "prd-1", "t2", "task-b", "codex", "sonnet", "completed", 20.0, 1),
            _jsonl_line("2026-01-01T00:02:00Z", "prd-1", "t3", "task-c", "codex", "sonnet", "hung", 9999.0, 1),
        ]
        self.log.write_text("\n".join(entries) + "\n")
        result = _run_script([str(self.log)])
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("9999", result.stdout)

        import re

        lines = result.stdout.splitlines()

        # Collect the p50 value for codex.
        p50_lines = [ln for ln in lines if "p50" in ln.lower()]
        self.assertTrue(p50_lines, "Report must contain a p50 line")
        p50_nums = [float(m) for ln in p50_lines for m in re.findall(r"\d+(?:\.\d+)?", ln)]
        p50_value = min(p50_nums, key=lambda v: abs(v - 15))  # pick closest to expected median

        # Collect the p95 value for codex.
        p95_lines = [ln for ln in lines if "p95" in ln.lower()]
        self.assertTrue(p95_lines, "Report must contain a p95 line")
        p95_nums = [float(m) for ln in p95_lines for m in re.findall(r"\d+(?:\.\d+)?", ln)]
        p95_value = min(p95_nums, key=lambda v: abs(v - 20))  # pick closest to expected max

        self.assertLessEqual(
            p95_value, 20,
            f"p95 must be ≤ max of completed sample (20); got {p95_value}",
        )
        self.assertGreaterEqual(
            p95_value, p50_value,
            f"p95 ({p95_value}) must be ≥ p50 ({p50_value})",
        )


    def test_p95_is_high_percentile_not_mean(self) -> None:
        # Asymmetric durations [10, 11, 12, 300] for codex completed.
        # Mean ≈ 83.25.  95th percentile ≥ 200 by any standard method
        # (nearest-rank → 300; linear interpolation → ~283).
        # A mean-based wrong implementation reports ~83 and must fail.
        import re

        entries = [
            _jsonl_line("2026-01-01T00:00:00Z", "prd-1", "t1", "task-a", "codex", "sonnet", "completed", 10.0, 1),
            _jsonl_line("2026-01-01T00:01:00Z", "prd-1", "t2", "task-b", "codex", "sonnet", "completed", 11.0, 1),
            _jsonl_line("2026-01-01T00:02:00Z", "prd-1", "t3", "task-c", "codex", "sonnet", "completed", 12.0, 1),
            _jsonl_line("2026-01-01T00:03:00Z", "prd-1", "t4", "task-d", "codex", "sonnet", "completed", 300.0, 1),
        ]
        self.log.write_text("\n".join(entries) + "\n")
        result = _run_script([str(self.log)])
        self.assertEqual(result.returncode, 0)

        lines = result.stdout.splitlines()
        p95_lines = [ln for ln in lines if "p95" in ln.lower()]
        self.assertTrue(p95_lines, "Report must contain a p95 line")

        p95_nums = [float(m) for ln in p95_lines for m in re.findall(r"\d+(?:\.\d+)?", ln)]
        p95_value = min(p95_nums, key=lambda v: abs(v - 300))  # pick closest to expected high value

        self.assertGreaterEqual(
            p95_value, 200,
            f"p95 must be a high percentile (≥ 200), not a central-tendency stat like the mean (~83); "
            f"numbers found on p95 line(s): {p95_nums}",
        )


class TestTopRecurringFailures(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.log = Path(self._tmpdir) / "dispatch-log.jsonl"

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_recurring_failure_task_name_appears_in_default_report(self) -> None:
        # task-flaky fails 3 times; task-stable always completes.
        # Wrong impl omitting failures section would not show task-flaky.
        # task-stable must be absent — a task that never failed has no place
        # in a failure-metrics report.
        entries = [
            _jsonl_line("2026-01-01T00:00:00Z", "prd-1", "t1", "task-flaky", "codex", "sonnet", "error", 5.0, 1),
            _jsonl_line("2026-01-01T00:01:00Z", "prd-2", "t2", "task-flaky", "codex", "sonnet", "error", 5.0, 1),
            _jsonl_line("2026-01-01T00:02:00Z", "prd-3", "t3", "task-flaky", "codex", "sonnet", "error", 5.0, 1),
            _jsonl_line("2026-01-01T00:03:00Z", "prd-1", "t4", "task-stable", "codex", "sonnet", "completed", 10.0, 1),
        ]
        self.log.write_text("\n".join(entries) + "\n")
        result = _run_script([str(self.log)])
        self.assertEqual(result.returncode, 0)
        self.assertIn("task-flaky", result.stdout)
        self.assertNotIn(
            "task-stable", result.stdout,
            "A task that only completed must not appear in a failure-metrics report",
        )


class TestEmptyAndMissingLog(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_empty_log_exits_zero(self) -> None:
        log = Path(self._tmpdir) / "dispatch-log.jsonl"
        log.write_text("")
        result = _run_script([str(log)])
        self.assertEqual(result.returncode, 0)

    def test_empty_log_no_traceback(self) -> None:
        log = Path(self._tmpdir) / "dispatch-log.jsonl"
        log.write_text("")
        result = _run_script([str(log)])
        self.assertNotIn("Traceback", result.stderr)

    def test_missing_log_exits_zero(self) -> None:
        log = Path(self._tmpdir) / "does-not-exist.jsonl"
        result = _run_script([str(log)])
        self.assertEqual(result.returncode, 0)

    def test_missing_log_no_traceback(self) -> None:
        log = Path(self._tmpdir) / "does-not-exist.jsonl"
        result = _run_script([str(log)])
        self.assertNotIn("Traceback", result.stderr)


class TestDeadletterMode(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.log = Path(self._tmpdir) / "dispatch-log.jsonl"

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_deadletter_lists_non_completed_and_omits_completed(self) -> None:
        # Completed task must be absent; failed tasks must be present.
        entries = [
            _jsonl_line("2026-01-01T00:00:00Z", "prd-1", "t1", "task-good", "codex", "sonnet", "completed", 10.0, 1),
            _jsonl_line("2026-01-01T00:01:00Z", "prd-1", "t2", "task-bad", "codex", "sonnet", "error", 5.0, 1),
            _jsonl_line("2026-01-01T00:02:00Z", "prd-1", "t3", "task-hung", "gemini", "sonnet", "hung", 300.0, 1),
        ]
        self.log.write_text("\n".join(entries) + "\n")
        result = _run_script(["--deadletter", str(self.log)])
        self.assertEqual(result.returncode, 0)
        out = result.stdout
        self.assertIn("task-bad", out)
        self.assertIn("task-hung", out)
        self.assertNotIn("task-good", out)

    def test_deadletter_flags_recurring_at_three_failures(self) -> None:
        # Exactly 3 failures — must emit the literal word "recurring".
        # Wrong impl with threshold=4 would not emit "recurring".
        entries = [
            _jsonl_line("2026-01-01T00:00:00Z", "prd-1", "t1", "task-trouble", "codex", "sonnet", "error", 5.0, 1),
            _jsonl_line("2026-01-01T00:01:00Z", "prd-2", "t2", "task-trouble", "codex", "sonnet", "timeout", 5.0, 1),
            _jsonl_line("2026-01-01T00:02:00Z", "prd-3", "t3", "task-trouble", "codex", "sonnet", "hung", 5.0, 1),
        ]
        self.log.write_text("\n".join(entries) + "\n")
        result = _run_script(["--deadletter", str(self.log)])
        self.assertEqual(result.returncode, 0)
        self.assertIn("recurring", result.stdout)

    def test_deadletter_does_not_flag_recurring_at_two_failures(self) -> None:
        # Exactly 2 failures — must NOT emit "recurring".
        # Wrong impl with threshold=2 would incorrectly flag this.
        entries = [
            _jsonl_line("2026-01-01T00:00:00Z", "prd-1", "t1", "task-almost", "codex", "sonnet", "error", 5.0, 1),
            _jsonl_line("2026-01-01T00:01:00Z", "prd-2", "t2", "task-almost", "codex", "sonnet", "error", 5.0, 1),
        ]
        self.log.write_text("\n".join(entries) + "\n")
        result = _run_script(["--deadletter", str(self.log)])
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("recurring", result.stdout.lower())

    def test_deadletter_newest_first_within_group(self) -> None:
        # Two failures for task-sorted: 2026-01-01 (older) and 2026-01-02 (newer).
        # Newer must appear at a lower string offset than older.
        entries = [
            _jsonl_line("2026-01-01T00:00:00Z", "prd-1", "t1", "task-sorted", "codex", "sonnet", "error", 5.0, 1),
            _jsonl_line("2026-01-02T00:00:00Z", "prd-2", "t2", "task-sorted", "codex", "sonnet", "error", 5.0, 1),
        ]
        self.log.write_text("\n".join(entries) + "\n")
        result = _run_script(["--deadletter", str(self.log)])
        self.assertEqual(result.returncode, 0)
        out = result.stdout
        pos_newer = out.find("2026-01-02")
        pos_older = out.find("2026-01-01")
        self.assertGreater(pos_newer, -1, "newer timestamp not found in output")
        self.assertGreater(pos_older, -1, "older timestamp not found in output")
        self.assertLess(pos_newer, pos_older, "newer entry must precede older entry within group")

    def test_deadletter_empty_log_exits_zero_no_crash(self) -> None:
        log = Path(self._tmpdir) / "empty.jsonl"
        log.write_text("")
        result = _run_script(["--deadletter", str(log)])
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
