#!/usr/bin/env python3
"""Tests for cli/selection.py - the PRD selection decision.

Binds the rule it encodes: lowest sequence, wip before backlog, `hold/`
unreachable. The last one is asserted structurally (on the signature) because
"the function never scans hold/" is a claim about what it CAN do, and a test
that only checks it did not scan hold this time would pass for a function that
grew a `hold` parameter tomorrow.
"""

from __future__ import annotations

import inspect
import unittest

from cli import selection


class SequenceTests(unittest.TestCase):
    def test_parses_the_five_digit_prefix(self) -> None:
        self.assertEqual(selection.sequence("00089-extract-core-v1.md"), 89)

    def test_leading_zeros_do_not_make_it_octal(self) -> None:
        self.assertEqual(selection.sequence("00010-x.md"), 10)

    def test_unnumbered_name_has_no_sequence(self) -> None:
        self.assertIsNone(selection.sequence("FASTTRACK-PLAN-v5.md"))

    def test_six_digit_prefix_is_not_truncated_to_five(self) -> None:
        # 001189- must not read as 00118, which would silently mis-order it
        # against a real 00118 PRD.
        self.assertIsNone(selection.sequence("001189-x.md"))

    def test_four_digit_prefix_is_not_a_sequence(self) -> None:
        self.assertIsNone(selection.sequence("0089-x.md"))


class SelectableTests(unittest.TestCase):
    def test_orders_by_sequence_not_by_string(self) -> None:
        # String order would put 00100 before 00089.
        names = ["00100-b.md", "00089-a.md", "00095-c.md"]
        self.assertEqual(
            selection.selectable(names),
            ["00089-a.md", "00095-c.md", "00100-b.md"],
        )

    def test_skips_unnumbered_names(self) -> None:
        # dev/local/prds/FASTTRACK-PLAN-v5.md is unnumbered precisely so no
        # PRD picker selects it.
        self.assertEqual(
            selection.selectable(["FASTTRACK-PLAN-v5.md", "00089-a.md"]),
            ["00089-a.md"],
        )

    def test_skips_non_markdown(self) -> None:
        self.assertEqual(
            selection.selectable(["00089-a.md.bak", "00090-b.txt", "00089-a.md"]),
            ["00089-a.md"],
        )

    def test_duplicate_sequence_breaks_on_name_deterministically(self) -> None:
        both = ["00089-zebra.md", "00089-alpha.md"]
        self.assertEqual(
            selection.selectable(both),
            ["00089-alpha.md", "00089-zebra.md"],
        )
        self.assertEqual(selection.selectable(both), selection.selectable(both[::-1]))

    def test_empty_listing_selects_nothing(self) -> None:
        self.assertEqual(selection.selectable([]), [])


class SelectTests(unittest.TestCase):
    def test_wip_lowest_sequence_wins(self) -> None:
        prd, source = selection.select(["00095-b.md", "00089-a.md"], [])
        self.assertEqual((prd, source), ("00089-a.md", "wip"))

    def test_wip_beats_a_lower_numbered_backlog_prd(self) -> None:
        # wip wins WHOLE, not per-number: an in-progress PRD finishes before a
        # lower-numbered backlog one starts.
        prd, source = selection.select(["00099-in-progress.md"], ["00001-older.md"])
        self.assertEqual((prd, source), ("00099-in-progress.md", "wip"))

    def test_backlog_used_only_when_wip_is_empty(self) -> None:
        prd, source = selection.select([], ["00095-b.md", "00089-a.md"])
        self.assertEqual((prd, source), ("00089-a.md", "backlog"))

    def test_wip_holding_only_unselectable_names_falls_through(self) -> None:
        prd, source = selection.select(["notes.txt", "README.md"], ["00089-a.md"])
        self.assertEqual((prd, source), ("00089-a.md", "backlog"))

    def test_both_empty_is_drained(self) -> None:
        self.assertEqual(selection.select([], []), (None, "drained"))

    def test_selection_cannot_reach_hold(self) -> None:
        # hold/ is excluded by construction, not by a rule the caller obeys.
        self.assertEqual(
            list(inspect.signature(selection.select).parameters),
            ["wip", "backlog"],
            "select() must take only wip and backlog; a hold parameter would "
            "make the parked/deferred exclusion optional",
        )


if __name__ == "__main__":
    unittest.main()
