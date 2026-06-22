"""Contract: the autopilot SKILL must describe the SAFE yield model, and Phase 8
must run its test step synchronously without the CI-only determinism sweep.

History: the 2026-06-17 fix forbade yielding on pending background work. That
rule was unsatisfiable for Agent dispatches — this harness backgrounds Agent
calls (no foreground mode) and Monitor is blocked — so the model yielded anyway
and the Stop hook's SIGINT stranded the phase (2026-06-19: design reviewer +
/work Tess/Ivan each 3x). The real fix lives in the Stop hook
(autopilot_stop_hook.py `_pending_background_task`): while a dispatched task is
in flight the hook abstains and the harness re-invokes the model on completion,
so yielding is now SAFE. This test pins the corrected SKILL prose: yield on a
dispatched task is fine, only an IDLE STOP thrashes, and long Bash still runs in
the foreground with a timeout. It guards against a regression back to the old
unsatisfiable rule.
"""

from __future__ import annotations

import unittest
from pathlib import Path

SKILL = (Path(__file__).resolve().parent.parent / "SKILL.md").read_text()


class SafeYieldOnPendingWorkContract(unittest.TestCase):
    """The SKILL must describe the safe-yield model, not the old unsatisfiable
    'never yield' rule."""

    def test_skill_says_stop_hook_keeps_session_alive_on_pending_task(self) -> None:
        # The mechanism: abstain + keep the session alive while a task is in
        # flight, instead of SIGINTing and stranding it.
        self.assertIn(
            "keeps the session alive",
            SKILL,
            "SKILL must state the Stop hook keeps the session alive on a pending task",
        )

    def test_skill_says_harness_reinvokes_on_completion(self) -> None:
        # The corrected belief: the harness DOES re-invoke (via task-notification).
        self.assertIn("re-invokes you with a", SKILL)

    def test_skill_warns_only_idle_stop_thrashes(self) -> None:
        # The remaining failure mode is the IDLE stop, not a yield on real work.
        self.assertIn("never STOP idle", SKILL)
        self.assertIn("idle STOP", SKILL)

    def test_skill_keeps_foreground_timeout_for_long_bash(self) -> None:
        # Long Bash still runs foreground with a timeout (an auto-background Bash
        # without its task-notification yet is not always detectable).
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
