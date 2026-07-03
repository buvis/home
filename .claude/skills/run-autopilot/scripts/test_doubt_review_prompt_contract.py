"""Contract test: the codex doubt-review prompt's coverage block must parse
and validate under the real review_coverage.py, and its rubric section must
cover exactly the rules in doubt-review-rubric.md.

If this fails, the doubt phase (codex OR Claude) would emit a block that the
downstream gate rejects — silently weakening a mandated review. Stdlib-only.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

_SKILLS = Path(__file__).resolve().parents[2]
_RC_PATH = (_SKILLS / "review-work-completion" / "scripts" / "review_coverage.py")
_RUBRIC_PATH = Path(__file__).resolve().parent.parent / "references" / "doubt-review-rubric.md"
_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "doubt-review.md"

_spec = importlib.util.spec_from_file_location("review_coverage", _RC_PATH)
rc = importlib.util.module_from_spec(_spec)
# Register before exec: review_coverage.py uses `from __future__ import
# annotations`, so its @dataclass fields are stringized. Python 3.14's
# dataclasses._is_type resolves them via sys.modules[cls.__module__]; without
# this registration that lookup returns None and class creation raises
# AttributeError. (Running review_coverage.py as a script is unaffected —
# __module__ is then "__main__", which is always registered.)
sys.modules["review_coverage"] = rc
_spec.loader.exec_module(rc)

# The canonical coverage block exactly as prompts/doubt-review.md prescribes.
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


class DoubtCoverageContractTests(unittest.TestCase):
    def test_canonical_block_parses_and_validates(self) -> None:
        inner = rc._extract_block_text(CANONICAL_BLOCK)
        self.assertIsNotNone(inner)
        sections = rc._parse_block(inner)
        self.assertEqual(
            set(sections), {"files", "tests", "features", "rubric"}
        )
        # Must not raise:
        rc._validate_verdicts(sections)

    def test_rubric_section_matches_doubt_rubric_rules(self) -> None:
        rules = set(rc._rubric_rules(_RUBRIC_PATH))
        self.assertEqual(rules, {"R1", "R2", "R3", "R4", "R5"})
        inner = rc._extract_block_text(CANONICAL_BLOCK)
        block_rules = set(rc._parse_block(inner)["rubric"].keys())
        self.assertEqual(block_rules, rules)

    def test_prompt_file_pins_the_same_block_shape(self) -> None:
        # Guard against the prompt drifting away from the parser contract.
        prompt = _PROMPT_PATH.read_text()
        self.assertIn("---review-coverage---", prompt)
        self.assertIn("---end-review-coverage---", prompt)
        for section in ("files:", "tests:", "features:", "rubric:"):
            self.assertIn(section, prompt)
        self.assertIn("pending: filled by consolidation", prompt)

    def test_parser_rejects_bad_files_verdict(self) -> None:
        bad = CANONICAL_BLOCK.replace(
            "src/foo.py: reviewed", "src/foo.py: looked-ok"
        )
        inner = rc._extract_block_text(bad)
        sections = rc._parse_block(inner)
        with self.assertRaises(ValueError):
            rc._validate_verdicts(sections)


if __name__ == "__main__":
    unittest.main()
