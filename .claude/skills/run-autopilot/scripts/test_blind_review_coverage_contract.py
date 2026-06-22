"""Contract test: the review-blindly SKILL.md must pin the exact gate invocation
and output filename, and its canonical coverage block must parse and validate
under the real review_coverage.py with rubric IDs matching blind rubric.md.

Tests 1 and 2 pin the SKILL.md gate invocation and output filename; tests 3-5
exercise the parser with a well-formed block.  Stdlib-only.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

_SKILLS = Path(__file__).resolve().parents[2]
_RC_PATH = _SKILLS / "review-work-completion" / "scripts" / "review_coverage.py"
_SKILL_PATH = _SKILLS / "review-blindly" / "SKILL.md"
_RUBRIC_PATH = _SKILLS / "review-blindly" / "references" / "rubric.md"

_spec = importlib.util.spec_from_file_location("review_coverage", _RC_PATH)
rc = importlib.util.module_from_spec(_spec)
# Register before exec: Python 3.14's @dataclass resolves cls.__module__ via
# sys.modules, which raises AttributeError on a spec-loaded module that was
# never registered.
sys.modules["review_coverage"] = rc
_spec.loader.exec_module(rc)

# Canonical per-reviewer block for the blindly surface.
# rubric IDs must exactly match _RUBRIC_PATH (R1-R19 per current rubric.md).
CANONICAL_BLOCK = """\
---review-coverage---
files:
  src/foo.py: reviewed
  gen/bar.py: n/a:generated file
tests:
  pending: filled by consolidation
features:
  widget rendering: reviewed
rubric:
  R1: pass
  R2: pass
  R3: pass
  R4: pass
  R5: pass
  R6: pass
  R7: pass
  R8: pass
  R9: pass
  R10: pass
  R11: pass
  R12: pass
  R13: pass
  R14: pass
  R15: pass
  R16: pass
  R17: pass
  R18: pass
  R19: pass
---end-review-coverage---
"""


class BlindReviewCoverageContractTests(unittest.TestCase):
    def test_skill_invokes_blindly_gate(self) -> None:
        """SKILL.md must pin the exact gate call: review_coverage.py --surface blindly --write-aggregate."""
        text = _SKILL_PATH.read_text()
        self.assertIn("review_coverage.py", text,
                      "SKILL.md must reference review_coverage.py")
        self.assertIn("--surface blindly", text,
                      "SKILL.md must pass --surface blindly to the gate")
        self.assertIn("--write-aggregate", text,
                      "SKILL.md must pass --write-aggregate to the gate")

    def test_skill_names_blind_review_file(self) -> None:
        """SKILL.md must name the exact output filename <prd>-blind-review.md."""
        text = _SKILL_PATH.read_text()
        self.assertIn("<prd>-blind-review.md", text,
                      "SKILL.md must contain the literal filename <prd>-blind-review.md")

    def test_canonical_block_parses_and_validates(self) -> None:
        """A well-formed blind-review coverage block must survive the parser and validator."""
        inner = rc._extract_block_text(CANONICAL_BLOCK)
        self.assertIsNotNone(inner, "_extract_block_text returned None — delimiters missing")
        sections = rc._parse_block(inner)
        self.assertEqual(
            set(sections), {"files", "tests", "features", "rubric"},
            "_parse_block must return exactly the four required sections",
        )
        # Must not raise:
        rc._validate_verdicts(sections)

    def test_block_rubric_ids_match_blind_rubric(self) -> None:
        """CANONICAL_BLOCK rubric keys must equal the IDs defined in review-blindly rubric.md."""
        expected = set(rc._rubric_rules(_RUBRIC_PATH))
        inner = rc._extract_block_text(CANONICAL_BLOCK)
        actual = set(rc._parse_block(inner)["rubric"].keys())
        self.assertEqual(
            actual, expected,
            f"CANONICAL_BLOCK rubric IDs {actual} do not match rubric.md IDs {expected}",
        )

    def test_parser_rejects_bad_files_verdict(self) -> None:
        """Parser must raise ValueError when a files entry carries an invalid verdict."""
        bad = CANONICAL_BLOCK.replace(
            "src/foo.py: reviewed", "src/foo.py: looked-ok"
        )
        inner = rc._extract_block_text(bad)
        sections = rc._parse_block(inner)
        with self.assertRaises(ValueError):
            rc._validate_verdicts(sections)

    def test_skill_runs_reviewer_as_direct_foreground_cli(self) -> None:
        """Root-cause guard (2026-06-19, three rounds): this harness backgrounds
        EVERY Agent/Task dispatch — even a `general-purpose` subagent with no
        `model` override — so a subagent-wrapped reviewer returns an async-launch
        ack whose notification lands after the autopilot Stop hook has killed the
        session, and "blind" never completes. The reviewer must run as a DIRECT
        foreground Bash call to the Sonnet CLI (which blocks the turn), not
        wrapped in a subagent. Pin all three halves so the fix cannot regress."""
        text = _SKILL_PATH.read_text()
        # (1) No model-override dispatch line (a real override is a standalone
        # YAML directive, not a backtick mention in prose).
        for raw in text.splitlines():
            line = raw.strip()
            self.assertFalse(
                line.startswith("model:") and "sonnet" in line,
                f"SKILL.md has a model-override dispatch line ({line!r})",
            )
        # (2) Reaches Sonnet via the CLI.
        self.assertIn(
            "sonnet-run.sh", text,
            "SKILL.md must run the reviewer via the Sonnet CLI (sonnet-run.sh)",
        )
        # (3) Runs it DIRECTLY in the main session, NOT wrapped in a subagent.
        # Every Agent/Task dispatch backgrounds, so no subagent may carry the run;
        # a direct foreground Bash call to the CLI blocks the turn instead.
        self.assertNotIn(
            "subagent_type", text,
            "the reviewer must run as a direct foreground Bash call, NOT a "
            "subagent — every Agent/Task dispatch backgrounds and strands blind",
        )


if __name__ == "__main__":
    unittest.main()
