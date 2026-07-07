"""Contract test for the codex-session-resume wiring in review-work-completion.

Pins the SKILL.md / agent-invocation.md text that carries `codex_thread_id`
across Phase 4 rework cycles (PRD 00040). Text-pinning only: stdlib unittest,
no import of any module. Deleting the step-3 read, the step-8 stamp/omission
rule, or the Bob-launch resume flags must fail one of these tests.

The Bob-launch flags are bound to the SPECIFIC fenced command block that must
carry them (cycle-1 full review vs incremental rework), not to a bare substring
anywhere in the section -- so the flag landing in prose or the wrong command
block fails a test instead of passing silently.
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


def _code_blocks(text: str) -> list[str]:
    """Return the bodies of ``` fenced code blocks in `text`, in order.

    Splitting on the fence yields prose and block bodies alternately, so the
    block bodies are the odd-indexed segments.
    """
    parts = text.split("```")
    return [parts[i] for i in range(1, len(parts), 2)]


class CodexResumeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = SKILL_MD.read_text(encoding="utf-8")
        cls.agents = AGENT_INVOCATION.read_text(encoding="utf-8")
        cls.step3 = _section(cls.skill, "### 3. Gather context")
        cls.step8 = _section(cls.skill, "### 8. Save review file")
        cls.bob = _section(cls.agents, "## Bob (Codex)")
        cls.bob_blocks = _code_blocks(cls.bob)

    def test_step3_reads_codex_thread_id(self) -> None:
        # The incremental path must read the resume thread id from the prior file.
        self.assertIn("codex_thread_id", self.step3)

    def test_step8_stamps_codex_thread_id(self) -> None:
        # The save step must stamp the captured thread id into the frontmatter.
        self.assertIn("codex_thread_id", self.step8)

    def test_step8_has_omission_rule(self) -> None:
        # The stamp is conditional: omit when Bob was skipped or capture failed.
        self.assertIn("omit", self.step8)

    def test_bob_section_has_two_command_blocks(self) -> None:
        # The Bob section carries exactly two fenced command blocks: the cycle-1
        # full-review launch and the incremental (rework) launch. The
        # block-scoped flag tests below index into these, so their positions are
        # part of the contract.
        self.assertEqual(
            len(self.bob_blocks),
            2,
            f"expected 2 fenced command blocks in the Bob section, got {len(self.bob_blocks)}",
        )

    def test_full_review_block_emits_without_resuming(self) -> None:
        # Cycle-1 full-review launch captures the thread id but must NOT resume
        # (no prior session exists yet). Binding to the block, not the whole
        # section, is what catches --resume-thread landing in the wrong command.
        full_review = self.bob_blocks[0]
        self.assertIn("--emit-thread-id", full_review)
        self.assertNotIn("--resume-thread", full_review)

    def test_incremental_block_has_both_flags(self) -> None:
        # Incremental (rework) launch both resumes the prior session and
        # re-captures the id so the following cycle can resume again. A flag in
        # prose or the cycle-1 block does not satisfy this.
        incremental = self.bob_blocks[1]
        self.assertIn("--emit-thread-id", incremental)
        self.assertIn("--resume-thread", incremental)


if __name__ == "__main__":
    unittest.main()
