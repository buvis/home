"""Contract tests for the post-00016 review prompt/file shapes.

Replaces test_doubt_review_prompt_contract.py and
test_blind_review_coverage_contract.py, which pinned the retired
`---review-coverage---` block format. The surviving contract is small:
doubt/blind reviewers emit findings plus per-rule `R{n}:` verdict lines, and
the saved review files are validated by check_review_file.py. Stdlib-only.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_SKILLS = Path(__file__).resolve().parents[2]
# PRD 00109 moved the doubt lens out of run-autopilot/prompts/doubt-review.md
# and into the agent registry. eve.md is now the single source: the native
# doubt persona's system prompt, and the base the codex/Claude-fallback lanes
# assemble from.
_DOUBT_PROMPT = _SKILLS.parent / "agents" / "eve.md"
_DOUBT_RUBRIC = (
    Path(__file__).resolve().parent.parent / "references" / "doubt-review-rubric.md"
)
_BLIND_SKILL = _SKILLS / "review-blindly" / "SKILL.md"


def _rubric_rule_ids(text: str) -> set[str]:
    # Prefix-agnostic since PRD 00108 split the shared R namespace into
    # consensus R, blind B and doubt D. Hardcoding `R` here would silently
    # return an empty set from BOTH sides of the doubt comparison below, and
    # `rubric_ids <= prompt_ids` would then pass vacuously.
    return set(re.findall(r"^([RDB]\d+):", text, re.MULTILINE))


class DoubtPromptContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prompt = _DOUBT_PROMPT.read_text()

    def test_prompt_requires_fix_verify_known_buckets(self) -> None:
        for bucket in ("FIX", "VERIFY", "KNOWN"):
            self.assertIn(bucket, self.prompt)

    def test_prompt_rubric_matches_rubric_reference(self) -> None:
        rubric_ids = _rubric_rule_ids(_DOUBT_RUBRIC.read_text())
        self.assertEqual(rubric_ids, {"D1", "D2", "D3", "D4", "D5"})
        prompt_ids = _rubric_rule_ids(self.prompt)
        self.assertTrue(
            rubric_ids <= prompt_ids,
            f"prompt must require every rubric rule; missing {rubric_ids - prompt_ids}",
        )

    def test_doubt_prompt_carries_no_stale_r_prefixed_ids(self) -> None:
        # The rename is prefix-only, so a surviving R-id here means a rule was
        # half-migrated — the emit-verbatim block and the rule list must agree.
        stale = sorted(re.findall(r"^(R\d+):", self.prompt, re.MULTILINE))
        self.assertEqual(stale, [], f"doubt persona still emits {stale}")

    def test_prompt_has_no_retired_coverage_block(self) -> None:
        self.assertNotIn(
            "---review-coverage---",
            self.prompt,
            "PRD 00016 retired the coverage block; reviewers emit findings + R lines only",
        )


class BlindSkillContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill = _BLIND_SKILL.read_text()

    def test_blind_skill_gates_with_check_review_file(self) -> None:
        self.assertIn("check_review_file.py", self.skill)
        self.assertNotIn("review_coverage.py", self.skill)

    def test_blind_skill_requires_rubric_verdict_lines(self) -> None:
        self.assertIn("PER-RULE VERDICTS ARE MANDATORY", self.skill)

    def test_blind_skill_has_no_retired_coverage_block(self) -> None:
        self.assertNotIn("---review-coverage---", self.skill)

    def test_blind_skill_writes_verdict_and_tests_lines(self) -> None:
        self.assertIn("Verdict:", self.skill)
        self.assertIn("Tests:", self.skill)


if __name__ == "__main__":
    unittest.main()
