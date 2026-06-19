"""Contract: the autopilot SKILL must forbid yielding the turn on pending
background work, and Phase 8 must run its test step synchronously without the
CI-only determinism sweep.

This is the behavioral root-cause guard for the 2026-06-17 phase thrashes: a
loop session that STOPs while a dispatched subagent / build / test run is still
pending strands the phase, so the loop re-enters it. The phase-thrash
circuit-breaker (test_autopilot_stop_hook.py) bounds the damage; this test pins
the rule that prevents the yield in the first place, so it cannot silently
regress out of the SKILL.
"""

from __future__ import annotations

import unittest
from pathlib import Path

SKILL = (Path(__file__).resolve().parent.parent / "SKILL.md").read_text()


class NoYieldOnPendingWorkContract(unittest.TestCase):
    """The universal 'block, don't yield' rule must be present and concrete."""

    def test_skill_forbids_yielding_on_pending_background_work(self) -> None:
        self.assertIn(
            "never yield on pending work",
            SKILL,
            "SKILL must forbid ending the turn while background work is pending",
        )

    def test_skill_contradicts_the_reinvoke_belief(self) -> None:
        # The model's wrong belief ("the harness re-invokes me when it exits")
        # is what thrashed; the SKILL must contradict it explicitly.
        self.assertIn("does NOT re-invoke a loop session after it STOPs", SKILL)

    def test_skill_gives_the_foreground_timeout_mechanism(self) -> None:
        # A concrete alternative to auto-background-then-yield is required.
        self.assertIn("600000", SKILL)
        self.assertIn("auto-background", SKILL)


class Phase8SynchronousTestStepContract(unittest.TestCase):
    """Phase 8's gate test step must run in the foreground and skip CI-only
    suites (the §55 10x e2e determinism sweep is CI's job, not the doubt gate's)."""

    def test_phase8_skips_ci_only_determinism_sweep(self) -> None:
        self.assertIn("CI-only", SKILL)
        self.assertRegex(SKILL, r"10x e2e determinism")


if __name__ == "__main__":
    unittest.main()
