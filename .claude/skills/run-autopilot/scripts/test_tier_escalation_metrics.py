"""Tests for tier_escalation_metrics.py — completeness requirements.

Covers:
  - haiku→sonnet escalation rate (including zero-denominator guard)
  - average attempts per task
  - per-tier first-pass success percentage
  - corrected overall_rate label (tasks with attempts, not total tasks)
  - metrics file write (batch_id present and absent)
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

# Import the module under test via sys.path manipulation so tests run from
# any working directory.
import sys

sys.path.insert(0, str(Path(__file__).parent))

import tier_escalation_metrics as tmet


def _make_task(
    task_id: str,
    attempts: list[dict],
) -> dict:
    return {"id": task_id, "attempts": attempts}


def _attempt(model: str, outcome: str, review_cycle: int | None = None) -> dict:
    a: dict = {"model": model, "outcome": outcome}
    if review_cycle is not None:
        a["review_cycle"] = review_cycle
    return a


class TestHaikuToSonnetRate(unittest.TestCase):
    def test_rate_computed_correctly(self) -> None:
        # 2 haiku-first tasks, 1 escalates to sonnet
        tasks = [
            _make_task(
                "1",
                [
                    _attempt("haiku", "completed"),
                    _attempt("sonnet", "completed", review_cycle=1),
                ],
            ),
            _make_task("2", [_attempt("haiku", "completed")]),
        ]
        m = tmet._compute(tasks)
        self.assertIn("haiku_to_sonnet_rate", m)
        self.assertAlmostEqual(m["haiku_to_sonnet_rate"], 50.0)

    def test_zero_denominator_returns_zero(self) -> None:
        # No haiku-first tasks
        tasks = [_make_task("1", [_attempt("sonnet", "completed")])]
        m = tmet._compute(tasks)
        self.assertEqual(m["haiku_to_sonnet_rate"], 0.0)

    def test_all_haiku_escalate(self) -> None:
        tasks = [
            _make_task(
                "1",
                [
                    _attempt("haiku", "completed"),
                    _attempt("sonnet", "completed", review_cycle=1),
                ],
            ),
            _make_task(
                "2",
                [
                    _attempt("haiku", "completed"),
                    _attempt("sonnet", "completed", review_cycle=1),
                ],
            ),
        ]
        m = tmet._compute(tasks)
        self.assertAlmostEqual(m["haiku_to_sonnet_rate"], 100.0)


class TestAverageAttemptsPerTask(unittest.TestCase):
    def test_single_attempt_tasks(self) -> None:
        tasks = [
            _make_task("1", [_attempt("sonnet", "completed")]),
            _make_task("2", [_attempt("sonnet", "completed")]),
        ]
        m = tmet._compute(tasks)
        self.assertIn("avg_attempts", m)
        self.assertAlmostEqual(m["avg_attempts"], 1.0)

    def test_mixed_attempt_counts(self) -> None:
        # task 1 has 2 attempts, task 2 has 1 attempt — avg = 1.5
        tasks = [
            _make_task(
                "1",
                [
                    _attempt("sonnet", "completed"),
                    _attempt("opus", "completed", review_cycle=1),
                ],
            ),
            _make_task("2", [_attempt("sonnet", "completed")]),
        ]
        m = tmet._compute(tasks)
        self.assertAlmostEqual(m["avg_attempts"], 1.5)

    def test_empty_tasks_returns_zero(self) -> None:
        m = tmet._compute([])
        self.assertEqual(m["avg_attempts"], 0.0)


class TestFirstPassSuccessPerTier(unittest.TestCase):
    def test_sonnet_first_pass_success(self) -> None:
        # 3 sonnet-first tasks: 2 completed first pass, 1 review-flagged on first pass
        tasks = [
            _make_task("1", [_attempt("sonnet", "completed")]),
            _make_task("2", [_attempt("sonnet", "completed")]),
            _make_task(
                "3",
                [
                    _attempt("sonnet", "review_flagged"),
                    _attempt("opus", "completed", review_cycle=1),
                ],
            ),
        ]
        m = tmet._compute(tasks)
        self.assertIn("first_pass_success", m)
        fps = m["first_pass_success"]
        self.assertIn("sonnet", fps)
        self.assertAlmostEqual(fps["sonnet"], round(2 / 3 * 100, 1))

    def test_haiku_first_pass_success(self) -> None:
        tasks = [
            _make_task("1", [_attempt("haiku", "completed")]),
            _make_task(
                "2",
                [
                    _attempt("haiku", "review_flagged"),
                    _attempt("sonnet", "completed", review_cycle=1),
                ],
            ),
        ]
        m = tmet._compute(tasks)
        fps = m["first_pass_success"]
        self.assertIn("haiku", fps)
        self.assertAlmostEqual(fps["haiku"], 50.0)

    def test_tier_with_zero_first_pass_excluded(self) -> None:
        # Only sonnet tasks — haiku and opus absent from first_pass_success
        tasks = [_make_task("1", [_attempt("sonnet", "completed")])]
        m = tmet._compute(tasks)
        fps = m["first_pass_success"]
        self.assertNotIn("haiku", fps)
        self.assertNotIn("opus", fps)

    def test_100_percent_success(self) -> None:
        tasks = [
            _make_task("1", [_attempt("opus", "completed")]),
            _make_task("2", [_attempt("opus", "completed")]),
        ]
        m = tmet._compute(tasks)
        fps = m["first_pass_success"]
        self.assertAlmostEqual(fps["opus"], 100.0)


class TestOverallRateDenominatorLabel(unittest.TestCase):
    def test_label_says_tasks_with_attempts(self) -> None:
        # The formatted output must not claim "tasks" when denominator is only
        # the filtered (tasks-with-attempts) list. The label should say
        # "tasks with attempts" to be honest when total > tasks_with_attempts.
        tasks_with_attempts = [
            _make_task("1", [_attempt("sonnet", "completed")]),
            _make_task(
                "2",
                [
                    _attempt("sonnet", "completed"),
                    _attempt("opus", "completed", review_cycle=1),
                ],
            ),
        ]
        m = tmet._compute(tasks_with_attempts)
        text = tmet.format_metrics(m)
        # The header line must say "tasks with attempts" not bare "tasks"
        self.assertIn("tasks with attempts", text)

    def test_escalated_count_matches_escalated_tasks(self) -> None:
        tasks = [
            _make_task(
                "1",
                [
                    _attempt("sonnet", "completed"),
                    _attempt("opus", "completed", review_cycle=1),
                ],
            ),
            _make_task("2", [_attempt("haiku", "completed")]),
        ]
        m = tmet._compute(tasks)
        self.assertEqual(m["escalated_count"], 1)


class TestFormatMetricsOutputLines(unittest.TestCase):
    def test_haiku_sonnet_rate_in_output(self) -> None:
        tasks = [_make_task("1", [_attempt("haiku", "completed")])]
        m = tmet._compute(tasks)
        text = tmet.format_metrics(m)
        self.assertIn("haiku→sonnet rate", text)

    def test_avg_attempts_in_output(self) -> None:
        tasks = [_make_task("1", [_attempt("sonnet", "completed")])]
        m = tmet._compute(tasks)
        text = tmet.format_metrics(m)
        self.assertIn("avg attempts", text)

    def test_first_pass_success_in_output(self) -> None:
        tasks = [_make_task("1", [_attempt("sonnet", "completed")])]
        m = tmet._compute(tasks)
        text = tmet.format_metrics(m)
        self.assertIn("first-pass success", text)


class TestMetricsFileWrite(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.root = Path(self._tmpdir)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_state(self, state: dict) -> Path:
        ap_dir = self.root / "dev" / "local" / "autopilot"
        ap_dir.mkdir(parents=True)
        state_path = ap_dir / "state.json"
        state_path.write_text(json.dumps(state, indent=2))
        return state_path

    def _make_state(self, batch_id: str | None = "202601010000") -> dict:
        state: dict = {
            "tasks": [
                {
                    "id": "1",
                    "attempts": [{"model": "sonnet", "outcome": "completed"}],
                },
                {
                    "id": "2",
                    "attempts": [
                        {"model": "haiku", "outcome": "completed"},
                        {
                            "model": "sonnet",
                            "outcome": "completed",
                            "review_cycle": 1,
                        },
                    ],
                },
            ]
        }
        if batch_id is not None:
            state["batch"] = {"id": batch_id}
        return state

    def test_metrics_file_created(self) -> None:
        state = self._make_state()
        state_path = self._write_state(state)
        tmet.run(state_path)
        metrics_file = (
            self.root / "dev" / "local" / "autopilot" / "metrics"
            / "202601010000-tier-metrics.md"
        )
        self.assertTrue(metrics_file.exists(), f"Expected {metrics_file} to exist")

    def test_metrics_file_contains_report(self) -> None:
        state = self._make_state()
        state_path = self._write_state(state)
        tmet.run(state_path)
        metrics_file = (
            self.root / "dev" / "local" / "autopilot" / "metrics"
            / "202601010000-tier-metrics.md"
        )
        content = metrics_file.read_text()
        self.assertIn("haiku→sonnet rate", content)
        self.assertIn("avg attempts", content)

    def test_no_batch_id_skips_file_write(self) -> None:
        state = self._make_state(batch_id=None)
        state_path = self._write_state(state)
        metrics_dir = self.root / "dev" / "local" / "autopilot" / "metrics"
        # run must not crash and must not create the metrics dir
        tmet.run(state_path)
        self.assertFalse(metrics_dir.exists())

    def test_metrics_dir_created_if_missing(self) -> None:
        state = self._make_state()
        state_path = self._write_state(state)
        metrics_dir = self.root / "dev" / "local" / "autopilot" / "metrics"
        self.assertFalse(metrics_dir.exists())
        tmet.run(state_path)
        self.assertTrue(metrics_dir.exists())


if __name__ == "__main__":
    unittest.main()
