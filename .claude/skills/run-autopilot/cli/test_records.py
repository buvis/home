#!/usr/bin/env python3
"""Tests for cli/records.py: the single per-PRD reset definition and the
idempotent deferred-record append.

records.py exposes:
  - PER_PRD_RESET_FIELDS: tuple of field names removed by the per-PRD reset.
  - reset_prd_fields(state: dict) -> dict: PURE, returns a NEW dict, never
    mutates the input. Removes every PER_PRD_RESET_FIELDS key (absent, not
    None); assigns phases_completed=[], cycle=1, tasks_total=0,
    tasks_completed=0, replan_count=0, phase="build", next_phase="build";
    preserves every other key (in particular `batch`, in full) unchanged.
  - record_defer(path, prd, batch_id, record) -> None: appends one record to
    <path>/deferred/<batch_id>-deferred.json, creating the file (and the
    deferred/ directory) with {"batch_id": ..., "items": []} when absent.
    Stamps record["prd"] with the prd argument. Idempotent by "op_id": a
    record whose op_id matches an existing item's op_id is skipped; a record
    with no op_id is always appended.

These tests bind only the public contract described in the task brief.
records.py was not read (it does not exist yet). references/state-schema.md
was read only to drive the required schema/reset parity test.
"""

from __future__ import annotations

import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cli import records


def _sample_state(**overrides) -> dict:
    """A realistic state dict exercising every PER_PRD_RESET_FIELDS member,
    every RESET_BY_ASSIGNMENT member (with non-default values, to prove the
    reset overwrites rather than merely defaults), and a representative set
    of NOT_RESET members including a fully-populated `batch`.
    """
    base = {
        # PER_PRD_RESET_FIELDS members
        "tasks": [{"id": "t1", "name": "x", "status": "completed"}],
        "task_aborts": [
            {
                "task_id": "t7",
                "turn": -1,
                "total_input_tokens": 13000,
                "cause": "subagent_prompt_overrun",
            },
        ],
        "cap_rotations": [{"task_id": "t3", "cycle": 1}],
        "autonomous_decisions": [{"cycle": 1, "issue": "x"}],
        "deferred_decisions": [{"cycle": 1, "issue": "y"}],
        "review_cycles": [{"cycle": 1, "review_file": "r.md"}],
        "doubts": [{"description": "z"}],
        "doubts_rubric_verdicts": [{"rule_id": "D1", "verdict": "pass"}],
        "rework_task_ids": ["t3"],
        "work_start_sha": "abc123",
        "design_doc": "dev/local/designs/00004-x-design.md",
        "design_gate": "user",
        "design_mode": "run",
        "pause_reason": {"site": "reviewer_fail", "detail": "carl hung"},
        "cap_pause_reason": {
            "cycle": 3,
            "cap": 3,
            "unresolved_findings": [
                {"issue": "x", "severity": "high", "consensus": "3/3"},
            ],
        },
        "stall_reason": {
            "stalled": "oversized_task",
            "task": "t8",
            "estimated_tokens": 167000,
        },
        "repo_root": "/repo",
        "pause_on_ambiguity": True,
        "review_lenses": {"consensus": "done"},
        "contract_card": "step 3, invariant X",
        "needs_attention": True,
        # RESET_BY_ASSIGNMENT members, given non-default values
        "phase": "review",
        "next_phase": "review",
        "phases_completed": ["review"],
        "cycle": 3,
        "tasks_total": 6,
        "tasks_completed": 6,
        "replan_count": 2,
        # NOT_RESET members
        "prd": "00004-feature-x.md",
        "catchup_mode": "skipped",
        "rework_cap": 3,
        "doubt_reviewer": "codex",
        "consensus_engine": "legacy",
        "qwen_gate_failures_consecutive": 1,
        "qwen_breaker": {
            "tripped": False,
            "after_task": None,
            "failed_tasks": [],
            "batch_id": "202603161000",
        },
        "codex_probe": {
            "batch_id": "202603161000",
            "verdict": "healthy",
            "backend": "codex",
            "detail": None,
            "checked_at": "2026-03-16T10:45:00Z",
        },
        "batch": {
            "id": "202603161000",
            "completed_prds": [
                {
                    "filename": "00001-user-auth.md",
                    "cycles": 2,
                    "autonomous_decisions": 3,
                    "escalated_decisions": 0,
                },
            ],
            "catchup_completed_at": "2026-03-16T10:42:13Z",
            "catchup_head_sha": "a1b2c3d4e5f6789",
            "plugin_versions": {
                "aegis@buvis-plugins": "1.2.3",
                "warden@buvis-plugins": "0.13.0",
            },
            "parks_consecutive": 0,
        },
    }
    base.update(overrides)
    return base


class PerPrdResetFieldsTest(unittest.TestCase):
    def test_matches_the_pinned_verbatim_field_set(self) -> None:
        expected = {
            "tasks",
            "task_aborts",
            "cap_rotations",
            "autonomous_decisions",
            "deferred_decisions",
            "review_cycles",
            "doubts",
            "doubts_rubric_verdicts",
            "rework_task_ids",
            "work_start_sha",
            "design_doc",
            "design_gate",
            "design_mode",
            "pause_reason",
            "cap_pause_reason",
            "stall_reason",
            "repo_root",
            "pause_on_ambiguity",
            "review_lenses",
            "contract_card",
            "needs_attention",
        }
        self.assertEqual(set(records.PER_PRD_RESET_FIELDS), expected)


class ResetPrdFieldsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.input_state = _sample_state()
        self.input_snapshot = copy.deepcopy(self.input_state)

    def test_removes_every_per_prd_reset_field(self) -> None:
        result = records.reset_prd_fields(self.input_state)
        for field in records.PER_PRD_RESET_FIELDS:
            self.assertNotIn(field, result, f"{field} should be removed by the reset")

    def test_clears_the_four_fields_that_leak_today(self) -> None:
        result = records.reset_prd_fields(self.input_state)
        for field in (
            "pause_on_ambiguity",
            "review_lenses",
            "contract_card",
            "needs_attention",
        ):
            self.assertNotIn(field, result, f"{field} leaks into the next PRD today")

    def test_resets_counters_and_phase_markers_by_assignment(self) -> None:
        result = records.reset_prd_fields(self.input_state)
        self.assertEqual(result["phases_completed"], [])
        self.assertEqual(result["cycle"], 1)
        self.assertEqual(result["tasks_total"], 0)
        self.assertEqual(result["tasks_completed"], 0)
        self.assertEqual(result["replan_count"], 0)
        self.assertEqual(result["phase"], "build")
        self.assertEqual(result["next_phase"], "build")

    def test_preserves_batch_in_full(self) -> None:
        result = records.reset_prd_fields(self.input_state)
        self.assertEqual(result["batch"], self.input_snapshot["batch"])

    def test_preserves_every_other_key_unchanged(self) -> None:
        result = records.reset_prd_fields(self.input_state)
        untouched_keys = {
            "prd",
            "catchup_mode",
            "rework_cap",
            "doubt_reviewer",
            "consensus_engine",
            "qwen_gate_failures_consecutive",
            "qwen_breaker",
            "codex_probe",
        }
        for key in untouched_keys:
            self.assertEqual(result[key], self.input_snapshot[key])

    def test_does_not_mutate_the_input_dict(self) -> None:
        records.reset_prd_fields(self.input_state)
        self.assertEqual(self.input_state, self.input_snapshot)

    def test_field_listed_in_reset_but_absent_from_input_is_not_an_error(self) -> None:
        minimal = {"phase": "review", "batch": {"id": "b1"}}
        result = records.reset_prd_fields(minimal)
        for field in records.PER_PRD_RESET_FIELDS:
            self.assertNotIn(field, result)
        self.assertEqual(result["phase"], "build")
        self.assertEqual(result["next_phase"], "build")
        self.assertEqual(result["cycle"], 1)
        self.assertEqual(result["batch"], {"id": "b1"})


class RecordDeferTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.autopilot_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _deferred_path(self, batch_id: str) -> Path:
        return self.autopilot_dir / "deferred" / f"{batch_id}-deferred.json"

    def test_creates_file_and_directory_with_skeleton_and_appends_first_record(
        self,
    ) -> None:
        result = records.record_defer(
            self.autopilot_dir,
            "00004-feature-x.md",
            "202603161000",
            {"type": "stall", "site": "wrapper_died", "detail": "died mid-session"},
        )
        self.assertIsNone(result)

        path = self._deferred_path("202603161000")
        self.assertTrue(path.exists())
        content = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(content["batch_id"], "202603161000")
        self.assertEqual(len(content["items"]), 1)
        item = content["items"][0]
        self.assertEqual(item["prd"], "00004-feature-x.md")
        self.assertEqual(item["type"], "stall")
        self.assertEqual(item["site"], "wrapper_died")
        self.assertEqual(item["detail"], "died mid-session")

    def test_accepts_str_path_as_well_as_path_object(self) -> None:
        records.record_defer(str(self.autopilot_dir), "prd.md", "b2", {"type": "doubt"})
        content = json.loads(self._deferred_path("b2").read_text(encoding="utf-8"))
        self.assertEqual(len(content["items"]), 1)

    def test_appends_to_existing_file_preserving_prior_items(self) -> None:
        path = self._deferred_path("b3")
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps(
                {
                    "batch_id": "b3",
                    "items": [
                        {"prd": "00001-old.md", "type": "doubt", "issue": "existing"},
                    ],
                },
            ),
            encoding="utf-8",
        )

        records.record_defer(
            self.autopilot_dir,
            "00002-new.md",
            "b3",
            {"type": "stall", "site": "clarification"},
        )

        content = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(content["items"]), 2)
        self.assertEqual(
            content["items"][0],
            {"prd": "00001-old.md", "type": "doubt", "issue": "existing"},
        )
        self.assertEqual(content["items"][1]["prd"], "00002-new.md")
        self.assertEqual(content["items"][1]["type"], "stall")

    def test_preserves_on_disk_batch_id_over_the_call_argument(self) -> None:
        path = self._deferred_path("b4")
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps({"batch_id": "original-on-disk-id", "items": []}),
            encoding="utf-8",
        )

        records.record_defer(self.autopilot_dir, "prd.md", "b4", {"type": "doubt"})

        content = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(content["batch_id"], "original-on-disk-id")

    def test_stamps_prd_argument_even_when_record_already_carries_a_different_prd(
        self,
    ) -> None:
        records.record_defer(
            self.autopilot_dir,
            "actual.md",
            "b5",
            {"prd": "should-be-overwritten.md", "type": "doubt"},
        )

        content = json.loads(self._deferred_path("b5").read_text(encoding="utf-8"))
        self.assertEqual(content["items"][0]["prd"], "actual.md")

    def test_second_append_with_same_op_id_is_skipped(self) -> None:
        records.record_defer(
            self.autopilot_dir,
            "00001-x.md",
            "b6",
            {"op_id": "abc-123", "type": "stall", "detail": "first"},
        )
        records.record_defer(
            self.autopilot_dir,
            "00002-y.md",
            "b6",
            {"op_id": "abc-123", "type": "stall", "detail": "second-should-be-dropped"},
        )

        content = json.loads(self._deferred_path("b6").read_text(encoding="utf-8"))
        self.assertEqual(len(content["items"]), 1)
        self.assertEqual(content["items"][0]["detail"], "first")
        self.assertEqual(content["items"][0]["prd"], "00001-x.md")

    def test_records_without_op_id_are_always_appended(self) -> None:
        record = {"type": "doubt", "issue": "same content every time"}
        records.record_defer(self.autopilot_dir, "prd.md", "b7", record)
        records.record_defer(self.autopilot_dir, "prd.md", "b7", record)

        content = json.loads(self._deferred_path("b7").read_text(encoding="utf-8"))
        self.assertEqual(len(content["items"]), 2)

    def test_distinct_op_ids_both_land(self) -> None:
        records.record_defer(
            self.autopilot_dir,
            "prd.md",
            "b8",
            {"op_id": "op-1", "type": "doubt"},
        )
        records.record_defer(
            self.autopilot_dir,
            "prd.md",
            "b8",
            {"op_id": "op-2", "type": "doubt"},
        )

        content = json.loads(self._deferred_path("b8").read_text(encoding="utf-8"))
        self.assertEqual(len(content["items"]), 2)
        op_ids = {item["op_id"] for item in content["items"]}
        self.assertEqual(op_ids, {"op-1", "op-2"})

    def test_file_remains_valid_json_after_several_appends(self) -> None:
        for i in range(5):
            records.record_defer(
                self.autopilot_dir,
                f"prd-{i}.md",
                "b9",
                {"type": "doubt", "n": i},
            )

        # Only json.load succeeding is asserted -- the contract explicitly
        # forbids asserting on whitespace or formatting.
        with self._deferred_path("b9").open(encoding="utf-8") as fh:
            content = json.load(fh)
        self.assertEqual(len(content["items"]), 5)


class SchemaResetParityTest(unittest.TestCase):
    """Every field documented in state-schema.md's Field Descriptions table
    must fall into exactly one reset bucket: removed by the per-PRD reset,
    reset by direct assignment, or deliberately left untouched. A field in
    zero or more than one bucket means a schema addition shipped without
    anyone deciding how reset_prd_fields should treat it.
    """

    RESET_BY_ASSIGNMENT = frozenset(
        {
            "phase",
            "next_phase",
            "phases_completed",
            "cycle",
            "tasks_total",
            "tasks_completed",
            "replan_count",
        },
    )

    NOT_RESET = frozenset(
        {
            "prd",
            "batch",
            "catchup_mode",
            "rework_cap",
            "doubt_reviewer",
            "consensus_engine",
            "qwen_gate_failures_consecutive",
            "qwen_breaker",
            "codex_probe",
            "qwen_preflight",
            "phase_guard",
            "thrash_halt",
        },
    )

    @staticmethod
    def _parse_top_level_field_names() -> list:
        schema_path = (
            Path(__file__).resolve().parent.parent / "references" / "state-schema.md"
        )
        lines = schema_path.read_text(encoding="utf-8").splitlines()

        start = None
        for i, line in enumerate(lines):
            if line.strip() == "## Field Descriptions":
                start = i + 1
                break
        if start is None:
            raise AssertionError(
                "'## Field Descriptions' heading not found in state-schema.md",
            )

        end = len(lines)
        for i in range(start, len(lines)):
            if lines[i].startswith("## "):
                end = i
                break

        names = []
        for line in lines[start:end]:
            if not line.lstrip().startswith("|"):
                continue
            match = re.search(r"`([^`]+)`", line)
            if not match:
                continue
            token = match.group(1)
            if re.fullmatch(r"[a-z0-9_]+", token):
                names.append(token)
        return names

    def test_parser_finds_a_sane_number_of_fields(self) -> None:
        names = self._parse_top_level_field_names()
        self.assertGreaterEqual(
            len(names),
            30,
            "field-name parser returned too few names -- a silent parse "
            "failure must not be able to green this test for free",
        )

    def test_every_schema_field_has_exactly_one_reset_decision(self) -> None:
        names = self._parse_top_level_field_names()
        reset_removed = set(records.PER_PRD_RESET_FIELDS)

        for name in names:
            count = sum(
                (
                    name in reset_removed,
                    name in self.RESET_BY_ASSIGNMENT,
                    name in self.NOT_RESET,
                ),
            )
            self.assertEqual(
                count,
                1,
                f"schema field `{name}` is in {count} of the three reset "
                f"buckets (removed / reset-by-assignment / not-reset); it "
                f"needs an explicit reset decision",
            )


if __name__ == "__main__":
    unittest.main()
