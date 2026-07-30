#!/usr/bin/env python3
"""Tests for cli/records.do_park: the Phase 0 park handler that consumes the
<autopilot_dir>/park-requested marker end-to-end.

do_park does not exist yet (records.py currently exposes reset_prd_fields,
record_defer, do_stall). These tests bind only the do_park contract given in
the task brief:

  do_park(state_path, *, prds_dir, autopilot_dir) -> int

  no marker            -> exit 3 (nothing to do; caller falls through)
  malformed            -> delete marker, log one line, exit 3
  stale                -> RECONCILE, then delete marker, exit 3
  park -> continue     -> the park transaction, exit 0
  park -> systemic halt -> the park transaction + pause, exit 5

  The park transaction is do_stall(site="wrapper_died", detail=<marker
  reason>) with ONE composed commit: its step-5 mutator additionally
  increments batch.parks_consecutive, and on the systemic branch also sets
  phase/next_phase="paused" and pause_reason={"site":"systemic_park",...}.
  Marker delete is LAST, after the commit. The match is on BOTH the marker's
  PRD and any pending stall_op's site; a stall_op naming a different PRD than
  the marker is a conflict (exit 10) regardless of wip/ placement.

  Exit codes: 0 parked | 3 no/ignored/reconciled marker | 5 parked AND
  systemic halt | 10 stall_op conflict | 2 state error. (Exit 4/9, inherited
  from do_stall, and exit 1, owned by the argparse layer, are out of scope
  here -- covered by test_records_stall.py.)

reset_prd_fields, record_defer, and do_stall are exercised only indirectly
here (through do_park); their own contracts are covered in test_records.py
and test_records_stall.py and are not re-tested in this file.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cli import records
from cli import state as state_module


FAILPOINT_ENV = "_AUTOPILOT_CLI_FAILPOINT"


def _without(state: dict, *keys: str) -> dict:
    """A shallow copy of `state` with `keys` dropped, for equality checks
    that must ignore write-boundary bookkeeping fields (schema_version)."""
    return {k: v for k, v in state.items() if k not in keys}


class _ParkTestCase(unittest.TestCase):
    """Shared fixture: <root>/prds/wip (pre-created), <root>/prds/hold (left
    absent unless a test needs the PRD pre-placed there),
    <root>/autopilot/state.json, <root>/autopilot/park-requested.
    """

    PRD = "00010-sample-prd.md"

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

    def _put_in_hold(self, prd: str | None = None, content: str = "prd body") -> None:
        (self.prds_dir / "hold").mkdir(parents=True, exist_ok=True)
        (self.prds_dir / "hold" / (prd or self.PRD)).write_text(content, encoding="utf-8")

    def _in_wip(self, prd: str | None = None) -> bool:
        return (self.prds_dir / "wip" / (prd or self.PRD)).exists()

    def _in_hold(self, prd: str | None = None) -> bool:
        return (self.prds_dir / "hold" / (prd or self.PRD)).exists()

    # -- marker -----------------------------------------------------------
    def _write_marker(self, prd: str | None = None, reason: str = "wrapper died mid-session") -> None:
        self.marker_path.write_text(
            json.dumps({"prd": prd if prd is not None else self.PRD, "reason": reason}),
            encoding="utf-8",
        )

    def _write_raw_marker(self, text: str) -> None:
        self.marker_path.write_text(text, encoding="utf-8")

    def _marker_exists(self) -> bool:
        return self.marker_path.exists()

    # -- state ----------------------------------------------------------
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
                "id": "202607300000",
                "completed_prds": [],
                "parks_consecutive": 0,
            },
        }
        base.update(overrides)
        return base

    # -- deferred log -----------------------------------------------------
    def _deferred_path(self, batch_id: str = "202607300000") -> Path:
        return self.autopilot_dir / "deferred" / f"{batch_id}-deferred.json"

    def _deferred_items(self, batch_id: str = "202607300000") -> list:
        path = self._deferred_path(batch_id)
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))["items"]

    # -- call under test --------------------------------------------------
    def _do_park(self) -> int:
        return records.do_park(
            self.state_path,
            prds_dir=self.prds_dir,
            autopilot_dir=self.autopilot_dir,
        )


class NoMarkerNoStallOpTests(_ParkTestCase):
    def test_no_marker_and_no_stall_op_exits_3_and_changes_nothing(self) -> None:
        self._write_state(self._sample_state())
        before = self._state()

        rc = self._do_park()

        self.assertEqual(rc, 3)
        self.assertFalse(self._marker_exists())
        self.assertEqual(self._deferred_items(), [])
        self.assertEqual(_without(self._state(), "schema_version"), _without(before, "schema_version"))


class MalformedMarkerTests(_ParkTestCase):
    def test_unparseable_json_marker_is_deleted_and_ignored(self) -> None:
        self._write_raw_marker("{not valid json")
        self._write_state(self._sample_state(batch={
            "id": "202607300000", "completed_prds": [], "parks_consecutive": 1,
        }))
        before = self._state()

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = self._do_park()

        self.assertEqual(rc, 3)
        self.assertFalse(self._marker_exists())
        self.assertEqual(buf.getvalue().rstrip("\n"), "autopilot: park-requested malformed; ignoring")
        self.assertEqual(_without(self._state(), "schema_version"), _without(before, "schema_version"))

    def test_marker_missing_or_empty_prd_is_deleted_and_ignored(self) -> None:
        cases = (
            ("missing prd key", json.dumps({"reason": "no prd field"})),
            ("empty prd value", json.dumps({"prd": "", "reason": "empty prd field"})),
        )
        for label, raw in cases:
            with self.subTest(label=label):
                self._write_raw_marker(raw)
                self._write_state(self._sample_state(batch={
                    "id": "202607300000", "completed_prds": [], "parks_consecutive": 1,
                }))
                before = self._state()

                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = self._do_park()

                self.assertEqual(rc, 3)
                self.assertFalse(self._marker_exists())
                self.assertEqual(
                    buf.getvalue().rstrip("\n"), "autopilot: park-requested malformed; ignoring"
                )
                self.assertEqual(
                    _without(self._state(), "schema_version"), _without(before, "schema_version")
                )


class StaleMarkerTests(_ParkTestCase):
    def test_marker_prd_not_in_wip_and_no_stall_op_is_deleted_as_stale(self) -> None:
        self._write_marker(reason="wrapper died mid-session")
        self._write_state(self._sample_state(batch={
            "id": "202607300000", "completed_prds": [], "parks_consecutive": 1,
        }))
        before = self._state()

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = self._do_park()

        self.assertEqual(rc, 3)
        self.assertFalse(self._marker_exists())
        self.assertEqual(
            buf.getvalue().rstrip("\n"),
            f"autopilot: park-requested named {self.PRD} not in wip/; ignoring",
        )
        self.assertEqual(_without(self._state(), "schema_version"), _without(before, "schema_version"))


class NormalParkTests(_ParkTestCase):
    def test_normal_park_moves_prd_records_stall_and_resets_state(self) -> None:
        self._put_in_wip()
        self._write_marker(reason="wrapper died mid-session")
        self._write_state(self._sample_state(batch={
            "id": "202607300000", "completed_prds": [], "parks_consecutive": 0,
        }))

        rc = self._do_park()

        self.assertEqual(rc, 0)
        self.assertFalse(self._in_wip())
        self.assertTrue(self._in_hold())
        self.assertFalse(self._marker_exists())

        items = self._deferred_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "stall")
        self.assertEqual(items[0]["site"], "wrapper_died")
        self.assertEqual(items[0]["detail"], "wrapper died mid-session")
        self.assertEqual(items[0]["prd"], self.PRD)
        self.assertIsInstance(items[0]["op_id"], str)
        self.assertTrue(items[0]["op_id"])

        final = self._state()
        self.assertNotIn("stall_op", final)
        self.assertNotIn("tasks", final, "reset_prd_fields must have run")
        self.assertEqual(final["cycle"], 1)
        self.assertEqual(final["phase"], "build")
        self.assertEqual(final["next_phase"], "build")
        self.assertEqual(final["batch"]["parks_consecutive"], 1)


class SystemicHaltTests(_ParkTestCase):
    def test_second_consecutive_park_triggers_systemic_halt(self) -> None:
        self._put_in_wip()
        self._write_marker(reason="wrapper died mid-session")
        self._write_state(self._sample_state(batch={
            "id": "202607300000", "completed_prds": [], "parks_consecutive": 1,
        }))

        rc = self._do_park()

        self.assertEqual(rc, 5)
        self.assertFalse(self._in_wip())
        self.assertTrue(self._in_hold())
        self.assertFalse(self._marker_exists())

        final = self._state()
        self.assertEqual(final["phase"], "paused")
        self.assertEqual(final["next_phase"], "paused")
        self.assertEqual(final["pause_reason"]["site"], "systemic_park")
        self.assertTrue(final["pause_reason"].get("detail"), "detail must be a non-empty string")
        self.assertEqual(final["batch"]["parks_consecutive"], 2)

        items = self._deferred_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["site"], "wrapper_died")


class OneCommitAssertionTests(_ParkTestCase):
    """The commit-counter spy: wraps cli.records.state.transaction so it
    still delegates to the real implementation, while recording every
    committed (returned) state. Proves the increment never lands in a commit
    that doesn't already carry the reset (and, on the systemic branch, the
    pause)."""

    def _run_with_commit_spy(self):
        committed: list = []
        original_transaction = state_module.transaction

        def _spy(*args, **kwargs):
            result = original_transaction(*args, **kwargs)
            committed.append(result)
            return result

        with mock.patch("cli.records.state.transaction", side_effect=_spy):
            rc = self._do_park()
        return rc, committed

    def test_normal_park_lands_the_increment_and_the_reset_in_the_same_commit(self) -> None:
        self._put_in_wip()
        self._write_marker(reason="wrapper died mid-session")
        self._write_state(self._sample_state(batch={
            "id": "202607300000", "completed_prds": [], "parks_consecutive": 0,
        }))

        rc, committed = self._run_with_commit_spy()

        self.assertEqual(rc, 0)
        incremented = [s for s in committed if s.get("batch", {}).get("parks_consecutive") == 1]
        self.assertEqual(len(incremented), 1, "the increment must land in exactly one committed state")
        self.assertEqual(incremented[0]["cycle"], 1, "that same commit must already carry the reset")
        self.assertNotIn("stall_op", incremented[0])

    def test_systemic_halt_lands_increment_reset_and_pause_in_the_same_commit(self) -> None:
        self._put_in_wip()
        self._write_marker(reason="wrapper died mid-session")
        self._write_state(self._sample_state(batch={
            "id": "202607300000", "completed_prds": [], "parks_consecutive": 1,
        }))

        rc, committed = self._run_with_commit_spy()

        self.assertEqual(rc, 5)
        incremented = [s for s in committed if s.get("batch", {}).get("parks_consecutive") == 2]
        self.assertEqual(len(incremented), 1, "the increment must land in exactly one committed state")
        self.assertEqual(incremented[0]["cycle"], 1)
        self.assertEqual(incremented[0]["phase"], "paused")
        self.assertEqual(incremented[0]["pause_reason"]["site"], "systemic_park")

        for s in committed:
            if s.get("batch", {}).get("parks_consecutive") == 2:
                self.assertEqual(
                    s.get("phase"), "paused",
                    "no committed state may carry the incremented counter without the pause",
                )


class FailpointRecoveryTests(_ParkTestCase):
    def test_after_commit_before_marker_delete_leaves_marker_and_recovers_as_stale_on_retry(self) -> None:
        self._put_in_wip()
        self._write_marker(reason="wrapper died mid-session")
        self._write_state(self._sample_state(batch={
            "id": "202607300000", "completed_prds": [], "parks_consecutive": 0,
        }))

        with mock.patch.dict(os.environ, {FAILPOINT_ENV: "after-commit-before-marker-delete"}):
            with self.assertRaises(RuntimeError) as ctx:
                self._do_park()
        self.assertEqual(str(ctx.exception), "failpoint: after-commit-before-marker-delete")

        self.assertTrue(self._marker_exists(), "marker delete happens after the commit")
        self.assertTrue(self._in_hold())
        self.assertFalse(self._in_wip())
        partial = self._state()
        self.assertNotIn("stall_op", partial)
        self.assertEqual(partial["cycle"], 1)
        self.assertEqual(partial["batch"]["parks_consecutive"], 1)
        self.assertEqual(len(self._deferred_items()), 1)

        # Retry without the failpoint: the marker now names a PRD no longer
        # in wip/, with no pending stall_op -- the stale row.
        rc = self._do_park()

        self.assertEqual(rc, 3)
        self.assertFalse(self._marker_exists())
        self.assertEqual(self._state()["batch"]["parks_consecutive"], 1, "no second increment")
        self.assertEqual(len(self._deferred_items()), 1, "no second deferred record")


class ResumeInFlightParkTests(_ParkTestCase):
    def test_resumes_a_park_left_mid_wip_by_reusing_its_stored_op_id(self) -> None:
        self._put_in_wip()
        self._write_marker(reason="wrapper died mid-session")
        state = self._sample_state(batch={
            "id": "202607300000", "completed_prds": [], "parks_consecutive": 0,
        })
        state["stall_op"] = {
            "op_id": "op-resume-1",
            "prd": self.PRD,
            "site": "wrapper_died",
            "detail": "wrapper died mid-session",
        }
        self._write_state(state)

        rc = self._do_park()

        self.assertEqual(rc, 0)
        self.assertFalse(self._marker_exists())
        self.assertFalse(self._in_wip())
        self.assertTrue(self._in_hold())

        items = self._deferred_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0]["op_id"], "op-resume-1",
            "resuming an in-flight intent must reuse its op_id, not mint a new one",
        )
        self.assertEqual(items[0]["site"], "wrapper_died")

        final = self._state()
        self.assertNotIn("stall_op", final)
        self.assertEqual(final["cycle"], 1)
        self.assertEqual(final["batch"]["parks_consecutive"], 1)


class NonWrapperCoexistenceTests(_ParkTestCase):
    def test_pending_design_gate_stall_is_reconciled_before_the_park_runs(self) -> None:
        self._put_in_wip()
        self._write_marker(reason="wrapper died mid-session")
        state = self._sample_state(batch={
            "id": "202607300000", "completed_prds": [], "parks_consecutive": 1,
        })
        state["stall_op"] = {
            "op_id": "op-dg-1",
            "prd": self.PRD,
            "site": "design_gate",
            "detail": "waiting on design review",
        }
        self._write_state(state)

        rc = self._do_park()

        self.assertEqual(rc, 0)
        self.assertFalse(self._marker_exists())
        self.assertFalse(self._in_wip())
        self.assertTrue(self._in_hold())

        items = self._deferred_items()
        self.assertEqual(len(items), 2, "the reconciled design_gate stall plus the park itself")
        self.assertEqual(items[0]["op_id"], "op-dg-1")
        self.assertEqual(items[0]["site"], "design_gate")
        self.assertEqual(items[1]["site"], "wrapper_died")
        self.assertNotEqual(items[1]["op_id"], "op-dg-1", "the park is a distinct operation")

        final = self._state()
        self.assertNotIn("stall_op", final)
        self.assertEqual(final["cycle"], 1)
        self.assertEqual(
            final["batch"]["parks_consecutive"], 1,
            "the reconcile resets to 0, then the park increments once",
        )


class ReconcileStoredNonWrapperStallNotInWipTests(_ParkTestCase):
    def test_marker_names_a_prd_not_in_wip_with_a_pending_design_gate_stall_op(self) -> None:
        self._put_in_hold()
        self._write_marker(reason="wrapper died mid-session")
        state = self._sample_state(batch={
            "id": "202607300000", "completed_prds": [], "parks_consecutive": 1,
        })
        state["stall_op"] = {
            "op_id": "op-dg-3",
            "prd": self.PRD,
            "site": "design_gate",
            "detail": "waiting on design review",
        }
        self._write_state(state)

        rc = self._do_park()

        self.assertEqual(rc, 3)
        self.assertFalse(self._marker_exists())
        self.assertTrue(self._in_hold())

        items = self._deferred_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["op_id"], "op-dg-3")
        self.assertEqual(items[0]["site"], "design_gate")

        final = self._state()
        self.assertNotIn("stall_op", final)
        self.assertEqual(final["cycle"], 1)
        self.assertEqual(
            final["batch"]["parks_consecutive"], 0, "non-wrapper reconcile resets, never increments"
        )


class MarkerAbsentReconcileTests(_ParkTestCase):
    def test_no_marker_but_a_pending_design_gate_stall_op_is_reconciled(self) -> None:
        self._put_in_wip()
        state = self._sample_state(batch={
            "id": "202607300000", "completed_prds": [], "parks_consecutive": 1,
        })
        state["stall_op"] = {
            "op_id": "op-dg-2",
            "prd": self.PRD,
            "site": "design_gate",
            "detail": "waiting on design review",
        }
        self._write_state(state)

        rc = self._do_park()

        self.assertEqual(rc, 3)
        self.assertFalse(self._marker_exists())
        self.assertFalse(self._in_wip())
        self.assertTrue(self._in_hold())

        items = self._deferred_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["op_id"], "op-dg-2")
        self.assertEqual(items[0]["site"], "design_gate")

        final = self._state()
        self.assertNotIn("stall_op", final)
        self.assertEqual(final["cycle"], 1)
        self.assertEqual(
            final["batch"]["parks_consecutive"], 0, "non-wrapper reconcile resets, never increments"
        )


class CrashMidParkReconcileTests(_ParkTestCase):
    def test_marker_names_a_prd_already_in_hold_with_a_pending_wrapper_died_stall_op(self) -> None:
        self._put_in_hold()
        self._write_marker(reason="died mid-session")
        state = self._sample_state(batch={
            "id": "202607300000", "completed_prds": [], "parks_consecutive": 0,
        })
        state["stall_op"] = {
            "op_id": "op-crashed-1",
            "prd": self.PRD,
            "site": "wrapper_died",
            "detail": "died mid-session",
        }
        self._write_state(state)

        rc = self._do_park()

        self.assertEqual(rc, 3)
        self.assertFalse(self._marker_exists())

        items = self._deferred_items()
        self.assertEqual(len(items), 1, "the interrupted park's own record must land exactly once")
        self.assertEqual(items[0]["op_id"], "op-crashed-1")
        self.assertEqual(items[0]["site"], "wrapper_died")

        final = self._state()
        self.assertNotIn("stall_op", final)
        self.assertEqual(final["cycle"], 1)
        self.assertEqual(
            final["batch"]["parks_consecutive"], 1,
            "the interrupted park's own increment lands exactly once",
        )


class ConflictTests(_ParkTestCase):
    OTHER_PRD = "00099-other-prd.md"

    def test_marker_prd_in_wip_conflicts_with_a_stall_op_naming_a_different_prd(self) -> None:
        self._put_in_wip()
        self._write_marker(reason="wrapper died mid-session")
        state = self._sample_state(prd=self.OTHER_PRD, batch={
            "id": "202607300000", "completed_prds": [], "parks_consecutive": 0,
        })
        state["stall_op"] = {
            "op_id": "op-other-1",
            "prd": self.OTHER_PRD,
            "site": "design_gate",
            "detail": "unrelated",
        }
        self._write_state(state)
        before = self._state()

        rc = self._do_park()

        self.assertEqual(rc, 10)
        self.assertTrue(self._marker_exists())
        self.assertTrue(self._in_wip())
        self.assertFalse(self._in_hold())
        self.assertEqual(self._deferred_items(), [])
        self.assertEqual(_without(self._state(), "schema_version"), _without(before, "schema_version"))

    def test_marker_prd_not_in_wip_conflicts_with_a_stall_op_naming_a_different_prd(self) -> None:
        self._write_marker(reason="wrapper died mid-session")
        state = self._sample_state(prd=self.OTHER_PRD, batch={
            "id": "202607300000", "completed_prds": [], "parks_consecutive": 0,
        })
        state["stall_op"] = {
            "op_id": "op-other-2",
            "prd": self.OTHER_PRD,
            "site": "design_gate",
            "detail": "unrelated",
        }
        self._write_state(state)
        before = self._state()

        rc = self._do_park()

        self.assertEqual(rc, 10)
        self.assertTrue(self._marker_exists())
        self.assertFalse(self._in_wip())
        self.assertFalse(self._in_hold())
        self.assertEqual(self._deferred_items(), [])
        self.assertEqual(_without(self._state(), "schema_version"), _without(before, "schema_version"))


class Exit2Tests(_ParkTestCase):
    def test_unreadable_state_file_exits_2_and_touches_nothing(self) -> None:
        self._put_in_wip()
        self._write_marker(reason="wrapper died mid-session")
        self.state_path.write_text("{not valid json", encoding="utf-8")

        rc = self._do_park()

        self.assertEqual(rc, 2)
        self.assertTrue(self._marker_exists())
        self.assertTrue(self._in_wip())
        self.assertFalse(self._in_hold())


if __name__ == "__main__":
    unittest.main()
