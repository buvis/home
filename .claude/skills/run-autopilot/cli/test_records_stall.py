#!/usr/bin/env python3
"""Tests for cli/records.do_stall: the Loop-mode stall procedure as ONE call
with a durable intent record (stall_op), so a kill at any of its three
internal boundaries is recoverable on retry.

do_stall does not exist yet (records.py currently exposes only
reset_prd_fields and record_defer). These tests bind only the do_stall
contract given in the task brief:

  do_stall(state_path, *, prd, site, detail, prds_dir, autopilot_dir,
           extra_mutator=None) -> int

  0. identity guard: no stall_op -> mint op_id; stall_op.prd == prd -> retry,
     reuse the stored op_id; stall_op naming a different prd, or
     stall_op.prd disagreeing with a non-empty state["prd"], -> exit 10.
  1. mkdir -p <prds_dir>/hold.
  2. transaction(): stamp state.stall_op = {op_id, prd, site, detail} (the
     intent, written before any effect).
  3. move <prds_dir>/wip/<prd> -> <prds_dir>/hold/<prd>, verify arrival;
     already-in-hold + absent-from-wip counts as success.
  4. append {"type": "stall", "site", "detail", "prd", "op_id"} to the batch
     deferred JSON, deduped by op_id.
  5. transaction() commit: reset_prd_fields, reset batch.parks_consecutive to
     0 unless site == "wrapper_died", delete stall_op. One write.

  Exit codes: 0 stalled | 4 move failed/unverified | 9 deferred-record I/O
  failed | 2 state unreadable/unwritable | 1 usage | 10 stall_op conflict.

  _AUTOPILOT_CLI_FAILPOINT, when set to a boundary name, makes do_stall raise
  RuntimeError("failpoint: <name>") at that boundary, simulating a kill.
  Boundaries owned by this task: after-mkdir-before-intent,
  after-intent-before-move, after-move-before-append,
  after-append-before-commit.

reset_prd_fields and record_defer are exercised only indirectly here (through
do_stall); their own field-by-field contracts are covered in test_records.py
and are not re-tested in this file.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cli import records


FAILPOINT_ENV = "_AUTOPILOT_CLI_FAILPOINT"


def _without(state: dict, *keys: str) -> dict:
    """A shallow copy of `state` with `keys` dropped, for equality checks
    that must ignore write-boundary bookkeeping fields (stall_op,
    schema_version)."""
    return {k: v for k, v in state.items() if k not in keys}


class _StallTestCase(unittest.TestCase):
    """Shared fixture: <root>/prds/wip (pre-created), <root>/prds/hold (left
    absent so do_stall's own mkdir -p is exercised by every success path),
    <root>/autopilot/state.json.
    """

    PRD = "00004-feature-x.md"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.prds_dir = self.root / "prds"
        self.autopilot_dir = self.root / "autopilot"
        self.state_path = self.autopilot_dir / "state.json"
        (self.prds_dir / "wip").mkdir(parents=True)
        self.autopilot_dir.mkdir(parents=True)

    # -- prd placement ------------------------------------------------
    def _put_in_wip(self, prd: str | None = None, content: str = "prd body") -> None:
        (self.prds_dir / "wip" / (prd or self.PRD)).write_text(content, encoding="utf-8")

    def _in_wip(self, prd: str | None = None) -> bool:
        return (self.prds_dir / "wip" / (prd or self.PRD)).exists()

    def _in_hold(self, prd: str | None = None) -> bool:
        return (self.prds_dir / "hold" / (prd or self.PRD)).exists()

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
                "parks_consecutive": 1,
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
    def _do_stall(self, *, prd=None, site="design_gate", detail="detail text", **kwargs):
        return records.do_stall(
            self.state_path,
            prd=prd if prd is not None else self.PRD,
            site=site,
            detail=detail,
            prds_dir=self.prds_dir,
            autopilot_dir=self.autopilot_dir,
            **kwargs,
        )


class DoStallSuccessTests(_StallTestCase):
    def test_stall_creates_hold_dir_moves_prd_and_appends_one_deferred_record(self) -> None:
        self._put_in_wip()
        self._write_state(self._sample_state())

        rc = self._do_stall(site="design_gate")

        self.assertEqual(rc, 0)
        self.assertFalse(self._in_wip())
        self.assertTrue(self._in_hold(), "mkdir -p hold/ plus the move must have happened")

        items = self._deferred_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "stall")
        self.assertEqual(items[0]["site"], "design_gate")
        self.assertEqual(items[0]["prd"], self.PRD)
        self.assertEqual(items[0]["detail"], "detail text")
        self.assertIsInstance(items[0]["op_id"], str)
        self.assertTrue(items[0]["op_id"])

        final = self._state()
        self.assertNotIn("stall_op", final)
        self.assertNotIn("tasks", final, "reset_prd_fields must have run")
        self.assertEqual(final["cycle"], 1)
        self.assertEqual(final["phase"], "build")
        self.assertEqual(final["next_phase"], "build")
        self.assertEqual(final["batch"]["id"], "202607300000")

    def test_accepts_str_paths_for_state_prds_dir_and_autopilot_dir(self) -> None:
        self._put_in_wip()
        self._write_state(self._sample_state())

        rc = records.do_stall(
            str(self.state_path),
            prd=self.PRD,
            site="design_gate",
            detail="detail text",
            prds_dir=str(self.prds_dir),
            autopilot_dir=str(self.autopilot_dir),
        )

        self.assertEqual(rc, 0)
        self.assertTrue(self._in_hold())
        self.assertEqual(len(self._deferred_items()), 1)


class ParksConsecutiveTests(_StallTestCase):
    def test_resets_parks_consecutive_to_zero_for_non_wrapper_died_site(self) -> None:
        self._put_in_wip()
        self._write_state(self._sample_state(batch={
            "id": "202607300000", "completed_prds": [], "parks_consecutive": 1,
        }))

        rc = self._do_stall(site="design_gate")

        self.assertEqual(rc, 0)
        self.assertEqual(self._state()["batch"]["parks_consecutive"], 0)

    def test_preserves_parks_consecutive_for_wrapper_died_site(self) -> None:
        self._put_in_wip()
        self._write_state(self._sample_state(batch={
            "id": "202607300000", "completed_prds": [], "parks_consecutive": 2,
        }))

        rc = self._do_stall(site="wrapper_died")

        self.assertEqual(rc, 0)
        self.assertEqual(
            self._state()["batch"]["parks_consecutive"], 2,
            "wrapper_died must preserve, not increment or reset, the counter",
        )


class IdentityGuardTests(_StallTestCase):
    def test_mints_a_fresh_op_id_when_no_prior_stall_op(self) -> None:
        self._put_in_wip()
        self._write_state(self._sample_state())

        rc = self._do_stall(site="design_gate")

        self.assertEqual(rc, 0)
        items = self._deferred_items()
        self.assertEqual(len(items), 1)
        self.assertIsInstance(items[0]["op_id"], str)
        self.assertTrue(items[0]["op_id"])

    def test_retry_with_matching_stall_op_prd_reuses_the_stored_op_id(self) -> None:
        # A prior run stamped the intent and crashed before the move step.
        self._put_in_wip()
        state = self._sample_state()
        state["stall_op"] = {
            "op_id": "existing-op-id-123",
            "prd": self.PRD,
            "site": "design_gate",
            "detail": "detail text",
        }
        self._write_state(state)

        rc = self._do_stall(site="design_gate", detail="detail text")

        self.assertEqual(rc, 0)
        items = self._deferred_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["op_id"], "existing-op-id-123")

    def test_conflict_when_stall_op_names_a_different_prd_refuses_and_changes_nothing(self) -> None:
        self._put_in_wip()
        state = self._sample_state()
        state["stall_op"] = {
            "op_id": "op-other",
            "prd": "00099-other-prd.md",
            "site": "design_gate",
            "detail": "unrelated",
        }
        self._write_state(state)
        before = self._state()

        rc = self._do_stall(prd=self.PRD, site="design_gate")

        self.assertEqual(rc, 10)
        self.assertTrue(self._in_wip())
        self.assertFalse(self._in_hold())
        self.assertEqual(self._deferred_items(), [])
        self.assertEqual(self._state(), before, "conflict must change nothing")

    def test_conflict_when_stall_op_prd_matches_arg_but_disagrees_with_state_prd(self) -> None:
        self._put_in_wip()
        state = self._sample_state(prd="00050-currently-active.md")
        state["stall_op"] = {
            "op_id": "op-mid-flight",
            "prd": self.PRD,
            "site": "design_gate",
            "detail": "detail text",
        }
        self._write_state(state)
        before = self._state()

        rc = self._do_stall(prd=self.PRD, site="design_gate")

        self.assertEqual(rc, 10)
        self.assertTrue(self._in_wip())
        self.assertFalse(self._in_hold())
        self.assertEqual(self._deferred_items(), [])
        self.assertEqual(self._state(), before, "conflict must change nothing")


class OwnedFieldsValidationTests(_StallTestCase):
    def test_malformed_unrelated_field_does_not_block_the_stall(self) -> None:
        self._put_in_wip()
        self._write_state(self._sample_state(cycle="three"))

        rc = self._do_stall(site="design_gate")

        self.assertEqual(rc, 0, "a malformed field do_stall doesn't own must not block it")
        self.assertTrue(self._in_hold())
        self.assertEqual(self._state()["cycle"], 1, "the boundary still writes its own fields")


class ExitCodeTests(_StallTestCase):
    def test_exit_4_when_prd_absent_from_both_wip_and_hold(self) -> None:
        # PRD placed nowhere -- the move can neither find a source nor land.
        self._write_state(self._sample_state())
        before = self._state()

        rc = self._do_stall(site="design_gate")

        self.assertEqual(rc, 4)
        self.assertFalse(self._in_wip())
        self.assertFalse(self._in_hold())
        final = self._state()
        self.assertIn("stall_op", final)
        self.assertEqual(final["stall_op"]["prd"], self.PRD)
        self.assertEqual(final["stall_op"]["site"], "design_gate")
        self.assertEqual(final["stall_op"]["detail"], "detail text")
        self.assertEqual(self._deferred_items(), [])
        self.assertEqual(
            _without(final, "stall_op", "schema_version"),
            _without(before, "schema_version"),
            "no reset may apply on a failed move",
        )

    def test_exit_9_when_deferred_dir_path_is_occupied_by_a_file(self) -> None:
        self._put_in_wip()
        self._write_state(self._sample_state())
        before = self._state()
        (self.autopilot_dir / "deferred").write_text("occupied", encoding="utf-8")

        rc = self._do_stall(site="design_gate")

        self.assertEqual(rc, 9)
        self.assertTrue(self._in_hold(), "the move happens before the append step")
        self.assertFalse(self._in_wip())
        final = self._state()
        self.assertIn("stall_op", final)
        self.assertEqual(
            _without(final, "stall_op", "schema_version"),
            _without(before, "schema_version"),
            "no reset may apply when the deferred append fails",
        )

    def test_exit_2_when_state_file_contains_invalid_json(self) -> None:
        self._put_in_wip()
        self.state_path.write_text("{not valid json", encoding="utf-8")

        rc = self._do_stall(site="design_gate")

        self.assertEqual(rc, 2)
        self.assertTrue(self._in_wip(), "nothing may move when state is unreadable")
        self.assertFalse(self._in_hold())

    def test_exit_4_when_hold_path_is_occupied_by_a_file(self) -> None:
        # <prds_dir>/hold exists as a regular file: mkdir(hold) raises before
        # any effect (step 1, before the intent stamp is even written).
        self._put_in_wip()
        self._write_state(self._sample_state())
        before = self._state()
        (self.prds_dir / "hold").write_text("occupied", encoding="utf-8")

        rc = self._do_stall(site="design_gate")

        self.assertEqual(rc, 4)
        self.assertTrue(self._in_wip())
        final = self._state()
        self.assertNotIn("stall_op", final)
        self.assertEqual(final, before)
        self.assertEqual(self._deferred_items(), [])


class DistinctOperationsTests(_StallTestCase):
    def test_two_full_stalls_of_the_same_prd_and_site_mint_different_op_ids(self) -> None:
        self._put_in_wip()
        self._write_state(self._sample_state())

        rc1 = self._do_stall(site="design_gate", detail="first stall")
        self.assertEqual(rc1, 0)
        first_items = self._deferred_items()
        self.assertEqual(len(first_items), 1)
        first_op_id = first_items[0]["op_id"]

        # The PRD returns to wip/ for a fresh build cycle, then stalls again.
        (self.prds_dir / "hold" / self.PRD).rename(self.prds_dir / "wip" / self.PRD)
        state = self._state()
        state["tasks"] = [{"id": "t2", "name": "y", "status": "in_progress"}]
        self._write_state(state)

        rc2 = self._do_stall(site="design_gate", detail="second stall")
        self.assertEqual(rc2, 0)

        items = self._deferred_items()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["op_id"], first_op_id)
        self.assertNotEqual(
            items[1]["op_id"], first_op_id,
            "op_ids are minted fresh per operation, never derived from (prd, site, batch)",
        )


class ExtraMutatorTests(_StallTestCase):
    def test_extra_mutator_is_composed_into_the_single_commit_after_reset(self) -> None:
        self._put_in_wip()
        self._write_state(self._sample_state())

        rc = self._do_stall(
            site="design_gate",
            extra_mutator=lambda s: {**s, "probe_key": "landed"},
        )

        self.assertEqual(rc, 0)
        final = self._state()
        self.assertEqual(final["probe_key"], "landed")
        self.assertEqual(final["cycle"], 1, "reset fields still apply alongside the mutator")
        self.assertNotIn("stall_op", final)


class FailpointRecoveryTests(_StallTestCase):
    """Each stall-side failpoint simulates a kill immediately after that
    step's on-disk effect. Re-running the identical call afterward, with the
    env var cleared, must complete exactly once."""

    def _run_with_failpoint(self, boundary: str) -> None:
        with mock.patch.dict(os.environ, {FAILPOINT_ENV: boundary}):
            with self.assertRaises(RuntimeError) as ctx:
                self._do_stall(site="design_gate", detail="hook failed")
        self.assertEqual(str(ctx.exception), f"failpoint: {boundary}")

    def test_after_mkdir_before_intent_leaves_no_durable_state_and_recovers_on_retry(self) -> None:
        self._put_in_wip()
        self._write_state(self._sample_state())
        before = self._state()

        self._run_with_failpoint("after-mkdir-before-intent")

        partial = self._state()
        self.assertEqual(partial, before, "no stall_op may be stamped before this boundary")
        self.assertTrue(self._in_wip(), "prd must still be in wip/ before the move step ran")
        self.assertFalse(self._in_hold())
        self.assertEqual(self._deferred_items(), [], "no deferred record before the intent stamp")
        self.assertTrue(
            (self.prds_dir / "hold").is_dir(),
            "the trip fires AFTER mkdir: hold/ must already exist at this boundary",
        )

        rc = self._do_stall(site="design_gate", detail="hook failed")

        self.assertEqual(rc, 0)
        self.assertFalse(self._in_wip())
        self.assertTrue(self._in_hold())
        items = self._deferred_items()
        self.assertEqual(len(items), 1, "exactly one deferred record after the rerun")
        final = self._state()
        self.assertNotIn("stall_op", final)
        self.assertEqual(final["cycle"], 1)
        self.assertEqual(final["phase"], "build")

    def test_after_intent_before_move_leaves_prd_in_wip_and_recovers_on_retry(self) -> None:
        self._put_in_wip()
        self._write_state(self._sample_state())

        self._run_with_failpoint("after-intent-before-move")

        partial = self._state()
        self.assertTrue(self._in_wip(), "prd must still be in wip/ before the move step ran")
        self.assertFalse(self._in_hold())
        self.assertIn("stall_op", partial)
        self.assertEqual(partial["stall_op"]["prd"], self.PRD)
        minted_op_id = partial["stall_op"]["op_id"]
        self.assertTrue(minted_op_id)
        self.assertEqual(self._deferred_items(), [], "no deferred record before the move step")

        rc = self._do_stall(site="design_gate", detail="hook failed")

        self.assertEqual(rc, 0)
        self.assertFalse(self._in_wip())
        self.assertTrue(self._in_hold())
        items = self._deferred_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["op_id"], minted_op_id, "retry must reuse the intent's op_id")
        final = self._state()
        self.assertNotIn("stall_op", final)
        self.assertEqual(final["cycle"], 1)
        self.assertEqual(final["phase"], "build")

    def test_after_move_before_append_leaves_prd_in_hold_and_recovers_on_retry(self) -> None:
        self._put_in_wip()
        self._write_state(self._sample_state())

        self._run_with_failpoint("after-move-before-append")

        partial = self._state()
        self.assertFalse(self._in_wip())
        self.assertTrue(self._in_hold(), "prd must have been moved before the append step ran")
        self.assertIn("stall_op", partial)
        minted_op_id = partial["stall_op"]["op_id"]
        self.assertEqual(self._deferred_items(), [], "no deferred record before the append step")

        rc = self._do_stall(site="design_gate", detail="hook failed")

        self.assertEqual(rc, 0)
        self.assertTrue(self._in_hold())
        self.assertFalse(self._in_wip())
        items = self._deferred_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["op_id"], minted_op_id, "retry must reuse the intent's op_id")
        final = self._state()
        self.assertNotIn("stall_op", final)
        self.assertEqual(final["cycle"], 1)

    def test_after_append_before_commit_dedupes_on_retry_and_completes_the_reset(self) -> None:
        self._put_in_wip()
        self._write_state(self._sample_state())

        self._run_with_failpoint("after-append-before-commit")

        partial = self._state()
        self.assertTrue(self._in_hold())
        self.assertIn("stall_op", partial, "commit did not run -- stall_op stays set")
        minted_op_id = partial["stall_op"]["op_id"]
        items = self._deferred_items()
        self.assertEqual(len(items), 1, "the append already landed before this failpoint")
        self.assertEqual(items[0]["op_id"], minted_op_id)

        rc = self._do_stall(site="design_gate", detail="hook failed")

        self.assertEqual(rc, 0)
        items_after = self._deferred_items()
        self.assertEqual(len(items_after), 1, "retry must not double-append (op_id dedup)")
        final = self._state()
        self.assertNotIn("stall_op", final)
        self.assertEqual(final["cycle"], 1)
        self.assertEqual(final["phase"], "build")


if __name__ == "__main__":
    unittest.main()
