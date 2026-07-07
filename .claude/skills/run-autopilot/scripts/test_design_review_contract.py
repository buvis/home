#!/usr/bin/env python3
"""Contract test for the design-review hardening (PRD 00039).

Pins the load-bearing lines in design-solution/SKILL.md and run-autopilot/SKILL.md
so the cross-model codex dispatch and the Phase 1.5 empty-review-log gate cannot
silently drift, and binds the dispatch-summary format to the gate regex (they MUST
agree). Modeled on test_doubt_review_prompt_contract.py. Stdlib only; pytest
collects the unittest.TestCase with no config.

RED-first: deleting any pinned line, or drifting the summary format and the gate
regex out of agreement, makes a specific assertion fail.
"""

import re
import unittest
from pathlib import Path

_SKILLS = Path(__file__).resolve().parents[2]
_DESIGN_SKILL = _SKILLS / "design-solution" / "SKILL.md"
_AUTOPILOT_SKILL = _SKILLS / "run-autopilot" / "SKILL.md"

# The exact awk gate regex body pinned in run-autopilot Phase 1.5. This same
# literal is both asserted-present in the SKILL.md (so a regex-body drift there
# fails `test_gate_regex_body_present`) and compiled for the format<->gate
# correspondence check (so a format drift fails `test_format_matches_gate_regex`).
_GATE_REGEX = (
    r"dispatch [0-9]+ \((claude|codex|claude-fallback)\): "
    r"cardinal-sin [0-9]+, blocker [0-9]+, non-blocker [0-9]+, question [0-9]+"
)


class DesignReviewContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.design = _DESIGN_SKILL.read_text()
        self.autopilot = _AUTOPILOT_SKILL.read_text()

    # --- design-solution: cross-model codex dispatch + pinned summary format ---

    def test_design_solution_pins_summary_line_format(self) -> None:
        self.assertIn(
            "dispatch <n> (<claude|codex|claude-fallback>): "
            "cardinal-sin <c>, blocker <b>, non-blocker <nb>, question <q>",
            self.design,
        )

    def test_design_solution_dispatches_codex(self) -> None:
        self.assertIn("codex-run.sh", self.design)

    def test_design_solution_codex_always_runs_on_clean_dispatch_1(self) -> None:
        self.assertIn("even when dispatch 1 found zero blockers", self.design)

    def test_design_solution_has_claude_fallback(self) -> None:
        self.assertIn("claude-fallback", self.design)

    # --- run-autopilot Phase 1.5: empty-review-log gate ---

    def test_gate_pause_detail(self) -> None:
        self.assertIn(
            "design doc has empty ## Review log (review never ran)", self.autopilot
        )

    def test_gate_bypass_is_net_new_phrase(self) -> None:
        # Pin a phrase unique to THIS gate, not the bare `design_mode == "skip"`
        # (which already appears elsewhere in Phase 1.5) — so the assertion is
        # genuinely RED-first for the new gate's bypass, not vacuously green.
        self.assertIn("bypasses the empty-review-log gate", self.autopilot)

    def test_gate_is_section_scoped(self) -> None:
        self.assertIn("awk '/^## Review log/", self.autopilot)

    def test_gate_regex_body_present(self) -> None:
        # Locks the gate's match pattern body, not just the awk prefix, so a
        # regex-body drift in the SKILL.md fails here.
        self.assertIn(_GATE_REGEX, self.autopilot)

    def test_gate_runs_on_both_continue_paths(self) -> None:
        self.assertIn("on this success path", self.autopilot)
        self.assertIn("on this artifact-reuse path", self.autopilot)

    # --- correspondence: the emitted summary format and the gate regex agree ---

    def test_format_matches_gate_regex(self) -> None:
        pattern = re.compile(_GATE_REGEX)
        self.assertRegex(
            "dispatch 2 (codex): cardinal-sin 0, blocker 0, non-blocker 1, question 0",
            pattern,
        )
        self.assertRegex(
            "dispatch 3 (claude-fallback): "
            "cardinal-sin 1, blocker 0, non-blocker 0, question 0",
            pattern,
        )
        # A bare heading (an empty Review log) must NOT satisfy the gate regex.
        self.assertNotRegex("## Review log", pattern)


if __name__ == "__main__":
    unittest.main()
