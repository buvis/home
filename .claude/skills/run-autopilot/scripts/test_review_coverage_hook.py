"""Tests for review_coverage_hook.py (module does NOT exist yet — TDD red phase).

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


class MainBlocksWhenReviewFileMissingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)

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


if __name__ == "__main__":
    unittest.main()
