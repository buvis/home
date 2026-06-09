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


def _setup_repo_with_test_file(
    tmp: Path, *, rel: str, body: str
) -> tuple[Path, str]:
    """
    Create a tiny two-commit repo whose single changed file is a REAL pytest
    file containing `body`. Returns (repo_path, base_sha).

    `_setup_repo` only writes a `# comment` stub, which pytest cannot run; this
    variant writes runnable test source so --run-tests can discover and run it.
    """
    repo = tmp / "repo"
    repo.mkdir()

    _git(["init"], repo)
    _git(["config", "core.autocrlf", "false"], repo)

    readme = repo / "README.md"
    readme.write_text("base\n")
    _git(["add", "README.md"], repo)
    _git(["commit", "-m", "init"], repo)
    base_sha = _git(["rev-parse", "HEAD"], repo)

    p = repo / Path(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
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
    env: dict[str, str] | None = None,
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
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


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


    # ------------------------------------------------------------------
    # Gap 6: duplicate section header -> MALFORMED_BLOCK
    # ------------------------------------------------------------------

    def test_duplicate_section_header_is_malformed(self) -> None:
        """Block with a repeated section header (two 'files:' lines) -> MALFORMED_BLOCK.
        All four required sections are present so the failure is specifically the
        duplicate, not a missing-section error."""
        repo, base_sha = _setup_repo(self.tmp)
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        block.write_text(
            "---review-coverage---\n"
            "files:\n"
            "  src/foo.py: reviewed\n"
            "files:\n"                       # duplicate header
            "  src/bar.py: reviewed\n"
            "tests:\n"
            "  pytest: pass=5 fail=0 skip=0\n"
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

    # ------------------------------------------------------------------
    # Gap 7: out-of-order sections -> MALFORMED_BLOCK
    # ------------------------------------------------------------------

    def test_out_of_order_sections_is_malformed(self) -> None:
        """Block whose sections appear out of order (tests before files; all four
        present, no duplicates) -> MALFORMED_BLOCK. The format mandates the fixed
        order: files, tests, features, rubric."""
        repo, base_sha = _setup_repo(self.tmp)
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        block.write_text(
            "---review-coverage---\n"
            "tests:\n"                       # tests before files (wrong order)
            "  pytest: pass=5 fail=0 skip=0\n"
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

    # ------------------------------------------------------------------
    # Fix 4: --write-aggregate emits a well-formed block on pass
    # ------------------------------------------------------------------

    def test_write_aggregate_emits_well_formed_block_on_pass(self) -> None:
        """--write-aggregate writes a complete block when coverage passes."""
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

        agg_path = self.tmp / "agg.txt"
        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
            extra_args=["--write-aggregate", str(agg_path)],
        )

        self.assertEqual(result.returncode, 0)
        self.assertTrue(agg_path.exists(), "aggregate file was not written")

        content = agg_path.read_text()
        self.assertIn("---review-coverage---", content)
        self.assertIn("---end-review-coverage---", content)
        for header in ("files:", "tests:", "features:", "rubric:"):
            self.assertIn(header, content)
        self.assertIn("src/foo.py", content)
        self.assertIn("src/bar.py", content)


    # ------------------------------------------------------------------
    # --run-tests contract
    # ------------------------------------------------------------------

    def test_run_tests_fills_pending_from_changed_passing_test(self) -> None:
        """--run-tests runs a changed passing test file and fills the pending
        tests dimension with real counts -> exit 0, aggregate tests line shows
        pass=N fail=N skip=N (not the pending sentinel)."""
        repo, base_sha = _setup_repo_with_test_file(
            self.tmp, rel="src/test_thing.py", body="def test_ok():\n    assert True\n"
        )
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"src/test_thing.py": "reviewed"},
            tests="pending: filled by consolidation",
            features={"Alpha": "verified", "Beta": "verified"},
            rubric={"R1": "pass", "R2": "pass", "R3": "pass"},
        )

        agg_path = self.tmp / "agg.txt"
        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
            extra_args=["--run-tests", "--write-aggregate", str(agg_path)],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(agg_path.exists(), "aggregate file was not written")
        content = agg_path.read_text()
        # The pending sentinel must have been replaced by real counts.
        self.assertNotIn("pending: filled by consolidation", content)
        self.assertRegex(content, r"pass=\d+ fail=\d+ skip=\d+")
        # One passing test -> pass=1 fail=0.
        self.assertIn("pass=1", content)
        self.assertIn("fail=0", content)

    def test_pending_only_tests_dimension_for_code_diff_fails(self) -> None:
        """Hardened completeness: code diff whose tests section is ONLY
        'pending: filled by consolidation' and no --run-tests -> EMPTY_TESTS.
        (This is the bug being fixed: pending previously passed.)"""
        repo, base_sha = _setup_repo(self.tmp)
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"src/foo.py": "reviewed", "src/bar.py": "reviewed"},
            tests="pending: filled by consolidation",
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

    def test_run_tests_with_no_changed_test_file_fails(self) -> None:
        """--run-tests with reviewed code files but NO changed test file: no
        counts can be produced -> EMPTY_TESTS."""
        repo, base_sha = _setup_repo(self.tmp)  # src/foo.py, src/bar.py: not tests
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"src/foo.py": "reviewed", "src/bar.py": "reviewed"},
            tests="pending: filled by consolidation",
            features={"Alpha": "verified", "Beta": "verified"},
            rubric={"R1": "pass", "R2": "pass", "R3": "pass"},
        )

        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
            extra_args=["--run-tests"],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            result.stderr.startswith("EMPTY_TESTS"),
            f"Expected EMPTY_TESTS prefix, got: {result.stderr[:80]!r}",
        )

    def test_run_tests_on_docs_only_diff_passes(self) -> None:
        """--run-tests on a docs-only diff with 'none: diff touches no code'
        sentinel -> exit 0 (no code to test)."""
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
            extra_args=["--run-tests"],
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_run_tests_failing_test_records_counts_and_still_passes_gate(self) -> None:
        """Coverage completeness is NOT test success: --run-tests on a changed
        FAILING test file records fail>0 and STILL exits 0 (tests were run and
        counted)."""
        repo, base_sha = _setup_repo_with_test_file(
            self.tmp, rel="src/test_thing.py", body="def test_bad():\n    assert False\n"
        )
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"src/test_thing.py": "reviewed"},
            tests="pending: filled by consolidation",
            features={"Alpha": "verified", "Beta": "verified"},
            rubric={"R1": "pass", "R2": "pass", "R3": "pass"},
        )

        agg_path = self.tmp / "agg.txt"
        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
            extra_args=["--run-tests", "--write-aggregate", str(agg_path)],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        content = agg_path.read_text()
        self.assertRegex(content, r"pass=\d+ fail=\d+ skip=\d+")
        # The failing test must be reflected as fail>0, not silently zeroed.
        self.assertNotIn("fail=0", content)
        self.assertIn("fail=1", content)

    def test_run_tests_changed_test_file_with_no_tests_fails(self) -> None:
        """--run-tests on a changed test_*.py that collects NO runnable tests
        (pytest 'no tests ran') must NOT be treated as real coverage: it yields
        EMPTY_TESTS, not a green gate with zero tests executed."""
        repo, base_sha = _setup_repo_with_test_file(
            self.tmp, rel="src/test_thing.py", body="def helper():\n    return 1\n"
        )
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"src/test_thing.py": "reviewed"},
            tests="pending: filled by consolidation",
            features={"Alpha": "verified", "Beta": "verified"},
            rubric={"R1": "pass", "R2": "pass", "R3": "pass"},
        )

        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
            extra_args=["--run-tests"],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            result.stderr.startswith("EMPTY_TESTS"),
            f"Expected EMPTY_TESTS prefix, got: {result.stderr[:80]!r}",
        )

    def test_run_tests_strips_fabricated_reviewer_counts_on_code_only_diff(self) -> None:
        """Reviewers never assert test results. Under --run-tests, a reviewer
        that FABRICATES a `pass=N fail=N skip=N` line on a code-only diff (no
        changed test file, so the consolidation run produces no real counts)
        must NOT satisfy the gate: the forged entry is discarded and the gate
        fails EMPTY_TESTS. This closes the reviewer-hearsay hole where a
        fabricated count bypassed test enforcement on a code-only diff."""
        repo, base_sha = _setup_repo(self.tmp)  # src/foo.py, src/bar.py: not tests
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"src/foo.py": "reviewed", "src/bar.py": "reviewed"},
            tests="pytest: pass=99 fail=0 skip=0",  # forged by a dishonest reviewer
            features={"Alpha": "verified", "Beta": "verified"},
            rubric={"R1": "pass", "R2": "pass", "R3": "pass"},
        )

        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
            extra_args=["--run-tests"],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            result.stderr.startswith("EMPTY_TESTS"),
            f"Expected EMPTY_TESTS prefix, got: {result.stderr[:80]!r}",
        )

    def test_invalid_work_tree_override_fails_clean_missing_files(self) -> None:
        """A bad AUTOPILOT_GIT_WORK_TREE override must yield the clean
        MISSING_FILES gap kind, not a raw OSError traceback. The plain git
        diff fails (the --repo dir is not a git repo), the bare-repo fallback
        is attempted, but the overridden work-tree does not exist -> the gate
        fails loud with MISSING_FILES rather than crashing on cwd."""
        non_repo = self.tmp / "not-a-repo"
        non_repo.mkdir()
        bare = self.tmp / "bare.git"
        _git(["init", "--bare", str(bare)], self.tmp)
        missing_work_tree = self.tmp / "does-not-exist"

        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)
        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"src/foo.py": "reviewed"},
            tests="none: diff touches no code",
            features={"Alpha": "verified", "Beta": "verified"},
            rubric={"R1": "pass", "R2": "pass", "R3": "pass"},
        )

        env = _hermetic_env()
        env.pop("GIT_DIR", None)
        env.pop("GIT_WORK_TREE", None)
        env["AUTOPILOT_GIT_DIR"] = str(bare)
        env["AUTOPILOT_GIT_WORK_TREE"] = str(missing_work_tree)

        result = _run(
            prd=prd,
            diff_range="HEAD~1..HEAD",
            rubric=rubric,
            repo=non_repo,
            reviewer_blocks=[block],
            env=env,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            result.stderr.startswith("MISSING_FILES"),
            f"Expected MISSING_FILES prefix, got: {result.stderr[:120]!r}",
        )
        self.assertNotIn("Traceback", result.stderr)

    def test_non_directory_work_tree_override_fails_clean_missing_files(self) -> None:
        """An AUTOPILOT_GIT_WORK_TREE that EXISTS but is not a directory must
        still yield the clean MISSING_FILES gap kind, not a raw
        NotADirectoryError from using it as cwd. (exists() is not enough.)"""
        non_repo = self.tmp / "not-a-repo"
        non_repo.mkdir()
        bare = self.tmp / "bare.git"
        _git(["init", "--bare", str(bare)], self.tmp)
        file_work_tree = self.tmp / "a-file"
        file_work_tree.write_text("i am a file, not a dir\n")

        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)
        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"src/foo.py": "reviewed"},
            tests="none: diff touches no code",
            features={"Alpha": "verified", "Beta": "verified"},
            rubric={"R1": "pass", "R2": "pass", "R3": "pass"},
        )

        env = _hermetic_env()
        env.pop("GIT_DIR", None)
        env.pop("GIT_WORK_TREE", None)
        env["AUTOPILOT_GIT_DIR"] = str(bare)
        env["AUTOPILOT_GIT_WORK_TREE"] = str(file_work_tree)

        result = _run(
            prd=prd,
            diff_range="HEAD~1..HEAD",
            rubric=rubric,
            repo=non_repo,
            reviewer_blocks=[block],
            env=env,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            result.stderr.startswith("MISSING_FILES"),
            f"Expected MISSING_FILES prefix, got: {result.stderr[:120]!r}",
        )
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("NotADirectoryError", result.stderr)


CONSOLIDATE_SCRIPT = Path(__file__).parent / "consolidate-findings.sh"


def _run_consolidate(
    reviewer_pairs: list[str],
    *,
    prd: "Path | None" = None,
    diff_range: "str | None" = None,
    surface: "str | None" = None,
    rubric: "Path | None" = None,
    repo: "Path | None" = None,
    write_aggregate: "Path | None" = None,
    run_tests: bool = False,
) -> "subprocess.CompletedProcess[str]":
    cmd = ["bash", str(CONSOLIDATE_SCRIPT)]
    if run_tests:
        cmd += ["--run-tests"]
    if prd is not None:
        cmd += ["--prd", str(prd)]
    if diff_range is not None:
        cmd += ["--diff-range", diff_range]
    if surface is not None:
        cmd += ["--surface", surface]
    if rubric is not None:
        cmd += ["--rubric", str(rubric)]
    if repo is not None:
        cmd += ["--repo", str(repo)]
    if write_aggregate is not None:
        cmd += ["--write-aggregate", str(write_aggregate)]
    cmd.extend(reviewer_pairs)
    return subprocess.run(cmd, capture_output=True, text=True)


class TestConsolidateFindingsCoverage(unittest.TestCase):
    """Tests for the coverage-gate wiring in consolidate-findings.sh."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)

    def test_exits_zero_on_complete_coverage_block(self) -> None:
        """Complete block embedded in reviewer output with coverage args -> exit 0."""
        repo, base_sha = _setup_repo(self.tmp)
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)
        out = self.tmp / "rev.txt"
        out.write_text(
            "[ALICE] 🟡 Minor | File: src/foo.py | Task: T1\n\n"
            "---review-coverage---\n"
            "files:\n  src/foo.py: reviewed\n  src/bar.py: reviewed\n"
            "tests:\n  pytest: pass=3 fail=0 skip=0\n"
            "features:\n  Alpha: verified\n  Beta: verified\n"
            "rubric:\n  R1: pass\n  R2: pass\n  R3: pass\n"
            "---end-review-coverage---\n"
        )
        result = _run_consolidate(
            [f"ALICE:{out}"],
            prd=prd, diff_range=base_sha, surface="work-completion", rubric=rubric, repo=repo,
        )
        self.assertEqual(result.returncode, 0)

    def test_exits_nonzero_when_reviewer_has_no_block(self) -> None:
        """Reviewer output with no coverage block and coverage args -> exit non-zero."""
        repo, base_sha = _setup_repo(self.tmp)
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)
        out = self.tmp / "rev.txt"
        out.write_text("[ALICE] 🟡 Minor | File: src/foo.py | Task: T1\n")
        result = _run_consolidate(
            [f"ALICE:{out}"],
            prd=prd, diff_range=base_sha, surface="work-completion", rubric=rubric, repo=repo,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_exits_nonzero_on_incomplete_block_missing_feature(self) -> None:
        """Block missing PRD feature 'Beta' -> exit non-zero."""
        repo, base_sha = _setup_repo(self.tmp)
        prd = _write_prd(self.tmp, features=["Alpha", "Beta"])
        rubric = _write_rubric(self.tmp)
        out = self.tmp / "rev.txt"
        out.write_text(
            "---review-coverage---\n"
            "files:\n  src/foo.py: reviewed\n  src/bar.py: reviewed\n"
            "tests:\n  pytest: pass=3 fail=0 skip=0\n"
            "features:\n  Alpha: verified\n"  # Beta omitted
            "rubric:\n  R1: pass\n  R2: pass\n  R3: pass\n"
            "---end-review-coverage---\n"
        )
        result = _run_consolidate(
            [f"ALICE:{out}"],
            prd=prd, diff_range=base_sha, surface="work-completion", rubric=rubric, repo=repo,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_writes_aggregate_file_on_pass(self) -> None:
        """--write-aggregate + complete block -> aggregate file with coverage delimiters."""
        repo, base_sha = _setup_repo(self.tmp)
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)
        out = self.tmp / "rev.txt"
        agg = self.tmp / "agg.txt"
        out.write_text(
            "---review-coverage---\n"
            "files:\n  src/foo.py: reviewed\n  src/bar.py: reviewed\n"
            "tests:\n  pytest: pass=3 fail=0 skip=0\n"
            "features:\n  Alpha: verified\n  Beta: verified\n"
            "rubric:\n  R1: pass\n  R2: pass\n  R3: pass\n"
            "---end-review-coverage---\n"
        )
        result = _run_consolidate(
            [f"ALICE:{out}"],
            prd=prd, diff_range=base_sha, surface="work-completion",
            rubric=rubric, repo=repo, write_aggregate=agg,
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue(agg.exists(), "aggregate file not written")
        content = agg.read_text()
        self.assertIn("---review-coverage---", content)
        self.assertIn("---end-review-coverage---", content)

    def test_run_tests_passthrough_fills_pending_block(self) -> None:
        """consolidate-findings.sh forwards --run-tests: a reviewer output whose
        tests section is 'pending: filled by consolidation' with a changed
        passing test file in the diff -> exit 0 (gate filled real counts)."""
        repo, base_sha = _setup_repo_with_test_file(
            self.tmp, rel="src/test_thing.py", body="def test_ok():\n    assert True\n"
        )
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)
        out = self.tmp / "rev.txt"
        out.write_text(
            "---review-coverage---\n"
            "files:\n  src/test_thing.py: reviewed\n"
            "tests:\n  pending: filled by consolidation\n"
            "features:\n  Alpha: verified\n  Beta: verified\n"
            "rubric:\n  R1: pass\n  R2: pass\n  R3: pass\n"
            "---end-review-coverage---\n"
        )
        result = _run_consolidate(
            [f"ALICE:{out}"],
            prd=prd, diff_range=base_sha, surface="work-completion",
            rubric=rubric, repo=repo, run_tests=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_backwards_compat_without_coverage_args(self) -> None:
        """Without coverage args, exits 0 regardless of reviewer content."""
        out = self.tmp / "rev.txt"
        out.write_text("[ALICE] 🟡 Minor | File: src/foo.py | Task: T1\n")
        result = _run_consolidate([f"ALICE:{out}"])
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
