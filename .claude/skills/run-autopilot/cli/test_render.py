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


def _batch_state() -> dict:
    """A reconstruction of real batch 202608162223 with hand-written dict
    counts (not the archived record) standing in for the batch that exposed
    all five original render_report.py defects."""
    return json.loads(
        (GOLDEN / "state-batch-202608162223-reconstructed.json").read_text(
            encoding="utf-8",
        ),
    )


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
            text,
            (EXPECTED / "report-section.md").read_text(encoding="utf-8"),
        )

    def test_batch_summary_matches_golden(self) -> None:
        text = render_report.batch_summary(_state(), _rows(), 2)
        self.assertEqual(
            text,
            (EXPECTED / "report-summary.md").read_text(encoding="utf-8"),
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

    def test_event_rows_are_not_counted_as_sessions(self) -> None:
        # PRD 00094: the review gate appends {"event": "review_converged", ...}
        # rows to the same file, sharing the fixture's prd+batch. They are not
        # sessions - counting one would inflate every Sessions and Total cell
        # and open a bogus `?` phase row. The fixture carries exactly one.
        raw = (GOLDEN / "metrics-render.jsonl").read_text(encoding="utf-8")
        self.assertEqual(raw.count('"event":"review_converged"'), 1)
        self.assertTrue(all("event" not in row for row in _rows()))
        self.assertEqual(len(_rows()), 6)

    def test_empty_rows_render_the_manual_run_line(self) -> None:
        self.assertEqual(render_metrics.phase_table([]), render_metrics.NO_METRICS)

    def test_missing_cost_renders_blank_not_zero(self) -> None:
        table = render_metrics.phase_table(
            [{"phase_launched": "done", "wall_secs": 10}],
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
            {"cycle": 1, "issue": "a | b", "action": "auto-fix"},
        ]
        self.assertIn("a \\| b", render_report.prd_section(state, [], NOW))

    def test_stalled_section_shape(self) -> None:
        text = render_report.stalled_section(
            "00040-x.md",
            "oversized_plan",
            "34 tasks",
            NOW,
        )
        self.assertIn("## 00040-x.md — STALLED (oversized_plan)", text)
        self.assertIn("- Detail: 34 tasks", text)
        self.assertIn("move back to dev/local/prds/wip/", text)


class PrdSectionTaskCountTests(unittest.TestCase):
    """Task counts come from the closing batch record or
    len(state['tasks']), never the stale state-root fields the batch
    drain wipes to 0 (R1, R2)."""

    def test_reads_counts_from_the_matching_completed_prds_record(self) -> None:
        state = _state()
        state["tasks_completed"] = 999  # stale root field: must be ignored
        state["tasks_total"] = 999
        state["tasks"] = []
        state["batch"]["completed_prds"] = [
            {
                "filename": state["prd"],
                "cycles": 2,
                "tasks_completed": 5,
                "tasks_total": 6,
            },
        ]
        text = render_report.prd_section(state, [], NOW)
        self.assertIn("- Tasks: 5/6", text)
        self.assertNotIn("- Tasks: 999/999", text)

    def test_falls_back_to_state_tasks_when_no_batch_record_matches(self) -> None:
        state = _state()
        state["tasks_completed"] = 999
        state["tasks_total"] = 999
        state["batch"]["completed_prds"] = []
        state["tasks"] = [
            {"status": "completed"},
            {"status": "completed"},
            {"status": "in_progress"},
        ]
        text = render_report.prd_section(state, [], NOW)
        self.assertIn("- Tasks: 2/3", text)
        self.assertNotIn("- Tasks: 999/999", text)

    def test_skips_bare_string_completed_prds_entries(self) -> None:
        state = _state()
        state["batch"]["completed_prds"] = [state["prd"]]  # bare string, no counts
        state["tasks"] = [{"status": "completed"}]
        text = render_report.prd_section(state, [], NOW)
        self.assertIn("- Tasks: 1/1", text)

    def test_renders_question_marks_when_no_task_data_is_available(self) -> None:
        state = _state()
        state["tasks_completed"] = 0
        state["tasks_total"] = 0
        state["batch"]["completed_prds"] = []
        state["tasks"] = []
        text = render_report.prd_section(state, [], NOW)
        self.assertIn("- Tasks: ?/?", text)
        self.assertNotIn("- Tasks: 0/0", text)


class AutonomousBlankRowTests(unittest.TestCase):
    """_autonomous drops rows where every cell is empty instead of
    rendering a blank record (R2)."""

    def test_drops_the_fully_blank_row_but_keeps_populated_ones(self) -> None:
        decisions = [
            {
                "cycle": 1,
                "issue": "Missing null check",
                "severity": "medium",
                "action": "auto-fix",
                "reason": "mechanical fix",
            },
            {},
            {
                "cycle": 2,
                "issue": "New dependency needed",
                "severity": "high",
                "action": "auto-fix",
                "reason": "research-passed",
            },
        ]
        lines = render_report._autonomous(decisions)
        text = "\n".join(lines)
        self.assertIn(
            "| 1 | Missing null check | medium | auto-fix | mechanical fix |",
            text,
        )
        self.assertIn(
            "| 2 | New dependency needed | high | auto-fix | research-passed |",
            text,
        )
        self.assertNotIn("|  |  |  |  |  |", text)
        # heading, blank, table header, separator, 2 data rows, trailing blank
        self.assertEqual(len(lines), 7)

    def test_omits_the_section_when_every_row_is_blank(self) -> None:
        self.assertEqual(render_report._autonomous([{}]), [])

    def test_partially_populated_rows_survive_the_blank_filter(self) -> None:
        # A clarification-shaped decision (question/resolution, no
        # severity/action) is not "blank" - only rows where every one of
        # the 5 cells is empty get dropped.
        decisions = [
            {
                "cycle": 1,
                "question": "Which tree gets the phases?",
                "resolution": "Operator chose the plugin tree.",
            },
        ]
        text = "\n".join(render_report._autonomous(decisions))
        self.assertIn(
            "| 1 | Which tree gets the phases? |  |  | "
            "Operator chose the plugin tree. |",
            text,
        )


class DeferredToBatchEndDispositionTests(unittest.TestCase):
    """_deferred_to_batch_end reads `disposition`, falling back to
    `reason` (R2)."""

    def test_renders_disposition_when_reason_is_absent(self) -> None:
        deferred = [
            {
                "issue": "API signature change needed",
                "severity": "high",
                "disposition": "revisit after v2 ships",
            },
        ]
        text = "\n".join(render_report._deferred_to_batch_end(deferred))
        self.assertIn(
            "| API signature change needed | high | revisit after v2 ships |",
            text,
        )

    def test_disposition_wins_over_reason_when_both_present(self) -> None:
        deferred = [
            {
                "issue": "Rename the config key",
                "severity": "medium",
                "reason": "user-visible rename",
                "disposition": "batch-end: needs a follow-up PRD",
            },
        ]
        text = "\n".join(render_report._deferred_to_batch_end(deferred))
        self.assertIn(
            "| Rename the config key | medium | batch-end: needs a follow-up PRD |",
            text,
        )
        self.assertNotIn("user-visible rename", text)

    def test_still_renders_plain_reason_when_no_disposition(self) -> None:
        # Regression: entries using only the pre-existing `reason` field
        # (no `disposition`) must keep rendering exactly as before.
        deferred = [
            {
                "issue": "Legacy entry",
                "severity": "low",
                "reason": "pre-migration shape",
            },
        ]
        text = "\n".join(render_report._deferred_to_batch_end(deferred))
        self.assertIn("| Legacy entry | low | pre-migration shape |", text)


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
            [
                "render",
                "report",
                "--stalled",
                "--site",
                "oversized_plan",
                "--detail",
                "34 tasks",
                "--now",
                NOW,
            ],
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

    def test_render_audit_outside_a_dev_local_autopilot_tree_refuses(self) -> None:
        """A --state outside dev/local/autopilot must exit 2, never derive a
        repo root from an arbitrary ancestor and plant dev/local/reviews
        there (the committed first version did exactly that)."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            stray = Path(tmp) / "state.json"
            stray.write_text(
                (GOLDEN / "state-render.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    str(CLI_MAIN),
                    "render",
                    "audit",
                    "--now",
                    NOW,
                    "--state",
                    str(stray),
                ],
                capture_output=True,
                text=True,
            )
            planted = list(Path(tmp).parents[2].glob("dev/local/reviews/*"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("not a dev/local/autopilot dir", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(planted, [])


class HeaderStartedTests(unittest.TestCase):
    """The report header's Started: line is the batch's real start -
    the first metrics row's ts_start for this batch, or batch.id's
    yyyymmddHHMM stamp when no metrics rows exist yet - never the
    file-write --now (R4)."""

    def setUp(self) -> None:
        import tempfile

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        self.ap_dir = self.repo / "dev" / "local" / "autopilot"
        self.ap_dir.mkdir(parents=True)
        self.state_path = self.ap_dir / "state.json"

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CLI_MAIN), *args, "--state", str(self.state_path)],
            capture_output=True,
            text=True,
        )

    def test_started_derives_from_the_first_metrics_row_for_this_batch(self) -> None:
        state = _state()
        state["batch"]["id"] = "202311142213"
        self.state_path.write_text(json.dumps(state), encoding="utf-8")
        (self.ap_dir / "loop-metrics.jsonl").write_text(
            json.dumps(
                {
                    "ts_start": 1700000000,
                    "ts_end": 1700000900,
                    "wall_secs": 900,
                    "prd": state["prd"],
                    "batch": "202311142213",
                    "phase_launched": "",
                    "phase_end": "review",
                    "signal": "continue",
                    "model": "claude-opus-5[1m]",
                    "cost_usd": 1.0,
                    "tokens_out": 100,
                },
            )
            + "\n",
            encoding="utf-8",
        )
        proc = self._run(["render", "report", "--now", NOW])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = self.ap_dir / "reports" / "202311142213-report.md"
        text = report.read_text(encoding="utf-8")
        self.assertIn("Started: 2023-11-14T22:13:20Z", text)
        self.assertNotIn(f"Started: {NOW}", text)

    def test_started_falls_back_to_batch_id_when_no_metrics_rows_exist(self) -> None:
        state = _state()
        state["batch"]["id"] = "202301020304"
        self.state_path.write_text(json.dumps(state), encoding="utf-8")
        (self.ap_dir / "loop-metrics.jsonl").write_text("", encoding="utf-8")
        proc = self._run(["render", "report", "--now", NOW])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = self.ap_dir / "reports" / "202301020304-report.md"
        text = report.read_text(encoding="utf-8")
        self.assertIn("Started: 2023-01-02T03:04:00Z", text)
        self.assertNotIn(f"Started: {NOW}", text)

    def test_started_derives_from_the_real_202608162223_batch_metrics_row(
        self,
    ) -> None:
        # PRD 00107 item 4 (R4), proven against the one batch this task
        # exists to reconstruct: earliest ts_start row tagged with
        # "batch": "202608162223" is epoch 1786911719.
        state = _batch_state()
        self.state_path.write_text(json.dumps(state), encoding="utf-8")
        (self.ap_dir / "loop-metrics.jsonl").write_text(
            json.dumps(
                {
                    "ts_start": 1786911719,
                    "ts_end": 1786919356,
                    "wall_secs": 7637,
                    "prd": state["prd"],
                    "batch": "202608162223",
                    "phase_launched": "",
                    "phase_end": "review",
                    "signal": "continue",
                    "model": "claude-opus-5[1m]",
                    "cost_usd": 1.0,
                    "tokens_out": 100,
                },
            )
            + "\n",
            encoding="utf-8",
        )
        proc = self._run(["render", "report", "--now", NOW])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = self.ap_dir / "reports" / "202608162223-report.md"
        text = report.read_text(encoding="utf-8")
        self.assertIn("Started: 2026-08-16T20:21:59Z", text)
        self.assertNotIn(f"Started: {NOW}", text)


class Batch202608162223ReconstructionTests(unittest.TestCase):
    """Rendering the reconstructed archived 202608162223 state (the batch
    that exposed all five original render_report.py defects) produces
    the real historical numbers instead of zeros/blanks."""

    def test_cycles_and_tasks_come_from_the_batch_record_not_the_wiped_root(
        self,
    ) -> None:
        state = _batch_state()
        self.assertEqual(state["tasks"], [])
        self.assertEqual(state["tasks_completed"], 0)
        self.assertEqual(state["tasks_total"], 0)

        section = render_report.prd_section(state, [], NOW)
        self.assertIn("- Tasks: 7/7", section)
        self.assertNotIn("- Tasks: 0/0", section)

        summary = render_report.batch_summary(
            state,
            [],
            len(state["deferred_decisions"]),
        )
        self.assertIn("- Total cycles: 2", summary)
        # The fixture's completed_prds record carries 6 (7 raw autonomous
        # decisions minus the 1 genuinely-blank one) - not the misleading
        # 0 a missing field would sum to.
        self.assertIn("- Autonomous decisions: 6", summary)

    def test_the_blank_autonomous_decision_row_is_dropped(self) -> None:
        state = _batch_state()
        self.assertEqual(len(state["autonomous_decisions"]), 7)
        section = render_report.prd_section(state, [], NOW)
        self.assertNotIn("|  |  |  |  |  |", section)
        # 7 raw decisions minus the 1 genuinely-blank entry = 6 rendered rows.
        rows = render_report._autonomous(state["autonomous_decisions"])
        table_rows = [
            ln for ln in rows if ln.startswith("| ") and not ln.startswith("| Cycle")
        ]
        self.assertEqual(len(table_rows), 6)

    def test_deferred_to_batch_end_reason_cells_are_populated_from_disposition(
        self,
    ) -> None:
        state = _batch_state()
        self.assertEqual(len(state["deferred_decisions"]), 5)
        self.assertTrue(all("status" not in d for d in state["deferred_decisions"]))
        text = "\n".join(
            render_report._deferred_to_batch_end(state["deferred_decisions"]),
        )
        for entry in state["deferred_decisions"]:
            self.assertIn(
                f"| {entry['issue']} | {entry['severity']} | {entry['disposition']} |",
                text,
            )

    def test_escalated_decisions_section_is_omitted(self) -> None:
        # All 5 deferred entries lack a `status` key, so `_is_pending`
        # defaults them to pending - none are escalated.
        state = _batch_state()
        section = render_report.prd_section(state, [], NOW)
        self.assertNotIn("### Escalated Decisions", section)
        summary = render_report.batch_summary(
            state,
            [],
            len(state["deferred_decisions"]),
        )
        self.assertIn("- Escalated decisions: 0", summary)


if __name__ == "__main__":
    unittest.main()
