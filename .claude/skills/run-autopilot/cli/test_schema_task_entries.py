#!/usr/bin/env python3
"""Tests for cli/schema.py's tasks[]-entry validation: the optional
`description` (str) and `blocked_by` (list[int]) per-entry fields.

Split out of test_schema.py (PRD 00120 file-size cleanup) to keep both files
under the 800-line limit; schema.py's overall public contract (SCHEMA_VERSION,
SchemaError, validate(), version_status()) is documented in test_schema.py's
module docstring, and these tests bind only the tasks[]-entry portion of it.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cli import schema


class ValidateTaskEntryOptionalFieldsTest(unittest.TestCase):
    """Both per-entry fields are optional and independent: any combination of
    present/absent must validate, and a non-dict entry stays tolerated."""

    def test_entry_with_neither_field_passes(self) -> None:
        # Today's shape, before this change. Backward compatibility: every
        # state.json already on disk carries entries without either field.
        state = {"tasks": [{"id": "1", "name": "do the thing", "status": "pending"}]}
        self.assertIsNone(schema.validate(state))

    def test_entry_with_only_one_of_the_two_fields_passes(self) -> None:
        for label, entry in (
            ("description only", {"id": "1", "description": "rewrite the doc"}),
            ("blocked_by only", {"id": "1", "blocked_by": [2, 3]}),
        ):
            with self.subTest(label=label):
                self.assertIsNone(schema.validate({"tasks": [entry]}))

    def test_entry_with_both_fields_passes(self) -> None:
        state = {
            "tasks": [
                {
                    "id": "1",
                    "name": "do the thing",
                    "status": "pending",
                    "description": "rewrite the state-schema task rows",
                    "blocked_by": [2, 3],
                },
            ],
        }
        self.assertIsNone(schema.validate(state))

    def test_empty_tasks_list_passes(self) -> None:
        self.assertIsNone(schema.validate({"tasks": []}))

    def test_non_dict_entry_is_skipped_not_rejected(self) -> None:
        # Pre-existing tolerance: validate() only ever required `tasks` itself
        # to be a list. The new per-entry check must not narrow that.
        for bad in ("stray", None, 42, [1, 2]):
            with self.subTest(entry=bad):
                state = {"tasks": [bad, {"id": "1", "description": "fine"}]}
                self.assertIsNone(schema.validate(state))


def tasks_with_offender_at(index: int, offender: dict, total: int) -> list:
    """A `total`-long tasks list of well-formed entries, `offender` at `index`.

    Filler entries carry neither `description` nor `blocked_by`, so the only
    thing any per-entry rule can trip on is the offender itself.
    """
    tasks = [{"id": str(i), "name": f"task {i}"} for i in range(total)]
    tasks[index] = offender
    return tasks


# Every offending entry must be found wherever it sits: alone, behind good
# entries, and -- the interior cases -- surrounded by good entries on BOTH
# sides in a longer list. An implementation that inspects only a fixed handful
# of slots (first, second, last) passes the first three and fails the last two.
OFFENDER_POSITIONS = (
    ("alone at index 0", 0, 1),
    ("at index 1 of 2", 1, 2),
    ("at index 2 of 3", 2, 3),
    ("interior at index 2 of 5", 2, 5),
    ("interior at index 3 of 6", 3, 6),
)


class ValidateTaskDescriptionFieldTest(unittest.TestCase):
    """tasks[].description: optional, must be str when present."""

    def test_well_formed_description_passes(self) -> None:
        for label, value in (("prose", "rewrite the schema doc"), ("empty str", "")):
            with self.subTest(label=label):
                self.assertIsNone(
                    schema.validate({"tasks": [{"id": "1", "description": value}]}),
                )

    def test_rejects_non_str_description_naming_its_entry_index(self) -> None:
        # The rule is positive -- "must be str" -- so the sample pool spans
        # unrelated corners of the type space (numbers, bytes, containers,
        # sets). Enumerating a fixed list of "bad" types cannot cover it.
        for label, value in (
            ("int", 3),
            ("float", 1.5),
            ("none", None),
            ("bytes", b"rewrite the doc"),
            ("list", ["a"]),
            ("tuple", ("a",)),
            ("set", {"a"}),
            ("dict", {"text": "a"}),
            ("bool", True),
        ):
            for position, index, total in OFFENDER_POSITIONS:
                with self.subTest(label=label, position=position):
                    offender = {"id": "x", "description": value}
                    state = {"tasks": tasks_with_offender_at(index, offender, total)}
                    with self.assertRaises(schema.SchemaError) as ctx:
                        schema.validate(state)
                    self.assertIn(f"tasks[{index}].description", str(ctx.exception))

    def test_error_message_names_the_offending_description_value(self) -> None:
        # The module names "the field and its offending value"; a message that
        # is only a field path leaves the operator grepping state.json by hand.
        state = {"tasks": [{"id": "1", "description": 4242}]}
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        msg = str(ctx.exception)
        self.assertIn("tasks[0].description", msg)
        self.assertIn("4242", msg)

    def test_error_message_for_a_giant_bad_description_is_bounded(self) -> None:
        # A message built by interpolating the raw value would drag all 100K
        # chars into the log and the operator's terminal; it must be truncated
        # -- truncated, not dropped, so the head of the value still identifies
        # which value was rejected.
        state = {"tasks": [{"id": "1", "description": ["x" * 100_000]}]}
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        msg = str(ctx.exception)
        self.assertIn("tasks[0].description", msg)
        self.assertIn("x" * 50, msg)
        self.assertLess(len(msg), 500)

    def test_reports_the_first_offending_entry_only(self) -> None:
        state = {
            "tasks": [
                {"id": "1"},
                {"id": "2", "description": 2},
                {"id": "3", "description": 3},
            ],
        }
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        msg = str(ctx.exception)
        self.assertIn("tasks[1].description", msg)
        self.assertNotIn("tasks[2]", msg)


class ValidateTaskBlockedByFieldTest(unittest.TestCase):
    """tasks[].blocked_by: optional, must be a list of plain int when present."""

    def test_well_formed_blocked_by_passes(self) -> None:
        for label, value in (
            ("empty list", []),
            ("single", [1]),
            ("several", [1, 2, 3]),
            ("zero and negative", [0, -1]),
        ):
            with self.subTest(label=label):
                self.assertIsNone(
                    schema.validate({"tasks": [{"id": "1", "blocked_by": value}]}),
                )

    def test_rejects_non_list_blocked_by_naming_its_entry_index(self) -> None:
        # "Must be a list" is a positive rule: every other container and scalar
        # shape is out, including the ones that iterate like a list (tuple,
        # set, bytes) and would slip past a fixed roster of rejected types.
        for label, value in (
            ("int", 1),
            ("float", 1.5),
            ("str", "1,2"),
            ("bytes", b"\x01\x02"),
            ("none", None),
            ("dict", {"0": 1}),
            ("tuple", (1, 2)),
            ("set", {1, 2}),
        ):
            for position, index, total in OFFENDER_POSITIONS:
                with self.subTest(label=label, position=position):
                    offender = {"id": "x", "blocked_by": value}
                    state = {"tasks": tasks_with_offender_at(index, offender, total)}
                    with self.assertRaises(schema.SchemaError) as ctx:
                        schema.validate(state)
                    self.assertIn(f"tasks[{index}].blocked_by", str(ctx.exception))

    def test_rejects_non_int_element_naming_its_entry_index(self) -> None:
        # `True`/`False` are the carve-out cases: bool is a subclass of int in
        # Python, but require()'s existing bool-is-not-int rule extends here.
        # Half the cases put the bad element FIRST with a valid int after it,
        # so checking only one end of the list is not enough to pass. The rule
        # is positive -- every element must be a plain int -- so the pool spans
        # scalars and containers alike, not a fixed roster of bad types.
        for label, value in (
            ("str element last", [1, "2"]),
            ("str element first", ["a", 2]),
            ("bytes element last", [1, b"2"]),
            ("none element alone", [None]),
            ("none element first", [None, 3]),
            ("float element last", [1.0]),
            ("float element first", [1.5, 2]),
            ("nested list alone", [[1]]),
            ("nested list first", [[1], 2]),
            ("dict element alone", [{"id": 1}]),
            ("dict element first", [{"id": 1}, 2]),
            ("tuple element last", [1, (2,)]),
            ("tuple element first", [(1,), 2]),
            ("set element alone", [{1}]),
            ("bool true last", [1, True]),
            ("bool true first", [True, 1]),
            ("bool false alone", [False]),
            ("bool false first", [False, 1]),
        ):
            for position, index, total in OFFENDER_POSITIONS:
                with self.subTest(label=label, position=position):
                    offender = {"id": "x", "blocked_by": value}
                    state = {"tasks": tasks_with_offender_at(index, offender, total)}
                    with self.assertRaises(schema.SchemaError) as ctx:
                        schema.validate(state)
                    self.assertIn(f"tasks[{index}].blocked_by", str(ctx.exception))

    def test_error_message_names_the_offending_blocked_by_value(self) -> None:
        # Same contract as description: the message identifies the value, not
        # just the field path. Both rejection branches (whole value, single
        # element) owe the operator the value they tripped on.
        for label, value, expected in (
            ("non-list value", "nope", "nope"),
            ("non-int element", ["nope-element"], "nope-element"),
        ):
            with self.subTest(label=label):
                state = {"tasks": [{"id": "1", "blocked_by": value}]}
                with self.assertRaises(schema.SchemaError) as ctx:
                    schema.validate(state)
                msg = str(ctx.exception)
                self.assertIn("tasks[0].blocked_by", msg)
                self.assertIn(expected, msg)

    def test_error_message_for_a_giant_bad_blocked_by_is_bounded(self) -> None:
        for label, value in (
            ("giant non-list value", "x" * 100_000),
            ("giant non-int element", ["x" * 100_000]),
        ):
            with self.subTest(label=label):
                state = {"tasks": [{"id": "1", "blocked_by": value}]}
                with self.assertRaises(schema.SchemaError) as ctx:
                    schema.validate(state)
                msg = str(ctx.exception)
                self.assertIn("tasks[0].blocked_by", msg)
                self.assertIn("x" * 50, msg)
                self.assertLess(len(msg), 500)

    def test_reports_the_first_offending_entry_only(self) -> None:
        state = {
            "tasks": [
                {"id": "1"},
                {"id": "2", "blocked_by": "nope"},
                {"id": "3", "blocked_by": [True]},
            ],
        }
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        msg = str(ctx.exception)
        self.assertIn("tasks[1].blocked_by", msg)
        self.assertNotIn("tasks[2]", msg)


if __name__ == "__main__":
    unittest.main()
