#!/usr/bin/env python3
"""Tests for the PRD 00107 render surfaces: render_audit, render_report,
render_metrics, status, and their `autopilot render` / `autopilot status`
CLI wiring.

Goldens live in cli/golden/: the fixture state mirrors the documented
schema PLUS the live-state deviations the renders must tolerate (bare-string
`batch.completed_prds` entries, question/resolution decision shapes, an
attempt with no `implementor`), and each render is pinned byte-for-byte
against cli/golden/expected/.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

CLI_DIR = Path(__file__).resolve().parent
CLI_MAIN = CLI_DIR / "__main__.py"
GOLDEN = CLI_DIR / "golden"
EXPECTED = GOLDEN / "expected"

sys.path.insert(0, str(CLI_DIR.parent))

from cli import render_audit, render_metrics, render_report, status

NOW = "2026-08-09T12:00:00Z"
STARTED = "2026-08-09T10:00:00Z"


def _state() -> dict:
    return json.loads((GOLDEN / "state-render.json").read_text(encoding="utf-8"))


def _rows() -> list[dict]:
    return render_metrics.load_rows(GOLDEN / "metrics-render.jsonl")


class GoldenRenderTests(unittest.TestCase):
    """Each render matches its golden built from the real-shaped fixture."""

    def test_audit_matches_golden(self) -> None:
        text = render_audit.render_audit(_state(), STARTED, NOW)
        self.assertEqual(text, (EXPECTED / "audit.md").read_text(encoding="utf-8"))

    def test_report_section_matches_golden(self) -> None:
        state = _state()
        rows = render_metrics.matching_rows(_rows(), state["prd"], state["batch"]["id"])
        text = render_report.prd_section(state, rows, NOW)
        self.assertEqual(
            text, (EXPECTED / "report-section.md").read_text(encoding="utf-8")
        )

    def test_batch_summary_matches_golden(self) -> None:
        text = render_report.batch_summary(_state(), _rows(), 2)
        self.assertEqual(
            text, (EXPECTED / "report-summary.md").read_text(encoding="utf-8")
        )

    def test_metrics_summary_matches_golden(self) -> None:
        text = render_metrics.render_metrics(_rows()) + "\n"
        self.assertEqual(text, (EXPECTED / "metrics.md").read_text(encoding="utf-8"))

    def test_status_matches_golden(self) -> None:
        text = status.render_status(_state()) + "\n"
        self.assertEqual(text, (EXPECTED / "status.txt").read_text(encoding="utf-8"))


class MetricsFilterTests(unittest.TestCase):
    def test_matching_rows_excludes_other_prd_and_other_batch(self) -> None:
        state = _state()
        rows = render_metrics.matching_rows(_rows(), state["prd"], state["batch"]["id"])
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(r["prd"] == state["prd"] for r in rows))
        self.assertTrue(all(r["batch"] == state["batch"]["id"] for r in rows))

    def test_empty_rows_render_the_manual_run_line(self) -> None:
        self.assertEqual(render_metrics.phase_table([]), render_metrics.NO_METRICS)

    def test_missing_cost_renders_blank_not_zero(self) -> None:
        table = render_metrics.phase_table(
            [{"phase_launched": "done", "wall_secs": 10}]
        )
        self.assertIn("| done | 1 | 10 |  |  |", table)
        self.assertNotIn("0.00", table)


class ReportEdgeTests(unittest.TestCase):
    def test_no_tasks_renders_no_implementor_data(self) -> None:
        state = _state()
        state["tasks"] = []
        self.assertIn("no implementor data", render_report.prd_section(state, [], NOW))

    def test_empty_decision_arrays_omit_their_sections(self) -> None:
        state = _state()
        for key in ("autonomous_decisions", "deferred_decisions", "doubts"):
            state[key] = []
        state["doubts_rubric_verdicts"] = []
        text = render_report.prd_section(state, [], NOW)
        for heading in (
            "### Autonomous Decisions",
            "### Escalated Decisions",
            "### Doubt Review Findings",
            "### Doubt Rubric Verdicts",
            "### Assumptions Made",
            "### Deferred to Batch End",
        ):
            self.assertNotIn(heading, text)
        self.assertIn(render_metrics.NO_METRICS, text)

    def test_source_tagged_verdicts_combine_per_rule(self) -> None:
        state = _state()
        state["doubts_rubric_verdicts"] = [
            {"rule_id": "D1", "verdict": "pass", "source": "codex"},
            {"rule_id": "D1", "verdict": "fail", "source": "fable"},
        ]
        text = render_report.prd_section(state, [], NOW)
        self.assertIn("| D1 | pass (codex) / fail (fable) |", text)

    def test_probe_from_another_batch_renders_not_run(self) -> None:
        state = _state()
        state["codex_probe"]["batch_id"] = "202601010000"
        self.assertIn("codex probe: not run", render_report.prd_section(state, [], NOW))

    def test_tripped_breaker_names_the_failures_and_reroutes(self) -> None:
        state = _state()
        state["qwen_breaker"] = {
            "tripped": True,
            "after_task": "t2",
            "failed_tasks": ["t1", "t2"],
            "batch_id": state["batch"]["id"],
        }
        state["tasks"][2]["attempts"][0]["breaker_skipped"] = True
        text = render_report.prd_section(state, [], NOW)
        self.assertIn(
            "capability breaker: tripped after t2 "
            "(2 consecutive gate failures: t1, t2); 1 tasks rerouted",
            text,
        )

    def test_pipes_in_issue_text_stay_table_safe(self) -> None:
        state = _state()
        state["autonomous_decisions"] = [
            {"cycle": 1, "issue": "a | b", "action": "auto-fix"}
        ]
        self.assertIn("a \\| b", render_report.prd_section(state, [], NOW))

    def test_stalled_section_shape(self) -> None:
        text = render_report.stalled_section("00040-x.md", "oversized_plan", "34 tasks", NOW)
        self.assertIn("## 00040-x.md — STALLED (oversized_plan)", text)
        self.assertIn("- Detail: 34 tasks", text)
        self.assertIn("move back to dev/local/prds/wip/", text)


class AuditEdgeTests(unittest.TestCase):
    def test_empty_arrays_render_no_decisions_recorded(self) -> None:
        state = _state()
        for key in ("autonomous_decisions", "deferred_decisions", "doubts"):
            state[key] = []
        text = render_audit.render_audit(state, STARTED, NOW)
        self.assertIn("no decisions recorded", text)
        self.assertIn("Autonomous: 0  |  Deferred: 0  |  Doubts: 0", text)

    def test_existing_started_is_extracted(self) -> None:
        text = render_audit.render_audit(_state(), STARTED, NOW)
        self.assertEqual(render_audit.existing_started(text), STARTED)


class StatusEdgeTests(unittest.TestCase):
    def test_flags_render_when_present(self) -> None:
        state = _state()
        state["stall_reason"] = {"stalled": "oversized_task", "task": "t9"}
        state["cap_pause_reason"] = {
            "cycle": 3,
            "cap": 3,
            "unresolved_findings": [{"issue": "x"}],
        }
        state["pause_reason"] = {"site": "reviewer_fail", "detail": "carl hung"}
        state["needs_attention"] = True
        text = status.render_status(state)
        self.assertIn("STALL:  oversized_task (task: t9)", text)
        self.assertIn("CAP-PAUSE: cycle 3 at cap 3, 1 unresolved finding(s)", text)
        self.assertIn("PAUSED: reviewer_fail — carl hung", text)
        self.assertIn("FLAG:   needs_attention", text)

    def test_empty_state_degrades_not_crashes(self) -> None:
        text = status.render_status({})
        self.assertIn("PRD:    (none)", text)


class CliWiringTests(unittest.TestCase):
    """`autopilot render`/`autopilot status` as real subprocesses against a
    constructed <repo>/dev/local/autopilot tree."""

    def setUp(self) -> None:
        import tempfile

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        self.ap_dir = self.repo / "dev" / "local" / "autopilot"
        self.ap_dir.mkdir(parents=True)
        self.state_path = self.ap_dir / "state.json"
        self.state_path.write_text(
            (GOLDEN / "state-render.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (self.ap_dir / "loop-metrics.jsonl").write_text(
            (GOLDEN / "metrics-render.jsonl").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CLI_MAIN), *args, "--state", str(self.state_path)],
            capture_output=True,
            text=True,
        )

    def test_render_audit_writes_the_reviews_file(self) -> None:
        proc = self._run(["render", "audit", "--now", NOW])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = self.repo / "dev" / "local" / "reviews" / "00040-feature-x-v1-audit.md"
        self.assertTrue(out.exists())
        text = out.read_text(encoding="utf-8")
        self.assertIn("# Decision Audit Log: 00040-feature-x-v1", text)
        # First render: Started == Completed == --now.
        self.assertIn(f"Started: {NOW}", text)

    def test_render_audit_preserves_started_on_rerender(self) -> None:
        self._run(["render", "audit", "--now", STARTED])
        proc = self._run(["render", "audit", "--now", NOW])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = self.repo / "dev" / "local" / "reviews" / "00040-feature-x-v1-audit.md"
        text = out.read_text(encoding="utf-8")
        self.assertIn(f"Started: {STARTED}", text)
        self.assertIn(f"Completed: {NOW}", text)

    def test_render_report_creates_header_once_then_appends(self) -> None:
        first = self._run(["render", "report", "--now", NOW])
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self._run(["render", "report", "--summary", "--now", NOW])
        self.assertEqual(second.returncode, 0, second.stderr)
        report = self.ap_dir / "reports" / "202607202320-report.md"
        text = report.read_text(encoding="utf-8")
        self.assertEqual(text.count("# Autopilot Batch Report 202607202320"), 1)
        self.assertIn("## 00040-feature-x-v1.md", text)
        self.assertIn("## Batch Summary", text)

    def test_render_report_stalled_appends_the_short_form(self) -> None:
        proc = self._run(
            ["render", "report", "--stalled", "--site", "oversized_plan",
             "--detail", "34 tasks", "--now", NOW]
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = self.ap_dir / "reports" / "202607202320-report.md"
        self.assertIn("STALLED (oversized_plan)", report.read_text(encoding="utf-8"))

    def test_render_metrics_prints_the_summary(self) -> None:
        proc = self._run(["render", "metrics"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("| 00040-feature-x-v1.md | 5 | 1069 | 28.16 |", proc.stdout)

    def test_render_stdout_writes_nothing(self) -> None:
        proc = self._run(["render", "report", "--stdout", "--now", NOW])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("## 00040-feature-x-v1.md", proc.stdout)
        self.assertFalse((self.ap_dir / "reports").exists())

    def test_status_prints_the_plain_view(self) -> None:
        proc = self._run(["status"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("PRD:    00040-feature-x-v1.md", proc.stdout)
        self.assertIn("Phase:  done -> next: done", proc.stdout)

    def test_status_on_missing_state_exits_2(self) -> None:
        self.state_path.unlink()
        proc = self._run(["status"])
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
