"""Tests for check_review_file.py (PRD 00016) — the minimal review-file gate.

Covers the PRD's four Test Strategy scenarios plus the frontmatter-reviewers
fallback. Run: python3 -m pytest test_check_review_file.py
"""

from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent / "check_review_file.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_review_file", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load()

GOOD_FILE = """---
head_sha: abc123
reviewers: alice,blake,bob
---

codex_rung_guard: not fired

## Alice

- 🟡 minor nit | File: x.py | Task: 3

## Blake

No spec drift found; all requirements verified.

## Bob

FIX:
- (none)
R1: pass
R2: pass

Verdict: converged
Tests: 34 passed, 0 failed, 1 skipped
"""


def run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )


class CheckReviewFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def _write(self, text: str) -> Path:
        p = self.dir / "prd-review-1.md"
        p.write_text(text)
        return p

    # Happy path: all sections + converged verdict + test counts → exit 0
    def test_happy_path_exit_0(self) -> None:
        p = self._write(GOOD_FILE)
        proc = run_cli(["--review-file", str(p), "--reviewers", "alice,blake,bob"])
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_findings_verdict_also_passes(self) -> None:
        p = self._write(GOOD_FILE.replace("Verdict: converged", "Verdict: 3 findings"))
        proc = run_cli(["--review-file", str(p), "--reviewers", "alice"])
        self.assertEqual(proc.returncode, 0, proc.stderr)

    # Edge: docs-only cycle → first-class value, no sentinel gymnastics
    def test_docs_only_tests_line_exit_0(self) -> None:
        p = self._write(
            GOOD_FILE.replace(
                "Tests: 34 passed, 0 failed, 1 skipped", "Tests: none (docs-only)"
            )
        )
        proc = run_cli(["--review-file", str(p), "--reviewers", "alice,bob"])
        self.assertEqual(proc.returncode, 0, proc.stderr)

    # Edge: launched reviewer with an empty section → exit 1 naming them
    def test_empty_reviewer_section_exit_1(self) -> None:
        text = GOOD_FILE.replace(
            "## Blake\n\nNo spec drift found; all requirements verified.\n",
            "## Blake\n\n",
        )
        p = self._write(text)
        proc = run_cli(["--review-file", str(p), "--reviewers", "alice,blake,bob"])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("blake", proc.stderr.lower())

    def test_missing_reviewer_section_exit_1(self) -> None:
        p = self._write(GOOD_FILE)
        proc = run_cli(["--review-file", str(p), "--reviewers", "alice,carl"])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("carl", proc.stderr.lower())

    def test_missing_verdict_line_exit_1(self) -> None:
        p = self._write(GOOD_FILE.replace("Verdict: converged\n", ""))
        proc = run_cli(["--review-file", str(p), "--reviewers", "alice"])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("verdict", proc.stderr.lower())

    def test_missing_tests_line_exit_1(self) -> None:
        p = self._write(
            GOOD_FILE.replace("Tests: 34 passed, 0 failed, 1 skipped\n", "")
        )
        proc = run_cli(["--review-file", str(p), "--reviewers", "alice"])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("tests", proc.stderr.lower())

    # Error: file missing entirely → exit 1 naming the path
    def test_missing_file_exit_1(self) -> None:
        p = self.dir / "absent.md"
        proc = run_cli(["--review-file", str(p)])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("missing review file", proc.stderr)

    # Error: unreadable due to I/O error → exit 0, loud stderr (fail open)
    def test_unreadable_file_fails_open(self) -> None:
        p = self._write(GOOD_FILE)
        os.chmod(p, 0)
        self.addCleanup(os.chmod, p, stat.S_IRUSR | stat.S_IWUSR)
        proc = run_cli(["--review-file", str(p), "--reviewers", "alice"])
        if os.geteuid() == 0:  # root ignores modes; scenario not testable
            self.skipTest("running as root; chmod 0 is not unreadable")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("infrastructure error", proc.stderr)

    # Frontmatter fallback: --reviewers omitted → frontmatter list is used
    def test_frontmatter_reviewers_fallback(self) -> None:
        p = self._write(GOOD_FILE)
        proc = run_cli(["--review-file", str(p)])
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_frontmatter_reviewers_fallback_catches_gap(self) -> None:
        # frontmatter names bob, but his section is gone → exit 1
        text = GOOD_FILE.replace(
            "## Bob\n\nFIX:\n- (none)\nR1: pass\nR2: pass\n", ""
        )
        p = self._write(text)
        proc = run_cli(["--review-file", str(p)])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("bob", proc.stderr.lower())

    # -- codex_rung_guard audit line: exactly one of two grammar forms is
    # required as a plain body line; this is a shape check, not semantic --

    def test_codex_rung_guard_fired_form_with_count_passes(self) -> None:
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "codex_rung_guard: fired (3 codex-implemented task(s))",
        )
        p = self._write(text)
        proc = run_cli(["--review-file", str(p), "--reviewers", "alice"])
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_codex_rung_guard_not_fired_form_passes(self) -> None:
        p = self._write(GOOD_FILE)
        proc = run_cli(["--review-file", str(p), "--reviewers", "alice"])
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_codex_rung_guard_position_in_file_does_not_matter(self) -> None:
        # Shape check only: the line may sit anywhere, not just up top.
        text = GOOD_FILE.replace("codex_rung_guard: not fired\n\n", "")
        text += "\ncodex_rung_guard: not fired\n"
        p = self._write(text)
        proc = run_cli(["--review-file", str(p), "--reviewers", "alice"])
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_codex_rung_guard_missing_entirely_exit_1(self) -> None:
        text = GOOD_FILE.replace("codex_rung_guard: not fired\n\n", "")
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"]
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("codex_rung_guard", proc.stderr.lower())

    def test_codex_rung_guard_fired_missing_count_exit_1(self) -> None:
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "codex_rung_guard: fired (codex-implemented task(s))",
        )
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"]
        )
        self.assertEqual(proc.returncode, 1)

    def test_codex_rung_guard_fired_non_numeric_count_exit_1(self) -> None:
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "codex_rung_guard: fired (three codex-implemented task(s))",
        )
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"]
        )
        self.assertEqual(proc.returncode, 1)

    def test_codex_rung_guard_bare_fired_no_parenthetical_exit_1(self) -> None:
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired", "codex_rung_guard: fired"
        )
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"]
        )
        self.assertEqual(proc.returncode, 1)

    def test_codex_rung_guard_trailing_junk_after_paren_exit_1(self) -> None:
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "codex_rung_guard: fired (3 codex-implemented task(s)) extra",
        )
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"]
        )
        self.assertEqual(proc.returncode, 1)

    def test_codex_rung_guard_wrong_key_casing_exit_1(self) -> None:
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired", "Codex_Rung_Guard: not fired"
        )
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"]
        )
        self.assertEqual(proc.returncode, 1)

    # Regression: the shared gate must stay usable for review kinds (blind
    # reviews, shadow-run renders) that never carry a codex_rung_guard line —
    # without --require-codex-guard, its absence is not a gap.
    def test_missing_codex_rung_guard_without_flag_exit_0(self) -> None:
        text = GOOD_FILE.replace("codex_rung_guard: not fired\n\n", "")
        p = self._write(text)
        proc = run_cli(["--review-file", str(p), "--reviewers", "alice"])
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
