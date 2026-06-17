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
    # Edge case: feature name containing '::' must still map -> exit 0
    # ------------------------------------------------------------------

    def test_feature_name_with_colons_maps_and_passes(self) -> None:
        """A PRD feature name containing '::' must map to its coverage entry.

        Regression: _parse_block split entry lines on the FIRST colon, so a
        feature key like 'Split update-pidash-tasks.py::main()' truncated to an
        unmatchable key with a bogus verdict and tripped the gate. Feature
        values are a colon-free enum, so the features section splits on the
        LAST colon.
        """
        repo, base_sha = _setup_repo(self.tmp)
        feature = "Split update-pidash-tasks.py::main()"
        prd = _write_prd(self.tmp, features=[feature])
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"src/foo.py": "reviewed", "src/bar.py": "reviewed"},
            tests="pytest: pass=5 fail=0 skip=0",
            features={feature: "verified"},
            rubric={"R1": "pass", "R2": "pass", "R3": "pass"},
        )

        result = _run(
            prd=prd,
            diff_range=base_sha,
            rubric=rubric,
            repo=repo,
            reviewer_blocks=[block],
        )
        self.assertEqual(
            result.returncode, 0,
            f"colon-containing feature should map; stderr: {result.stderr[:200]!r}",
        )

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

    def test_invalid_work_tree_override_fails_clean_diff_error(self) -> None:
        """A bad AUTOPILOT_GIT_WORK_TREE override must yield the clean
        DIFF_ERROR kind, not a raw OSError traceback. The plain git diff
        fails (the --repo dir is not a git repo), the bare-repo fallback is
        attempted, but the overridden work-tree does not exist -> the gate
        fails loud with DIFF_ERROR rather than crashing on cwd. DIFF_ERROR,
        not MISSING_FILES: an uncomputable diff is an infra failure, not
        evidence the reviewer skipped files."""
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
            result.stderr.startswith("DIFF_ERROR"),
            f"Expected DIFF_ERROR prefix, got: {result.stderr[:120]!r}",
        )
        self.assertNotIn("Traceback", result.stderr)

    def test_non_directory_work_tree_override_fails_clean_diff_error(self) -> None:
        """An AUTOPILOT_GIT_WORK_TREE that EXISTS but is not a directory must
        still yield the clean DIFF_ERROR kind, not a raw NotADirectoryError
        from using it as cwd. (exists() is not enough.)"""
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
            result.stderr.startswith("DIFF_ERROR"),
            f"Expected DIFF_ERROR prefix, got: {result.stderr[:120]!r}",
        )
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("NotADirectoryError", result.stderr)


# ---------------------------------------------------------------------------
# White-box layer
#
# The black-box tests above drive the CLI via subprocess and never import the
# module. The tests below import review_coverage directly to pin the internal
# Stack registry, the native-test engine's detection behavior, the pytest
# command builder's argv, and the pytest count parser (PRD: Stack registry +
# native-test engine + pytest stack). Subprocess is the only mocked boundary;
# all logic under test runs for real.
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent))
import re
import review_coverage
from unittest import mock


class StackRegistryTests(unittest.TestCase):
    """The registry is a DATA STRUCTURE listing stacks, not a chain of ifs."""

    def test_stacks_is_a_sequence_of_stack_instances(self) -> None:
        """STACKS is an enumerable tuple/sequence whose members are Stack."""
        stacks = review_coverage.STACKS
        # A data structure you can enumerate, not a function/dispatch table.
        self.assertIsInstance(stacks, (tuple, list))
        self.assertGreaterEqual(len(stacks), 1)
        for s in stacks:
            self.assertIsInstance(s, review_coverage.Stack)

    def test_pytest_stack_is_registered_with_callables(self) -> None:
        """Exactly the pytest entry ships in task 1, and its build_cmd/parse are
        the REAL implementations -- we invoke them and assert genuine output, so
        lambda placeholders (e.g. `lambda *a: "WRONG"`) cannot satisfy this."""
        by_name = {s.name: s for s in review_coverage.STACKS}
        self.assertIn("pytest", by_name)
        pytest_stack = by_name["pytest"]
        # pytest is the first registered stack (task 1); later tasks append more.
        # The exact registry membership is pinned by FullRegistryEnumerationTests.
        self.assertEqual(review_coverage.STACKS[0].name, "pytest")
        # parse: real count folding, including the no-tests None case.
        self.assertEqual(
            pytest_stack.parse("7 passed in 0.30s", 0), "pass=7 fail=0 skip=0"
        )
        self.assertEqual(
            pytest_stack.parse("3 failed, 4 passed, 1 skipped in 1s", 1),
            "pass=4 fail=3 skip=1",
        )
        self.assertIsNone(pytest_stack.parse("no tests ran in 0.01s", 5))
        # build_cmd: real scoped, quiet argv with the changed file as abs target.
        with tempfile.TemporaryDirectory() as td:
            work_tree = Path(td)
            argv = pytest_stack.build_cmd(work_tree, work_tree, ["src/test_x.py"])
            self.assertEqual(argv[0], sys.executable)
            self.assertEqual(argv[1:3], ["-m", "pytest"])
            self.assertEqual(argv[-1], "-q")
            expected_abs = str((work_tree / "src/test_x.py").resolve())
            abs_targets = argv[3:-1]
            self.assertEqual(len(abs_targets), 1)
            self.assertTrue(Path(abs_targets[0]).is_absolute())
            self.assertEqual(str(Path(abs_targets[0]).resolve()), expected_abs)

    def test_pytest_stack_markers_and_file_re(self) -> None:
        """pytest entry: markerless project files + test-file basename regex."""
        pytest_stack = {s.name: s for s in review_coverage.STACKS}["pytest"]
        self.assertEqual(
            pytest_stack.markers,
            ("pyproject.toml", "setup.py", "setup.cfg", "tox.ini"),
        )
        # file_re matches test-file basenames test_*.py and *_test.py ...
        self.assertTrue(pytest_stack.file_re.search("test_thing.py"))
        self.assertTrue(pytest_stack.file_re.search("thing_test.py"))
        # ... and not an ordinary module.
        self.assertFalse(pytest_stack.file_re.search("thing.py"))


class PytestCommandBuilderTests(unittest.TestCase):
    """_pytest_cmd builds the scoped, current argv from changed test files."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)

    def test_pytest_cmd_argv_is_scoped_quiet_form(self) -> None:
        """argv == [sys.executable, '-m', 'pytest', <abs test file>, '-q']."""
        work_tree = self.tmp / "repo"
        work_tree.mkdir()
        rel = "src/test_thing.py"
        argv = review_coverage._pytest_cmd(work_tree, work_tree, [rel])
        expected_abs = str((work_tree / rel).resolve())
        self.assertEqual(argv[0], sys.executable)
        self.assertEqual(argv[1:3], ["-m", "pytest"])
        self.assertEqual(argv[-1], "-q")
        # The changed test file is passed as an absolute path target.
        abs_targets = argv[3:-1]
        self.assertEqual(len(abs_targets), 1)
        self.assertTrue(Path(abs_targets[0]).is_absolute())
        self.assertEqual(str(Path(abs_targets[0]).resolve()), expected_abs)

    def test_pytest_cmd_preserves_multiple_changed_targets(self) -> None:
        """Each changed rel target becomes its own absolute argv entry, in order."""
        work_tree = self.tmp / "repo"
        work_tree.mkdir()
        rels = ["a/test_one.py", "b/test_two.py"]
        argv = review_coverage._pytest_cmd(work_tree, work_tree, rels)
        abs_targets = argv[3:-1]
        self.assertEqual(len(abs_targets), 2)
        resolved = [str(Path(p).resolve()) for p in abs_targets]
        self.assertEqual(
            resolved,
            [str((work_tree / r).resolve()) for r in rels],
        )


class RunCmdTimeoutTests(unittest.TestCase):
    """_run_cmd runs foreground with a FINITE timeout (no unbounded waits)."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)

    def test_run_cmd_default_timeout_is_finite_600(self) -> None:
        """Default timeout passed to subprocess.run is the finite int 600."""
        captured: dict[str, object] = {}

        def fake_run(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(
                args=args[0] if args else kwargs.get("args"),
                returncode=0,
                stdout="1 passed in 0.01s",
                stderr="",
            )

        with mock.patch.object(review_coverage.subprocess, "run", side_effect=fake_run):
            review_coverage._run_cmd(["echo", "hi"], self.tmp)

        timeout = captured["kwargs"].get("timeout")
        self.assertIsInstance(timeout, int)
        self.assertEqual(timeout, 600)

    def test_run_cmd_passes_explicit_finite_timeout(self) -> None:
        """An explicit timeout is forwarded verbatim and stays finite."""
        captured: dict[str, object] = {}

        def fake_run(*args, **kwargs):
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(
                args=args[0] if args else kwargs.get("args"),
                returncode=0, stdout="", stderr="",
            )

        with mock.patch.object(review_coverage.subprocess, "run", side_effect=fake_run):
            review_coverage._run_cmd(["echo", "hi"], self.tmp, timeout=42)

        self.assertEqual(captured["kwargs"].get("timeout"), 42)

    def test_run_cmd_returns_captured_stdout_and_returncode(self) -> None:
        """_run_cmd must RETURN the subprocess stdout (not discard it) paired
        with the returncode, and must capture text output -- so a stub that
        throws stdout away cannot pass."""
        captured: dict[str, object] = {}

        def fake_run(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(
                args=args[0] if args else kwargs.get("args"),
                returncode=7,
                stdout="MARKER 3 passed",
                stderr="",
            )

        with mock.patch.object(review_coverage.subprocess, "run", side_effect=fake_run):
            out, rc = review_coverage._run_cmd(["echo", "hi"], self.tmp)

        # The distinctive stdout must survive to the caller.
        self.assertIn("MARKER 3 passed", out)
        self.assertEqual(rc, 7)

    def test_run_cmd_captures_text_in_passed_cwd(self) -> None:
        """subprocess.run is invoked capturing text output in the given cwd."""
        captured: dict[str, object] = {}

        def fake_run(*args, **kwargs):
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(
                args=args[0] if args else kwargs.get("args"),
                returncode=0, stdout="ok", stderr="",
            )

        with mock.patch.object(review_coverage.subprocess, "run", side_effect=fake_run):
            review_coverage._run_cmd(["echo", "hi"], self.tmp)

        kwargs = captured["kwargs"]
        # Output is captured (either capture_output=True or stdout=PIPE).
        captures = kwargs.get("capture_output") is True or (
            kwargs.get("stdout") is subprocess.PIPE
        )
        self.assertTrue(captures, f"stdout not captured; kwargs={kwargs!r}")
        self.assertEqual(kwargs.get("text"), True)
        self.assertEqual(kwargs.get("cwd"), self.tmp)


class ParsePytestTests(unittest.TestCase):
    """_parse_pytest must PARSE arbitrary pytest -q summaries, not look up a
    fixed set of golden strings. We build many (P, F, S, E) summaries
    programmatically with varied clause order and whitespace, so a dict-literal
    lookup table is infeasible -- the parser has to actually count."""

    @staticmethod
    def _summary(clauses: "list[str]", tail: str) -> str:
        """Join count clauses with ', ' then append the timing tail."""
        return ", ".join(clauses) + tail

    def test_parse_counts_over_many_combinations(self) -> None:
        """For many (P, F, S, E) tuples in VARIED clause order/whitespace,
        _parse_pytest folds errors into fail and reports pass/fail/skip.

        Each tuple yields a programmatically-built summary string; a lookup
        table keyed on literal strings cannot satisfy this."""
        # (passed, failed, skipped, errors) -- includes combinations NOT in the
        # original 7 golden strings (e.g. P=9/S=4, P=10/F=2/S=3/E=1).
        cases = [
            (5, 0, 1, 0),
            (5, 3, 2, 0),
            (7, 0, 0, 0),
            (2, 0, 0, 1),
            (0, 0, 0, 3),
            (9, 0, 4, 0),
            (10, 2, 3, 1),
            (1, 1, 1, 1),
            (0, 4, 0, 0),
            (12, 0, 0, 2),
            (8, 5, 0, 0),
            (0, 0, 6, 0),
            (3, 0, 0, 0),
            (15, 7, 11, 0),
            (4, 0, 2, 5),
        ]
        for passed, failed, skipped, errors in cases:
            # Build the clause list in a non-canonical order to defeat any
            # order-sensitive shortcut: failed, passed, errors, skipped.
            clauses: list[str] = []
            if failed:
                clauses.append(f"{failed} failed")
            if passed:
                clauses.append(f"{passed} passed")
            if errors:
                noun = "error" if errors == 1 else "errors"
                clauses.append(f"{errors} {noun}")
            if skipped:
                clauses.append(f"{skipped} skipped")
            if not clauses:
                continue  # the all-zero summary is covered by the None cases
            # Vary the timing tail whitespace/precision across cases.
            tail = " in 0.12s" if (passed + failed) % 2 == 0 else " in 1s"
            summary = self._summary(clauses, tail)
            rc = 0 if (failed + errors) == 0 else 1
            expected = f"pass={passed} fail={failed + errors} skip={skipped}"
            with self.subTest(summary=summary, rc=rc):
                self.assertEqual(
                    review_coverage._parse_pytest(summary, rc), expected
                )

    def test_parse_tolerates_extra_internal_whitespace(self) -> None:
        """Irregular spacing between clauses must not change the parsed counts."""
        cases = [
            ("4 failed,  6 passed,   2 skipped in 0.5s", 1, "pass=6 fail=4 skip=2"),
            ("7 passed,1 skipped in 0.12s", 0, "pass=7 fail=0 skip=1"),
            ("11 passed,  3 errors in 0.2s", 1, "pass=11 fail=3 skip=0"),
        ]
        for summary, rc, expected in cases:
            with self.subTest(summary=summary):
                self.assertEqual(
                    review_coverage._parse_pytest(summary, rc), expected
                )

    def test_parse_zero_tests_returns_none(self) -> None:
        """pytest exit-5 'no tests ran' summary -> None (loud-fail parity)."""
        out = "no tests ran in 0.01s"
        self.assertIsNone(review_coverage._parse_pytest(out, 5))

    def test_parse_empty_output_returns_none(self) -> None:
        """No countable tokens at all -> None, not a fabricated all-zero pass."""
        self.assertIsNone(review_coverage._parse_pytest("", 5))


class RunNativeTestsDetectionTests(unittest.TestCase):
    """_run_native_tests detection: which diffs activate which stacks."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.work_tree = self.tmp / "repo"
        self.work_tree.mkdir()

    def _touch(self, rel: str) -> None:
        p = self.work_tree / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n")

    def test_non_test_py_only_diff_yields_empty(self) -> None:
        """A changed non-test .py is recognized but not a run target: returns {}
        (downstream _check_empty_tests then yields EMPTY_TESTS, not
        UNSUPPORTED_STACK -- pytest is markerless and owns .py)."""
        self._touch("src/foo.py")
        with mock.patch.object(review_coverage, "_run_cmd") as run_cmd:
            result = review_coverage._run_native_tests(["src/foo.py"], self.work_tree)
        self.assertEqual(result, {})
        run_cmd.assert_not_called()

    def test_docs_only_diff_yields_empty(self) -> None:
        """A docs/config-only diff is code-free: no stack activates, returns {}."""
        with mock.patch.object(review_coverage, "_run_cmd") as run_cmd:
            result = review_coverage._run_native_tests(
                ["docs/guide.md", "config/app.yaml", "data.json"], self.work_tree
            )
        self.assertEqual(result, {})
        run_cmd.assert_not_called()

    def test_empty_diff_yields_empty(self) -> None:
        """An empty diff activates nothing and returns {}."""
        with mock.patch.object(review_coverage, "_run_cmd") as run_cmd:
            result = review_coverage._run_native_tests([], self.work_tree)
        self.assertEqual(result, {})
        run_cmd.assert_not_called()

    def test_changed_test_file_runs_pytest_and_fills_counts(self) -> None:
        """A changed, existing test_*.py activates the pytest stack: _run_cmd is
        called once with the scoped argv and the parsed counts are returned under
        the stack name."""
        self._touch("src/test_thing.py")
        captured: dict[str, object] = {}

        def fake_run_cmd(argv, cwd, *a, **k):
            captured["argv"] = argv
            captured["cwd"] = cwd
            return ("1 passed in 0.02s", 0)

        with mock.patch.object(review_coverage, "_run_cmd", side_effect=fake_run_cmd):
            result = review_coverage._run_native_tests(
                ["src/test_thing.py"], self.work_tree
            )

        self.assertEqual(result, {"pytest": "pass=1 fail=0 skip=0"})
        argv = captured["argv"]
        self.assertEqual(argv[0], sys.executable)
        self.assertEqual(argv[1:3], ["-m", "pytest"])
        self.assertEqual(argv[-1], "-q")
        abs_target = argv[3]
        self.assertEqual(
            str(Path(abs_target).resolve()),
            str((self.work_tree / "src/test_thing.py").resolve()),
        )

    def test_changed_test_file_collecting_nothing_fails_loud(self) -> None:
        """A changed test file that pytest collects nothing from (parse -> None)
        is an activated stack producing no counts: the gate fails loud with
        EMPTY_TESTS naming the stack (design contract L175-176), NOT a silent
        omit. The net exit kind stays EMPTY_TESTS, so the single-stack outcome
        matches the prior behavior, while the message now names the stack and a
        polyglot sibling can no longer mask it."""
        self._touch("src/test_thing.py")
        import io
        import contextlib
        buf = io.StringIO()
        with mock.patch.object(
            review_coverage, "_run_cmd",
            side_effect=lambda *a, **k: ("no tests ran in 0.01s", 5),
        ):
            with contextlib.redirect_stderr(buf):
                with self.assertRaises(SystemExit) as ctx:
                    review_coverage._run_native_tests(
                        ["src/test_thing.py"], self.work_tree
                    )
        self.assertNotEqual(ctx.exception.code, 0)
        err = buf.getvalue()
        self.assertTrue(
            err.startswith("EMPTY_TESTS"),
            f"Expected EMPTY_TESTS prefix, got: {err[:120]!r}",
        )
        self.assertIn("pytest", err)

    # Genuinely-unknown languages the PRD never adds. We deliberately AVOID
    # .rs/.go/.ts/.js (those become recognized stacks in later tasks and would
    # make this test fragile). A per-extension if/else cannot cover all of them.
    _UNSUPPORTED_EXTS = (".rb", ".java", ".cpp", ".swift")

    def test_unknown_language_files_fail_unsupported_stack(self) -> None:
        """A changed code file in any genuinely-unknown language fails loud via
        _fail('UNSUPPORTED_STACK', ...): non-zero exit, no native command run.
        Parametrized over several extensions so a single `.rb` check cannot
        satisfy it."""
        for ext in self._UNSUPPORTED_EXTS:
            rel = f"src/thing{ext}"
            with self.subTest(ext=ext):
                # Fresh markerless work tree per extension.
                self.work_tree = self.tmp / f"repo{ext.replace('.', '_')}"
                self.work_tree.mkdir()
                self._touch(rel)
                with mock.patch.object(review_coverage, "_run_cmd") as run_cmd:
                    with self.assertRaises(SystemExit) as ctx:
                        review_coverage._run_native_tests([rel], self.work_tree)
                self.assertNotEqual(ctx.exception.code, 0)
                run_cmd.assert_not_called()

    def test_unsupported_stack_stderr_names_file_and_registry(self) -> None:
        """The UNSUPPORTED_STACK gap message starts with the kind, names the
        offending file, and mentions the STACKS registry -- for each unknown
        language, not just .rb."""
        import io
        import contextlib
        for ext in self._UNSUPPORTED_EXTS:
            rel = f"src/thing{ext}"
            with self.subTest(ext=ext):
                self.work_tree = self.tmp / f"errrepo{ext.replace('.', '_')}"
                self.work_tree.mkdir()
                self._touch(rel)
                buf = io.StringIO()
                with contextlib.redirect_stderr(buf):
                    with mock.patch.object(review_coverage, "_run_cmd"):
                        with self.assertRaises(SystemExit):
                            review_coverage._run_native_tests([rel], self.work_tree)
                err = buf.getvalue()
                self.assertTrue(
                    err.startswith("UNSUPPORTED_STACK"),
                    f"Expected UNSUPPORTED_STACK prefix, got: {err[:120]!r}",
                )
                self.assertIn(f"thing{ext}", err)
                self.assertIn("STACKS", err)

    def test_mixed_test_py_plus_unknown_file_fails_before_running(self) -> None:
        """A diff mixing a runnable test_*.py with one unknown-language file
        must still fail UNSUPPORTED_STACK -- the unsupported file is detected
        BEFORE any test runs, so _run_cmd is never called."""
        self._touch("src/test_thing.py")
        self._touch("src/thing.rb")
        import io
        import contextlib
        buf = io.StringIO()
        with mock.patch.object(review_coverage, "_run_cmd") as run_cmd:
            with contextlib.redirect_stderr(buf):
                with self.assertRaises(SystemExit) as ctx:
                    review_coverage._run_native_tests(
                        ["src/test_thing.py", "src/thing.rb"], self.work_tree
                    )
        self.assertNotEqual(ctx.exception.code, 0)
        err = buf.getvalue()
        self.assertTrue(
            err.startswith("UNSUPPORTED_STACK"),
            f"Expected UNSUPPORTED_STACK prefix, got: {err[:120]!r}",
        )
        self.assertIn("thing.rb", err)
        run_cmd.assert_not_called()

    def test_suffix_form_test_py_activates_pytest(self) -> None:
        """A changed *_test.py (suffix form) activates pytest -- detection must
        match the test-file regex, not merely substring-match 'test'."""
        self._touch("src/thing_test.py")
        captured: dict[str, object] = {}

        def fake_run_cmd(argv, cwd, *a, **k):
            captured["argv"] = argv
            return ("1 passed in 0.01s", 0)

        with mock.patch.object(review_coverage, "_run_cmd", side_effect=fake_run_cmd):
            result = review_coverage._run_native_tests(
                ["src/thing_test.py"], self.work_tree
            )
        self.assertEqual(result, {"pytest": "pass=1 fail=0 skip=0"})
        argv = captured["argv"]
        self.assertEqual(
            str(Path(argv[3]).resolve()),
            str((self.work_tree / "src/thing_test.py").resolve()),
        )

    def test_run_native_tests_consults_the_registry(self) -> None:
        """The engine DETECTS and RESULT-KEYS off STACKS, not a hardcoded
        'pytest'. We inject a stack named 'injected' (NOT 'pytest') that matches
        test-file basenames and activates via a real marker, then assert the
        result is keyed on the injected name with the injected parse's output.
        An engine that ignores STACKS would return {'pytest': ...} or {} here."""
        import re

        injected_stack = review_coverage.Stack(
            name="injected",
            file_re=re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.py)$"),
            markers=("pyproject.toml",),
            build_cmd=lambda wt, sd, rels: ["true"],
            parse=lambda *a, **k: "pass=1 fail=0 skip=0",
        )
        # A resolvable marker at the work_tree root activates the injected stack
        # purely by its presence in STACKS (no pytest-name special-case needed).
        (self.work_tree / "pyproject.toml").write_text("[tool]\n")
        self._touch("src/test_thing.py")

        with mock.patch.object(review_coverage, "STACKS", (injected_stack,)), \
                mock.patch.object(
                    review_coverage, "_run_cmd",
                    return_value=("ignored output", 0),
                ):
            result = review_coverage._run_native_tests(
                ["src/test_thing.py"], self.work_tree
            )

        self.assertEqual(result, {"injected": "pass=1 fail=0 skip=0"})


class NativeTestsCarveOutCliTests(unittest.TestCase):
    """End-to-end guard for the non-test-.py carve-out via the real CLI."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)

    def test_non_test_py_code_diff_under_run_tests_yields_empty_tests(self) -> None:
        """A code-only diff of NON-test .py files under --run-tests must exit
        non-zero with EMPTY_TESTS (the carve-out: pytest recognizes .py but the
        changed files are not run targets, so no real counts -> EMPTY_TESTS, NOT
        UNSUPPORTED_STACK). Drives the actual CLI like the black-box suite."""
        repo, base_sha = _setup_repo(
            self.tmp, code_files=["src/alpha.py", "src/beta.py"]
        )
        prd = _write_prd(self.tmp)
        rubric = _write_rubric(self.tmp)

        block = self.tmp / "reviewer-1.txt"
        _write_block(
            block,
            files={"src/alpha.py": "reviewed", "src/beta.py": "reviewed"},
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
            f"Expected EMPTY_TESTS prefix, got: {result.stderr[:120]!r}",
        )
        self.assertNotIn("UNSUPPORTED_STACK", result.stderr)


class CargoStackTests(unittest.TestCase):
    """The cargo (Rust) stack: registry entry, scoped argv, libtest parser, detection."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.work_tree = (self.tmp / "repo")
        self.work_tree.mkdir()
        self.work_tree = self.work_tree.resolve()

    def _touch(self, rel: str) -> None:
        p = self.work_tree / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n")

    def test_cargo_stack_is_registered_with_real_callables(self) -> None:
        """A 'cargo' entry exists; its file_re/markers/parse are the real impls."""
        by_name = {s.name: s for s in review_coverage.STACKS}
        self.assertIn("cargo", by_name)
        cargo = by_name["cargo"]
        self.assertEqual(cargo.markers, ("Cargo.toml",))
        self.assertTrue(cargo.file_re.search("src/lib.rs"))
        self.assertFalse(cargo.file_re.search("src/lib.py"))
        # parse is the genuine summing impl, not a placeholder constant.
        self.assertEqual(
            cargo.parse("test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured;", 0),
            "pass=3 fail=0 skip=0",
        )

    def test_cargo_cmd_is_manifest_scoped_and_no_fail_fast(self) -> None:
        """argv pins the changed crate via --manifest-path and runs every test."""
        scope = self.work_tree / "crates" / "core"
        scope.mkdir(parents=True)
        argv = review_coverage._cargo_cmd(self.work_tree, scope, ["crates/core/src/lib.rs"])
        self.assertEqual(argv[:2], ["cargo", "test"])
        self.assertIn("--manifest-path", argv)
        manifest = argv[argv.index("--manifest-path") + 1]
        self.assertEqual(str(Path(manifest).resolve()), str((scope / "Cargo.toml").resolve()))
        self.assertIn("--no-fail-fast", argv)

    def test_parse_cargo_single_binary(self) -> None:
        """A single libtest summary folds ignored into skip."""
        out = "test result: ok. 12 passed; 0 failed; 3 ignored; 0 measured; 0 filtered out; finished in 0.05s\n"
        self.assertEqual(review_coverage._parse_cargo(out, 0), "pass=12 fail=0 skip=3")

    def test_parse_cargo_sums_across_binaries(self) -> None:
        """Multiple test binaries each print a summary line; counts sum."""
        out = (
            "test result: ok. 4 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out;\n"
            "running 6 tests\n"
            "test result: FAILED. 5 passed; 2 failed; 0 ignored; 0 measured; 0 filtered out;\n"
        )
        self.assertEqual(review_coverage._parse_cargo(out, 101), "pass=9 fail=2 skip=1")

    def test_parse_cargo_no_summary_line_returns_none(self) -> None:
        """No libtest summary anywhere (build error, nothing ran) -> None."""
        self.assertIsNone(review_coverage._parse_cargo("error[E0432]: unresolved import\n", 101))

    def test_parse_cargo_all_zero_returns_none(self) -> None:
        """A summary with zero tests across all binaries is no-coverage -> None
        (fail-loud parity with the pytest 'no tests ran' contract)."""
        out = "test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;\n"
        self.assertIsNone(review_coverage._parse_cargo(out, 0))

    def test_rust_file_with_cargo_toml_activates_cargo(self) -> None:
        """A changed .rs with Cargo.toml above it activates only the cargo stack."""
        (self.work_tree / "Cargo.toml").write_text("[package]\nname='x'\n")
        self._touch("src/lib.rs")
        captured: dict[str, object] = {}

        def fake(argv, cwd, *a, **k):
            captured["argv"] = argv
            return ("test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured;", 0)

        with mock.patch.object(review_coverage, "_run_cmd", side_effect=fake):
            result = review_coverage._run_native_tests(["src/lib.rs"], self.work_tree)
        self.assertEqual(result, {"cargo": "pass=2 fail=0 skip=0"})
        self.assertEqual(captured["argv"][:2], ["cargo", "test"])

    def test_rust_file_without_cargo_toml_is_unsupported(self) -> None:
        """A changed .rs with NO Cargo.toml above it is a marker-requiring stack
        missing its marker -> UNSUPPORTED_STACK, no command run."""
        self._touch("src/lib.rs")
        with mock.patch.object(review_coverage, "_run_cmd") as run_cmd:
            with self.assertRaises(SystemExit) as ctx:
                review_coverage._run_native_tests(["src/lib.rs"], self.work_tree)
        self.assertNotEqual(ctx.exception.code, 0)
        run_cmd.assert_not_called()


class GoStackTests(unittest.TestCase):
    """The go (Go) stack: registry entry, package-scoped argv run from the module
    root, go test -json parser, detection, and the engine cwd=scope_dir contract."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.work_tree = (self.tmp / "repo")
        self.work_tree.mkdir()
        self.work_tree = self.work_tree.resolve()

    def _touch(self, rel: str) -> None:
        p = self.work_tree / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n")

    def test_go_stack_is_registered_with_real_callables(self) -> None:
        by_name = {s.name: s for s in review_coverage.STACKS}
        self.assertIn("go", by_name)
        go = by_name["go"]
        self.assertEqual(go.markers, ("go.mod",))
        self.assertTrue(go.file_re.search("pkg/handler.go"))
        self.assertFalse(go.file_re.search("pkg/handler.py"))
        self.assertEqual(
            go.parse('{"Action":"pass","Test":"TestX"}\n', 0), "pass=1 fail=0 skip=0"
        )

    def test_go_cmd_scopes_to_changed_packages_relative_to_module(self) -> None:
        """Each changed .go file's package dir becomes a './pkg/...' pattern
        relative to the module root (scope_dir), deduped."""
        scope = self.work_tree / "svc"
        scope.mkdir()
        argv = review_coverage._go_cmd(
            self.work_tree, scope, ["svc/handler/h.go", "svc/store/s.go", "svc/handler/h2.go"]
        )
        self.assertEqual(argv[:3], ["go", "test", "-json"])
        self.assertIn("./handler/...", argv)
        self.assertIn("./store/...", argv)
        # handler appears once despite two changed files in it.
        self.assertEqual(argv.count("./handler/..."), 1)

    def test_go_cmd_root_package_pattern(self) -> None:
        """A .go file directly in the module root yields the './...' pattern."""
        scope = self.work_tree / "svc"
        scope.mkdir()
        argv = review_coverage._go_cmd(self.work_tree, scope, ["svc/main.go"])
        self.assertEqual(argv, ["go", "test", "-json", "./..."])

    def test_parse_go_json_counts_test_level_actions_only(self) -> None:
        """pass/fail/skip on objects WITH a 'Test' key are counted; package-level
        actions (no 'Test') and run/output actions are ignored."""
        out = (
            '{"Action":"run","Test":"TestA"}\n'
            '{"Action":"output","Test":"TestA","Output":"ok\\n"}\n'
            '{"Action":"pass","Test":"TestA","Elapsed":0.01}\n'
            '{"Action":"fail","Test":"TestB"}\n'
            '{"Action":"skip","Test":"TestC"}\n'
            '{"Action":"pass","Package":"x","Elapsed":0.1}\n'   # package-level: ignored
        )
        self.assertEqual(review_coverage._parse_go_json(out, 1), "pass=1 fail=1 skip=1")

    def test_parse_go_json_tolerates_non_json_noise(self) -> None:
        """Stray non-JSON lines (build output) are skipped, not fatal."""
        out = (
            "go: downloading example.com/x v1.2.3\n"
            '{"Action":"pass","Test":"TestA"}\n'
            "FAIL\tbad line\n"
            '{"Action":"pass","Test":"TestB"}\n'
        )
        self.assertEqual(review_coverage._parse_go_json(out, 0), "pass=2 fail=0 skip=0")

    def test_parse_go_json_zero_test_actions_returns_none(self) -> None:
        """No test-level action at all (only package events / build failure) -> None."""
        out = '{"Action":"fail","Package":"x"}\nbuild failed\n'
        self.assertIsNone(review_coverage._parse_go_json(out, 2))

    def test_go_file_with_go_mod_activates_and_runs_from_module_root(self) -> None:
        """A changed .go under a nested go.mod activates the go stack; the engine
        runs the command with cwd = the module root (scope_dir), not the repo root,
        and scopes to the changed package."""
        (self.work_tree / "svc").mkdir()
        (self.work_tree / "svc" / "go.mod").write_text("module x\n")
        self._touch("svc/handler/h.go")
        captured: dict[str, object] = {}

        def fake(argv, cwd, *a, **k):
            captured["argv"] = argv
            captured["cwd"] = cwd
            return ('{"Action":"pass","Test":"TestH"}\n', 0)

        with mock.patch.object(review_coverage, "_run_cmd", side_effect=fake):
            result = review_coverage._run_native_tests(["svc/handler/h.go"], self.work_tree)
        self.assertEqual(result, {"go": "pass=1 fail=0 skip=0"})
        self.assertEqual(Path(captured["cwd"]).resolve(), (self.work_tree / "svc").resolve())
        self.assertEqual(captured["argv"], ["go", "test", "-json", "./handler/..."])

    def test_go_file_without_go_mod_is_unsupported(self) -> None:
        """A changed .go with no go.mod above it -> UNSUPPORTED_STACK, no run."""
        self._touch("pkg/thing.go")
        with mock.patch.object(review_coverage, "_run_cmd") as run_cmd:
            with self.assertRaises(SystemExit) as ctx:
                review_coverage._run_native_tests(["pkg/thing.go"], self.work_tree)
        self.assertNotEqual(ctx.exception.code, 0)
        run_cmd.assert_not_called()


class NpmStackTests(unittest.TestCase):
    """The npm (JS/TS) stack: runner detection, jest/vitest JSON + text parser,
    file-extension family, and detection."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.work_tree = (self.tmp / "repo")
        self.work_tree.mkdir()
        self.work_tree = self.work_tree.resolve()

    def _touch(self, rel: str) -> None:
        p = self.work_tree / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n")

    def _scope_with_pkg(self, body: str) -> Path:
        sd = self.tmp / "app"
        sd.mkdir()
        (sd / "package.json").write_text(body)
        return sd

    def test_npm_stack_is_registered_with_real_callables(self) -> None:
        by_name = {s.name: s for s in review_coverage.STACKS}
        self.assertIn("npm", by_name)
        npm = by_name["npm"]
        self.assertEqual(npm.markers, ("package.json",))

    def test_npm_file_re_matches_js_ts_family_not_json(self) -> None:
        """The npm file_re matches the JS/TS extension family but NOT package.json
        (a config file that must stay code-free, not activate the stack)."""
        npm = {s.name: s for s in review_coverage.STACKS}["npm"]
        for good in ("src/a.js", "a.jsx", "a.ts", "a.tsx", "a.mjs", "a.cjs", "a.mts", "a.cts"):
            self.assertTrue(npm.file_re.search(good), good)
        for bad in ("package.json", "tsconfig.json", "a.py", "a.go", "a.rs", "a.md"):
            self.assertFalse(npm.file_re.search(bad), bad)

    def test_npm_cmd_detects_vitest_json_reporter(self) -> None:
        sd = self._scope_with_pkg('{"devDependencies": {"vitest": "^1.0.0"}}')
        argv = review_coverage._npm_cmd(self.work_tree, sd, ["app/src/a.test.ts"])
        self.assertEqual(argv, ["npx", "vitest", "run", "--reporter=json"])

    def test_npm_cmd_detects_jest_json(self) -> None:
        sd = self._scope_with_pkg('{"devDependencies": {"jest": "^29.0.0"}}')
        argv = review_coverage._npm_cmd(self.work_tree, sd, ["app/a.test.js"])
        self.assertEqual(argv, ["npx", "jest", "--json"])

    def test_npm_cmd_falls_back_to_npm_test(self) -> None:
        """No vitest/jest dep -> best-effort `npm test --prefix <scope>`."""
        sd = self._scope_with_pkg('{"scripts": {"test": "mocha"}}')
        argv = review_coverage._npm_cmd(self.work_tree, sd, ["app/a.test.js"])
        self.assertEqual(argv, ["npm", "test", "--prefix", str(sd)])

    def test_parse_jest_vitest_json_report(self) -> None:
        out = '{"numTotalTests":8,"numPassedTests":5,"numFailedTests":1,"numPendingTests":2}'
        self.assertEqual(review_coverage._parse_jest_vitest(out, 1), "pass=5 fail=1 skip=2")

    def test_parse_jest_vitest_json_amid_noise(self) -> None:
        """The JSON report is extracted even with surrounding stderr/progress noise."""
        out = (
            "stderr: some progress\n"
            '{"numPassedTests":3,"numFailedTests":0,"numPendingTests":0}\n'
            "Done in 1.2s\n"
        )
        self.assertEqual(review_coverage._parse_jest_vitest(out, 0), "pass=3 fail=0 skip=0")

    def test_parse_jest_vitest_text_fallback(self) -> None:
        """When no JSON report is present, fall back to the `Tests:` summary line."""
        out = "Tests:       1 failed, 2 skipped, 5 passed, 8 total\n"
        self.assertEqual(review_coverage._parse_jest_vitest(out, 1), "pass=5 fail=1 skip=2")

    def test_parse_jest_vitest_zero_counts_returns_none(self) -> None:
        out = '{"numPassedTests":0,"numFailedTests":0,"numPendingTests":0}'
        self.assertIsNone(review_coverage._parse_jest_vitest(out, 0))

    def test_parse_jest_vitest_no_counts_returns_none(self) -> None:
        self.assertIsNone(review_coverage._parse_jest_vitest("no json, no summary line", 1))

    def test_ts_file_with_package_json_activates_npm(self) -> None:
        (self.work_tree / "package.json").write_text('{"devDependencies": {"vitest": "^1"}}')
        self._touch("src/a.test.ts")
        captured: dict[str, object] = {}

        def fake(argv, cwd, *a, **k):
            captured["argv"] = argv
            return ('{"numPassedTests":4,"numFailedTests":0,"numPendingTests":1}', 0)

        with mock.patch.object(review_coverage, "_run_cmd", side_effect=fake):
            result = review_coverage._run_native_tests(["src/a.test.ts"], self.work_tree)
        self.assertEqual(result, {"npm": "pass=4 fail=0 skip=1"})
        self.assertEqual(captured["argv"], ["npx", "vitest", "run", "--reporter=json"])

    def test_js_file_without_package_json_is_unsupported(self) -> None:
        """A changed .js with no package.json above it -> UNSUPPORTED_STACK, no run."""
        self._touch("src/app.js")
        with mock.patch.object(review_coverage, "_run_cmd") as run_cmd:
            with self.assertRaises(SystemExit) as ctx:
                review_coverage._run_native_tests(["src/app.js"], self.work_tree)
        self.assertNotEqual(ctx.exception.code, 0)
        run_cmd.assert_not_called()


class FullRegistryEnumerationTests(unittest.TestCase):
    """The registry is the single extension point: it enumerates exactly the four
    PRD stacks, and adding a stack is a pure registry append (no control-flow edit)."""

    def test_registry_enumerates_exactly_the_four_named_stacks(self) -> None:
        names = [s.name for s in review_coverage.STACKS]
        self.assertEqual(set(names), {"pytest", "cargo", "npm", "go"})
        self.assertEqual(len(names), 4)  # no duplicates
        for s in review_coverage.STACKS:
            self.assertTrue(callable(s.build_cmd))
            self.assertTrue(callable(s.parse))
            self.assertIsInstance(s.file_re, re.Pattern)
            self.assertIsInstance(s.markers, tuple)
            self.assertGreaterEqual(len(s.markers), 1)

    def test_adding_a_stack_via_registry_alone_is_detected(self) -> None:
        """PRD: prove the engine is data-driven by adding a stack purely via the
        registry. Append a synthetic Elixir stack to STACKS (NO edit to
        _run_native_tests) and assert a matching diff activates it and keys the
        result on the new stack's name -- an `if/elif` engine could not do this."""
        with tempfile.TemporaryDirectory() as td:
            work_tree = Path(td).resolve()
            (work_tree / "mix.exs").write_text("defmodule X do\nend\n")
            (work_tree / "lib").mkdir()
            (work_tree / "lib" / "thing.ex").write_text("x\n")
            elixir = review_coverage.Stack(
                name="mix",
                file_re=re.compile(r"\.ex$"),
                markers=("mix.exs",),
                build_cmd=lambda wt, sd, rels: ["mix", "test"],
                parse=lambda out, rc: "pass=2 fail=0 skip=0",
            )
            with mock.patch.object(
                review_coverage, "STACKS", review_coverage.STACKS + (elixir,)
            ), mock.patch.object(
                review_coverage, "_run_cmd", return_value=("ignored", 0)
            ):
                result = review_coverage._run_native_tests(["lib/thing.ex"], work_tree)
            self.assertEqual(result, {"mix": "pass=2 fail=0 skip=0"})


CONSOLIDATE_SCRIPT = Path(__file__).parent / "consolidate-findings.sh"


class ReworkCycle2EngineTests(unittest.TestCase):
    """Cycle-1 review rework: polyglot detection (C), per-stack fail-loud on a
    None parse (D), pytest cwd=work_tree under a sub-dir marker (G), and the
    symlinked-work_tree boundary (E)."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.work_tree = self.tmp / "repo"
        self.work_tree.mkdir()

    def _touch(self, rel: str) -> None:
        p = self.work_tree / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n")

    def test_polyglot_rust_python_activates_both_stacks(self) -> None:
        """A mixed Rust+Python diff (a .rs under Cargo.toml plus a changed
        test_*.py) activates BOTH stacks; the tests dimension is keyed per stack
        (PRD acceptance; design L235)."""
        (self.work_tree / "Cargo.toml").write_text("[package]\nname='x'\n")
        self._touch("src/lib.rs")
        self._touch("tests/test_thing.py")

        def fake(argv, cwd, *a, **k):
            if argv[0] == "cargo":
                return ("test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured;", 0)
            return ("3 passed in 0.1s", 0)

        with mock.patch.object(review_coverage, "_run_cmd", side_effect=fake):
            result = review_coverage._run_native_tests(
                ["src/lib.rs", "tests/test_thing.py"], self.work_tree
            )
        self.assertEqual(
            result, {"cargo": "pass=2 fail=0 skip=0", "pytest": "pass=3 fail=0 skip=0"}
        )

    def test_polyglot_one_stack_none_fails_loud_naming_stack(self) -> None:
        """In a polyglot diff, an activated stack whose parser returns None must
        fail loud (EMPTY_TESTS naming that stack) rather than be silently dropped
        while a sibling stack masks it green (design L175-176; the PRD's
        'never a silent green' goal)."""
        (self.work_tree / "Cargo.toml").write_text("[package]\nname='x'\n")
        self._touch("src/lib.rs")
        self._touch("tests/test_thing.py")

        def fake(argv, cwd, *a, **k):
            if argv[0] == "cargo":  # zero tests -> parser returns None
                return ("test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured;", 0)
            return ("3 passed in 0.1s", 0)

        import io
        import contextlib
        buf = io.StringIO()
        with mock.patch.object(review_coverage, "_run_cmd", side_effect=fake):
            with contextlib.redirect_stderr(buf):
                with self.assertRaises(SystemExit) as ctx:
                    review_coverage._run_native_tests(
                        ["src/lib.rs", "tests/test_thing.py"], self.work_tree
                    )
        self.assertNotEqual(ctx.exception.code, 0)
        err = buf.getvalue()
        self.assertTrue(
            err.startswith("EMPTY_TESTS"),
            f"Expected EMPTY_TESTS prefix, got: {err[:120]!r}",
        )
        self.assertIn("cargo", err)

    def test_pytest_runs_from_work_tree_even_with_subdir_marker(self) -> None:
        """pytest must run with cwd=work_tree even when a pyproject.toml sits in a
        sub-dir between the changed test file and work_tree (design L82). Running
        from the sub-dir would change pytest's rootdir/config discovery and break
        byte-for-byte parity (the PRD's hard pytest requirement)."""
        (self.work_tree / "pkg").mkdir()
        (self.work_tree / "pkg" / "pyproject.toml").write_text("[tool]\n")
        self._touch("pkg/test_thing.py")
        captured: dict[str, object] = {}

        def fake(argv, cwd, *a, **k):
            captured["cwd"] = cwd
            return ("1 passed in 0.01s", 0)

        with mock.patch.object(review_coverage, "_run_cmd", side_effect=fake):
            result = review_coverage._run_native_tests(
                ["pkg/test_thing.py"], self.work_tree
            )
        self.assertEqual(result, {"pytest": "pass=1 fail=0 skip=0"})
        self.assertEqual(
            Path(captured["cwd"]).resolve(), self.work_tree.resolve()
        )

    def test_symlinked_work_tree_does_not_escape_to_out_of_tree_marker(self) -> None:
        """When work_tree is a symlink (resolved != unresolved, e.g. macOS
        /tmp->/private or a relative --repo .), the scope walk must terminate at
        the work_tree boundary, NOT climb above it and activate a marker-requiring
        stack against an out-of-tree marker. A .rs with no in-tree Cargo.toml but
        one ABOVE the tree must fail UNSUPPORTED_STACK, never silently run cargo
        against the outer manifest (design L156; Alice's verified boundary bug)."""
        real = self.tmp / "real_tree"
        real.mkdir()
        (real / "src").mkdir()
        (real / "src" / "lib.rs").write_text("x\n")
        # Marker ABOVE the work tree (in the shared parent), out of the tree.
        (self.tmp / "Cargo.toml").write_text("[package]\nname='outer'\n")
        link = self.tmp / "link_tree"
        link.symlink_to(real)  # link.resolve() == real, so resolved != unresolved

        import io
        import contextlib
        buf = io.StringIO()
        with mock.patch.object(review_coverage, "_run_cmd") as run_cmd:
            with contextlib.redirect_stderr(buf):
                with self.assertRaises(SystemExit) as ctx:
                    review_coverage._run_native_tests(["src/lib.rs"], link)
        self.assertNotEqual(ctx.exception.code, 0)
        self.assertTrue(
            buf.getvalue().startswith("UNSUPPORTED_STACK"),
            f"Expected UNSUPPORTED_STACK prefix, got: {buf.getvalue()[:120]!r}",
        )
        run_cmd.assert_not_called()

    def test_polyglot_non_test_py_source_with_filling_sibling_fails_loud(self) -> None:
        """Doubt review (codex): a non-test .py SOURCE change activates no pytest
        run target, so in a polyglot diff a sibling stack that fills counts would
        otherwise mask the un-tested Python change green. The gate must fail loud
        (EMPTY_TESTS naming pytest) when a .py source changed but no changed test
        file ran AND another stack filled — never silently account for only the
        sibling. (Pure non-test-.py stays {} and is handled downstream; see
        test_non_test_py_only_diff_yields_empty.)"""
        (self.work_tree / "Cargo.toml").write_text("[package]\nname='x'\n")
        self._touch("src/lib.rs")
        self._touch("src/foo.py")  # non-test .py source, no test file in diff

        def fake(argv, cwd, *a, **k):
            if argv[0] == "cargo":
                return ("test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured;", 0)
            return ("", 0)

        import io
        import contextlib
        buf = io.StringIO()
        with mock.patch.object(review_coverage, "_run_cmd", side_effect=fake):
            with contextlib.redirect_stderr(buf):
                with self.assertRaises(SystemExit) as ctx:
                    review_coverage._run_native_tests(
                        ["src/lib.rs", "src/foo.py"], self.work_tree
                    )
        self.assertNotEqual(ctx.exception.code, 0)
        err = buf.getvalue()
        self.assertTrue(
            err.startswith("EMPTY_TESTS"),
            f"Expected EMPTY_TESTS prefix, got: {err[:120]!r}",
        )
        self.assertIn("pytest", err)


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
