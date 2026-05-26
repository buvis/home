"""Tests for review_coverage.py.

Invokes the CLI via subprocess. Asserts on exit code and stderr gap-kind prefix.
Stdlib-only unittest. Does NOT import review_coverage.py directly.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PARSER_PATH = Path(__file__).parent / "review_coverage.py"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hermetic_env() -> dict[str, str]:
    """Return env with git identity set; preserves PATH."""
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "Test"
    env["GIT_AUTHOR_EMAIL"] = "test@example.com"
    env["GIT_COMMITTER_NAME"] = "Test"
    env["GIT_COMMITTER_EMAIL"] = "test@example.com"
    return env


def _git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=_hermetic_env(),
        check=True,
    )
    return result.stdout.strip()


def _setup_repo(tmp: Path, code_files: list[str] | None = None) -> tuple[Path, str]:
    """
    Create a tiny two-commit repo under tmp/repo/.

    Returns (repo_path, base_sha). The diff between base_sha and HEAD
    contains code_files (default: ["src/foo.py", "src/bar.py"]).
    """
    repo = tmp / "repo"
    repo.mkdir()
    code_files = code_files or ["src/foo.py", "src/bar.py"]

    _git(["init"], repo)
    _git(["config", "core.autocrlf", "false"], repo)

    # Base commit: an empty README so there is a parent commit.
    readme = repo / "README.md"
    readme.write_text("base\n")
    _git(["add", "README.md"], repo)
    _git(["commit", "-m", "init"], repo)
    base_sha = _git(["rev-parse", "HEAD"], repo)

    # Feature commit: add/modify the code files.
    for rel in code_files:
        p = repo / Path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# {rel}\n")
    _git(["add", "."], repo)
    _git(["commit", "-m", "feature"], repo)

    return repo, base_sha


def _write_prd(tmp: Path, features: list[str] | None = None) -> Path:
    features = features or ["Alpha", "Beta"]
    lines = ["# PRD\n\nSome intro.\n"]
    for f in features:
        lines.append(f"#### Feature: {f}\n\nDetails.\n")
    p = tmp / "prd.md"
    p.write_text("\n".join(lines))
    return p


def _write_rubric(tmp: Path, rule_ids: list[str] | None = None) -> Path:
    rule_ids = rule_ids or ["R1", "R2", "R3"]
    lines = ["# Rubric\n"]
    for r in rule_ids:
        lines.append(f"{r}: some rule description\n")
    p = tmp / "rubric.md"
    p.write_text("\n".join(lines))
    return p


def _write_block(
    path: Path,
    *,
    files: dict[str, str],
    tests: str | None,
    features: dict[str, str],
    rubric: dict[str, str],
) -> None:
    """Write a single reviewer-block file at path."""
    lines = ["---review-coverage---\n"]

    lines.append("files:\n")
    for fname, verdict in files.items():
        lines.append(f"  {fname}: {verdict}\n")

    lines.append("tests:\n")
    if tests:
        lines.append(f"  {tests}\n")

    lines.append("features:\n")
    for feat, verdict in features.items():
        lines.append(f"  {feat}: {verdict}\n")

    lines.append("rubric:\n")
    for rule, verdict in rubric.items():
        lines.append(f"  {rule}: {verdict}\n")

    lines.append("---end-review-coverage---\n")
    path.write_text("".join(lines))


def _run(
    *,
    surface: str = "work-completion",
    prd: Path,
    diff_range: str,
    rubric: Path,
    repo: Path,
    reviewer_blocks: list[Path],
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable, str(PARSER_PATH),
        "--surface", surface,
        "--prd", str(prd),
        "--diff-range", diff_range,
        "--rubric", str(rubric),
        "--repo", str(repo),
    ]
    for rb in reviewer_blocks:
        cmd += ["--reviewer-block", str(rb)]
    if extra_args:
        cmd += extra_args
    return subprocess.run(cmd, capture_output=True, text=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class ReviewCoverageTests(unittest.TestCase):

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)

    # ------------------------------------------------------------------
    # AC1: complete block -> exit 0
    # ------------------------------------------------------------------

    def test_complete_block_passes(self) -> None:
        """AC1: all dimensions filled, all files covered -> exit 0."""
        repo, base_sha = _setup_repo(self.tmp)
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"src/foo.py": "reviewed", "src/bar.py": "reviewed"},
            tests="pytest: pass=5 fail=0 skip=0",
            features={"Alpha": "verified", "Beta": "verified"},
            rubric={"R1": "pass", "R2": "pass", "R3": "pass"},
        )

        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
        )
        self.assertEqual(result.returncode, 0)

    # ------------------------------------------------------------------
    # AC4: docs-only diff with tests: none sentinel -> exit 0
    # ------------------------------------------------------------------

    def test_docs_only_diff_with_none_sentinel_passes(self) -> None:
        """AC4: diff touches only docs, tests sentinel 'none: diff touches no code' -> exit 0."""
        repo, base_sha = _setup_repo(self.tmp, code_files=["docs/guide.md"])
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"docs/guide.md": "n/a:docs only"},
            tests="none: diff touches no code",
            features={"Alpha": "verified", "Beta": "verified"},
            rubric={"R1": "pass", "R2": "pass", "R3": "pass"},
        )

        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
        )
        self.assertEqual(result.returncode, 0)

    # ------------------------------------------------------------------
    # AC2: block missing a diff file -> non-zero, MISSING_FILES names it
    # ------------------------------------------------------------------

    def test_missing_diff_file_fails_with_named_file(self) -> None:
        """AC2: reviewer block omits src/bar.py -> non-zero, MISSING_FILES: src/bar.py."""
        repo, base_sha = _setup_repo(self.tmp)
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"src/foo.py": "reviewed"},  # src/bar.py omitted
            tests="pytest: pass=5 fail=0 skip=0",
            features={"Alpha": "verified", "Beta": "verified"},
            rubric={"R1": "pass", "R2": "pass", "R3": "pass"},
        )

        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            result.stderr.startswith("MISSING_FILES"),
            f"Expected MISSING_FILES prefix, got: {result.stderr[:80]!r}",
        )
        self.assertIn("src/bar.py", result.stderr)

    # ------------------------------------------------------------------
    # AC3a: malformed block (bad structure) -> non-zero, MALFORMED_BLOCK
    # ------------------------------------------------------------------

    def test_malformed_block_fails_with_malformed_kind(self) -> None:
        """AC3: block has valid delimiters but no valid sections -> non-zero, MALFORMED_BLOCK."""
        repo, base_sha = _setup_repo(self.tmp)
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        # Valid delimiters but no sections inside - structurally malformed.
        block.write_text(
            "---review-coverage---\n"
            "this is garbage content with no valid sections\n"
            "---end-review-coverage---\n"
        )

        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            result.stderr.startswith("MALFORMED_BLOCK"),
            f"Expected MALFORMED_BLOCK prefix, got: {result.stderr[:80]!r}",
        )

    # ------------------------------------------------------------------
    # AC3b / edge-case: no delimiters at all -> non-zero, MISSING_REVIEW_BLOCK
    # ------------------------------------------------------------------

    def test_missing_review_block_delimiters_fails(self) -> None:
        """AC3 / edge-case: reviewer-block file has no delimiters -> MISSING_REVIEW_BLOCK."""
        repo, base_sha = _setup_repo(self.tmp)
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        block.write_text("Some summary text with no coverage block at all.\n")

        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            result.stderr.startswith("MISSING_REVIEW_BLOCK"),
            f"Expected MISSING_REVIEW_BLOCK prefix, got: {result.stderr[:80]!r}",
        )

    # ------------------------------------------------------------------
    # Edge case: code in diff but tests dimension empty -> EMPTY_TESTS
    # ------------------------------------------------------------------

    def test_empty_tests_dimension_for_code_diff_fails(self) -> None:
        """Code diff with empty tests dimension -> non-zero, EMPTY_TESTS."""
        repo, base_sha = _setup_repo(self.tmp)
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"src/foo.py": "reviewed", "src/bar.py": "reviewed"},
            tests=None,  # omitted / empty
            features={"Alpha": "verified", "Beta": "verified"},
            rubric={"R1": "pass", "R2": "pass", "R3": "pass"},
        )

        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            result.stderr.startswith("EMPTY_TESTS"),
            f"Expected EMPTY_TESTS prefix, got: {result.stderr[:80]!r}",
        )

    # ------------------------------------------------------------------
    # Edge case: PRD feature missing from features dimension -> UNMAPPED_FEATURE
    # ------------------------------------------------------------------

    def test_unmapped_prd_feature_fails_with_feature_name(self) -> None:
        """PRD Feature 'Beta' absent from features dimension -> non-zero, UNMAPPED_FEATURE names it."""
        repo, base_sha = _setup_repo(self.tmp)
        prd = _write_prd(self.tmp, features=["Alpha", "Beta"])
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"src/foo.py": "reviewed", "src/bar.py": "reviewed"},
            tests="pytest: pass=5 fail=0 skip=0",
            features={"Alpha": "verified"},  # Beta omitted
            rubric={"R1": "pass", "R2": "pass", "R3": "pass"},
        )

        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            result.stderr.startswith("UNMAPPED_FEATURE"),
            f"Expected UNMAPPED_FEATURE prefix, got: {result.stderr[:80]!r}",
        )
        self.assertIn("Beta", result.stderr)

    # ------------------------------------------------------------------
    # Edge case: rubric rule absent from rubric dimension -> MISSING_RUBRIC_RULE
    # ------------------------------------------------------------------

    def test_missing_rubric_rule_fails_with_rule_id(self) -> None:
        """Rubric rule R3 absent from rubric dimension -> non-zero, MISSING_RUBRIC_RULE names it."""
        repo, base_sha = _setup_repo(self.tmp)
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp, rule_ids=["R1", "R2", "R3"])

        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"src/foo.py": "reviewed", "src/bar.py": "reviewed"},
            tests="pytest: pass=5 fail=0 skip=0",
            features={"Alpha": "verified", "Beta": "verified"},
            rubric={"R1": "pass", "R2": "pass"},  # R3 omitted
        )

        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            result.stderr.startswith("MISSING_RUBRIC_RULE"),
            f"Expected MISSING_RUBRIC_RULE prefix, got: {result.stderr[:80]!r}",
        )
        self.assertIn("R3", result.stderr)


    # ------------------------------------------------------------------
    # Gap 1: invalid files verdict -> MALFORMED_BLOCK
    # ------------------------------------------------------------------

    def test_invalid_files_verdict_fails_with_malformed(self) -> None:
        """files verdict 'skipped' is not in {reviewed, n/a:<reason>} -> MALFORMED_BLOCK."""
        repo, base_sha = _setup_repo(self.tmp)
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"src/foo.py": "skipped", "src/bar.py": "reviewed"},
            tests="pytest: pass=5 fail=0 skip=0",
            features={"Alpha": "verified", "Beta": "verified"},
            rubric={"R1": "pass", "R2": "pass", "R3": "pass"},
        )

        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            result.stderr.startswith("MALFORMED_BLOCK"),
            f"Expected MALFORMED_BLOCK prefix, got: {result.stderr[:80]!r}",
        )

    # ------------------------------------------------------------------
    # Gap 2: invalid rubric verdict (wrong case) -> MALFORMED_BLOCK
    # ------------------------------------------------------------------

    def test_invalid_rubric_verdict_fails_with_malformed(self) -> None:
        """rubric verdict 'FAIL' (uppercase) is not in {pass, fail} -> MALFORMED_BLOCK naming R1."""
        repo, base_sha = _setup_repo(self.tmp)
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"src/foo.py": "reviewed", "src/bar.py": "reviewed"},
            tests="pytest: pass=5 fail=0 skip=0",
            features={"Alpha": "verified", "Beta": "verified"},
            rubric={"R1": "FAIL", "R2": "pass", "R3": "pass"},
        )

        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            result.stderr.startswith("MALFORMED_BLOCK"),
            f"Expected MALFORMED_BLOCK prefix, got: {result.stderr[:80]!r}",
        )
        self.assertIn("R1", result.stderr)

    # ------------------------------------------------------------------
    # Gap 3: invalid features verdict -> MALFORMED_BLOCK
    # ------------------------------------------------------------------

    def test_invalid_features_verdict_fails_with_malformed(self) -> None:
        """features verdict 'skipped' is not in {verified, reviewed, failed} -> MALFORMED_BLOCK naming Alpha."""
        repo, base_sha = _setup_repo(self.tmp)
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"src/foo.py": "reviewed", "src/bar.py": "reviewed"},
            tests="pytest: pass=5 fail=0 skip=0",
            features={"Alpha": "skipped", "Beta": "verified"},
            rubric={"R1": "pass", "R2": "pass", "R3": "pass"},
        )

        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            result.stderr.startswith("MALFORMED_BLOCK"),
            f"Expected MALFORMED_BLOCK prefix, got: {result.stderr[:80]!r}",
        )
        self.assertIn("Alpha", result.stderr)

    # ------------------------------------------------------------------
    # Gap 4: misleading none-tests sentinel when code files are reviewed -> EMPTY_TESTS
    # ------------------------------------------------------------------

    def test_misleading_none_tests_sentinel_fails(self) -> None:
        """'none: diff touches no code' is invalid when files are marked reviewed -> EMPTY_TESTS."""
        repo, base_sha = _setup_repo(self.tmp)
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"src/foo.py": "reviewed", "src/bar.py": "reviewed"},
            tests="none: diff touches no code",
            features={"Alpha": "verified", "Beta": "verified"},
            rubric={"R1": "pass", "R2": "pass", "R3": "pass"},
        )

        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            result.stderr.startswith("EMPTY_TESTS"),
            f"Expected EMPTY_TESTS prefix, got: {result.stderr[:80]!r}",
        )

    # ------------------------------------------------------------------
    # Gap 5: block missing the tests: section header -> MALFORMED_BLOCK
    # ------------------------------------------------------------------

    def test_missing_section_header_is_malformed(self) -> None:
        """Block with valid delimiters but no 'tests:' header line -> MALFORMED_BLOCK."""
        repo, base_sha = _setup_repo(self.tmp)
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        # Write the block manually, omitting the tests: header entirely.
        block.write_text(
            "---review-coverage---\n"
            "files:\n"
            "  src/foo.py: reviewed\n"
            "  src/bar.py: reviewed\n"
            "features:\n"
            "  Alpha: verified\n"
            "  Beta: verified\n"
            "rubric:\n"
            "  R1: pass\n"
            "  R2: pass\n"
            "  R3: pass\n"
            "---end-review-coverage---\n"
        )

        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            result.stderr.startswith("MALFORMED_BLOCK"),
            f"Expected MALFORMED_BLOCK prefix, got: {result.stderr[:80]!r}",
        )


if __name__ == "__main__":
    unittest.main()
