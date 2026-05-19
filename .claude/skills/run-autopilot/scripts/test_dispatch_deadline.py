"""Tests for dispatch_deadline.py — adaptive watchdog deadline computation.

Covers:
  - cold-start (<5 successful samples) → 900
  - boundary: exactly 4 samples (cold-start) vs 5 (computed path)
  - p95*2 in range [300, 900] → computed value
  - p95*2 below 300 → clamps up to 300
  - p95*2 above 900 → clamps down to 900
  - only `completed` outcomes for the matching dispatch_type count
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent / "dispatch_deadline.py"


def _make_log(entries: list[dict]) -> str:
    return "\n".join(json.dumps(e) for e in entries) + "\n"


def _entry(
    dispatch_type: str,
    outcome: str,
    duration_s: float,
    ts: str = "2026-01-01T00:00:00Z",
    prd: str = "test-prd",
    task_id: str = "t1",
    task_name: str = "task",
    model: str = "sonnet",
    attempt: int = 1,
) -> dict:
    return {
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


def _run_deadline(dispatch_type: str, log_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), dispatch_type, str(log_path)],
        capture_output=True,
        text=True,
    )


class TestColdStart(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.root = Path(self._tmpdir)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_log(self, entries: list[dict]) -> Path:
        p = self.root / "dispatch-log.jsonl"
        p.write_text(_make_log(entries))
        return p

    def test_cold_start_zero_samples_returns_900(self) -> None:
        # No entries at all — 0 completed samples for "tess"
        log = self._write_log([])
        result = _run_deadline("tess", log)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "900")

    def test_cold_start_four_samples_returns_900(self) -> None:
        # Exactly 4 completed entries for "ivan" — boundary just below threshold
        entries = [
            _entry("ivan", "completed", 100.0, task_id=str(i))
            for i in range(4)
        ]
        log = self._write_log(entries)
        result = _run_deadline("ivan", log)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "900")

    def test_five_samples_switches_to_computed_path(self) -> None:
        # Exactly 5 completed entries — must NOT return 900 when p95*2 != 900.
        # 5 identical durations of 200s → p95 = 200, p95*2 = 400 (unambiguous).
        entries = [
            _entry("devon", "completed", 200.0, task_id=str(i))
            for i in range(5)
        ]
        log = self._write_log(entries)
        result = _run_deadline("devon", log)
        self.assertEqual(result.returncode, 0)
        value = int(result.stdout.strip())
        self.assertNotEqual(
            value, 900, "5 samples should use computed path, not cold-start 900"
        )
        self.assertEqual(value, 400)

    def test_cold_start_ignores_non_completed_outcomes(self) -> None:
        # 4 completed + many hung/error for "reviewer" — still cold-start
        completed = [
            _entry("reviewer", "completed", 150.0, task_id=str(i))
            for i in range(4)
        ]
        noise = [
            _entry("reviewer", "hung", 500.0, task_id=str(i + 10))
            for i in range(10)
        ]
        log = self._write_log(completed + noise)
        result = _run_deadline("reviewer", log)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "900")


class TestClampBounds(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.root = Path(self._tmpdir)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_log(self, entries: list[dict]) -> Path:
        p = self.root / "dispatch-log.jsonl"
        p.write_text(_make_log(entries))
        return p

    def test_clamps_up_to_300_floor(self) -> None:
        # All 10 durations are 10s → p95 ~ 10s by any method, p95*2 ~ 20s → 300
        entries = [
            _entry("codex", "completed", 10.0, task_id=str(i))
            for i in range(10)
        ]
        log = self._write_log(entries)
        result = _run_deadline("codex", log)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "300")

    def test_clamps_down_to_900_ceiling(self) -> None:
        # All 10 durations are 1000s → p95 ~ 1000s by any method, p95*2 ~ 2000s → 900
        entries = [
            _entry("gemini", "completed", 1000.0, task_id=str(i))
            for i in range(10)
        ]
        log = self._write_log(entries)
        result = _run_deadline("gemini", log)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "900")

    def test_in_range_returns_computed_value(self) -> None:
        # 10 identical durations of 200s → p95 = 200, p95*2 = 400 (unambiguous)
        entries = [
            _entry("tess", "completed", 200.0, task_id=str(i))
            for i in range(10)
        ]
        log = self._write_log(entries)
        result = _run_deadline("tess", log)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "400")

    def test_p95_distinguished_from_median(self) -> None:
        # 20 entries for "codex": 11 × 50.0s + 9 × 600.0s.
        # Sorted: positions 1-11 are 50.0, positions 12-20 are 600.0.
        # Median (p50): position 10 or 10.5 → 50.0. p50*2 = 100 → clamps UP to 300. ✗
        # p95 (any method): 95th-percentile position falls among the 600s → 600.0.
        #   p95*2 = 1200 → clamps DOWN to ceiling → 900. ✓
        # Mean: (11*50 + 9*600)/20 = 297.5. mean*2 = 595 → in-range 595. ✗
        entries = [
            _entry("codex", "completed", 50.0, task_id=f"fast-{i}")
            for i in range(11)
        ] + [
            _entry("codex", "completed", 600.0, task_id=f"slow-{i}")
            for i in range(9)
        ]
        log = self._write_log(entries)
        result = _run_deadline("codex", log)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "900")

    def test_p95_distinguished_from_max_and_mean(self) -> None:
        # 100 entries: 99 × 100.0s + 1 × 10000.0s (a single extreme outlier).
        # The outlier sits at position 100 (1-indexed), so the 95th-percentile
        # position falls inside the dense block of 100s — p95 = 100 by every
        # standard percentile method (nearest-rank and linear interpolation alike).
        # p95 * 2 = 200 → clamps UP to floor → expected 300.
        #
        # Wrong max-based impl:  max=10000 → 10000*2=20000 → clamps to 900. ✗
        # Wrong mean-based impl: mean=(99*100+10000)/100=199 → 199*2=398 → 398. ✗
        entries = [
            _entry("codex", "completed", 100.0, task_id=str(i))
            for i in range(99)
        ] + [_entry("codex", "completed", 10000.0, task_id="outlier")]
        log = self._write_log(entries)
        result = _run_deadline("codex", log)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "300")


class TestSampleFiltering(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.root = Path(self._tmpdir)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_log(self, entries: list[dict]) -> Path:
        p = self.root / "dispatch-log.jsonl"
        p.write_text(_make_log(entries))
        return p

    def test_excludes_other_dispatch_types(self) -> None:
        # "ivan" has 5 completed entries at 200s (→ 400).
        # "tess" has 10 completed entries at 1000s (→ 900 clamped).
        # Querying "ivan" must return 400, not be contaminated by "tess" entries.
        ivan = [
            _entry("ivan", "completed", 200.0, task_id=f"ivan-{i}")
            for i in range(5)
        ]
        tess = [
            _entry("tess", "completed", 1000.0, task_id=f"tess-{i}")
            for i in range(10)
        ]
        log = self._write_log(ivan + tess)
        result = _run_deadline("ivan", log)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "400")

    def test_excludes_non_completed_outcomes(self) -> None:
        # 5 completed entries at 200s → p95*2 = 400.
        # 10 additional hung/timeout/error entries at 1000s must be excluded.
        completed = [
            _entry("devon", "completed", 200.0, task_id=f"ok-{i}")
            for i in range(5)
        ]
        bad_outcomes = [
            _entry("devon", outcome, 1000.0, task_id=f"bad-{i}")
            for i, outcome in enumerate(
                [
                    "hung",
                    "timeout",
                    "context_overrun",
                    "subagent_prompt_overrun",
                    "error",
                    "infra_failure",
                    "hung",
                    "timeout",
                    "error",
                    "hung",
                ]
            )
        ]
        log = self._write_log(completed + bad_outcomes)
        result = _run_deadline("devon", log)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "400")

    def test_mixed_types_and_outcomes_only_matching_completed_count(self) -> None:
        # Mix of types and outcomes; only "reviewer" completed entries at 200s
        # (exactly 5) should determine the result → 400.
        entries = [
            _entry("reviewer", "completed", 200.0, task_id=f"r-{i}")
            for i in range(5)
        ]
        entries += [
            _entry("reviewer", "hung", 600.0, task_id="r-hung"),
            _entry("codex", "completed", 1000.0, task_id="c-1"),
            _entry("codex", "completed", 1000.0, task_id="c-2"),
            _entry("gemini", "completed", 50.0, task_id="g-1"),
        ]
        log = self._write_log(entries)
        result = _run_deadline("reviewer", log)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "400")


if __name__ == "__main__":
    unittest.main()
