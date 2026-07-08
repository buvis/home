"""Resume ward for the autopilot five-gate collapse.

This suite is the safety net for the PRD that collapses the autopilot skill's
eleven phase names into FIVE gates plus a paused state:

    build | review | blind | doubt | done | paused

Old -> new gate map:
    prd-selection / catchup / planning / work  -> build
    review / decision-gate / rework            -> review
    blind-review                               -> blind
    doubt-review                               -> doubt
    done                                       -> done
    paused                                     -> paused

`build` is ONE session (selection -> catchup -> planning -> work, no mid-build
handoff). The three review surfaces stay in separate fresh sessions.

RED/GREEN contract:
- Layer 1 tests invoke the REAL hooks (subprocess / importlib, mirroring the
  sibling suites). They are RED against pre-collapse code (the cap hook gates
  on phase=="work" and replans; the coverage map is keyed on the old phase
  names) and go GREEN once the phase collapse + cap-rotation rework land.
- Layer 2 tests pin a pure reference model (`resume_target`), imported from
  the shared `scripts/resume_target.py` module (C11). It documents the SKILL's
  prose-only resume/skip contract in the five-gate vocabulary. Importing the
  module rather than re-defining it inline means editing the resume logic flips
  a test red; its job is to lock the contract against future drift.

Stdlib + unittest + subprocess only, matching the sibling test suites.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
CAP_HOOK = SCRIPTS_DIR / "autopilot_context_cap_hook.py"
COVERAGE_HOOK = SCRIPTS_DIR / "review_coverage_hook.py"

# Ensure _walk_up (sibling of the hooks) is importable for the coverage hook.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# Shared fixture: build a temp autopilot dir + state.json, run a hook.
# Mirrors HookFixture from test_autopilot_context_cap_hook.py.
# ---------------------------------------------------------------------------


class CapHookFixture:
    """A temp dev/local/autopilot/ tree + transcript for the cap hook."""

    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.autopilot_dir = self.cwd / "dev" / "local" / "autopilot"
        self.autopilot_dir.mkdir(parents=True, exist_ok=True)
        self.transcript = self.cwd / "transcript.jsonl"
        self.transcript.touch()

    def write_state(self, **fields: object) -> None:
        default: dict[str, object] = {
            "prd": "00099-test.md",
            "phase": "build",
            "phases_completed": [],
            "cycle": 1,
            "tasks_total": 0,
            "tasks_completed": 0,
            "tasks": [],
            "review_cycles": [],
            "task_aborts": [],
            "cap_rotations": [],
            "replan_count": 0,
        }
        default.update(fields)
        (self.autopilot_dir / "state.json").write_text(json.dumps(default))

    def write_usage(self, input_tokens: int) -> None:
        line = {
            "type": "assistant",
            "message": {"usage": {"input_tokens": input_tokens}},
        }
        self.transcript.write_text(json.dumps(line) + "\n")

    def run_hook(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CAP_HOOK)],
            input=json.dumps(
                {"session_id": "t", "transcript_path": str(self.transcript)}
            ),
            capture_output=True,
            text=True,
            cwd=str(self.cwd),
            timeout=5,
        )

    def state(self) -> dict:
        return json.loads((self.autopilot_dir / "state.json").read_text())

    def cleanup(self) -> None:
        self.tmp.cleanup()


def _load_coverage_hook():
    spec = importlib.util.spec_from_file_location(
        "review_coverage_hook_under_test", COVERAGE_HOOK
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ===========================================================================
# LAYER 1 — live-consumer assertions (RED against pre-collapse code).
# ===========================================================================


class CapHookGateTests(unittest.TestCase):
    """The cap hook must gate on the new `build` phase, not the old `work`."""

    def setUp(self) -> None:
        self.fx = CapHookFixture()
        self.addCleanup(self.fx.cleanup)

    def _fired(self) -> bool:
        return (self.fx.autopilot_dir / ".cap-fired").exists()

    def test_cap_fires_on_build_phase(self) -> None:
        """phase=="build" + over the hard cap => the hook fires (RED now: the
        current gate is phase=="work")."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "t1", "name": "x", "status": "in_progress"}],
        )
        self.fx.write_usage(600_000)
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertTrue(self._fired(), "cap must fire when phase is 'build'")

    def test_cap_noops_on_work_phase(self) -> None:
        """The literal string "work" is no longer a valid phase. Over the cap
        with phase=="work" must NOOP (RED now: current code fires on "work")."""
        self.fx.write_state(
            phase="work",
            tasks=[{"id": "t1", "name": "x", "status": "in_progress"}],
        )
        self.fx.write_usage(600_000)
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")
        self.assertFalse(self._fired(), "stale 'work' phase must not fire")

    def test_cap_noops_on_review_phase(self) -> None:
        self.fx.write_state(phase="review")
        self.fx.write_usage(600_000)
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")
        self.assertFalse(self._fired())

    def test_cap_noops_on_blind_phase(self) -> None:
        self.fx.write_state(phase="blind")
        self.fx.write_usage(600_000)
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertFalse(self._fired())

    def test_cap_noops_on_doubt_phase(self) -> None:
        self.fx.write_state(phase="doubt")
        self.fx.write_usage(600_000)
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertFalse(self._fired())

    def test_cap_noops_on_done_phase(self) -> None:
        self.fx.write_state(phase="done")
        self.fx.write_usage(600_000)
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertFalse(self._fired())

    def test_cap_noops_on_paused_phase(self) -> None:
        self.fx.write_state(phase="paused")
        self.fx.write_usage(600_000)
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertFalse(self._fired())


class CapFireRotationResponseTests(unittest.TestCase):
    """The cap-fire response is now a rotation, not a stall+replan.

    RED now: the current fire path sets stall_reason={"stalled":
    "context_overrun",...} and next_phase="planning", and never touches
    cap_rotations.
    """

    def setUp(self) -> None:
        self.fx = CapHookFixture()
        self.addCleanup(self.fx.cleanup)

    def test_cap_fire_appends_cap_rotations_not_stall_reason(self) -> None:
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-big", "name": "x", "status": "in_progress"}],
            cap_rotations=[],
            replan_count=0,
        )
        self.fx.write_usage(600_000)
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)

        state = self.fx.state()
        rotations = state.get("cap_rotations")
        self.assertIsInstance(rotations, list)
        self.assertEqual(len(rotations), 1, "fire must append one rotation")
        entry = rotations[-1]
        # Each rotation entry names at least the in-flight task and cycle.
        self.assertEqual(entry.get("task_id"), "task-big")
        self.assertEqual(entry.get("cycle"), 1)

    def test_cap_fire_does_not_set_stall_reason(self) -> None:
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-big", "name": "x", "status": "in_progress"}],
        )
        self.fx.write_usage(600_000)
        self.fx.run_hook()
        self.assertNotIn(
            "stall_reason",
            self.fx.state(),
            "cap rotation must NOT set stall_reason (that's the replan path)",
        )

    def test_cap_fire_does_not_create_replan_context(self) -> None:
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-big", "name": "x", "status": "in_progress"}],
        )
        self.fx.write_usage(600_000)
        self.fx.run_hook()
        self.assertFalse(
            (self.fx.autopilot_dir / "replan-context.md").exists(),
            "cap rotation must NOT write replan-context.md",
        )

    def test_cap_fire_leaves_replan_count_unchanged(self) -> None:
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-big", "name": "x", "status": "in_progress"}],
            replan_count=2,
        )
        self.fx.write_usage(600_000)
        self.fx.run_hook()
        self.assertEqual(
            self.fx.state().get("replan_count"),
            2,
            "cap rotation is not a replan; replan_count must not change",
        )


class CapRotationInFlightResetTests(unittest.TestCase):
    """A NORMAL cap rotation must reset the in-flight task to pending.

    The rotated-into /work only processes pending tasks, so the in-flight
    (in_progress) task must flip back to pending for it to be re-attempted.
    RED now: the current fire path appends cap_rotations but never mutates
    the in-flight task's status, so the rotated /work skips it.
    """

    def setUp(self) -> None:
        self.fx = CapHookFixture()
        self.addCleanup(self.fx.cleanup)

    def test_cap_rotation_resets_in_flight_task_to_pending(self) -> None:
        self.fx.write_state(
            phase="build",
            cycle=1,
            tasks_total=6,
            tasks_completed=3,
            cap_rotations=[],
            replan_count=0,
            tasks=[
                {"id": "1", "status": "completed"},
                {"id": "2", "status": "completed"},
                {"id": "3", "status": "completed"},
                {"id": "4", "status": "in_progress"},
                {"id": "5", "status": "pending"},
                {"id": "6", "status": "pending"},
            ],
        )
        self.fx.write_usage(600_000)
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)

        state = self.fx.state()
        by_id = {t["id"]: t for t in state["tasks"]}

        # The in-flight task is reset so the rotated /work re-attempts it.
        self.assertEqual(by_id["4"]["status"], "pending")

        # Exactly one rotation entry, naming the in-flight task.
        self.assertEqual(len(state["cap_rotations"]), 1)
        self.assertEqual(state["cap_rotations"][0]["task_id"], "4")

        # Rotation is not a replan: replan_count untouched, no replan-context.
        self.assertEqual(state["replan_count"], 0)
        self.assertFalse(
            (self.fx.autopilot_dir / "replan-context.md").exists()
        )

        # Every OTHER task's status is unchanged.
        self.assertEqual(by_id["1"]["status"], "completed")
        self.assertEqual(by_id["2"]["status"], "completed")
        self.assertEqual(by_id["3"]["status"], "completed")
        self.assertEqual(by_id["5"]["status"], "pending")
        self.assertEqual(by_id["6"]["status"], "pending")


class CapFireLivelockGuardTests(unittest.TestCase):
    """A second cap fire on the SAME task must stall, not rotate forever.

    RED now: no livelock guard exists; the current path has no concept of
    cap_rotations at all.
    """

    def setUp(self) -> None:
        self.fx = CapHookFixture()
        self.addCleanup(self.fx.cleanup)

    def test_livelock_guard_stalls_on_second_same_task_fire(self) -> None:
        # cap_rotations already names the in-flight task: a previous rotation
        # for task-big already happened. A second fire must take the
        # oversized-task stall path, not append a third same-task rotation.
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-big", "name": "x", "status": "in_progress"}],
            cap_rotations=[{"task_id": "task-big", "cycle": 1}],
        )
        self.fx.write_usage(600_000)
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)

        state = self.fx.state()
        rotations = state.get("cap_rotations", [])
        same_task = [r for r in rotations if r.get("task_id") == "task-big"]
        self.assertEqual(
            len(same_task),
            1,
            "must NOT append a second rotation for the same task; stall instead",
        )
        # The fire must signal the stalled / oversized-task path.
        envelope = result.stdout + json.dumps(state.get("stall_reason", {}))
        self.assertIn(
            "stall",
            envelope.lower(),
            "second same-task fire must reference the stall path",
        )


class CoverageMapRekeyTests(unittest.TestCase):
    """The review-coverage map matches the three-gate machine (PRD 00015):
    only the done hand-off is review-gated, and the surface that just
    finished is the work-completion review cycle."""

    def setUp(self) -> None:
        self.hook = _load_coverage_hook()

    def test_coverage_map_done_maps_to_work_completion(self) -> None:
        self.assertEqual(self.hook.surface_for_phase("done"), "work-completion")

    def test_coverage_map_drops_legacy_phase_keys(self) -> None:
        keys = set(self.hook._PHASE_TO_SURFACE.keys())
        self.assertNotIn("blind", keys, "legacy blind leg was folded into the review lenses")
        self.assertNotIn("doubt", keys, "legacy doubt leg was folded into the review lenses")

    def test_coverage_map_build_review_unmapped(self) -> None:
        # build and review gates are not review-coverage handoffs.
        self.assertIsNone(self.hook.surface_for_phase("build"))
        self.assertIsNone(self.hook.surface_for_phase("review"))


# ===========================================================================
# LAYER 2 — resume-contract reference model (locks the SKILL prose).
# ===========================================================================
#
# `resume_target(state)` is a pure function now extracted to the importable
# module `scripts/resume_target.py` (C11) and imported here, so these tests
# bind to the shared decision core: editing the resume logic in
# resume_target.py flips a test red, rather than the test re-implementing the
# contract inline. It encodes the SKILL's resume/skip rules in the five-gate
# vocabulary and never uses the old eleven phase names.

from resume_target import resume_target


class ResumeBuildReentryTests(unittest.TestCase):
    """Build re-entry is by artifact: capsule freshness, tasks-exist, all-done."""

    def test_resume_build_fresh_capsule_skips_catchup(self) -> None:
        target = resume_target(
            {"phase": "build", "tasks": [], "capsule_fresh": True}
        )
        self.assertEqual(target, "skip catchup -> planning")

    def test_resume_build_tasks_present_skips_planning(self) -> None:
        # tasks non-empty => planning is skipped; resume drops into /work.
        target = resume_target(
            {
                "phase": "build",
                "tasks": [
                    {"id": "t1", "status": "completed"},
                    {"id": "t2", "status": "pending"},
                ],
            }
        )
        self.assertEqual(
            target, "/work continues at first non-completed task t2"
        )

    def test_resume_build_all_tasks_done_targets_review(self) -> None:
        target = resume_target(
            {
                "phase": "build",
                "tasks": [
                    {"id": "t1", "status": "completed"},
                    {"id": "t2", "status": "completed"},
                ],
            }
        )
        self.assertEqual(target, "all tasks done -> review gate")

    def test_resume_build_identifies_first_non_completed_task(self) -> None:
        target = resume_target(
            {
                "phase": "build",
                "tasks": [
                    {"id": "t1", "status": "completed"},
                    {"id": "t2", "status": "completed"},
                    {"id": "t3", "status": "in_progress"},
                    {"id": "t4", "status": "pending"},
                ],
            }
        )
        self.assertEqual(
            target, "/work continues at first non-completed task t3"
        )


class ResumeReviewCascadeTests(unittest.TestCase):
    """Review resume via phases_completed; legacy blind/doubt map to review."""

    def test_resume_review_not_completed_runs_review(self) -> None:
        self.assertEqual(
            resume_target({"phase": "review", "phases_completed": []}),
            "run review loop",
        )

    def test_resume_review_completed_skips_to_done(self) -> None:
        self.assertEqual(
            resume_target(
                {"phase": "review", "phases_completed": ["review"]}
            ),
            "skip review -> done",
        )

    def test_resume_legacy_blind_phase_runs_review_loop(self) -> None:
        # Pre-00015 state parked at the standalone blind leg: the leg is gone;
        # its scrutiny now lives in the review cycle's lenses, so one full
        # cycle runs instead of skipping ahead.
        self.assertEqual(
            resume_target(
                {"phase": "blind", "phases_completed": ["review"]}
            ),
            "run review loop",
        )

    def test_resume_legacy_doubt_phase_runs_review_loop(self) -> None:
        self.assertEqual(
            resume_target(
                {
                    "phase": "doubt",
                    "phases_completed": ["review", "blind"],
                }
            ),
            "run review loop",
        )


class ResumeCapRotationTests(unittest.TestCase):
    """Cap rotation resumes /work at the in-flight task with NO replan."""

    def test_cap_rotation_resume_continues_at_inflight_task(self) -> None:
        state = {
            "phase": "build",
            "tasks": [
                {"id": "t1", "status": "completed"},
                {"id": "t2", "status": "completed"},
                {"id": "t3", "status": "completed"},
                {"id": "t4", "status": "in_progress"},
                {"id": "t5", "status": "pending"},
            ],
            "cap_rotations": [{"task_id": "t4", "cycle": 1}],
            "replan_count": 0,
        }
        self.assertEqual(
            resume_target(state),
            "/work continues at first non-completed task t4",
        )
        # The rotation resume is lossless: no replan side effects in state.
        self.assertNotIn("stall_reason", state)
        self.assertEqual(state["replan_count"], 0)


class ResumePromptOverrunReplanTests(unittest.TestCase):
    """subagent_prompt_overrun is the ONE surviving replan path."""

    def test_prompt_overrun_replan_clears_tasks(self) -> None:
        target = resume_target(
            {
                "phase": "build",
                "tasks": [{"id": "t1", "status": "in_progress"}],
                "stall_reason": {"stalled": "subagent_prompt_overrun"},
            }
        )
        self.assertEqual(
            target,
            "replan: clear tasks, re-enter build at planning, write replan-context.md",
        )


class ResumeCapPauseTests(unittest.TestCase):
    """phase=="paused" + cap_pause_reason routes to the cap-pause handler."""

    def test_cap_pause_runs_resume_handler(self) -> None:
        target = resume_target(
            {"phase": "paused", "cap_pause_reason": "budget exhausted"}
        )
        self.assertEqual(
            target,
            "cap-pause resume handler: present unresolved findings, branch resume/abandon",
        )


class ResumeEscalationExhaustedTests(unittest.TestCase):
    """escalation_exhausted routes to crash-recovery at selection."""

    def test_escalation_exhausted_recovers_at_selection(self) -> None:
        target = resume_target(
            {
                "phase": "build",
                "stall_reason": {"stalled": "escalation_exhausted"},
            }
        )
        self.assertEqual(target, "crash-recovery at selection")


if __name__ == "__main__":
    unittest.main()
