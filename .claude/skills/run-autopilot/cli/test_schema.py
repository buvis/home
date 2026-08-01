#!/usr/bin/env python3
"""Tests for cli/schema.py: state shape/type/enum validation + version stamp.

schema.py is stdlib-only. It exposes:
  - SCHEMA_VERSION: int, the current schema stamp.
  - SchemaError: raised by validate(), naming the offending field.
  - validate(state: dict) -> None: whole-state shape/type/enum check of
    KNOWN fields only. Nothing is required; unknown top-level fields are
    tolerated. Raises on the FIRST offending known field.
  - version_status(state: dict) -> str: exhaustive classification of the
    state's "schema_version" key into one of "unstamped" | "current" |
    "old" | "future" | "invalid".

These tests bind only the public contract described in the task brief. No
implementation was read or referenced.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cli import schema

LIVE_STATE_JSON = Path("/Users/bob/.claude/dev/local/autopilot/state.json")
GOLDEN_DIR = Path("/Users/bob/.claude/skills/run-autopilot/scripts/golden")


def valid_state() -> dict:
    """A fresh, fully-populated dict where every documented field is valid.

    Fresh dict/list/nested-dict literals every call, so callers may mutate
    the result freely without cross-test contamination.
    """
    return {
        "phase": "build",
        "next_phase": "review",
        "catchup_mode": "run",
        "design_mode": "run",
        "doubt_reviewer": "codex",
        "consensus_engine": "legacy",
        "cycle": 1,
        "rework_cap": 3,
        "tasks_total": 5,
        "tasks_completed": 2,
        "tasks": [{"id": "1", "name": "do the thing", "status": "pending"}],
        "phases_completed": ["build"],
        "autonomous_decisions": [],
        "deferred_decisions": [],
        "review_cycles": [],
        "doubts": [],
        "batch": {"id": "202607290001", "mode": "autopilot"},
    }


class ValidateFullyPopulatedStateTest(unittest.TestCase):
    def test_fully_populated_valid_state_passes(self) -> None:
        self.assertIsNone(schema.validate(valid_state()))


class ValidateEmptyAndMissingFieldsTest(unittest.TestCase):
    def test_empty_dict_passes(self) -> None:
        self.assertIsNone(schema.validate({}))

    def test_state_missing_phase_passes(self) -> None:
        state = valid_state()
        del state["phase"]
        self.assertIsNone(schema.validate(state))

    def test_state_missing_next_phase_passes(self) -> None:
        state = valid_state()
        del state["next_phase"]
        self.assertIsNone(schema.validate(state))


class ValidateEnumFieldsTest(unittest.TestCase):
    """Each documented enum field, tested independently, out-of-set value."""

    def test_rejects_out_of_enum_phase(self) -> None:
        state = valid_state()
        state["phase"] = "blils"
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        msg = str(ctx.exception)
        self.assertIn("phase", msg)
        self.assertIn("blils", msg)

    def test_rejects_out_of_enum_next_phase(self) -> None:
        state = valid_state()
        state["next_phase"] = "nope"
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        msg = str(ctx.exception)
        self.assertIn("next_phase", msg)
        self.assertIn("nope", msg)

    def test_rejects_out_of_enum_catchup_mode(self) -> None:
        state = valid_state()
        state["catchup_mode"] = "maybe"
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        msg = str(ctx.exception)
        self.assertIn("catchup_mode", msg)
        self.assertIn("maybe", msg)

    def test_rejects_out_of_enum_design_mode(self) -> None:
        state = valid_state()
        state["design_mode"] = "maybe"
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        msg = str(ctx.exception)
        self.assertIn("design_mode", msg)
        self.assertIn("maybe", msg)

    def test_rejects_out_of_enum_doubt_reviewer(self) -> None:
        state = valid_state()
        state["doubt_reviewer"] = "gpt"
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        msg = str(ctx.exception)
        self.assertIn("doubt_reviewer", msg)
        self.assertIn("gpt", msg)

    def test_rejects_out_of_enum_consensus_engine(self) -> None:
        state = valid_state()
        state["consensus_engine"] = "hybrid"
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        msg = str(ctx.exception)
        self.assertIn("consensus_engine", msg)
        self.assertIn("hybrid", msg)


class ValidateLegacyPhaseToleranceTest(unittest.TestCase):
    """Regression guard: legacy phase values must never be rejected."""

    def test_tolerates_legacy_blind_phase(self) -> None:
        state = valid_state()
        state["phase"] = "blind"
        self.assertIsNone(schema.validate(state))

    def test_tolerates_legacy_doubt_phase(self) -> None:
        state = valid_state()
        state["phase"] = "doubt"
        self.assertIsNone(schema.validate(state))

    def test_next_phase_empty_string_passes(self) -> None:
        state = valid_state()
        state["next_phase"] = ""
        self.assertIsNone(schema.validate(state))


class ValidateIntFieldsTest(unittest.TestCase):
    """Each documented int field, tested independently, non-int value."""

    def test_rejects_non_int_cycle(self) -> None:
        state = valid_state()
        state["cycle"] = "3"
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        msg = str(ctx.exception)
        self.assertIn("cycle", msg)
        self.assertIn("3", msg)

    def test_rejects_non_int_rework_cap(self) -> None:
        state = valid_state()
        state["rework_cap"] = "3"
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        msg = str(ctx.exception)
        self.assertIn("rework_cap", msg)
        self.assertIn("3", msg)

    def test_rejects_non_int_tasks_total(self) -> None:
        state = valid_state()
        state["tasks_total"] = "5"
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        msg = str(ctx.exception)
        self.assertIn("tasks_total", msg)
        self.assertIn("5", msg)

    def test_rejects_non_int_tasks_completed(self) -> None:
        state = valid_state()
        state["tasks_completed"] = "2"
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        msg = str(ctx.exception)
        self.assertIn("tasks_completed", msg)
        self.assertIn("2", msg)

    def test_rejects_bool_for_cycle(self) -> None:
        # ASSUMPTION (see report): bool is a subclass of int in Python, but
        # this validator treats bool as NOT a valid int value. A True/False
        # slipping into an int-typed field is always a bug, never a
        # legitimate value, so it is rejected rather than silently coerced.
        state = valid_state()
        state["cycle"] = True
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        self.assertIn("cycle", str(ctx.exception))


class ValidateListFieldsTest(unittest.TestCase):
    """Each documented list field, tested independently, non-list value."""

    def test_rejects_non_list_tasks(self) -> None:
        state = valid_state()
        state["tasks"] = {"id": "1"}
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        self.assertIn("tasks", str(ctx.exception))

    def test_rejects_non_list_phases_completed(self) -> None:
        state = valid_state()
        state["phases_completed"] = {"build": True}
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        self.assertIn("phases_completed", str(ctx.exception))

    def test_rejects_non_list_autonomous_decisions(self) -> None:
        state = valid_state()
        state["autonomous_decisions"] = {"a": 1}
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        self.assertIn("autonomous_decisions", str(ctx.exception))

    def test_rejects_non_list_deferred_decisions(self) -> None:
        state = valid_state()
        state["deferred_decisions"] = {"a": 1}
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        self.assertIn("deferred_decisions", str(ctx.exception))

    def test_rejects_non_list_review_cycles(self) -> None:
        state = valid_state()
        state["review_cycles"] = {"a": 1}
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        self.assertIn("review_cycles", str(ctx.exception))

    def test_rejects_non_list_doubts(self) -> None:
        state = valid_state()
        state["doubts"] = {"a": 1}
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        self.assertIn("doubts", str(ctx.exception))


class ValidateBatchFieldTest(unittest.TestCase):
    def test_rejects_non_dict_batch(self) -> None:
        state = valid_state()
        state["batch"] = "202607290001"
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        self.assertIn("batch", str(ctx.exception))

    def test_rejects_batch_id_wrong_type(self) -> None:
        state = valid_state()
        state["batch"] = {"id": 123}
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        msg = str(ctx.exception)
        self.assertIn("batch", msg)
        self.assertIn("123", msg)

    def test_empty_batch_dict_passes(self) -> None:
        state = valid_state()
        state["batch"] = {}
        self.assertIsNone(schema.validate(state))


class ValidateUnknownFieldsToleratedTest(unittest.TestCase):
    def test_tolerates_unknown_top_level_string_field(self) -> None:
        state = valid_state()
        state["contract_card"] = "anything"
        self.assertIsNone(schema.validate(state))

    def test_tolerates_unknown_top_level_bool_field(self) -> None:
        state = valid_state()
        state["needs_attention"] = False
        self.assertIsNone(schema.validate(state))

    def test_tolerates_multiple_unknown_top_level_fields_together(self) -> None:
        state = valid_state()
        state["contract_card"] = "anything"
        state["needs_attention"] = False
        state["some_future_field"] = {"nested": [1, 2, 3]}
        self.assertIsNone(schema.validate(state))


class ValidateFirstOffendingFieldTest(unittest.TestCase):
    def test_reports_exactly_one_field_when_several_are_wrong(self) -> None:
        # Three independently-invalid known fields, chosen so none of their
        # names is a substring of another (unlike e.g. "phase" / "next_phase").
        state = {
            "cycle": "not-an-int",
            "rework_cap": "also-not-an-int",
            "doubt_reviewer": "gpt",
        }
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate(state)
        msg = str(ctx.exception)
        self.assertTrue(msg, "SchemaError must carry a non-empty message")
        named = [f for f in ("cycle", "rework_cap", "doubt_reviewer") if f in msg]
        self.assertEqual(
            len(named),
            1,
            f"expected exactly one offending field named (the first), got {named} in: {msg!r}",
        )


class SchemaVersionConstantTest(unittest.TestCase):
    def test_schema_version_is_int(self) -> None:
        self.assertIsInstance(schema.SCHEMA_VERSION, int)

    def test_schema_version_equals_documented_value(self) -> None:
        self.assertEqual(schema.SCHEMA_VERSION, 1)


class VersionStatusTest(unittest.TestCase):
    def test_unstamped_when_key_absent(self) -> None:
        self.assertEqual(schema.version_status({}), "unstamped")

    def test_unstamped_ignores_other_fields(self) -> None:
        self.assertEqual(schema.version_status({"phase": "build"}), "unstamped")

    def test_current_when_equal_to_schema_version(self) -> None:
        self.assertEqual(
            schema.version_status({"schema_version": schema.SCHEMA_VERSION}), "current"
        )

    def test_old_when_zero(self) -> None:
        # At SCHEMA_VERSION == 1, 0 is the ONLY reachable 'old' value. This
        # is the branch that was previously unreachable / mis-specified.
        self.assertEqual(schema.version_status({"schema_version": 0}), "old")

    def test_future_when_greater_than_schema_version(self) -> None:
        self.assertEqual(schema.version_status({"schema_version": 2}), "future")

    def test_invalid_for_string(self) -> None:
        self.assertEqual(schema.version_status({"schema_version": "1"}), "invalid")

    def test_invalid_for_float(self) -> None:
        self.assertEqual(schema.version_status({"schema_version": 1.0}), "invalid")

    def test_invalid_for_none(self) -> None:
        self.assertEqual(schema.version_status({"schema_version": None}), "invalid")

    def test_invalid_for_negative_int(self) -> None:
        self.assertEqual(schema.version_status({"schema_version": -1}), "invalid")

    def test_invalid_for_bool_true(self) -> None:
        # Pinned explicitly by the contract's invalid-family list (bool is
        # named alongside str/float/None/negative), unlike the ambiguous
        # int-field bool question in validate().
        self.assertEqual(schema.version_status({"schema_version": True}), "invalid")

    def test_invalid_for_bool_false(self) -> None:
        self.assertEqual(schema.version_status({"schema_version": False}), "invalid")


class ValidateHostileInputTest(unittest.TestCase):
    """Regressions found by the task-2 per-task review, 2026-07-29.

    All three shipped in the first implementation and all three break the
    boundary contract that `transaction()` depends on: it promises its callers
    either a committed write or a raised `SchemaError`, and callers branch on
    documented exit codes derived from exactly that. Any other exception
    escaping, or any silent acceptance, breaks it.
    """

    def test_rejects_unhashable_value_in_enum_field(self) -> None:
        # `state[field] not in allowed` against a set raises TypeError for an
        # unhashable value. Reachable: `statectl set phase '[]'` writes it,
        # since statectl has no validation -- the gap this module closes.
        for bad in ([], {}):
            with self.subTest(value=bad):
                with self.assertRaises(schema.SchemaError) as ctx:
                    schema.validate({"phase": bad})
                self.assertIn("phase", str(ctx.exception))

    def test_rejects_non_dict_state_root(self) -> None:
        # The severe one: a root that is a list or str silently returned None,
        # i.e. a FULL validation bypass -- `transaction()` would then commit a
        # corrupt root through the very boundary meant to prevent it.
        for bad in ([], "x", None, 42):
            with self.subTest(root=bad):
                with self.assertRaises(schema.SchemaError) as ctx:
                    schema.validate(bad)
                self.assertIn("state", str(ctx.exception))

    def test_version_status_classifies_non_dict_state_as_invalid(self) -> None:
        # `version_status(None)` leaked TypeError; `version_status([])`
        # answered "unstamped", which a caller would treat as a healthy
        # legacy state and stamp as current.
        for bad in (None, [], "x", 42):
            with self.subTest(root=bad):
                self.assertEqual(schema.version_status(bad), "invalid")


class LiveStateFixtureTest(unittest.TestCase):
    """The live autopilot state file must always validate clean."""

    def test_live_autopilot_state_validates_clean(self) -> None:
        if not LIVE_STATE_JSON.exists():
            self.skipTest(f"live state fixture not found: {LIVE_STATE_JSON}")
        state = json.loads(LIVE_STATE_JSON.read_text(encoding="utf-8"))
        try:
            schema.validate(state)
        except schema.SchemaError as exc:
            self.fail(f"{LIVE_STATE_JSON}: {exc}")


class GoldenFixturesTest(unittest.TestCase):
    """Every golden state-*.json fixture must always validate clean."""

    def test_all_golden_state_fixtures_validate_clean(self) -> None:
        if not GOLDEN_DIR.exists():
            self.skipTest(f"golden fixtures dir not found: {GOLDEN_DIR}")
        golden_files = sorted(GOLDEN_DIR.glob("state-*.json"))
        self.assertTrue(golden_files, f"no golden fixtures found under {GOLDEN_DIR}")
        for path in golden_files:
            with self.subTest(fixture=path.name):
                state = json.loads(path.read_text(encoding="utf-8"))
                try:
                    schema.validate(state)
                except schema.SchemaError as exc:
                    self.fail(f"{path}: {exc}")


WIDENED_SCALAR_REJECT_CASES = (
    ("prd", lambda s: s.__setitem__("prd", 123), "prd"),
    ("work_start_sha", lambda s: s.__setitem__("work_start_sha", 123), "work_start_sha"),
    ("repo_root", lambda s: s.__setitem__("repo_root", 123), "repo_root"),
    ("design_doc", lambda s: s.__setitem__("design_doc", 123), "design_doc"),
    ("replan_count_non_int", lambda s: s.__setitem__("replan_count", "3"), "replan_count"),
    ("replan_count_bool", lambda s: s.__setitem__("replan_count", True), "replan_count"),
    (
        "batch_parks_consecutive_non_int",
        lambda s: s["batch"].__setitem__("parks_consecutive", "3"),
        "batch.parks_consecutive",
    ),
    (
        "batch_parks_consecutive_bool",
        lambda s: s["batch"].__setitem__("parks_consecutive", True),
        "batch.parks_consecutive",
    ),
    (
        "batch_completed_prds_non_list",
        lambda s: s["batch"].__setitem__("completed_prds", "not-a-list"),
        "batch.completed_prds",
    ),
)

WIDENED_SCALAR_ACCEPT_CASES = (
    ("prd", lambda s: s.__setitem__("prd", "00004-feature-x.md")),
    ("work_start_sha", lambda s: s.__setitem__("work_start_sha", "3f2c1a9")),
    (
        "repo_root",
        lambda s: s.__setitem__("repo_root", "/Users/bob/git/src/github.com/buvis/run-autopilot"),
    ),
    (
        "design_doc",
        lambda s: s.__setitem__(
            "design_doc", "dev/local/prds/wip/00004-feature-x/design.md"
        ),
    ),
    ("replan_count", lambda s: s.__setitem__("replan_count", 0)),
    ("batch_parks_consecutive", lambda s: s["batch"].__setitem__("parks_consecutive", 0)),
    (
        "batch_completed_prds",
        lambda s: s["batch"].__setitem__("completed_prds", ["00001-x.md"]),
    ),
)


class ValidateWidenedScalarFieldsTest(unittest.TestCase):
    """The scalar fields this task adds: prd/work_start_sha/repo_root/design_doc
    (str), replan_count and batch.parks_consecutive (int, bool rejected),
    batch.completed_prds (list). Each is optional -- only checked if present."""

    def test_rejects_malformed_widened_scalar_fields_naming_the_offending_field(self) -> None:
        for label, mutate, expected_name in WIDENED_SCALAR_REJECT_CASES:
            with self.subTest(label=label):
                state = valid_state()
                mutate(state)
                with self.assertRaises(schema.SchemaError) as ctx:
                    schema.validate(state)
                self.assertIn(expected_name, str(ctx.exception))

    def test_well_formed_widened_scalar_fields_pass(self) -> None:
        for label, mutate in WIDENED_SCALAR_ACCEPT_CASES:
            with self.subTest(label=label):
                state = valid_state()
                mutate(state)
                self.assertIsNone(schema.validate(state))


class SchemaErrorReprBoundedTest(unittest.TestCase):
    def test_error_message_for_giant_field_value_is_bounded_not_interpolated_in_full(
        self,
    ) -> None:
        # A MALFORMED giant value (str where int is required): the rejection
        # message must truncate the value, never interpolate all 100K chars.
        # (A giant-but-valid str field passes validation and raises nothing —
        # the widened `prd: str` rule has no length limit.)
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.validate({"replan_count": "x" * 100_000})
        self.assertLess(len(str(ctx.exception)), 500)
        self.assertIsNone(schema.validate({"prd": "x" * 100_000}))


if __name__ == "__main__":
    unittest.main()
