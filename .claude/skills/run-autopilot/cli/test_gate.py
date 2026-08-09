#!/usr/bin/env python3
"""Tests for `autopilot gate` (PRD 00107 Phase 0).

Binds the CLI wiring and the two entry points, not the full check matrix —
that stays in review-work-completion/scripts/test_check_review_file.py,
which now exercises the same code through the re-export shim and must keep
passing unmodified (the parity proof for the move).
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

CLI_DIR = Path(__file__).resolve().parent
CLI_MAIN = CLI_DIR / "__main__.py"
GATE_SCRIPT = CLI_DIR / "gate.py"
SHIM = (
    CLI_DIR.parents[1] / "review-work-completion" / "scripts" / "check_review_file.py"
)

GOOD_FILE = """---
reviewers: alice,blake,bob
---

codex_rung_guard: not fired

## Alice

- finding one

## Blake

No spec drift found.

## Bob

D1: pass

Verdict: converged
Tests: 12 passed, 0 failed
"""

DOCS_ONLY_FILE = """---
reviewers: alice
---

## Alice

docs read clean

Verdict: converged
Tests: none (docs-only)
"""

CONSTRAINT_UNMET_FILE = """---
reviewers: alice
---

codex_rung_guard: fired (2 codex-implemented task(s)); constraint UNMET

## Alice

- ok

Verdict: converged
Tests: 3 passed, 0 failed
"""


def _run(entry: list[str], args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *entry, *args],
        capture_output=True,
        text=True,
    )


class GateSubcommandTests(unittest.TestCase):
    """`autopilot gate` via cli/__main__.py."""

    def _write(self, tmp_name: str, text: str) -> Path:
        import tempfile

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / tmp_name
        path.write_text(text, encoding="utf-8")
        return path

    def test_well_formed_file_passes(self) -> None:
        path = self._write("prd-review-1.md", GOOD_FILE)
        proc = _run([str(CLI_MAIN)], ["gate", "--review-file", str(path)])
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_docs_only_sentinel_passes(self) -> None:
        path = self._write("prd-review-1.md", DOCS_ONLY_FILE)
        proc = _run([str(CLI_MAIN)], ["gate", "--review-file", str(path)])
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_shape_gap_blocks_with_reason(self) -> None:
        path = self._write("prd-review-1.md", "## Alice\n\nhm\n")
        proc = _run(
            [str(CLI_MAIN)],
            ["gate", "--review-file", str(path), "--reviewers", "alice"],
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("verdict", proc.stderr.lower())

    def test_missing_reviewer_section_names_the_reviewer(self) -> None:
        path = self._write("prd-review-1.md", GOOD_FILE)
        proc = _run(
            [str(CLI_MAIN)],
            ["gate", "--review-file", str(path), "--reviewers", "alice,carl"],
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("carl", proc.stderr)

    def test_missing_file_exits_1(self) -> None:
        proc = _run(
            [str(CLI_MAIN)],
            ["gate", "--review-file", "/nonexistent/rev.md"],
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("missing review file", proc.stderr)

    def test_constraint_unmet_exits_2_only_under_the_flag(self) -> None:
        path = self._write("prd-review-1.md", CONSTRAINT_UNMET_FILE)
        without = _run(
            [str(CLI_MAIN)],
            ["gate", "--review-file", str(path), "--require-codex-guard"],
        )
        self.assertEqual(without.returncode, 0, without.stderr)
        with_flag = _run(
            [str(CLI_MAIN)],
            [
                "gate",
                "--review-file",
                str(path),
                "--require-codex-guard",
                "--assert-constraint-met",
            ],
        )
        self.assertEqual(with_flag.returncode, 2)
        self.assertIn("constraint UNMET", with_flag.stderr)

    def test_plain_fired_without_eve_section_blocks(self) -> None:
        text = CONSTRAINT_UNMET_FILE.replace("; constraint UNMET", "")
        path = self._write("prd-review-1.md", text)
        proc = _run(
            [str(CLI_MAIN)],
            ["gate", "--review-file", str(path), "--require-codex-guard"],
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("eve", proc.stderr.lower())


class DirectScriptTests(unittest.TestCase):
    """cli/gate.py must stay standalone-runnable: review_coverage_hook.py
    shells to it by path, outside the `autopilot` dispatcher."""

    def test_direct_invocation_matches_subcommand(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prd-review-1.md"
            path.write_text(GOOD_FILE, encoding="utf-8")
            direct = _run([str(GATE_SCRIPT)], ["--review-file", str(path)])
            self.assertEqual(direct.returncode, 0, direct.stderr)


class ShimParityTests(unittest.TestCase):
    def test_shim_objects_are_the_cli_gate_objects(self) -> None:
        """The shim re-exports, never copies: its `check` must BE cli.gate's."""
        import importlib.util

        sys.path.insert(0, str(CLI_DIR.parent))
        try:
            from cli import gate as cli_gate

            spec = importlib.util.spec_from_file_location("check_review_file", SHIM)
            assert spec is not None and spec.loader is not None
            shim = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(shim)
        finally:
            sys.path.remove(str(CLI_DIR.parent))
        self.assertIs(shim.check, cli_gate.check)
        self.assertIs(shim.run_gate, cli_gate.run_gate)
        self.assertIs(shim.FRONTMATTER_REVIEWERS_RE, cli_gate.FRONTMATTER_REVIEWERS_RE)


if __name__ == "__main__":
    unittest.main()
