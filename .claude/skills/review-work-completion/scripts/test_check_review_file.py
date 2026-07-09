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


if __name__ == "__main__":
    unittest.main()
