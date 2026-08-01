#!/usr/bin/env python3
"""Tests for cli/records.py: the hardened failure-path contract for do_stall
and do_park (documented exit codes instead of raw tracebacks) plus
record_defer's shape-corruption handling and boundary validation.

do_stall's happy-path, identity-guard, and failpoint-recovery contract is
covered in test_records_stall.py; do_park's marker-driven happy-path,
staleness, conflict, and reconcile contract is covered in
test_records_park.py; reset_prd_fields and record_defer's field-level append
contract is covered in test_records.py. None of those are re-tested here --
this file binds only the failure-mapping contract given in the task brief:

  1. wip->hold move failures (OSError) -> do_stall returns 4, never raises;
     stall_op stays set.
  2. transaction()/commit failures -> do_stall returns 2, never raises.
  3. malformed state.stall_op -> do_stall and do_park return 2 with zero
     filesystem effects (no PRD move, no deferred record, no marker delete).
  4. resume_target(state) never raises on a malformed stall_op; missing or
     non-str op_id/prd are each rendered as the literal string "unknown".
  5. a shape-corrupt <batch_id>-deferred.json makes record_defer raise
     ValueError; do_stall hitting that file during its append step (after
     the move already landed) returns 9.
  6. record_defer boundary-validates prd (bare basename only) and batch_id
     (non-empty str, no "/", no "..", no leading "/"), raising ValueError
     and writing nothing on violation.
  7. a missing/non-str batch.id makes do_stall return 2 before any
     filesystem effect.
  8. a retried record_defer with a duplicate op_id is a true no-op: the
     deferred file is left byte-identical and is not reopened for writing.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cli import records

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from resume_target import resume_target


class _RecordsFailureFixture(unittest.TestCase):
    """<root>/prds/wip (pre-created), <root>/prds/hold (left absent),
    <root>/autopilot/state.json, <root>/autopilot/park-requested. Mirrors
    _StallTestCase in test_records_stall.py and _ParkTestCase in
    test_records_park.py.
    """

    PRD = "00004-feature-x.md"
    BATCH_ID = "202607300000"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.prds_dir = self.root / "prds"
        self.autopilot_dir = self.root / "autopilot"
        self.state_path = self.autopilot_dir / "state.json"
        self.marker_path = self.autopilot_dir / "park-requested"
        (self.prds_dir / "wip").mkdir(parents=True)
        self.autopilot_dir.mkdir(parents=True)

    # -- prd placement ------------------------------------------------
    def _put_in_wip(self, prd: str | None = None, content: str = "prd body") -> None:
        (self.prds_dir / "wip" / (prd or self.PRD)).write_text(content, encoding="utf-8")

    def _in_wip(self, prd: str | None = None) -> bool:
        return (self.prds_dir / "wip" / (prd or self.PRD)).exists()

    def _in_hold(self, prd: str | None = None) -> bool:
        return (self.prds_dir / "hold" / (prd or self.PRD)).exists()

    # -- park marker --------------------------------------------------------
    def _write_marker(self, prd: str | None = None, reason: str = "wrapper died mid-session") -> None:
        self.marker_path.write_text(
            json.dumps({"prd": prd if prd is not None else self.PRD, "reason": reason}),
            encoding="utf-8",
        )

    def _marker_exists(self) -> bool:
        return self.marker_path.exists()

    # -- state ------------------------------------------------------------
    def _write_state(self, state: dict) -> None:
        self.state_path.write_text(json.dumps(state), encoding="utf-8")

    def _state(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _sample_state(self, **overrides) -> dict:
        base = {
            "prd": self.PRD,
            "phase": "build",
            "next_phase": "build",
            "cycle": 2,
            "tasks": [{"id": "t1", "name": "x", "status": "in_progress"}],
            "batch": {
                "id": self.BATCH_ID,
                "completed_prds": [],
                "parks_consecutive": 1,
            },
        }
        base.update(overrides)
        return base

    # -- deferred log -------------------------------------------------------
    def _deferred_path(self, batch_id: str | None = None) -> Path:
        return self.autopilot_dir / "deferred" / f"{batch_id or self.BATCH_ID}-deferred.json"

    def _deferred_dir_exists(self) -> bool:
        return (self.autopilot_dir / "deferred").exists()

    def _deferred_items(self, batch_id: str | None = None) -> list:
        path = self._deferred_path(batch_id)
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))["items"]

    # -- calls under test ---------------------------------------------------
    def _do_stall(self, *, prd=None, site="design_gate", detail="detail text", **kwargs) -> int:
        return records.do_stall(
            self.state_path,
            prd=prd if prd is not None else self.PRD,
            site=site,
            detail=detail,
            prds_dir=self.prds_dir,
            autopilot_dir=self.autopilot_dir,
            **kwargs,
        )

    def _do_park(self) -> int:
        return records.do_park(
            self.state_path,
            prds_dir=self.prds_dir,
            autopilot_dir=self.autopilot_dir,
        )


# ---------------------------------------------------------------------------
# 1. Move failures -> return 4, never raise.
# ---------------------------------------------------------------------------


class MoveFailureReturns4Tests(_RecordsFailureFixture):
    def test_unremovable_wip_file_returns_4_and_keeps_stall_op(self) -> None:
        # hold/ doesn't exist yet so mkdir succeeds; the rename itself is
        # what fails, because the wip/ directory (the rename's source
        # parent) has no write permission -- the OS can look the file up
        # but cannot unlink it from that directory.
        self._put_in_wip()
        self._write_state(self._sample_state())
        wip_dir = self.prds_dir / "wip"
        original_mode = wip_dir.stat().st_mode
        os.chmod(wip_dir, stat.S_IRUSR | stat.S_IXUSR)
        self.addCleanup(os.chmod, wip_dir, original_mode)

        rc = self._do_stall(site="design_gate")

        self.assertEqual(rc, 4, "an OSError during the move must map to exit 4, not raise")
        final = self._state()
        self.assertIn("stall_op", final, "the durable intent must stay set on a failed move")
        self.assertEqual(final["stall_op"]["prd"], self.PRD)
        self.assertEqual(final["stall_op"]["site"], "design_gate")


# ---------------------------------------------------------------------------
# 2. State/transaction failures -> return 2, never raise.
# ---------------------------------------------------------------------------


class StateTransactionFailureReturns2Tests(_RecordsFailureFixture):
    def test_wrapper_died_stall_on_batch_missing_parks_consecutive_returns_2(self) -> None:
        # site="wrapper_died" must preserve batch.parks_consecutive at
        # commit time; when the field isn't there to preserve, the
        # commit-time validator rejects the write.
        self._put_in_wip()
        self._write_state(self._sample_state(batch={
            "id": self.BATCH_ID, "completed_prds": [],
        }))

        rc = self._do_stall(site="wrapper_died")

        self.assertEqual(rc, 2, "a commit-time validator rejection must map to exit 2, not raise")
        # The move and append steps precede the failing commit, so their
        # effects have already landed and stall_op has not been cleared.
        self.assertTrue(self._in_hold())
        self.assertFalse(self._in_wip())
        final = self._state()
        self.assertIn("stall_op", final)
        self.assertEqual(len(self._deferred_items()), 1)

    def test_unwritable_state_store_returns_2_before_any_move(self) -> None:
        # The intent stamp (the first transaction()) is written before any
        # effect; making the state directory unwritable fails that write
        # and nothing downstream (the move) may run.
        self._put_in_wip()
        self._write_state(self._sample_state())
        original_mode = self.autopilot_dir.stat().st_mode
        os.chmod(self.autopilot_dir, stat.S_IRUSR | stat.S_IXUSR)
        self.addCleanup(os.chmod, self.autopilot_dir, original_mode)

        rc = self._do_stall(site="design_gate")

        self.assertEqual(rc, 2, "an unwritable state store must map to exit 2, not raise")
        self.assertTrue(self._in_wip(), "nothing may move when the intent stamp cannot be written")
        self.assertFalse(self._in_hold())


# ---------------------------------------------------------------------------
# 3. Malformed stall_op -> return 2, zero filesystem effects.
# ---------------------------------------------------------------------------


class MalformedStallOpReturns2NoEffectsTests(_RecordsFailureFixture):
    MALFORMED_STALL_OPS = (
        ("not_a_dict", "just a string"),
        ("missing_op_id_and_prd", {"site": "s", "detail": "d"}),
        ("missing_site_and_detail", {"op_id": "x", "prd": _RecordsFailureFixture.PRD}),
    )

    def test_do_stall_with_malformed_stall_op_returns_2_without_filesystem_effects(self) -> None:
        self._put_in_wip()
        self._write_state(self._sample_state())

        for label, malformed in self.MALFORMED_STALL_OPS:
            with self.subTest(label=label):
                current = self._state()
                current["stall_op"] = malformed
                self._write_state(current)

                rc = self._do_stall(site="design_gate")

                self.assertEqual(rc, 2, label)
                self.assertTrue(self._in_wip(), f"{label}: the PRD must not move")
                self.assertFalse(self._in_hold(), label)
                self.assertFalse(
                    self._deferred_dir_exists(), f"{label}: no deferred record may be written"
                )

    def test_do_park_with_malformed_stall_op_returns_2_without_filesystem_effects(self) -> None:
        # A well-formed marker naming a PRD that's actually in wip/ isolates
        # the malformed-stall_op guard from the marker validity/staleness
        # branches covered in test_records_park.py.
        self._put_in_wip()
        self._write_marker()
        self._write_state(self._sample_state())

        for label, malformed in self.MALFORMED_STALL_OPS:
            with self.subTest(label=label):
                current = self._state()
                current["stall_op"] = malformed
                self._write_state(current)

                rc = self._do_park()

                self.assertEqual(rc, 2, label)
                self.assertTrue(self._marker_exists(), f"{label}: no marker may be deleted")
                self.assertTrue(self._in_wip(), f"{label}: the PRD must not move")
                self.assertFalse(self._in_hold(), label)
                self.assertFalse(
                    self._deferred_dir_exists(), f"{label}: no deferred record may be written"
                )


# ---------------------------------------------------------------------------
# 4. resume_target never crashes on a malformed stall_op.
# ---------------------------------------------------------------------------


class ResumeTargetMalformedStallOpNeverCrashesTests(unittest.TestCase):
    def test_missing_or_non_str_fields_are_rendered_as_the_literal_string_unknown(self) -> None:
        cases = (
            ("not_a_dict", "just a string", "reconcile stall unknown for unknown"),
            (
                "missing_both_fields",
                {"site": "design_gate", "detail": "hook failed"},
                "reconcile stall unknown for unknown",
            ),
            (
                "op_id_not_str",
                {"op_id": 42, "prd": "00004-feature-x.md", "site": "s", "detail": "d"},
                "reconcile stall unknown for 00004-feature-x.md",
            ),
            (
                "prd_missing",
                {"op_id": "op-77af3", "site": "s", "detail": "d"},
                "reconcile stall op-77af3 for unknown",
            ),
        )
        for label, malformed_stall_op, expected in cases:
            with self.subTest(label=label):
                state = {
                    "phase": "review",
                    "phases_completed": [],
                    "stall_reason": {"stalled": "oversized_task", "task": "t8"},
                    "stall_op": malformed_stall_op,
                }
                target = resume_target(state)
                self.assertEqual(target, expected)


# ---------------------------------------------------------------------------
# 5. Shape-corrupt deferred file -> ValueError from record_defer, exit 9
#    from do_stall.
# ---------------------------------------------------------------------------


class RecordDeferShapeCorruptionTests(_RecordsFailureFixture):
    SHAPE_CORRUPT_VARIANTS = (
        ("root_is_a_list", ["not", "the", "right", "shape"]),
        ("dict_missing_items", {"batch_id": "b1"}),
        ("items_not_a_list", {"batch_id": "b1", "items": {"oops": "not-a-list"}}),
        ("items_contain_non_dict", {"batch_id": "b1", "items": ["not-a-dict"]}),
    )

    def test_record_defer_raises_valueerror_on_shape_corrupt_existing_file(self) -> None:
        for label, corrupt_shape in self.SHAPE_CORRUPT_VARIANTS:
            with self.subTest(label=label):
                batch_id = f"corrupt-{label}"
                path = self._deferred_path(batch_id)
                path.parent.mkdir(parents=True, exist_ok=True)
                raw = json.dumps(corrupt_shape)
                path.write_text(raw, encoding="utf-8")

                with self.assertRaises(ValueError):
                    records.record_defer(
                        self.autopilot_dir, self.PRD, batch_id, {"type": "doubt"}
                    )

                self.assertEqual(
                    path.read_text(encoding="utf-8"), raw,
                    f"{label}: a rejected append must not touch the corrupt file",
                )

    def test_do_stall_returns_9_when_deferred_file_is_shape_corrupt(self) -> None:
        self._put_in_wip()
        self._write_state(self._sample_state())
        deferred_path = self._deferred_path()
        deferred_path.parent.mkdir(parents=True)
        deferred_path.write_text(json.dumps(["wrong", "shape"]), encoding="utf-8")

        rc = self._do_stall(site="design_gate")

        self.assertEqual(rc, 9, "record_defer's ValueError must map to exit 9, not raise")
        self.assertTrue(self._in_hold(), "the move already landed before the append step")
        self.assertFalse(self._in_wip())
        final = self._state()
        self.assertIn("stall_op", final, "stall_op stays set when the append step fails")


# ---------------------------------------------------------------------------
# 6. Boundary validation in record_defer -> ValueError, writes nothing.
# ---------------------------------------------------------------------------


class RecordDeferBoundaryValidationTests(_RecordsFailureFixture):
    INVALID_PRDS = (
        ("contains_slash", "sub/prd.md"),
        ("is_dotdot", ".."),
    )
    INVALID_BATCH_IDS = (
        ("none", None),
        ("not_a_str", 123),
        ("empty_str", ""),
        ("contains_slash", "b/1"),
        ("contains_dotdot", "b..1"),
        ("starts_with_slash", "/abs"),
    )

    def test_record_defer_rejects_non_basename_prd_writing_nothing(self) -> None:
        for label, bad_prd in self.INVALID_PRDS:
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    records.record_defer(
                        self.autopilot_dir, bad_prd, f"batch-{label}", {"type": "doubt"}
                    )
                self.assertFalse(self._deferred_dir_exists(), f"{label}: nothing may be written")

    def test_record_defer_rejects_invalid_batch_id_writing_nothing(self) -> None:
        for label, bad_batch_id in self.INVALID_BATCH_IDS:
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    records.record_defer(
                        self.autopilot_dir, self.PRD, bad_batch_id, {"type": "doubt"}
                    )
                self.assertFalse(self._deferred_dir_exists(), f"{label}: nothing may be written")

    def test_record_defer_well_formed_call_is_unaffected_by_the_boundary_checks(self) -> None:
        records.record_defer(self.autopilot_dir, self.PRD, self.BATCH_ID, {"type": "doubt"})

        content = json.loads(self._deferred_path().read_text(encoding="utf-8"))
        self.assertEqual(len(content["items"]), 1)
        self.assertEqual(content["items"][0]["prd"], self.PRD)


# ---------------------------------------------------------------------------
# 7. Missing batch.id -> return 2 before any effect.
# ---------------------------------------------------------------------------


class MissingBatchIdReturns2Tests(_RecordsFailureFixture):
    def test_do_stall_returns_2_before_any_effect_when_batch_id_is_absent_or_not_a_str(self) -> None:
        variants = (
            ("no_batch_key", lambda s: s.pop("batch")),
            ("batch_without_id", lambda s: s.__setitem__("batch", {"completed_prds": []})),
            ("batch_id_not_a_str", lambda s: s.__setitem__("batch", {"id": 42, "completed_prds": []})),
        )
        for label, mutate in variants:
            with self.subTest(label=label):
                self._put_in_wip()
                state = self._sample_state()
                mutate(state)
                self._write_state(state)

                rc = self._do_stall(site="design_gate")

                self.assertEqual(rc, 2, label)
                self.assertTrue(self._in_wip(), f"{label}: the PRD must stay in wip/")
                self.assertFalse(self._in_hold(), label)
                self.assertFalse(
                    self._deferred_dir_exists(),
                    f"{label}: no deferred file of any name -- in particular no "
                    "'None-deferred.json' -- may be created",
                )


# ---------------------------------------------------------------------------
# 8. Duplicate-op_id retry is a true no-op on the file.
# ---------------------------------------------------------------------------


class RecordDeferDuplicateOpIdIsANoOpTests(_RecordsFailureFixture):
    def test_retried_append_with_existing_op_id_leaves_the_file_byte_identical_and_unwritten(
        self,
    ) -> None:
        records.record_defer(
            self.autopilot_dir, self.PRD, self.BATCH_ID,
            {"op_id": "dup-op-1", "type": "stall", "detail": "first"},
        )
        path = self._deferred_path()
        before_bytes = path.read_bytes()
        before_mtime_ns = path.stat().st_mtime_ns

        records.record_defer(
            self.autopilot_dir, self.PRD, self.BATCH_ID,
            {"op_id": "dup-op-1", "type": "stall", "detail": "retried-should-not-land"},
        )

        after_bytes = path.read_bytes()
        after_mtime_ns = path.stat().st_mtime_ns
        self.assertEqual(
            after_bytes, before_bytes, "a duplicate op_id retry must not rewrite the file"
        )
        self.assertEqual(
            after_mtime_ns, before_mtime_ns,
            "the file must not even be reopened for writing on a duplicate op_id",
        )


if __name__ == "__main__":
    unittest.main()
