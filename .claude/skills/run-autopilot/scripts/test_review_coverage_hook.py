"""Tests for review_coverage_hook.py.

Pins the public API of the hook that blocks session exit when the just-completed
review surface's saved review file lacks a complete coverage block.

Stdlib-only unittest. Imports the module directly via importlib (no subprocess).
"""

from __future__ import annotations

import importlib.util
import json
import os
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
        # Three-gate machine (PRD 00015): only the done hand-off is gated,
        # and the surface that just finished is the work-completion cycle.
        self.assertEqual(hook.surface_for_phase("done"), "work-completion")

    def test_surface_mapping_non_review_phase_is_none(self) -> None:
        self.assertIsNone(hook.surface_for_phase("build"))
        self.assertIsNone(hook.surface_for_phase("review"))
        self.assertIsNone(hook.surface_for_phase("paused"))
        # Legacy pre-00015 phase values are no longer review-gated hand-offs.
        self.assertIsNone(hook.surface_for_phase("blind"))
        self.assertIsNone(hook.surface_for_phase("doubt"))


class ReviewFileForTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.reviews_dir = Path(self.tmp.name)

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


def _make_autopilot_dir(
    root: Path,
    phase: str,
    prd: str = "X.md",
    work_start_sha: str = "abc",
    repo_root: str | None = None,
) -> Path:
    """Build a minimal dev/local/autopilot dir tree under root."""
    autopilot_dir = root / "dev" / "local" / "autopilot"
    autopilot_dir.mkdir(parents=True, exist_ok=True)
    state = {"phase": phase, "prd": prd, "work_start_sha": work_start_sha}
    if repo_root is not None:
        state["repo_root"] = repo_root
    (autopilot_dir / "state.json").write_text(json.dumps(state))
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

    def test_main_blocks_on_gate_failure(self) -> None:
        autopilot_dir = _make_autopilot_dir(
            self.repo, phase="done", prd="X.md", work_start_sha="abc"
        )
        reviews_dir = self._make_reviews_dir()
        # Create the review file that main() will discover.
        (reviews_dir / "X-review-1.md").write_text("review content")

        with mock.patch.object(
            hook, "find_autopilot_dir", return_value=autopilot_dir
        ), mock.patch.object(
            hook, "run_gate", return_value=(2, "MISSING_FILES foo.py")
        ):
            result = hook.main()

        self.assertEqual(result, 2)

    def test_main_exit0_outside_loop_without_gating(self) -> None:
        # Footgun fix: outside the autopilot shell loop ($_AUTOPILOT_LOOP unset)
        # the hook must never block exit, even when state.json is parked in a
        # review phase. It must not resolve the autopilot dir or run the gate —
        # a leftover review-phase state must not deadlock unrelated sessions
        # that merely share the cwd tree.
        _make_autopilot_dir(
            self.repo, phase="blind", prd="X.md", work_start_sha="abc"
        )

        def _must_not_be_called(*args, **kwargs):
            raise AssertionError("hook must not act outside the autopilot loop")

        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            hook, "find_autopilot_dir", side_effect=_must_not_be_called
        ), mock.patch.object(hook, "run_gate", side_effect=_must_not_be_called):
            result = hook.main()

        self.assertEqual(result, 0)

    def test_main_exit0_on_non_review_phase(self) -> None:
        autopilot_dir = _make_autopilot_dir(self.repo, phase="planning")

        def _fail_if_called(*args, **kwargs):
            raise AssertionError("run_gate must NOT be called for non-review phases")

        with mock.patch.object(
            hook, "find_autopilot_dir", return_value=autopilot_dir
        ), mock.patch.object(hook, "run_gate", side_effect=_fail_if_called):
            result = hook.main()

        self.assertEqual(result, 0)

    def test_main_exit0_when_gate_passes(self) -> None:
        # phase "done" means the review loop converged -> work-completion
        # surface -> highest <prd>-review-N.md.
        autopilot_dir = _make_autopilot_dir(self.repo, phase="done", prd="Y.md")
        reviews_dir = self._make_reviews_dir()
        (reviews_dir / "Y-review-1.md").write_text("review content")

        with mock.patch.object(
            hook, "find_autopilot_dir", return_value=autopilot_dir
        ), mock.patch.object(hook, "run_gate", return_value=(0, "")):
            result = hook.main()

        self.assertEqual(result, 0)


class BlockCapTests(unittest.TestCase):
    """Liveness valve (2026-07-19): the gate blocks at most BLOCK_CAP exits
    per handoff, then fails loud (exit 0 + .review-gate-failed marker) so a
    never-converging review file cannot burn the session to the context cap."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        loop_env = mock.patch.dict(os.environ, {"_AUTOPILOT_LOOP": "1"})
        loop_env.start()
        self.addCleanup(loop_env.stop)

    def _reviews_dir(self) -> Path:
        reviews = self.repo / "dev" / "local" / "reviews"
        reviews.mkdir(parents=True, exist_ok=True)
        return reviews

    def test_main_stops_blocking_after_block_cap(self) -> None:
        autopilot_dir = _make_autopilot_dir(
            self.repo, phase="done", prd="X.md", work_start_sha="abc"
        )
        (self._reviews_dir() / "X-review-1.md").write_text("review content")

        with mock.patch.object(
            hook, "find_autopilot_dir", return_value=autopilot_dir
        ), mock.patch.object(
            hook, "run_gate", return_value=(2, "MISSING_FILES foo.py")
        ):
            for _ in range(hook.BLOCK_CAP):
                self.assertEqual(hook.main(), 2)
            self.assertEqual(hook.main(), 0)

        self.assertTrue((autopilot_dir / ".review-gate-failed").exists())
        self.assertFalse((autopilot_dir / ".review-gate-blocks").exists())

    def test_main_pass_clears_block_counter(self) -> None:
        autopilot_dir = _make_autopilot_dir(self.repo, phase="done", prd="Y.md")
        (self._reviews_dir() / "Y-review-1.md").write_text("review content")
        (autopilot_dir / ".review-gate-blocks").write_text("2")
        (autopilot_dir / ".review-gate-failed").write_text("stale")

        with mock.patch.object(
            hook, "find_autopilot_dir", return_value=autopilot_dir
        ), mock.patch.object(hook, "run_gate", return_value=(0, "")):
            self.assertEqual(hook.main(), 0)

        self.assertFalse((autopilot_dir / ".review-gate-blocks").exists())
        self.assertFalse((autopilot_dir / ".review-gate-failed").exists())


class RunGateTests(unittest.TestCase):
    def test_run_gate_invokes_subprocess_and_returns_code(self) -> None:
        import types

        fake_result = types.SimpleNamespace(returncode=1, stderr="no verdict line\n")
        with mock.patch.object(hook.subprocess, "run", return_value=fake_result) as patched:
            code, msg = hook.run_gate(Path("/tmp/rev.md"))

        self.assertEqual(code, 1)
        self.assertEqual(msg, "no verdict line")

        # Verify subprocess.run was actually called with a list as first arg.
        patched.assert_called_once()
        argv = patched.call_args[0][0]
        self.assertIsInstance(argv, list)

        # Key flags and values must appear in the argv list.
        self.assertIn("--review-file", argv)
        self.assertIn("/tmp/rev.md", argv)
        self.assertTrue(
            any(elem.endswith("check_review_file.py") for elem in argv),
            msg=f"No element ending with 'check_review_file.py' found in argv: {argv}",
        )

    def test_run_gate_end_to_end_against_real_files(self) -> None:
        """No mocks: the delegation must pass a well-shaped file and fail a
        gapped one through the real check_review_file.py subprocess."""
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good-review-1.md"
            good.write_text(
                "---\nreviewers: alice\n---\n\n## Alice\n\nall clear\n\n"
                "Verdict: converged\nTests: 3 passed, 0 failed\n"
            )
            code, msg = hook.run_gate(good)
            self.assertEqual(code, 0, msg)

            gapped = Path(tmp) / "gapped-review-1.md"
            gapped.write_text("---\nreviewers: alice\n---\n\n## Alice\n\nhm\n")
            code, msg = hook.run_gate(gapped)
            self.assertEqual(code, 1)
            self.assertIn("verdict", msg.lower())


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
        # phase "done" means the review loop converged -> work-completion
        # surface -> the HIGHEST-numbered <prd>-review-N.md.
        autopilot_dir = _make_autopilot_dir(self.repo, phase="done", prd="Y.md")
        reviews_dir = self._make_reviews_dir()
        (reviews_dir / "Y-review-1.md").write_text("cycle 1")
        expected_review_file = reviews_dir / "Y-review-3.md"
        expected_review_file.write_text("cycle 3 review content")

        gate_mock = mock.MagicMock(return_value=(0, ""))

        with mock.patch.object(
            hook, "find_autopilot_dir", return_value=autopilot_dir
        ), mock.patch.object(hook, "run_gate", gate_mock):
            hook.main()

        gate_mock.assert_called_once()
        # First positional argument must be the resolved review file path.
        actual_review_file = gate_mock.call_args[0][0]
        self.assertEqual(Path(actual_review_file), expected_review_file)


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
        autopilot_dir = _make_autopilot_dir(self.repo, phase="done", prd="Z.md")
        # reviews dir exists but no Z-review-*.md is created.
        reviews_dir = self.repo / "dev" / "local" / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)

        def _gate_must_not_be_called(*args, **kwargs):
            raise AssertionError("run_gate must NOT be called when review file is missing")

        with mock.patch.object(
            hook, "find_autopilot_dir", return_value=autopilot_dir
        ), mock.patch.object(hook, "run_gate", side_effect=_gate_must_not_be_called):
            result = hook.main()

        self.assertEqual(result, 2)


class GateBlocksDecisionTests(unittest.TestCase):
    """Pin the pure gate decision. gate_blocks is side-effect-free — pure
    (bool, message) — so main() can block deterministically. (It was once
    shared with the retired autopilot_stop_hook, PRD 00014.)"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.autopilot_dir = self.repo / "dev" / "local" / "autopilot"
        self.autopilot_dir.mkdir(parents=True)

    def _reviews_dir(self) -> Path:
        d = self.repo / "dev" / "local" / "reviews"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_non_review_phase_does_not_block(self) -> None:
        def _fail(*a, **k):
            raise AssertionError("run_gate must not run for a non-review phase")

        with mock.patch.object(hook, "run_gate", side_effect=_fail):
            blocks, msg = hook.gate_blocks(
                self.autopilot_dir, {"phase": "build", "prd": "X.md"}
            )
        self.assertFalse(blocks)
        self.assertEqual(msg, "")

    def test_missing_review_file_blocks_without_running_gate(self) -> None:
        self._reviews_dir()  # empty: no Z-review-*.md

        def _fail(*a, **k):
            raise AssertionError("run_gate must not run when the review file is missing")

        with mock.patch.object(hook, "run_gate", side_effect=_fail):
            blocks, msg = hook.gate_blocks(
                self.autopilot_dir, {"phase": "done", "prd": "Z.md"}
            )
        self.assertTrue(blocks)
        self.assertIn("no work-completion review file", msg)

    def test_coverage_gap_blocks(self) -> None:
        (self._reviews_dir() / "X-review-1.md").write_text("r")
        with mock.patch.object(hook, "run_gate", return_value=(2, "MISSING_FILES foo.py")):
            blocks, msg = hook.gate_blocks(
                self.autopilot_dir, {"phase": "done", "prd": "X.md"}
            )
        self.assertTrue(blocks)
        self.assertIn("review coverage gap [work-completion]", msg)

    def test_gate_pass_does_not_block(self) -> None:
        (self._reviews_dir() / "Y-review-1.md").write_text("r")
        with mock.patch.object(hook, "run_gate", return_value=(0, "")):
            blocks, msg = hook.gate_blocks(
                self.autopilot_dir, {"phase": "done", "prd": "Y.md"}
            )
        self.assertFalse(blocks)
        self.assertEqual(msg, "")


if __name__ == "__main__":
    unittest.main()
