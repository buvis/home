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
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
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
                "Tests: 34 passed, 0 failed, 1 skipped",
                "Tests: none (docs-only)",
            ),
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
            GOOD_FILE.replace("Tests: 34 passed, 0 failed, 1 skipped\n", ""),
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
            "## Bob\n\nFIX:\n- (none)\nR1: pass\nR2: pass\n",
            "",
        )
        p = self._write(text)
        proc = run_cli(["--review-file", str(p)])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("bob", proc.stderr.lower())

    # -- codex_rung_guard audit line: exactly one of two grammar forms is
    # required as a plain body line; this is a shape check, not semantic --

    def test_codex_rung_guard_fired_form_with_count_passes(self) -> None:
        # Plain fired(N) now asserts the doubt-roster constraint held via
        # Eve, so the fixture must carry a non-empty Eve section.
        text = (
            GOOD_FILE.replace(
                "codex_rung_guard: not fired",
                "codex_rung_guard: fired (3 codex-implemented task(s))",
            ).replace("reviewers: alice,blake,bob", "reviewers: alice,blake,bob,eve")
            + "\n## Eve\n\nNo constraint issues found; doubt lens confirmed.\n"
        )
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_codex_rung_guard_not_fired_form_passes(self) -> None:
        p = self._write(GOOD_FILE)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_codex_rung_guard_position_in_file_does_not_matter(self) -> None:
        # Shape check only: the line may sit anywhere, not just up top.
        text = GOOD_FILE.replace("codex_rung_guard: not fired\n\n", "")
        text += "\ncodex_rung_guard: not fired\n"
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_codex_rung_guard_missing_entirely_exit_1(self) -> None:
        text = GOOD_FILE.replace("codex_rung_guard: not fired\n\n", "")
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"],
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
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"],
        )
        self.assertEqual(proc.returncode, 1)

    def test_codex_rung_guard_fired_non_numeric_count_exit_1(self) -> None:
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "codex_rung_guard: fired (three codex-implemented task(s))",
        )
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"],
        )
        self.assertEqual(proc.returncode, 1)

    def test_codex_rung_guard_bare_fired_no_parenthetical_exit_1(self) -> None:
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "codex_rung_guard: fired",
        )
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"],
        )
        self.assertEqual(proc.returncode, 1)

    def test_codex_rung_guard_trailing_junk_after_paren_exit_1(self) -> None:
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "codex_rung_guard: fired (3 codex-implemented task(s)) extra",
        )
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"],
        )
        self.assertEqual(proc.returncode, 1)

    def test_codex_rung_guard_wrong_key_casing_exit_1(self) -> None:
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "Codex_Rung_Guard: not fired",
        )
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"],
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

    # -- widened grammar: two additional suffix forms after the parenthetical,
    # each naming a distinct guard-fired outcome; still a shape check only --

    def test_codex_rung_guard_eve_unavailable_fallback_form_passes(self) -> None:
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "codex_rung_guard: fired (3 codex-implemented task(s)); "
            "eve unavailable, doubt lens fell back to claude",
        )
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_codex_rung_guard_constraint_unmet_form_passes(self) -> None:
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "codex_rung_guard: fired (3 codex-implemented task(s)); constraint UNMET",
        )
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_codex_rung_guard_eve_unavailable_alone_not_full_suffix_exit_1(
        self,
    ) -> None:
        # Has the "; " separator but not the full documented suffix — must
        # not be accepted by a loosely-widened (e.g. ".*") suffix pattern.
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "codex_rung_guard: fired (3 codex-implemented task(s)); eve unavailable",
        )
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"],
        )
        self.assertEqual(proc.returncode, 1)

    def test_codex_rung_guard_constraint_unmet_wrong_case_exit_1(self) -> None:
        # Lowercase "unmet" is not the documented literal suffix.
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "codex_rung_guard: fired (3 codex-implemented task(s)); constraint unmet",
        )
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"],
        )
        self.assertEqual(proc.returncode, 1)

    # -- consistency: the guard's record must match the roster, not just
    # parse — enforced only under --require-codex-guard --

    def test_codex_rung_guard_fired_zero_count_exit_1(self) -> None:
        # fired(0) is self-contradictory: fired implies at least one
        # codex-implemented task.
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "codex_rung_guard: fired (0 codex-implemented task(s))",
        )
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"],
        )
        self.assertEqual(proc.returncode, 1)

    def test_codex_rung_guard_plain_fired_without_eve_section_exit_1(self) -> None:
        # KEY RED TEST: plain fired(N) with no Eve section claims a
        # non-codex doubt reviewer ran when the roster shows none.
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "codex_rung_guard: fired (3 codex-implemented task(s))",
        )
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"],
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("eve", proc.stderr.lower())

    def test_codex_rung_guard_plain_fired_with_eve_section_exit_0(self) -> None:
        text = (
            GOOD_FILE.replace(
                "codex_rung_guard: not fired",
                "codex_rung_guard: fired (3 codex-implemented task(s))",
            ).replace("reviewers: alice,blake,bob", "reviewers: alice,blake,bob,eve")
            + "\n## Eve\n\nNo constraint issues found; doubt lens confirmed.\n"
        )
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_codex_rung_guard_eve_unavailable_form_needs_no_eve_section_exit_0(
        self,
    ) -> None:
        # Control: the suffix self-documents Eve's absence (Bob's Claude
        # fallback covered doubt), so no Eve section is required even
        # though the count is otherwise plain-fired-shaped.
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "codex_rung_guard: fired (3 codex-implemented task(s)); "
            "eve unavailable, doubt lens fell back to claude",
        )
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    # -- --assert-constraint-met: opt-in semantic check on top of the shape
    # check. "; constraint UNMET" is still a VALID recorded shape (script
    # exits 0 on it without this flag); this flag lets a caller additionally
    # ask whether that recorded constraint was actually met. --

    def test_constraint_unmet_without_assert_flag_stays_exit_0(self) -> None:
        # Regression pin: today's only caller (the Stop hook) passes
        # --require-codex-guard alone and must never gain a new halt class
        # just because this flag now exists in the parser.
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "codex_rung_guard: fired (3 codex-implemented task(s)); constraint UNMET",
        )
        p = self._write(text)
        proc = run_cli(
            ["--review-file", str(p), "--reviewers", "alice", "--require-codex-guard"],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_assert_constraint_met_fails_when_guard_constraint_unmet(self) -> None:
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "codex_rung_guard: fired (3 codex-implemented task(s)); constraint UNMET",
        )
        p = self._write(text)
        proc = run_cli(
            [
                "--review-file",
                str(p),
                "--reviewers",
                "alice",
                "--require-codex-guard",
                "--assert-constraint-met",
            ],
        )
        # Guard against a false pass: argparse's own "unrecognized arguments"
        # error also exits non-zero, so a bare assertNotEqual(0) would pass
        # even with the flag unimplemented. Rule that out explicitly.
        self.assertNotIn("unrecognized arguments", proc.stderr)
        self.assertNotEqual(proc.returncode, 0)

    def test_assert_constraint_met_uses_exit_code_2_not_shape_gap_code(self) -> None:
        # An unmet constraint is its own failure class, distinct from a
        # shape gap (1), so a caller can tell "malformed file" apart from
        # "constraint not certified".
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "codex_rung_guard: fired (3 codex-implemented task(s)); constraint UNMET",
        )
        p = self._write(text)
        proc = run_cli(
            [
                "--review-file",
                str(p),
                "--reviewers",
                "alice",
                "--require-codex-guard",
                "--assert-constraint-met",
            ],
        )
        # Same false-pass guard as above: code 2 must come from the
        # constraint check, not from argparse rejecting an unknown flag.
        self.assertNotIn("unrecognized arguments", proc.stderr)
        self.assertEqual(proc.returncode, 2)

    def test_assert_constraint_met_passes_when_guard_not_fired(self) -> None:
        p = self._write(GOOD_FILE)  # "codex_rung_guard: not fired"
        proc = run_cli(
            [
                "--review-file",
                str(p),
                "--reviewers",
                "alice",
                "--require-codex-guard",
                "--assert-constraint-met",
            ],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_assert_constraint_met_passes_when_guard_fired_plain(self) -> None:
        # Intent: a guard line that is NOT "; constraint UNMET" must not trip
        # exit 2. The fixture carries an Eve section because plain fired(N)
        # asserts a non-codex doubt reviewer ran, and the roster-consistency
        # check now enforces that (see
        # test_codex_rung_guard_plain_fired_without_eve_section_exit_1). Without
        # it this test and that one would demand opposite results from the same
        # file, with --assert-constraint-met somehow making the gate LAXER.
        text = (
            GOOD_FILE.replace(
                "codex_rung_guard: not fired",
                "codex_rung_guard: fired (3 codex-implemented task(s))",
            ).replace("reviewers: alice,blake,bob", "reviewers: alice,blake,bob,eve")
            + "\n## Eve\n\nNo constraint issues found; doubt lens confirmed.\n"
        )
        p = self._write(text)
        proc = run_cli(
            [
                "--review-file",
                str(p),
                "--reviewers",
                "alice",
                "--require-codex-guard",
                "--assert-constraint-met",
            ],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_assert_constraint_met_passes_when_eve_unavailable_fallback_form(
        self,
    ) -> None:
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "codex_rung_guard: fired (3 codex-implemented task(s)); "
            "eve unavailable, doubt lens fell back to claude",
        )
        p = self._write(text)
        proc = run_cli(
            [
                "--review-file",
                str(p),
                "--reviewers",
                "alice",
                "--require-codex-guard",
                "--assert-constraint-met",
            ],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_shape_gap_reported_over_unmet_constraint_when_both_present(self) -> None:
        # A file that is both malformed (missing verdict line) and records
        # constraint UNMET cannot be trusted for a constraint reading, so
        # the shape-gap exit code (1) wins over the constraint code (2).
        text = GOOD_FILE.replace(
            "codex_rung_guard: not fired",
            "codex_rung_guard: fired (3 codex-implemented task(s)); constraint UNMET",
        ).replace("Verdict: converged\n", "")
        p = self._write(text)
        proc = run_cli(
            [
                "--review-file",
                str(p),
                "--reviewers",
                "alice",
                "--require-codex-guard",
                "--assert-constraint-met",
            ],
        )
        self.assertEqual(proc.returncode, 1)

    def test_assert_constraint_met_exit_code_differs_from_unrelated_shape_gap(
        self,
    ) -> None:
        # A pure shape gap with no constraint-UNMET involved at all (guard
        # line is the plain "not fired" form) must still exit 1, not step
        # on the constraint-specific code 2.
        text = GOOD_FILE.replace("Verdict: converged\n", "")
        p = self._write(text)
        proc = run_cli(
            [
                "--review-file",
                str(p),
                "--reviewers",
                "alice",
                "--require-codex-guard",
                "--assert-constraint-met",
            ],
        )
        self.assertEqual(proc.returncode, 1)


if __name__ == "__main__":
    unittest.main()
