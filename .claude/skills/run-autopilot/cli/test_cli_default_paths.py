#!/usr/bin/env python3
"""Tests for the walk-up default paths on the `stall` and `park` CLI
subparsers (cli/__main__.py). Complements test_cli.py, which already pins
`--state`'s own walk-up default (DefaultStatePathTests) and the pre-existing
--autopilot-dir-defaults-to-state-parent behavior (ParkTests). This file
pins the NEW contract: `stall` and `park` also default `--prds` (derived as
the walked-up autopilot dir's sibling `dev/local/prds`) by walking up from
the current working directory, the same `_walk_up` mechanism `--state`
already uses -- so the documented bare invocations (`autopilot park`,
`autopilot stall --prd <f> --site <slug> --detail <s>`) work unmodified from
anywhere inside a project tree.

Each test runs the CLI as a real subprocess against a synthetic project
tree rooted in a fresh tmpdir, per the task brief's pinned layout:

    <project-root>/dev/local/autopilot/state.json
    <project-root>/dev/local/prds/wip/<prd>
    (hold/ may be absent -- the CLI creates it)

Library semantics (do_stall/do_park internals, exit 4/5/9/10 matrices) are
covered elsewhere (test_records_stall.py, test_records_park.py) and are not
re-tested here.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI_DIR = Path(__file__).resolve().parent
CLI_MAIN = CLI_DIR / "__main__.py"


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI_MAIN), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )


def _minimal_state(**overrides) -> dict:
    """A schema-valid state, shaped like test_cli.py's _minimal_state /
    test_records_park.py's _sample_state (prd/phase/next_phase/batch)."""
    base = {
        "prd": "00004-feature-x.md",
        "phase": "build",
        "next_phase": "build",
        "cycle": 2,
        "tasks": [{"id": "t1", "name": "x", "status": "in_progress"}],
        "batch": {"id": "202607300000", "completed_prds": [], "parks_consecutive": 0},
    }
    base.update(overrides)
    return base


def _write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj), encoding="utf-8")


def _fresh_dir(testcase: unittest.TestCase) -> Path:
    tmp = tempfile.TemporaryDirectory()
    testcase.addCleanup(tmp.cleanup)
    return Path(tmp.name)


def _make_project(root: Path, prd: str) -> tuple[Path, Path]:
    """Builds the pinned synthetic layout under `root`:
    <root>/dev/local/autopilot/state.json and <root>/dev/local/prds/wip/.
    Returns (autopilot_dir, prds_dir).
    """
    autopilot_dir = root / "dev" / "local" / "autopilot"
    autopilot_dir.mkdir(parents=True)
    prds_dir = root / "dev" / "local" / "prds"
    (prds_dir / "wip").mkdir(parents=True)
    _write_json(autopilot_dir / "state.json", _minimal_state(prd=prd))
    return autopilot_dir, prds_dir


class _TempDirTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = _fresh_dir(self)


class BareStallWalkUpTests(_TempDirTestCase):
    """Behavior 1: bare `stall` (no --prds, no --state) works via walk-up
    defaults from the project root."""

    PRD = "00004-feature-x.md"

    def test_bare_stall_resolves_state_and_prds_by_walking_up_from_cwd(self) -> None:
        autopilot_dir, prds_dir = _make_project(self.root, self.PRD)
        (prds_dir / "wip" / self.PRD).write_text("prd body", encoding="utf-8")

        proc = _run(
            ["stall", "--prd", self.PRD, "--site", "design_gate", "--detail", "x"],
            cwd=self.root,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse((prds_dir / "wip" / self.PRD).exists())
        self.assertTrue((prds_dir / "hold" / self.PRD).exists())

        deferred_path = autopilot_dir / "deferred" / "202607300000-deferred.json"
        items = json.loads(deferred_path.read_text(encoding="utf-8"))["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["prd"], self.PRD)
        self.assertEqual(items[0]["site"], "design_gate")
        self.assertEqual(items[0]["detail"], "x")


class BareParkWalkUpTests(_TempDirTestCase):
    """Behavior 2: bare `park` (no flags at all) works via walk-up defaults,
    given a valid park-requested marker naming a wip PRD."""

    PRD = "00004-feature-x.md"

    def test_bare_park_resolves_state_and_prds_by_walking_up_from_cwd(self) -> None:
        autopilot_dir, prds_dir = _make_project(self.root, self.PRD)
        (prds_dir / "wip" / self.PRD).write_text("prd body", encoding="utf-8")
        marker_path = autopilot_dir / "park-requested"
        _write_json(marker_path, {"prd": self.PRD, "reason": "died"})

        proc = _run(["park"], cwd=self.root)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse((prds_dir / "wip" / self.PRD).exists())
        self.assertTrue((prds_dir / "hold" / self.PRD).exists())
        self.assertFalse(marker_path.exists())


class BareParkNoMarkerTests(_TempDirTestCase):
    """Behavior 3: bare `park` with no marker exits 3 (nothing to do),
    still flag-free."""

    PRD = "00004-feature-x.md"

    def test_bare_park_with_no_marker_exits_3(self) -> None:
        _make_project(self.root, self.PRD)

        proc = _run(["park"], cwd=self.root)

        self.assertEqual(proc.returncode, 3)


class NestedCwdWalkUpTests(_TempDirTestCase):
    """Behavior 4: defaults resolve from cwd, not from the skill root --
    running from a nested subdirectory of the project still finds that
    same project's dirs."""

    PRD = "00004-feature-x.md"

    def test_bare_stall_from_nested_subdir_still_resolves_the_project_root_dirs(
        self,
    ) -> None:
        autopilot_dir, prds_dir = _make_project(self.root, self.PRD)
        (prds_dir / "wip" / self.PRD).write_text("prd body", encoding="utf-8")
        nested_cwd = self.root / "some" / "nested" / "dir"
        nested_cwd.mkdir(parents=True)

        proc = _run(
            ["stall", "--prd", self.PRD, "--site", "design_gate", "--detail", "x"],
            cwd=nested_cwd,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse((prds_dir / "wip" / self.PRD).exists())
        self.assertTrue((prds_dir / "hold" / self.PRD).exists())

        deferred_path = autopilot_dir / "deferred" / "202607300000-deferred.json"
        items = json.loads(deferred_path.read_text(encoding="utf-8"))["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["prd"], self.PRD)


class ExplicitPrdsOverridesWalkUpTests(_TempDirTestCase):
    """Behavior 5: an explicit --prds pointing at a second synthetic tree
    wins over the cwd-derived default -- no behavior change for existing
    flagged callers."""

    PRD = "00004-feature-x.md"

    def test_explicit_prds_flag_overrides_the_cwd_derived_default(self) -> None:
        autopilot_dir, primary_prds_dir = _make_project(self.root, self.PRD)
        # Deliberately do NOT place the PRD under the primary tree's wip/:
        # if the implementation ignored --prds and fell back to the
        # cwd-derived prds dir, the move would fail instead of succeeding
        # against the second tree.
        second_root = _fresh_dir(self)
        second_prds_dir = second_root / "prds"
        (second_prds_dir / "wip").mkdir(parents=True)
        (second_prds_dir / "wip" / self.PRD).write_text("prd body", encoding="utf-8")

        proc = _run(
            [
                "stall",
                "--prd", self.PRD,
                "--site", "design_gate",
                "--detail", "x",
                "--prds", str(second_prds_dir),
            ],
            cwd=self.root,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse((second_prds_dir / "wip" / self.PRD).exists())
        self.assertTrue((second_prds_dir / "hold" / self.PRD).exists())
        self.assertFalse((primary_prds_dir / "hold" / self.PRD).exists())
        self.assertFalse((primary_prds_dir / "hold").exists())


class NoAncestorProjectTests(_TempDirTestCase):
    """Behavior 6: no dev/local/autopilot ancestor anywhere above cwd --
    bare stall/park must fail cleanly (nonzero, no traceback, no
    filesystem writes), not crash or silently do nothing successfully.
    self.root is a bare tmpdir with no dev/local/autopilot anywhere above
    it (same guarantee test_cli.py's DefaultStatePathTests relies on)."""

    PRD = "00004-feature-x.md"

    def _list_all(self) -> set[str]:
        return {str(p.relative_to(self.root)) for p in self.root.rglob("*")}

    def test_bare_stall_and_bare_park_fail_cleanly_with_no_project_ancestor(self) -> None:
        with self.subTest(subcommand="stall"):
            before = self._list_all()

            proc = _run(
                ["stall", "--prd", self.PRD, "--site", "design_gate", "--detail", "x"],
                cwd=self.root,
            )

            self.assertNotEqual(proc.returncode, 0)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertNotEqual(proc.stderr.strip(), "")
            self.assertEqual(self._list_all(), before)

        with self.subTest(subcommand="park"):
            before = self._list_all()

            proc = _run(["park"], cwd=self.root)

            self.assertNotEqual(proc.returncode, 0)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertNotEqual(proc.stderr.strip(), "")
            self.assertEqual(self._list_all(), before)


class ExplicitStateAnchorsPrdsDefaultTests(_TempDirTestCase):
    """Behavior 7 (PRD 00051 review cycle 1 task #14, Item 5): an explicit
    --state anchors the bare --prds default to ITS OWN tree, not an
    independent cwd-derived walk-up. Running from inside a DIFFERENT
    project's tree (tree A) with --state pointed at tree B must move the PRD
    in tree B; tree A's prds/ (which never gets the PRD written into wip/)
    is left untouched -- if the implementation still independently walked
    up from cwd for --prds, the move would fail against tree A's empty
    wip/ instead of succeeding against tree B."""

    PRD = "00004-feature-x.md"

    def test_explicit_state_anchors_bare_prds_default_to_states_own_tree(self) -> None:
        _tree_a_autopilot_dir, tree_a_prds_dir = _make_project(self.root, self.PRD)

        tree_b_root = _fresh_dir(self)
        tree_b_autopilot_dir, tree_b_prds_dir = _make_project(tree_b_root, self.PRD)
        (tree_b_prds_dir / "wip" / self.PRD).write_text("prd body", encoding="utf-8")
        tree_b_state_path = tree_b_autopilot_dir / "state.json"

        proc = _run(
            [
                "stall",
                "--prd", self.PRD,
                "--site", "design_gate",
                "--detail", "x",
                "--state", str(tree_b_state_path),
            ],
            cwd=self.root,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse((tree_b_prds_dir / "wip" / self.PRD).exists())
        self.assertTrue((tree_b_prds_dir / "hold" / self.PRD).exists())
        self.assertFalse((tree_a_prds_dir / "hold" / self.PRD).exists())
        self.assertFalse((tree_a_prds_dir / "hold").exists())


if __name__ == "__main__":
    unittest.main()
