#!/usr/bin/env python3
"""Tests for cli/resume.py - the absorbed resume/park decision cores.

`scripts/test_autopilot_resume.py` covers this logic in depth and keeps
running UNMODIFIED through the `scripts/resume_target.py` shim, which is the
regression gate on the shim. This file pins the absorbed module DIRECTLY, so a
broken core and a broken shim fail as two different tests rather than one
ambiguous one, and it re-asserts the golden-fixture targets this PRD names as
the absorption's acceptance.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from cli import resume

GOLDEN = Path(__file__).resolve().parent.parent / "scripts" / "golden"

# The three fixtures and the target each documents.
GOLDEN_TARGETS = [
    ("state-build-pending.json", "/work continues at first non-completed task task-2"),
    ("state-review-cycle2.json", "run review loop at cycle 2"),
    ("state-review-converged.json", "skip review -> done"),
]


class GoldenFixtureTests(unittest.TestCase):
    def test_each_golden_state_resolves_its_documented_target(self) -> None:
        for fixture, expected in GOLDEN_TARGETS:
            with self.subTest(fixture=fixture):
                state = json.loads((GOLDEN / fixture).read_text(encoding="utf-8"))
                self.assertEqual(resume.resume_target(state), expected)


class ResolutionOrderTests(unittest.TestCase):
    """The order is the contract: a stall_op outranks everything, and the
    crash/replan stalls outrank phase routing."""

    def test_stall_op_wins_over_every_other_branch(self) -> None:
        target = resume.resume_target(
            {
                "stall_op": {"op_id": "op-1", "prd": "00089-x.md"},
                "stall_reason": {"stalled": "escalation_exhausted"},
                "phase": "build",
            }
        )
        self.assertEqual(target, "reconcile stall op-1 for 00089-x.md")

    def test_stall_reason_outranks_phase_routing(self) -> None:
        target = resume.resume_target(
            {
                "stall_reason": {"stalled": "escalation_exhausted"},
                "phase": "review",
            }
        )
        self.assertEqual(target, "crash-recovery at selection")

    def test_legacy_phases_run_a_full_review_cycle(self) -> None:
        # pre-00015 state files: the standalone legs are gone, and their
        # scrutiny must not be skipped.
        for phase in ("blind", "doubt"):
            with self.subTest(phase=phase):
                self.assertEqual(
                    resume.resume_target({"phase": phase, "cycle": 4}),
                    "run review loop at cycle 4",
                )

    def test_unknown_phase_is_surfaced_not_guessed(self) -> None:
        self.assertEqual(
            resume.resume_target({"phase": "reticulating"}),
            "unknown phase: reticulating",
        )


class ParkDecisionTests(unittest.TestCase):
    def test_absent_marker_falls_through(self) -> None:
        self.assertEqual(resume.park_decision(None, [], 0), "no marker")

    def test_marker_without_a_prd_is_malformed(self) -> None:
        self.assertEqual(
            resume.park_decision({"reason": "sick"}, ["00089-x.md"], 0),
            "malformed marker -> ignore",
        )

    def test_marker_naming_a_prd_not_in_wip_is_stale(self) -> None:
        self.assertEqual(
            resume.park_decision({"prd": "00001-gone.md"}, ["00089-x.md"], 0),
            "stale marker -> ignore",
        )

    def test_first_park_continues_the_batch(self) -> None:
        self.assertEqual(
            resume.park_decision({"prd": "00089-x.md"}, ["00089-x.md"], 0),
            "park 00089-x.md -> continue batch",
        )

    def test_second_consecutive_park_halts_systemically(self) -> None:
        # The count passed in is PRE-increment, so 1 means this park makes it
        # the second in a row.
        self.assertEqual(
            resume.park_decision({"prd": "00089-x.md"}, ["00089-x.md"], 1),
            "park 00089-x.md -> systemic halt",
        )


class PurityTests(unittest.TestCase):
    def test_resume_target_does_not_mutate_the_state_it_reads(self) -> None:
        state = json.loads(
            (GOLDEN / "state-build-pending.json").read_text(encoding="utf-8"),
        )
        before = json.dumps(state, sort_keys=True)
        resume.resume_target(state)
        self.assertEqual(json.dumps(state, sort_keys=True), before)


if __name__ == "__main__":
    unittest.main()
