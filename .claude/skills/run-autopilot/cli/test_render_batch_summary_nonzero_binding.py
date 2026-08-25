#!/usr/bin/env python3
"""Tests for render_report.batch_summary's R5 binding: a batch that ran
cycles and decisions cannot render a report claiming zero of either. Also
covers the inverse: a state with no real completed_prds legitimately
renders 0.

Split out as a new sibling of test_render.py (PRD 00122 item 7, Phase 3)
to keep both files under the 800-line limit; render_report.py's overall
render contract (golden fixtures, prd_section, batch_summary, etc.) is
documented in test_render.py's module docstring.

These are property assertions (parse trailing integer, assert > 0), not
golden-file matches, the existing golden passes with the bug in place,
so golden alone is not the check.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

CLI_DIR = Path(__file__).resolve().parent
GOLDEN = CLI_DIR / "golden"

sys.path.insert(0, str(CLI_DIR.parent))

from cli import render_report
from cli.test_render import _batch_state, _state


class BatchSummaryNonZeroBindingTests(unittest.TestCase):
    """Tests for render_report.batch_summary's R5 binding - see the module
    docstring for the rationale and the property-assertion approach."""

    def _raw_cell(self, summary: str, label: str) -> str:
        """Extract the raw text after the colon from a summary line like
        '- Total cycles: ?' - for asserting the non-integer `?` cell."""
        for line in summary.splitlines():
            if line.strip().startswith(f"- {label}:"):
                return line.strip().split(":", 1)[1].strip()
        raise ValueError(f"No line starting with '- {label}:' in summary")

    def _parse_counter(self, summary: str, label: str) -> int:
        """Extract the trailing integer from a summary line like
        '- Total cycles: 2'."""
        return int(self._raw_cell(summary, label))

    def test_nonzero_state_renders_nonzero_counters(self) -> None:
        """batch_summary of the real 202608162223 batch (2 cycles, 6
        autonomous decisions, 1 PRD completed) must not render 0 for
        any of those counters."""
        state = _batch_state()
        summary = render_report.batch_summary(
            state,
            [],
            len(state["deferred_decisions"]),
        )
        # PRDs completed: 1 dict entry in completed_prds → nonzero
        self.assertGreater(
            self._parse_counter(summary, "PRDs completed"),
            0,
            "PRDs completed rendered 0 despite 1 completed PRD in state",
        )
        # Total cycles: 2 (from the dict record) → nonzero
        self.assertGreater(
            self._parse_counter(summary, "Total cycles"),
            0,
            "Total cycles rendered 0 despite 2 real cycles in state",
        )
        # Autonomous decisions: 6 (from the dict record) → nonzero
        self.assertGreater(
            self._parse_counter(summary, "Autonomous decisions"),
            0,
            "Autonomous decisions rendered 0 despite 6 real decisions in state",
        )
        # Escalated decisions: genuinely 0 in this fixture, do NOT assert > 0
        self.assertEqual(
            self._parse_counter(summary, "Escalated decisions"),
            0,
            "Escalated decisions should be 0 (fixture has no escalated entries)",
        )

    def test_empty_completed_prds_legitimately_renders_zero(self) -> None:
        """A state with no completed_prds legitimately renders 0 for
        cycle/decision counters - the binding must not forbid 0
        outright."""
        state = _state()
        state["batch"]["completed_prds"] = []
        summary = render_report.batch_summary(state, [], 0)
        # With no completed PRDs, these counters are legitimately 0
        self.assertEqual(self._parse_counter(summary, "PRDs completed"), 0)
        self.assertEqual(self._parse_counter(summary, "Total cycles"), 0)
        self.assertEqual(self._parse_counter(summary, "Autonomous decisions"), 0)
        self.assertEqual(self._parse_counter(summary, "Escalated decisions"), 0)

    def test_bare_string_completed_prds_renders_question_marks_for_cycle_sums(
        self,
    ) -> None:
        """When completed_prds holds only bare filename strings (legacy
        shape), PRD count is still the list length but the cycle/decision
        sums render `?` - the data was lost, and a `0` would claim
        nothing ran (R2, R5)."""
        state = _state()
        state["batch"]["completed_prds"] = [
            "00120-migrate-task-tracking-to-statectl-v1.md",
        ]
        summary = render_report.batch_summary(state, [], 0)
        # PRD count reflects the bare string entry
        self.assertEqual(self._parse_counter(summary, "PRDs completed"), 1)
        # Cycle/decision sums are unknown for bare strings - never 0
        self.assertEqual(self._raw_cell(summary, "Total cycles"), "?")
        self.assertEqual(self._raw_cell(summary, "Autonomous decisions"), "?")
        self.assertEqual(self._raw_cell(summary, "Escalated decisions"), "?")

    def test_mixed_completed_prds_renders_question_marks_for_cycle_sums(
        self,
    ) -> None:
        """One dict record and one bare string in the same list (the live
        shape of batch 202608180438): the count is 2 but the sums are
        `?` - a partial sum over the dict half would understate the
        batch."""
        state = _state()
        state["batch"]["completed_prds"] = [
            {
                "filename": "00120-migrate-task-tracking-to-statectl-v1.md",
                "cycles": 2,
                "autonomous_decisions": 6,
                "escalated_decisions": 0,
                "tasks_completed": 7,
                "tasks_total": 7,
            },
            "00029-cartographer-evaluate-phase-4-6-reactivation-v1.md",
        ]
        summary = render_report.batch_summary(state, [], 0)
        self.assertEqual(self._parse_counter(summary, "PRDs completed"), 2)
        self.assertEqual(self._raw_cell(summary, "Total cycles"), "?")
        self.assertEqual(self._raw_cell(summary, "Autonomous decisions"), "?")
        self.assertEqual(self._raw_cell(summary, "Escalated decisions"), "?")

    def test_archived_bare_string_fixture_renders_question_marks(self) -> None:
        """The archived 202608162223 state as the real batch wrote it -
        completed_prds holding the bare filename, not the dict record -
        renders `?` for every sum and 1 for the PRD count."""
        state = json.loads(
            (GOLDEN / "state-batch-202608162223.json").read_text(
                encoding="utf-8",
            ),
        )
        self.assertEqual(
            state["batch"]["completed_prds"],
            ["00120-migrate-task-tracking-to-statectl-v1.md"],
        )
        summary = render_report.batch_summary(
            state,
            [],
            len(state["deferred_decisions"]),
        )
        self.assertEqual(self._parse_counter(summary, "PRDs completed"), 1)
        self.assertEqual(self._raw_cell(summary, "Total cycles"), "?")
        self.assertEqual(self._raw_cell(summary, "Autonomous decisions"), "?")
        self.assertEqual(self._raw_cell(summary, "Escalated decisions"), "?")


if __name__ == "__main__":
    unittest.main()
