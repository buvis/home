#!/usr/bin/env python3
"""Tests for cli/transitions.py - the phase table and its field effects.

Every row asserts its FULL effect set, not just the phase it lands on. That is
the point of the table: the four writes the review-rework handoff used to make
one at a time are one commit now, and a test that checked only `phase` would
pass for a transition that silently dropped the cycle increment - the exact
miss that once let a loop run past its cap.
"""

from __future__ import annotations

import json
import unittest

from cli import records, transitions


def _review_state(**overrides) -> dict:
    state = {
        "prd": "00089-example-v1.md",
        "phase": "review",
        "next_phase": "review",
        "cycle": 2,
        "rework_cap": 3,
        "phases_completed": [],
        "rework_task_ids": ["7", "9"],
        "batch": {"id": "202608071200", "completed_prds": ["00088-x.md"]},
    }
    state.update(overrides)
    return state


class BuildToReviewTests(unittest.TestCase):
    def test_advances_both_phase_fields(self) -> None:
        new = transitions.apply({"phase": "build", "next_phase": "build"}, "tasks_done")
        self.assertEqual(new["phase"], "review")
        self.assertEqual(new["next_phase"], "review")

    def test_leaves_no_membership_marker(self) -> None:
        # The build gate adds nothing to phases_completed; only convergence does.
        new = transitions.apply(
            {"phase": "build", "phases_completed": []},
            "tasks_done",
        )
        self.assertEqual(new["phases_completed"], [])

    def test_does_not_touch_the_task_snapshot(self) -> None:
        # The snapshot is written by the statectl task verbs, not a derivable
        # effect - the transition must not blank it.
        tasks = [{"id": "1", "status": "completed"}]
        new = transitions.apply({"phase": "build", "tasks": tasks}, "tasks_done")
        self.assertEqual(new["tasks"], tasks)


class ReworkTests(unittest.TestCase):
    def test_increments_cycle_and_clears_rework_ids_together(self) -> None:
        new = transitions.apply(_review_state(), "rework")
        self.assertEqual(new["cycle"], 3)
        self.assertEqual(new["rework_task_ids"], [])
        self.assertEqual(new["phase"], "review")
        self.assertEqual(new["next_phase"], "review")

    def test_absent_cycle_starts_from_one(self) -> None:
        new = transitions.apply({"phase": "review"}, "rework")
        self.assertEqual(new["cycle"], 2)

    def test_does_not_mark_review_complete(self) -> None:
        # Only convergence appends "review"; a continuing loop must not, or the
        # next session's loop-level skip jumps straight to done.
        new = transitions.apply(_review_state(), "rework")
        self.assertEqual(new["phases_completed"], [])

    def test_non_int_cycle_is_rejected_by_name(self) -> None:
        with self.assertRaises(Exception) as caught:
            transitions.apply(_review_state(cycle="two"), "rework")
        self.assertIn("cycle", str(caught.exception))


class ConvergedTests(unittest.TestCase):
    def test_appends_the_marker_because_it_is_convergence(self) -> None:
        new = transitions.apply(_review_state(), "converged")
        self.assertEqual(new["phase"], "done")
        self.assertEqual(new["next_phase"], "done")
        self.assertEqual(new["phases_completed"], ["review"])

    def test_marker_is_appended_not_replaced(self) -> None:
        new = transitions.apply(
            _review_state(phases_completed=["something"]),
            "converged",
        )
        self.assertEqual(new["phases_completed"], ["something", "review"])

    def test_re_running_convergence_does_not_double_the_marker(self) -> None:
        once = transitions.apply(_review_state(), "converged")
        twice = transitions.apply({**once, "phase": "review"}, "converged")
        self.assertEqual(twice["phases_completed"], ["review"])

    def test_needs_no_flag_to_produce_the_marker(self) -> None:
        self.assertEqual(
            list(
                transitions.apply.__code__.co_varnames[
                    : transitions.apply.__code__.co_argcount
                ],
            ),
            ["state", "outcome"],
            "apply() takes an outcome only - a caller cannot pass, or forget, "
            "a flag for a mandatory effect",
        )


class MorePrdsTests(unittest.TestCase):
    def test_applies_the_per_prd_reset(self) -> None:
        state = _review_state(phase="done", next_phase="done", tasks=[{"id": "1"}])
        state["phases_completed"] = ["review"]
        state["work_start_sha"] = "abc123"
        new = transitions.apply(state, "more_prds")
        self.assertEqual(new["phase"], "build")
        self.assertEqual(new["next_phase"], "build")
        self.assertEqual(new["phases_completed"], [])
        self.assertEqual(new["cycle"], 1)
        for field in ("tasks", "work_start_sha", "rework_task_ids"):
            self.assertNotIn(field, new)

    def test_preserves_batch_in_full(self) -> None:
        state = _review_state(phase="done")
        new = transitions.apply(state, "more_prds")
        self.assertEqual(new["batch"], state["batch"])

    def test_delegates_to_the_one_authoritative_reset_list(self) -> None:
        state = _review_state(phase="done")
        self.assertEqual(
            transitions.apply(state, "more_prds"),
            records.reset_prd_fields(state),
        )


class DrainedTests(unittest.TestCase):
    def test_writes_the_empty_next_phase_not_the_word_done(self) -> None:
        # The wrapper reads an EMPTY next_phase as drained. The literal string
        # "done" is a phase with work queued after it and spins the loop until
        # the safety kill.
        new = transitions.apply({"phase": "done", "next_phase": "done"}, "drained")
        self.assertEqual(new["phase"], "done")
        self.assertEqual(new["next_phase"], "")

    def test_a_batch_can_also_drain_at_phase_0_selection(self) -> None:
        # "No PRDs anywhere" is reached with phase still "build" and needs the
        # same effect, or the wrapper reads the exit as died rather than drained.
        new = transitions.apply({"phase": "build", "next_phase": "build"}, "drained")
        self.assertEqual(new["phase"], "done")
        self.assertEqual(new["next_phase"], "")


class TableTests(unittest.TestCase):
    def test_unknown_pair_raises_naming_both_halves(self) -> None:
        with self.assertRaises(transitions.UnknownTransition) as caught:
            transitions.apply({"phase": "build"}, "converged")
        message = str(caught.exception)
        self.assertIn("build", message)
        self.assertIn("converged", message)

    def test_unknown_outcome_raises(self) -> None:
        with self.assertRaises(transitions.UnknownTransition):
            transitions.apply({"phase": "review"}, "sideways")

    def test_missing_phase_raises_rather_than_guessing(self) -> None:
        with self.assertRaises(transitions.UnknownTransition):
            transitions.apply({}, "rework")

    def test_next_phase_agrees_with_what_apply_writes(self) -> None:
        for phase, outcome in transitions.TRANSITIONS:
            with self.subTest(phase=phase, outcome=outcome):
                self.assertEqual(
                    transitions.next_phase(phase, outcome),
                    transitions.apply({"phase": phase}, outcome)["next_phase"],
                )

    def test_the_table_holds_exactly_the_documented_rows(self) -> None:
        self.assertEqual(
            sorted(transitions.TRANSITIONS),
            [
                ("build", "drained"),
                ("build", "tasks_done"),
                ("done", "drained"),
                ("done", "more_prds"),
                ("review", "converged"),
                ("review", "rework"),
            ],
        )

    def test_every_transition_is_pure(self) -> None:
        for phase, outcome in transitions.TRANSITIONS:
            with self.subTest(phase=phase, outcome=outcome):
                state = _review_state(phase=phase)
                before = json.dumps(state, sort_keys=True)
                transitions.apply(state, outcome)
                self.assertEqual(json.dumps(state, sort_keys=True), before)


if __name__ == "__main__":
    unittest.main()
