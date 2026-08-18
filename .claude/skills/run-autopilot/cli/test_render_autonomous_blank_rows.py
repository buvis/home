#!/usr/bin/env python3
"""Tests for render_report._autonomous's blank-row filter: a decision whose
five cells are all empty must be dropped, whether the source keys are
absent (rendering None) or present-but-empty ("").

Split out as a new sibling of test_render.py (PRD 00122 item 6) to keep
both files under the 800-line limit; render_report.py's overall render
contract (golden fixtures, prd_section, batch_summary, etc.) is documented
in test_render.py's module docstring. test_render.py's own
AutonomousBlankRowTests class already covers the None-only baseline (an
absent key renders None, which the pre-existing filter already dropped);
these tests add the ""-aware cases PRD 00122 item 6 requires.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cli import render_report


class AutonomousBlankRowEmptyStringTests(unittest.TestCase):
    """_cell() already renders "" the same as None (both come out blank),
    so _autonomous's blank-row filter must treat them the same way too: a
    decision whose five keys are all present but set to "" must be dropped
    exactly like an all-absent-keys decision is."""

    def test_drops_a_decision_whose_cells_are_all_empty_strings(self) -> None:
        # Exactly one row, not two: today's `any(cell is not None ...)`
        # predicate treats "" as non-blank and wrongly keeps this row.
        decisions = [
            {
                "cycle": 1,
                "issue": "Missing null check",
                "severity": "medium",
                "action": "auto-fix",
                "reason": "mechanical fix",
            },
            {"cycle": "", "issue": "", "severity": "", "action": "", "reason": ""},
        ]
        lines = render_report._autonomous(decisions)
        table_rows = [
            ln for ln in lines if ln.startswith("| ") and not ln.startswith("| Cycle")
        ]
        self.assertEqual(len(table_rows), 1)
        self.assertNotIn("|  |  |  |  |  |", "\n".join(lines))

    def test_drops_a_decision_mixing_absent_and_empty_string_keys(self) -> None:
        # issue/severity/reason absent, cycle/action present but "" -- still
        # nothing but emptiness in every one of the 5 cells.
        decisions = [{"cycle": "", "action": ""}]
        self.assertEqual(render_report._autonomous(decisions), [])

    def test_omits_the_section_when_every_row_is_blank_via_empty_strings(
        self,
    ) -> None:
        decisions = [
            {"cycle": "", "issue": "", "severity": "", "action": "", "reason": ""},
        ]
        self.assertEqual(render_report._autonomous(decisions), [])

    def test_keeps_a_decision_whose_only_populated_cell_is_cycle(self) -> None:
        text = "\n".join(render_report._autonomous([{"cycle": 1}]))
        self.assertIn("| 1 |  |  |  |  |", text)

    def test_keeps_a_decision_whose_only_populated_cell_is_integer_zero(self) -> None:
        # Guards against a truthiness-based fix (`any(cell for cell in
        # row)`): _cell(0) renders "0", not blank, so this row must survive.
        text = "\n".join(render_report._autonomous([{"cycle": 0}]))
        self.assertIn("| 0 |  |  |  |  |", text)


if __name__ == "__main__":
    unittest.main()
