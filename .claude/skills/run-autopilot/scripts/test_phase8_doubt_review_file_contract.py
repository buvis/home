"""Contract test: Phase 8 of run-autopilot must invoke review_coverage.py with
--surface doubt and --write-aggregate, and must name the output file
<prd>-doubt-review.md.

Also validates a canonical doubt coverage block against the real parser and
asserts the rubric section exactly matches doubt-review-rubric.md.

This covers a DIFFERENT concern from test_doubt_review_prompt_contract.py,
which tests the PROMPT's emitted block shape. Here we test the CONSUMPTION
side: the gate-call contract and output filename pinned in SKILL.md.

Stdlib-only; run with: python3 .../test_phase8_doubt_review_file_contract.py
"""

import importlib.util
import unittest
from pathlib import Path

_SKILLS = Path(__file__).resolve().parents[2]
_SKILL_PATH = _SKILLS / "run-autopilot" / "SKILL.md"
_RC_PATH = _SKILLS / "review-work-completion" / "scripts" / "review_coverage.py"
_RUBRIC_PATH = Path(__file__).resolve().parent.parent / "references" / "doubt-review-rubric.md"

_spec = importlib.util.spec_from_file_location("review_coverage", _RC_PATH)
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

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
---end-review-coverage---
"""


class Phase8DoubtReviewFileContractTests(unittest.TestCase):
    def test_phase8_invokes_doubt_gate(self) -> None:
        """SKILL.md Phase 8 must call review_coverage.py with --surface doubt and --write-aggregate."""
        skill_text = _SKILL_PATH.read_text()
        self.assertIn(
            "review_coverage.py",
            skill_text,
            "SKILL.md must reference review_coverage.py in Phase 8",
        )
        self.assertIn(
            "--surface doubt",
            skill_text,
            "SKILL.md must pass --surface doubt to the gate",
        )
        self.assertIn(
            "--write-aggregate",
            skill_text,
            "SKILL.md must pass --write-aggregate to the gate",
        )

    def test_phase8_names_doubt_review_file(self) -> None:
        """SKILL.md must pin the output filename <prd>-doubt-review.md."""
        skill_text = _SKILL_PATH.read_text()
        self.assertIn(
            "<prd>-doubt-review.md",
            skill_text,
            "SKILL.md must name the doubt review output file as <prd>-doubt-review.md",
        )

    def test_canonical_doubt_block_parses_and_validates(self) -> None:
        """The canonical doubt coverage block must parse to all four sections and pass verdict validation."""
        inner = rc._extract_block_text(CANONICAL_BLOCK)
        self.assertIsNotNone(inner, "Canonical block delimiters not found")
        sections = rc._parse_block(inner)
        self.assertEqual(
            set(sections),
            {"files", "tests", "features", "rubric"},
            "Canonical block must yield exactly the four required sections",
        )
        # Must not raise:
        rc._validate_verdicts(sections)

    def test_block_rubric_ids_match_doubt_rubric(self) -> None:
        """Canonical block's rubric keys must equal the rule IDs in doubt-review-rubric.md."""
        rules = set(rc._rubric_rules(_RUBRIC_PATH))
        inner = rc._extract_block_text(CANONICAL_BLOCK)
        block_rules = set(rc._parse_block(inner)["rubric"].keys())
        self.assertEqual(
            block_rules,
            rules,
            f"Canonical block rubric keys {block_rules} must equal rubric file rules {rules}",
        )

    def test_parser_rejects_bad_files_verdict(self) -> None:
        """Parser must raise ValueError when a files verdict is not 'reviewed' or 'n/a:...'."""
        bad = CANONICAL_BLOCK.replace(
            "src/foo.py: reviewed", "src/foo.py: looked-ok"
        )
        inner = rc._extract_block_text(bad)
        self.assertIsNotNone(inner)
        sections = rc._parse_block(inner)
        with self.assertRaises(ValueError):
            rc._validate_verdicts(sections)


if __name__ == "__main__":
    unittest.main()
