"""Tests for review_coverage_hook.py.

Pins the public API of the hook that blocks session exit when the just-completed
review surface's saved review file lacks a complete coverage block.

Stdlib-only unittest. Imports the module directly via importlib (no subprocess).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOOK_PATH = Path(__file__).parent / "review_coverage_hook.py"

# Ensure _walk_up is importable (same dir as the hook).
_scripts_dir = str(Path(__file__).parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "review_coverage_hook_under_test", HOOK_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load_module()


class SurfaceForPhaseTests(unittest.TestCase):
    def test_surface_mapping_each_phase(self) -> None:
        self.assertEqual(hook.surface_for_phase("blind-review"), "work-completion")
        self.assertEqual(hook.surface_for_phase("doubt-review"), "blindly")
        self.assertEqual(hook.surface_for_phase("done"), "doubt")

    def test_surface_mapping_non_review_phase_is_none(self) -> None:
        self.assertIsNone(hook.surface_for_phase("planning"))
        self.assertIsNone(hook.surface_for_phase("work"))
        self.assertIsNone(hook.surface_for_phase("review"))


class ReviewFileForTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.reviews_dir = Path(self.tmp.name)

    def test_review_file_for_blindly_and_doubt(self) -> None:
        self.assertEqual(
            hook.review_file_for("blindly", "P", self.reviews_dir),
            self.reviews_dir / "P-blind-review.md",
        )
        self.assertEqual(
            hook.review_file_for("doubt", "P", self.reviews_dir),
            self.reviews_dir / "P-doubt-review.md",
        )

    def test_review_file_for_work_completion_picks_highest_nn(self) -> None:
        (self.reviews_dir / "P-review-1.md").write_text("r1")
        (self.reviews_dir / "P-review-2.md").write_text("r2")
        (self.reviews_dir / "P-review-10.md").write_text("r10")

        result = hook.review_file_for("work-completion", "P", self.reviews_dir)

        # Must use integer comparison (10 > 2), not lexical (which would pick 2).
        self.assertEqual(result, self.reviews_dir / "P-review-10.md")

    def test_review_file_for_work_completion_returns_none_when_no_files(self) -> None:
        result = hook.review_file_for("work-completion", "P", self.reviews_dir)
        self.assertIsNone(result)


class DeleteSignalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.autopilot_dir = Path(self.tmp.name)

    def test_delete_signal_removes_file(self) -> None:
        signal_file = self.autopilot_dir / "signal"
        signal_file.write_text("next\n")

        hook.delete_signal(self.autopilot_dir)

        self.assertFalse(signal_file.exists())

    def test_delete_signal_absent_does_not_raise(self) -> None:
        # signal already absent — must be best-effort, no exception.
        hook.delete_signal(self.autopilot_dir)


def _make_autopilot_dir(
    root: Path,
    phase: str,
    prd: str = "X.md",
    work_start_sha: str = "abc",
    write_signal: bool = True,
) -> Path:
    """Build a minimal dev/local/autopilot dir tree under root."""
    autopilot_dir = root / "dev" / "local" / "autopilot"
    autopilot_dir.mkdir(parents=True, exist_ok=True)
    state = {"phase": phase, "prd": prd, "work_start_sha": work_start_sha}
    (autopilot_dir / "state.json").write_text(json.dumps(state))
    if write_signal:
        (autopilot_dir / "signal").write_text("next\n")
    return autopilot_dir


class MainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # repo root is tmp; autopilot dir is repo/dev/local/autopilot
        # so repo = autopilot_dir.parents[2]
        self.repo = Path(self.tmp.name)
        # The hook only gates inside the autopilot shell loop; mark these
        # tests as loop-wrapped so they exercise the gate logic.
        loop_env = mock.patch.dict(os.environ, {"_AUTOPILOT_LOOP": "1"})
        loop_env.start()
        self.addCleanup(loop_env.stop)

    def _make_reviews_dir(self) -> Path:
        reviews = self.repo / "dev" / "local" / "reviews"
        reviews.mkdir(parents=True, exist_ok=True)
        return reviews

    def test_main_blocks_and_deletes_signal_on_gate_failure(self) -> None:
        autopilot_dir = _make_autopilot_dir(
            self.repo, phase="blind-review", prd="X.md", work_start_sha="abc"
        )
        reviews_dir = self._make_reviews_dir()
        # Create the review file that main() will discover.
        (reviews_dir / "X-review-1.md").write_text("review content")

        signal_file = autopilot_dir / "signal"
        self.assertTrue(signal_file.exists())

        with mock.patch.object(
            hook, "find_autopilot_dir", return_value=autopilot_dir
        ), mock.patch.object(
            hook, "run_gate", return_value=(2, "MISSING_FILES foo.py")
        ):
            result = hook.main()

        self.assertEqual(result, 2)
        self.assertFalse(signal_file.exists())

    def test_main_exit0_outside_loop_without_gating(self) -> None:
        # Footgun fix: outside the autopilot shell loop ($_AUTOPILOT_LOOP unset)
        # the hook must never block exit, even when state.json is parked in a
        # review phase. It must not resolve the autopilot dir or run the gate —
        # a leftover review-phase state must not deadlock unrelated sessions
        # that merely share the cwd tree.
        autopilot_dir = _make_autopilot_dir(
            self.repo, phase="blind-review", prd="X.md", work_start_sha="abc"
        )
        signal_file = autopilot_dir / "signal"
        self.assertTrue(signal_file.exists())

        def _must_not_be_called(*args, **kwargs):
            raise AssertionError("hook must not act outside the autopilot loop")

        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            hook, "find_autopilot_dir", side_effect=_must_not_be_called
        ), mock.patch.object(hook, "run_gate", side_effect=_must_not_be_called):
            result = hook.main()

        self.assertEqual(result, 0)
        # signal left intact — no handoff was gated
        self.assertTrue(signal_file.exists())

    def test_main_exit0_on_non_review_phase(self) -> None:
        autopilot_dir = _make_autopilot_dir(self.repo, phase="planning")
        signal_file = autopilot_dir / "signal"

        def _fail_if_called(*args, **kwargs):
            raise AssertionError("run_gate must NOT be called for non-review phases")

        with mock.patch.object(
            hook, "find_autopilot_dir", return_value=autopilot_dir
        ), mock.patch.object(hook, "run_gate", side_effect=_fail_if_called):
            result = hook.main()

        self.assertEqual(result, 0)
        # signal must remain untouched
        self.assertTrue(signal_file.exists())

    def test_main_exit0_when_gate_passes(self) -> None:
        # phase "doubt-review" means the blind review just finished -> blindly
        # surface -> <prd>-blind-review.md.
        autopilot_dir = _make_autopilot_dir(
            self.repo, phase="doubt-review", prd="Y.md", write_signal=True
        )
        reviews_dir = self._make_reviews_dir()
        (reviews_dir / "Y-blind-review.md").write_text("blind review content")

        signal_file = autopilot_dir / "signal"

        with mock.patch.object(
            hook, "find_autopilot_dir", return_value=autopilot_dir
        ), mock.patch.object(hook, "run_gate", return_value=(0, "")):
            result = hook.main()

        self.assertEqual(result, 0)
        # signal must be untouched when gate passes
        self.assertTrue(signal_file.exists())


class RunGateTests(unittest.TestCase):
    def test_run_gate_invokes_subprocess_and_returns_code(self) -> None:
        import types

        fake_result = types.SimpleNamespace(returncode=2, stderr="MALFORMED_BLOCK detail\n")
        with mock.patch.object(hook.subprocess, "run", return_value=fake_result) as patched:
            code, msg = hook.run_gate(
                Path("/tmp/rev.md"),
                "doubt",
                Path("/tmp/prd.md"),
                "abc..HEAD",
                Path("/repo"),
            )

        self.assertEqual(code, 2)
        self.assertEqual(msg, "MALFORMED_BLOCK detail")

        # Verify subprocess.run was actually called with a list as first arg.
        patched.assert_called_once()
        argv = patched.call_args[0][0]
        self.assertIsInstance(argv, list)

        # Key flags and values must appear in the argv list.
        self.assertIn("--surface", argv)
        self.assertIn("doubt", argv)
        self.assertIn("--reviewer-block", argv)
        self.assertIn("/tmp/rev.md", argv)
        self.assertTrue(
            any(elem.endswith("review_coverage.py") for elem in argv),
            msg=f"No element ending with 'review_coverage.py' found in argv: {argv}",
        )


class MainPassesCorrectReviewFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        # The hook only gates inside the autopilot shell loop; mark these
        # tests as loop-wrapped so they exercise the gate logic.
        loop_env = mock.patch.dict(os.environ, {"_AUTOPILOT_LOOP": "1"})
        loop_env.start()
        self.addCleanup(loop_env.stop)

    def _make_reviews_dir(self) -> Path:
        reviews = self.repo / "dev" / "local" / "reviews"
        reviews.mkdir(parents=True, exist_ok=True)
        return reviews

    def test_main_passes_resolved_review_file_to_gate(self) -> None:
        # phase "done" means the doubt review just finished -> doubt surface
        # -> <prd>-doubt-review.md.
        autopilot_dir = _make_autopilot_dir(
            self.repo, phase="done", prd="Y.md", write_signal=True
        )
        reviews_dir = self._make_reviews_dir()
        expected_review_file = reviews_dir / "Y-doubt-review.md"
        expected_review_file.write_text("doubt review content")

        gate_mock = mock.MagicMock(return_value=(0, ""))

        with mock.patch.object(
            hook, "find_autopilot_dir", return_value=autopilot_dir
        ), mock.patch.object(hook, "run_gate", gate_mock):
            hook.main()

        gate_mock.assert_called_once()
        # First positional argument must be the resolved review file path.
        actual_review_file = gate_mock.call_args[0][0]
        self.assertEqual(Path(actual_review_file), expected_review_file)


class MainBlocksCleanlyWhenPrdMissingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        # The hook only gates inside the autopilot shell loop; mark these
        # tests as loop-wrapped so they exercise the gate logic.
        loop_env = mock.patch.dict(os.environ, {"_AUTOPILOT_LOOP": "1"})
        loop_env.start()
        self.addCleanup(loop_env.stop)

    def _make_reviews_dir(self) -> Path:
        reviews = self.repo / "dev" / "local" / "reviews"
        reviews.mkdir(parents=True, exist_ok=True)
        return reviews

    def test_main_blocks_cleanly_when_prd_file_missing(self) -> None:
        """main() returns 2, deletes the signal, and writes a clear stderr
        message naming the missing PRD - no Python traceback - when the PRD
        file exists in neither prds/wip/ nor prds/done/."""
        import contextlib
        import io

        autopilot_dir = _make_autopilot_dir(
            self.repo, phase="blind-review", prd="missing.md", write_signal=True
        )
        reviews_dir = self._make_reviews_dir()
        # Create the review file so the review-file check passes.
        (reviews_dir / "missing-review-1.md").write_text("review content")
        # Deliberately create NO PRD file in prds/wip/ or prds/done/.

        signal_file = autopilot_dir / "signal"
        self.assertTrue(signal_file.exists())

        buf = io.StringIO()
        with mock.patch.object(
            hook, "find_autopilot_dir", return_value=autopilot_dir
        ):
            with contextlib.redirect_stderr(buf):
                result = hook.main()

        stderr_output = buf.getvalue()
        self.assertEqual(result, 2)
        self.assertFalse(signal_file.exists(), "signal must be deleted even when PRD is missing")
        self.assertNotIn("Traceback", stderr_output, "must not expose a Python traceback")
        self.assertIn("missing.md", stderr_output, "stderr must name the missing PRD file")


class DeleteSignalLogsLoudlyOnOsErrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.autopilot_dir = Path(self.tmp.name)

    def test_delete_signal_logs_loudly_on_oserror(self) -> None:
        """delete_signal must not raise when unlink fails, and must write a
        warning to stderr so the failure is never silently swallowed."""
        import contextlib
        import io

        # Create a non-empty directory named 'signal'; unlink on a directory
        # raises OSError, giving us a deterministic failure path.
        signal_dir = self.autopilot_dir / "signal"
        signal_dir.mkdir()
        (signal_dir / "dummy").write_text("non-empty")

        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            # Must not raise.
            hook.delete_signal(self.autopilot_dir)

        self.assertGreater(len(buf.getvalue()), 0, "stderr must contain a warning on OSError")


class MainBlocksWhenReviewFileMissingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        # The hook only gates inside the autopilot shell loop; mark these
        # tests as loop-wrapped so they exercise the gate logic.
        loop_env = mock.patch.dict(os.environ, {"_AUTOPILOT_LOOP": "1"})
        loop_env.start()
        self.addCleanup(loop_env.stop)

    def test_main_blocks_when_review_file_missing(self) -> None:
        autopilot_dir = _make_autopilot_dir(
            self.repo, phase="doubt-review", prd="Z.md", write_signal=True
        )
        # reviews dir exists but Z-doubt-review.md is NOT created.
        reviews_dir = self.repo / "dev" / "local" / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)

        signal_file = autopilot_dir / "signal"
        self.assertTrue(signal_file.exists())

        def _gate_must_not_be_called(*args, **kwargs):
            raise AssertionError("run_gate must NOT be called when review file is missing")

        with mock.patch.object(
            hook, "find_autopilot_dir", return_value=autopilot_dir
        ), mock.patch.object(hook, "run_gate", side_effect=_gate_must_not_be_called):
            result = hook.main()

        self.assertEqual(result, 2)
        self.assertFalse(signal_file.exists(), "signal file must be deleted when review file is missing")


# ---------------------------------------------------------------------------
# REAL integration tests of review_coverage.py (no mocks of run_gate / git).
#
# These exercise the hook -> gate -> git path end to end via subprocess against
# real temp git repos, pinning PRD 00038 [D1]: the gate must resolve changed
# files when the project root is a bare-repo work-tree (git data in a separate
# dir), where plain `git -C <root> diff` fails.
# ---------------------------------------------------------------------------

import os
import subprocess


GATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "review-work-completion"
    / "scripts"
    / "review_coverage.py"
)
WORK_COMPLETION_RUBRIC = (
    Path(__file__).resolve().parents[2]
    / "review-work-completion"
    / "references"
    / "rubric.md"
)


def _git(args: list[str], cwd: str | None = None, env: dict | None = None) -> None:
    """Run a git command, raising with captured output on failure."""
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True,
                   capture_output=True, text=True)


def _rubric_rule_ids(rubric_path: Path) -> list[str]:
    """Extract the R<n> rule IDs from the real work-completion rubric."""
    import re

    ids = []
    for line in rubric_path.read_text().splitlines():
        m = re.match(r"^(R\d+):", line)
        if m:
            ids.append(m.group(1))
    return ids


def _coverage_block(files: list[str], rubric_ids: list[str], feature: str) -> str:
    """Build a complete ---review-coverage--- block covering the given inputs."""
    lines = ["---review-coverage---", "files:"]
    for f in files:
        lines.append(f"  {f}: reviewed")
    lines.append("tests:")
    lines.append("  tests/test_x.py: pass=1 fail=0 skip=0")
    lines.append("features:")
    lines.append(f"  {feature}: verified")
    lines.append("rubric:")
    for rid in rubric_ids:
        lines.append(f"  {rid}: pass")
    lines.append("---end-review-coverage---")
    return "\n".join(lines) + "\n"


class ReviewCoverageGitIntegrationTests(unittest.TestCase):
    """End-to-end subprocess tests against real git repos. No mocks."""

    def setUp(self) -> None:
        self.rubric_ids = _rubric_rule_ids(WORK_COMPLETION_RUBRIC)
        self.assertTrue(self.rubric_ids, "real rubric must yield rule IDs")
        self.feature = "Example feature"

    def _write_prd(self, root: Path) -> Path:
        prd = root / "prd.md"
        prd.write_text(f"# PRD\n\n#### Feature: {self.feature}\n\nbody\n")
        return prd

    def _run_gate(self, repo: Path, diff_range: str, prd: Path,
                  review: Path, env: dict | None = None) -> subprocess.CompletedProcess:
        argv = [
            sys.executable, str(GATE_PATH),
            "--surface", "work-completion",
            "--prd", str(prd),
            "--diff-range", diff_range,
            "--reviewer-block", str(review),
            "--rubric", str(WORK_COMPLETION_RUBRIC),
            "--repo", str(repo),
        ]
        return subprocess.run(argv, capture_output=True, text=True, env=env)

    def _normal_repo_with_range(self) -> tuple[Path, str, list[str]]:
        """Build a plain git repo with a 2-commit range; return (root, range, files)."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        _git(["init"], cwd=str(root))
        _git(["config", "user.name", "Tess"], cwd=str(root))
        _git(["config", "user.email", "tess@example.com"], cwd=str(root))

        (root / "alpha.py").write_text("x = 1\n")
        (root / "beta.py").write_text("y = 2\n")
        _git(["add", "alpha.py", "beta.py"], cwd=str(root))
        _git(["commit", "-m", "init"], cwd=str(root))
        base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root),
                              capture_output=True, text=True).stdout.strip()

        (root / "alpha.py").write_text("x = 2\n")
        (root / "beta.py").write_text("y = 3\n")
        _git(["commit", "-am", "change"], cwd=str(root))
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root),
                             capture_output=True, text=True).stdout.strip()

        diff_range = f"{base}..{head}"
        changed = subprocess.run(
            ["git", "diff", "--name-only", diff_range], cwd=str(root),
            capture_output=True, text=True,
        ).stdout.split()
        self.assertEqual(sorted(changed), ["alpha.py", "beta.py"])
        return root, diff_range, changed

    def test_complete_coverage_passes_on_normal_repo(self) -> None:
        """Regression: a plain git repo with full coverage exits 0."""
        root, diff_range, changed = self._normal_repo_with_range()
        prd = self._write_prd(root)
        review = root / "review.md"
        review.write_text(_coverage_block(changed, self.rubric_ids, self.feature))

        result = self._run_gate(root, diff_range, prd, review)

        self.assertEqual(result.returncode, 0,
                         msg=f"stderr: {result.stderr}")

    def test_missing_file_in_block_fails_missing_files(self) -> None:
        """Dropping a changed file from the block yields MISSING_FILES."""
        root, diff_range, changed = self._normal_repo_with_range()
        prd = self._write_prd(root)
        review = root / "review.md"
        # Cover only the first changed file; omit the rest.
        review.write_text(
            _coverage_block(changed[:1], self.rubric_ids, self.feature)
        )

        result = self._run_gate(root, diff_range, prd, review)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MISSING_FILES", result.stderr)
        for omitted in changed[1:]:
            self.assertIn(omitted, result.stderr)

    def test_bare_repo_worktree_resolves_changed_files(self) -> None:
        """Bare-repo work-tree (no .git in root) must still resolve changed files.

        Reproduces PRD 00038 [D1] faithfully: git data lives in a separate bare
        dir and the work-tree root has NO .git link and NO standard GIT_DIR in
        the gate's environment, so plain `git -C <root> diff` fails with 'Not a
        git repository' — exactly the real ~/.buvis-backed .claude condition.

        The gate must fall back to the documented bare-repo-home convention. That
        fallback location defaults to ~/.buvis + $HOME in production but is
        overridable for tests via AUTOPILOT_GIT_DIR / AUTOPILOT_GIT_WORK_TREE.
        Standard GIT_DIR/GIT_WORK_TREE are deliberately cleared from the gate env
        so this test exercises the fix's own resolution logic, not native git.
        """
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base_dir = Path(tmp.name)
        worktree = base_dir / "home"
        gitdir = base_dir / "repo.git"
        worktree.mkdir()
        _git(["init", "--bare", str(gitdir)])

        env = dict(os.environ)
        env["GIT_DIR"] = str(gitdir)
        env["GIT_WORK_TREE"] = str(worktree)
        _git(["config", "user.name", "Tess"], env=env)
        _git(["config", "user.email", "tess@example.com"], env=env)

        (worktree / "gamma.py").write_text("a = 1\n")
        _git(["add", "gamma.py"], env=env)
        _git(["commit", "-m", "init"], env=env)
        base = subprocess.run(["git", "rev-parse", "HEAD"], env=env,
                              capture_output=True, text=True).stdout.strip()

        (worktree / "gamma.py").write_text("a = 2\n")
        _git(["commit", "-am", "change"], env=env)
        head = subprocess.run(["git", "rev-parse", "HEAD"], env=env,
                             capture_output=True, text=True).stdout.strip()
        diff_range = f"{base}..{head}"

        # Sanity: prove plain `git -C <worktree>` fails here (the bug condition).
        plain = subprocess.run(
            ["git", "-C", str(worktree), "diff", "--name-only", diff_range],
            capture_output=True, text=True,
        )
        self.assertNotEqual(
            plain.returncode, 0,
            "precondition: plain git diff from work-tree cwd must fail",
        )

        prd = self._write_prd(worktree)
        review = worktree / "review.md"
        review.write_text(
            _coverage_block(["gamma.py"], self.rubric_ids, self.feature)
        )

        # Gate env: NO standard GIT_DIR/GIT_WORK_TREE (so native git can't
        # short-circuit), only the autopilot fallback override pointing at the
        # test's bare repo. This is what the real fix must honor.
        gate_env = dict(os.environ)
        gate_env.pop("GIT_DIR", None)
        gate_env.pop("GIT_WORK_TREE", None)
        gate_env["AUTOPILOT_GIT_DIR"] = str(gitdir)
        gate_env["AUTOPILOT_GIT_WORK_TREE"] = str(worktree)

        result = self._run_gate(worktree, diff_range, prd, review, env=gate_env)

        self.assertEqual(
            result.returncode, 0,
            msg=("gate must resolve changed files via the bare-repo-home "
                 f"fallback; stderr: {result.stderr}"),
        )
        self.assertNotIn("MISSING_FILES", result.stderr)


class RunGateHookIntegrationTests(unittest.TestCase):
    """Drive the REAL review_coverage_hook.run_gate() against a real bare repo.

    Closes the residual half of cycle-1's [2/2] "hook->gate->git path never
    tested" finding: the gate-level integration test exercised review_coverage.py
    directly, never the hook's own invocation of the real gate. These tests call
    hook.run_gate() (no mock) so the hook -> subprocess(review_coverage.py) ->
    bare-repo git resolution path — the exact cycle-1 production deadlock path —
    is executed end to end. They would fail if review_coverage.py's bare-repo
    _diff_files fallback regressed.
    """

    def setUp(self) -> None:
        self.rubric_ids = _rubric_rule_ids(WORK_COMPLETION_RUBRIC)
        self.assertTrue(self.rubric_ids, "real rubric must yield rule IDs")
        self.feature = "Example feature"

    def _bare_repo_worktree(self) -> tuple[Path, Path, str]:
        """Build a bare git dir + work-tree with a 2-commit range touching
        gamma.py. Returns (gitdir, worktree, diff_range). The work-tree has no
        .git link, so plain `git -C <worktree>` fails — the hook's gate must use
        the AUTOPILOT_GIT_DIR/WORK_TREE fallback to resolve the diff."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base_dir = Path(tmp.name)
        worktree = base_dir / "home"
        gitdir = base_dir / "repo.git"
        worktree.mkdir()
        _git(["init", "--bare", str(gitdir)])

        env = dict(os.environ)
        env["GIT_DIR"] = str(gitdir)
        env["GIT_WORK_TREE"] = str(worktree)
        _git(["config", "user.name", "Tess"], env=env)
        _git(["config", "user.email", "tess@example.com"], env=env)

        (worktree / "gamma.py").write_text("a = 1\n")
        _git(["add", "gamma.py"], env=env)
        _git(["commit", "-m", "init"], env=env)
        base = subprocess.run(["git", "rev-parse", "HEAD"], env=env,
                              capture_output=True, text=True).stdout.strip()
        (worktree / "gamma.py").write_text("a = 2\n")
        _git(["commit", "-am", "change"], env=env)
        head = subprocess.run(["git", "rev-parse", "HEAD"], env=env,
                             capture_output=True, text=True).stdout.strip()
        return gitdir, worktree, f"{base}..{head}"

    def _write_prd(self, root: Path) -> Path:
        prd = root / "prd.md"
        prd.write_text(f"# PRD\n\n#### Feature: {self.feature}\n\nbody\n")
        return prd

    def _gate_env(self, gitdir: Path, worktree: Path) -> dict[str, str]:
        """os.environ minus standard GIT_DIR/GIT_WORK_TREE (so native git can't
        short-circuit) plus only the autopilot bare-repo override."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("GIT_DIR", "GIT_WORK_TREE")}
        env["AUTOPILOT_GIT_DIR"] = str(gitdir)
        env["AUTOPILOT_GIT_WORK_TREE"] = str(worktree)
        return env

    def test_run_gate_passes_through_hook_against_bare_repo(self) -> None:
        """Complete coverage: hook.run_gate -> real gate -> bare-repo fallback
        resolves gamma.py and the block covers it -> exit 0. This only passes if
        the hook actually drives the real gate and the bare-repo fallback works."""
        gitdir, worktree, diff_range = self._bare_repo_worktree()
        prd = self._write_prd(worktree)
        # run_gate writes its aggregate under <repo>/dev/local/reviews/.
        (worktree / "dev" / "local" / "reviews").mkdir(parents=True)
        review = worktree / "review.md"
        review.write_text(_coverage_block(["gamma.py"], self.rubric_ids, self.feature))

        with mock.patch.dict(os.environ, self._gate_env(gitdir, worktree), clear=True):
            code, msg = hook.run_gate(
                review, "work-completion", prd, diff_range, worktree
            )

        self.assertEqual(code, 0, msg=f"hook.run_gate gap: {msg}")

    def test_run_gate_reports_gap_through_hook_against_bare_repo(self) -> None:
        """Incomplete coverage: the block omits the changed gamma.py. The hook's
        real gate must resolve gamma.py via the bare-repo fallback and fail
        MISSING_FILES naming it (proving resolution happened, not a git error)."""
        gitdir, worktree, diff_range = self._bare_repo_worktree()
        prd = self._write_prd(worktree)
        (worktree / "dev" / "local" / "reviews").mkdir(parents=True)
        review = worktree / "review.md"
        # Cover NO files — gamma.py is the changed file and is omitted.
        review.write_text(_coverage_block([], self.rubric_ids, self.feature))

        with mock.patch.dict(os.environ, self._gate_env(gitdir, worktree), clear=True):
            code, msg = hook.run_gate(
                review, "work-completion", prd, diff_range, worktree
            )

        self.assertNotEqual(code, 0)
        self.assertIn("MISSING_FILES", msg)
        self.assertIn("gamma.py", msg)


if __name__ == "__main__":
    unittest.main()
