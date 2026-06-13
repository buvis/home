"""Cap-rotation and livelock-guard tests for autopilot_context_cap_hook.py.

Split out of test_autopilot_context_cap_hook.py to keep each file under the
800-line limit. Shares HookFixture (and the HOOK path constant) with that
module; the suite runs from scripts/ on sys.path, so the import resolves.
"""

import json
import unittest

from test_autopilot_context_cap_hook import HookFixture


class ContextCapRotationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = HookFixture()
        self.addCleanup(self.fx.cleanup)

    # Overrun cases ----------------------------------------------------------

    def test_overrun_writes_marker_and_rotation_and_stdout(self) -> None:
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "Big task", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([
            self.fx.usage_line(input_tokens=400_000, cache_read=80_000, cache_create=120_000),
        ])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)

        marker = self.fx.autopilot_dir / ".cap-fired"
        self.assertTrue(marker.exists())
        # Marker carries the in-progress task id so the hook can self-clear
        # when the task changes between PostToolUse fires.
        self.assertEqual(marker.read_text().strip(), "task-x")

        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        # Rotation, not abort/replan: one cap_rotations entry, no stall_reason.
        self.assertEqual(
            state["cap_rotations"], [{"task_id": "task-x", "cycle": 1}]
        )
        self.assertNotIn("stall_reason", state)
        self.assertEqual(state["task_aborts"], [])

        # next_phase stays on the build gate so the fresh session resumes
        # build and /work continues at the first non-completed task.
        self.assertEqual(state["next_phase"], "build")

        out = json.loads(result.stdout)
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        context = out["hookSpecificOutput"]["additionalContext"].lower()
        # Rotation handoff: references rotation/continue, never a replan.
        self.assertIn("rotation", context)
        self.assertNotIn("replan", context)

    def test_overrun_uses_most_recent_usage_line(self) -> None:
        self.fx.write_state(phase="build")
        self.fx.write_transcript_lines([
            self.fx.usage_line(input_tokens=50_000),
            {"type": "user", "message": {"content": "noise"}},
            self.fx.usage_line(input_tokens=600_000),
        ])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertTrue((self.fx.autopilot_dir / ".cap-fired").exists())
        out = json.loads(result.stdout)
        self.assertIn("hookSpecificOutput", out)

    def test_overrun_with_no_in_progress_task_uses_unknown(self) -> None:
        self.fx.write_state(phase="build", tasks=[])
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        self.assertEqual(state["cap_rotations"][-1]["task_id"], "unknown")

    # Rotation response ------------------------------------------------------

    def test_cap_fire_appends_rotation_entry(self) -> None:
        """A fire appends exactly one {task_id, cycle} entry to cap_rotations."""
        self.fx.write_state(
            phase="build",
            cycle=3,
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        self.assertEqual(
            state["cap_rotations"], [{"task_id": "task-x", "cycle": 3}]
        )

    def test_cap_fire_appends_to_existing_rotations(self) -> None:
        """A prior rotation for a DIFFERENT task is preserved; the new entry
        is appended (the list is not replaced)."""
        self.fx.write_state(
            phase="build",
            cycle=1,
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
            cap_rotations=[{"task_id": "task-prior", "cycle": 1}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        self.assertEqual(
            state["cap_rotations"],
            [
                {"task_id": "task-prior", "cycle": 1},
                {"task_id": "task-x", "cycle": 1},
            ],
        )

    def test_cap_fire_sets_no_stall_reason(self) -> None:
        """A normal rotation must NOT set stall_reason — that is the replan
        path the rework deletes."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        self.assertNotIn("stall_reason", state)

    def test_cap_fire_resets_in_flight_task_and_leaves_other_state(self) -> None:
        """A rotation resets the in-flight task to pending so /work re-attempts
        it, and leaves phases_completed, replan_count, tasks_completed, and
        task_aborts untouched (only cap_rotations, next_phase, and the
        in-flight task's status change)."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
            phases_completed=["review"],
            replan_count=2,
            tasks_completed=4,
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        self.assertEqual(state["tasks"][0]["status"], "pending")
        self.assertEqual(state["phases_completed"], ["review"])
        self.assertEqual(state["replan_count"], 2)
        self.assertEqual(state["tasks_completed"], 4)
        self.assertEqual(state["task_aborts"], [])

    def test_cap_fire_sets_next_phase_build(self) -> None:
        """next_phase stays on the build gate so the fresh session resumes
        build and /work continues at the first non-completed task."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        self.assertEqual(state["next_phase"], "build")

    def test_cap_fire_does_not_create_replan_context(self) -> None:
        """The rotation path must NOT write replan-context.md — that file
        only belongs to the replan path the rework removes."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertFalse(
            (self.fx.autopilot_dir / "replan-context.md").exists()
        )

    # Livelock guard ---------------------------------------------------------

    def test_livelock_guard_stalls_on_second_same_task_fire(self) -> None:
        """When cap_rotations' last entry already names the in-flight task,
        a second fire is the second consecutive rotation for the same task:
        it is genuinely oversized. The hook must NOT append another rotation
        and must set stall_reason.stalled == "oversized_task" instead."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
            cap_rotations=[{"task_id": "task-x", "cycle": 1}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        # No second same-task rotation appended.
        same_task = [
            r for r in state["cap_rotations"] if r.get("task_id") == "task-x"
        ]
        self.assertEqual(len(same_task), 1)
        # The oversized-task stall is recorded instead.
        self.assertEqual(state["stall_reason"]["stalled"], "oversized_task")
        self.assertEqual(state["stall_reason"]["task"], "task-x")

    def test_post_reset_refire_does_not_spuriously_rotate(self) -> None:
        """A rotation already fired for task "4" earlier this turn and reset
        task 4 to pending. The model is now winding down (committing, writing
        the signal), so there is NO in-progress task and the `.cap-fired`
        marker already exists. A redundant over-cap fire in this window must
        NOOP: it must not append another rotation (least of all a spurious
        `{"task_id": "unknown"}` entry) and must not delete the marker."""
        self.fx.write_state(
            phase="build",
            cap_rotations=[{"task_id": "4", "cycle": 1}],
            replan_count=0,
            tasks=[
                {"id": "4", "name": "t", "status": "pending"},
                {"id": "5", "name": "u", "status": "pending"},
            ],
        )
        (self.fx.autopilot_dir / ".cap-fired").write_text("4")
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        # No rotation envelope emitted.
        self.assertEqual(result.stdout.strip(), "")
        # cap_rotations unchanged: exactly the one task "4" entry, no
        # "unknown" entry appended.
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        self.assertEqual(state["cap_rotations"], [{"task_id": "4", "cycle": 1}])
        self.assertNotIn(
            "unknown", [r.get("task_id") for r in state["cap_rotations"]]
        )
        # Marker not deleted.
        self.assertEqual(
            (self.fx.autopilot_dir / ".cap-fired").read_text().strip(), "4"
        )

    def test_stale_marker_from_prior_prd_does_not_suppress_fire(self) -> None:
        """A `.cap-fired` marker left by a PRIOR PRD must NOT suppress a
        legitimate over-cap fire during the next PRD's build prologue.

        After a livelock stall the PRD moves to stalled/ and cap_rotations is
        cleared, but recovery does not clear `.cap-fired`, so a stale marker
        (a real, old task id) survives into the next PRD. During that PRD's
        prologue no task is claimed yet (task_id == "unknown"). The cycle-2
        unknown-task block is scoped to the post-rotation wind-down
        (marker_task == last rotation); a stale marker whose task is NOT the
        last rotation must self-clear and let the hook fire. Without the
        scoping the cost cap is silently disabled for the whole build prologue
        until the first task is claimed."""
        self.fx.write_state(
            phase="build",
            cycle=2,
            cap_rotations=[],
            tasks=[{"id": "7", "name": "next-prd-task", "status": "pending"}],
        )
        (self.fx.autopilot_dir / ".cap-fired").write_text("old-task-from-prior-prd")
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        # FIRES (not suppressed): a rotation envelope is emitted. Contrast with
        # test_post_reset_refire_does_not_spuriously_rotate, where stdout == "".
        self.assertNotEqual(result.stdout.strip(), "")
        self.assertIn("rotation", result.stdout.lower())
        # The over-cap prologue fire rotated on the "unknown" task.
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        self.assertEqual(state["cap_rotations"], [{"task_id": "unknown", "cycle": 2}])
        # The stale marker self-cleared AND _handle_rotation rewrote it for the
        # new ("unknown") fire — it was not left in place to block.
        self.assertEqual(
            (self.fx.autopilot_dir / ".cap-fired").read_text().strip(),
            "unknown",
        )

    # Persistence-safety: hook bails on state-write failure -----------------

    def test_write_failure_skips_marker_envelope_and_records_no_rotation(self) -> None:
        """If the autopilot dir is unwritable, the hook MUST NOT emit the
        rotation envelope, MUST NOT leave a .cap-fired marker, and MUST NOT
        record a rotation in state.cap_rotations.

        Marker-first ordering (C2): the marker write is attempted first and
        fails on the read-only dir, so the hook returns before the state
        append and cap_rotations never grows. The marker is present iff a
        rotation was recorded, so a partial write can never leave a rotation
        the next fire would misread as a livelock.
        """
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "Big task", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([
            self.fx.usage_line(input_tokens=600_000),
        ])

        # write_text / os.replace into a 555 dir both raise OSError. state.json
        # stays readable, so _load_state succeeds and the hook reaches the
        # marker write (which fails first under marker-first ordering).
        original_mode = self.fx.autopilot_dir.stat().st_mode
        self.fx.autopilot_dir.chmod(0o555)
        self.addCleanup(self.fx.autopilot_dir.chmod, original_mode)

        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)

        # No rotation envelope, no marker, and no recorded rotation.
        self.assertEqual(result.stdout.strip(), "")
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        self.assertEqual(state.get("cap_rotations"), [])

    # Race safety: merge-write preserves concurrent model edits ---------------

    def test_merge_write_preserves_non_rotation_fields(self) -> None:
        """The rotation write must preserve fields the hook does not own.

        The hook writes cap_rotations and next_phase. All other fields
        (tasks_completed, tasks[].status, etc.) are owned by the model or
        /work; the hook must not overwrite them with stale values from its
        initial state read.

        Note: this test cannot simulate a true concurrent write (subprocess
        + no sync), but verifies that fields not touched by the hook survive
        the merge-write — the property the re-read achieves.
        """
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
            tasks_completed=7,
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        self.assertEqual(state["tasks_completed"], 7)
        self.assertEqual(len(state["cap_rotations"]), 1)

    def test_rotation_preserves_work_start_sha(self) -> None:
        """C7/C12: a cap rotation must not shrink the Phase 8 doubt diff.

        The rotation merge-write touches cap_rotations, next_phase, and the
        in-flight task's status — never work_start_sha. This binds the C7
        contract (a rotation must leave work_start_sha..HEAD spanning the full
        PRD) to executable behavior: if a rotation ever clobbered or dropped
        work_start_sha, the doubt diff would collapse to post-rotation commits
        only, and this test would go red. Complements the SKILL.md Phase 3
        prose guard (which stops the orchestrator re-capturing on resume).
        """
        sha = "15a0637f0d3e60c06ffe16ad9015353d46487cbc"
        self.fx.write_state(
            phase="build",
            work_start_sha=sha,
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        # Sanity: the rotation actually fired.
        self.assertEqual(len(state["cap_rotations"]), 1)
        # The contract: work_start_sha is byte-identical after the rotation.
        self.assertEqual(state["work_start_sha"], sha)

    # Rotation-envelope robustness ------------------------------------------

    def test_rotation_message_has_no_model_signal_directive(self) -> None:
        """C1: the rotation envelope must not tell the model to write the loop
        signal. The Stop hook owns the signal write (gated on $_AUTOPILOT_LOOP),
        so the message carries no "write 'next'" directive, no $_AUTOPILOT_LOOP
        branch, and no signal path.
        """
        self.fx.write_state(phase="build")
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        out = json.loads(result.stdout)
        context = out["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("write 'next'", context)
        self.assertNotIn("$_AUTOPILOT_LOOP", context)
        self.assertNotIn("signal", context.lower())

    def test_rotation_message_defers_handoff_to_stop_hook(self) -> None:
        """C1: the rotation envelope tells the model to STOP and states that the
        autopilot Stop hook performs the loop handoff from next_phase — the
        model itself writes nothing.
        """
        self.fx.write_state(phase="build")
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        out = json.loads(result.stdout)
        context = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("STOP", context)
        self.assertIn("Stop hook", context)
        self.assertIn("next_phase", context)

    def test_rotation_fire_message_mentions_rotation_not_replan(self) -> None:
        """The rotation envelope references rotation/continue and must NOT
        instruct a replan (no replan-context.md, no stall_reason, no
        re-planning of tasks)."""
        self.fx.write_state(phase="build")
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        out = json.loads(result.stdout)
        context = out["hookSpecificOutput"]["additionalContext"].lower()
        self.assertIn("rotation", context)
        self.assertNotIn("replan", context)


if __name__ == "__main__":
    unittest.main()
