"""Contract test for the codex-session-resume wiring in review-work-completion.

Pins the SKILL.md / agent-invocation.md text that carries `codex_thread_id`
across Phase 4 rework cycles (PRD 00040). Text-pinning only: stdlib unittest,
no import of any module. Deleting the step-3 read, the step-8 stamp/omission
rule, or the Bob-launch resume flags must fail one of these tests.
"""

from __future__ import annotations

import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL_MD = SKILL_DIR / "SKILL.md"
AGENT_INVOCATION = SKILL_DIR / "references" / "agent-invocation.md"


def _section(text: str, header: str) -> str:
    """Return the slice from `header` up to the next `## ` or `### ` header."""
    start = text.index(header)
    after = start + len(header)
    ends = [
        e
        for e in (text.find("\n### ", after), text.find("\n## ", after))
        if e != -1
    ]
    end = min(ends) if ends else len(text)
    return text[start:end]


class CodexResumeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = SKILL_MD.read_text(encoding="utf-8")
        cls.agents = AGENT_INVOCATION.read_text(encoding="utf-8")
        cls.step3 = _section(cls.skill, "### 3. Gather context")
        cls.step8 = _section(cls.skill, "### 8. Save review file")
        cls.bob = _section(cls.agents, "## Bob (Codex)")

    def test_step3_reads_codex_thread_id(self) -> None:
        # The incremental path must read the resume thread id from the prior file.
        self.assertIn("codex_thread_id", self.step3)

    def test_step8_stamps_codex_thread_id(self) -> None:
        # The save step must stamp the captured thread id into the frontmatter.
        self.assertIn("codex_thread_id", self.step8)

    def test_step8_has_omission_rule(self) -> None:
        # The stamp is conditional: omit when Bob was skipped or capture failed.
        self.assertIn("omit", self.step8)

    def test_bob_block_has_emit_thread_id_flag(self) -> None:
        # Cycle-1 Bob launch captures the thread id.
        self.assertIn("--emit-thread-id", self.bob)

    def test_bob_block_has_resume_thread_flag(self) -> None:
        # Incremental Bob launch resumes the prior session.
        self.assertIn("--resume-thread", self.bob)


if __name__ == "__main__":
    unittest.main()
