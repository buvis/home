#!/usr/bin/env python3
"""Tests for cli/__main__.py: the argparse dispatch CLI wrapping cli/records.py
(do_stall, do_park, reset_prd_fields, record_defer) and cli/state.py
(init, restore, transaction).

cli/__main__.py does not exist yet. Every test here runs the CLI as a real
subprocess (`python __main__.py <subcommand> <flags...>`) except one, pinned
by the task brief, that imports the `cli` package in-process only to check
where it resolves from on disk.

These tests bind ONLY the CLI wiring: argument mapping onto the underlying
library calls, exit-code passthrough, default --state path resolution (via
_walk_up.find_autopilot_dir), and stdout/stderr routing. They do not re-test
full library semantics -- those are covered by test_records_stall.py,
test_records_park.py, test_records.py and test_state.py; this file pins
exits 5, 9, and 10 as real CLI process exits (fixture shapes mirrored from
the library tests), not their full internal matrices. The CLI runs a
schema-version preflight on stall/park/reset-prd/restore before dispatch;
every fixture here leaves state.json's schema_version unstamped (or at 1) so
the preflight stays silent. Exit 6 (future-schema preflight) and the bash
`autopilot` alias are out of scope here. So are the lifecycle subcommands
select/frontmatter/phase-done/resume-target (PRD 00089, covered by
test_lifecycle_cli.py) and check-plan (F5, covered by test_policy.py).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI_DIR = Path(__file__).resolve().parent
RUN_AUTOPILOT_DIR = CLI_DIR.parent
CLI_MAIN = CLI_DIR / "__main__.py"


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI_MAIN), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )


def _minimal_state(**overrides) -> dict:
    """A schema-valid state, shaped like test_records_stall.py's
    _StallTestCase._sample_state (prd/phase/next_phase/cycle/tasks/batch)."""
    base = {
        "prd": "00004-feature-x.md",
        "phase": "build",
        "next_phase": "build",
        "cycle": 2,
        "tasks": [{"id": "t1", "name": "x", "status": "in_progress"}],
        "batch": {"id": "202607300000", "completed_prds": [], "parks_consecutive": 1},
    }
    base.update(overrides)
    return base


def _write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj), encoding="utf-8")


def _fresh_dir(testcase: unittest.TestCase) -> Path:
    tmp = tempfile.TemporaryDirectory()
    testcase.addCleanup(tmp.cleanup)
    return Path(tmp.name)


class _TempDirTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = _fresh_dir(self)


class StallTests(_TempDirTestCase):
    PRD = "00004-feature-x.md"

    def setUp(self) -> None:
        super().setUp()
        # S's own directory IS the autopilot dir stall resolves deferred/ under.
        self.autopilot_dir = self.root / "autopilot"
        self.autopilot_dir.mkdir()
        self.state_path = self.autopilot_dir / "state.json"
        self.prds_dir = self.root / "prds"
        (self.prds_dir / "wip").mkdir(parents=True)

    def test_happy_path_moves_prd_to_hold_and_appends_one_deferred_record(self) -> None:
        (self.prds_dir / "wip" / self.PRD).write_text("prd body", encoding="utf-8")
        _write_json(
            self.state_path,
            _minimal_state(
                prd=self.PRD,
                batch={
                    "id": "202607300000",
                    "completed_prds": [],
                    "parks_consecutive": 0,
                },
            ),
        )

        proc = _run(
            [
                "stall",
                "--state",
                str(self.state_path),
                "--prd",
                self.PRD,
                "--site",
                "design_gate",
                "--detail",
                "detail text",
                "--prds",
                str(self.prds_dir),
            ],
            cwd=self.root,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse((self.prds_dir / "wip" / self.PRD).exists())
        self.assertTrue((self.prds_dir / "hold" / self.PRD).exists())

        deferred_path = self.autopilot_dir / "deferred" / "202607300000-deferred.json"
        items = json.loads(deferred_path.read_text(encoding="utf-8"))["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["prd"], self.PRD)
        self.assertEqual(items[0]["site"], "design_gate")
        self.assertEqual(items[0]["detail"], "detail text")

    def test_prd_absent_from_wip_and_hold_exits_4(self) -> None:
        # Not placed in wip/ or hold/: the move has no source and no arrival.
        _write_json(
            self.state_path,
            _minimal_state(
                prd=self.PRD,
                batch={
                    "id": "202607300000",
                    "completed_prds": [],
                    "parks_consecutive": 0,
                },
            ),
        )

        proc = _run(
            [
                "stall",
                "--state",
                str(self.state_path),
                "--prd",
                self.PRD,
                "--site",
                "design_gate",
                "--detail",
                "detail text",
                "--prds",
                str(self.prds_dir),
            ],
            cwd=self.root,
        )

        self.assertEqual(proc.returncode, 4)


class StallExitCodeTests(_TempDirTestCase):
    """Pins exits 9 and 10 (do_stall-internal, see test_records_stall.py's
    ExitCodeTests / IdentityGuardTests for the library-level matrices) as
    real CLI process exits, with the same fixture shapes StallTests uses."""

    PRD = "00004-feature-x.md"

    def setUp(self) -> None:
        super().setUp()
        self.autopilot_dir = self.root / "autopilot"
        self.autopilot_dir.mkdir()
        self.state_path = self.autopilot_dir / "state.json"
        self.prds_dir = self.root / "prds"
        (self.prds_dir / "wip").mkdir(parents=True)

    def _stall_args(self) -> list[str]:
        return [
            "stall",
            "--state",
            str(self.state_path),
            "--prd",
            self.PRD,
            "--site",
            "design_gate",
            "--detail",
            "detail text",
            "--prds",
            str(self.prds_dir),
        ]

    def test_corrupt_deferred_file_shape_exits_9_after_the_move_already_landed(
        self,
    ) -> None:
        # A list root is valid JSON but the wrong shape for the deferred
        # file; the move (step 3) lands before the append (step 4) fails.
        (self.prds_dir / "wip" / self.PRD).write_text("prd body", encoding="utf-8")
        _write_json(
            self.state_path,
            _minimal_state(
                prd=self.PRD,
                batch={
                    "id": "202607300000",
                    "completed_prds": [],
                    "parks_consecutive": 0,
                },
            ),
        )
        deferred_dir = self.autopilot_dir / "deferred"
        deferred_dir.mkdir()
        (deferred_dir / "202607300000-deferred.json").write_text("[]", encoding="utf-8")

        proc = _run(self._stall_args(), cwd=self.root)

        self.assertEqual(proc.returncode, 9)
        self.assertFalse((self.prds_dir / "wip" / self.PRD).exists())
        self.assertTrue(
            (self.prds_dir / "hold" / self.PRD).exists(),
            "the move lands before the append",
        )

    def test_stall_op_naming_a_different_prd_exits_10_with_no_filesystem_effects(
        self,
    ) -> None:
        (self.prds_dir / "wip" / self.PRD).write_text("prd body", encoding="utf-8")
        state = _minimal_state(
            prd=self.PRD,
            batch={"id": "202607300000", "completed_prds": [], "parks_consecutive": 0},
        )
        state["stall_op"] = {
            "op_id": "op-other",
            "prd": "00099-other-prd.md",
            "site": "design_gate",
            "detail": "unrelated",
        }
        _write_json(self.state_path, state)
        before = self.state_path.read_bytes()

        proc = _run(self._stall_args(), cwd=self.root)

        self.assertEqual(proc.returncode, 10)
        self.assertTrue((self.prds_dir / "wip" / self.PRD).exists())
        self.assertFalse((self.prds_dir / "hold").exists())
        self.assertEqual(self.state_path.read_bytes(), before)


class ParkTests(_TempDirTestCase):
    PRD = "00004-feature-x.md"

    def setUp(self) -> None:
        super().setUp()
        self.autopilot_dir = self.root / "autopilot"
        self.autopilot_dir.mkdir()
        self.state_path = self.autopilot_dir / "state.json"
        self.prds_dir = self.root / "prds"
        (self.prds_dir / "wip").mkdir(parents=True)
        _write_json(
            self.state_path,
            _minimal_state(
                prd=self.PRD,
                batch={
                    "id": "202607300000",
                    "completed_prds": [],
                    "parks_consecutive": 0,
                },
            ),
        )

    def _park_args(self) -> list[str]:
        return [
            "park",
            "--state",
            str(self.state_path),
            "--prds",
            str(self.prds_dir),
            "--autopilot-dir",
            str(self.autopilot_dir),
        ]

    def test_no_marker_exits_3_with_human_line_on_stdout_and_empty_stderr(self) -> None:
        proc = _run(self._park_args(), cwd=self.root)

        self.assertEqual(proc.returncode, 3)
        self.assertNotEqual(proc.stdout.strip(), "")
        self.assertEqual(proc.stderr, "")

    def test_happy_path_moves_prd_to_hold_and_deletes_marker(self) -> None:
        (self.prds_dir / "wip" / self.PRD).write_text("prd body", encoding="utf-8")
        marker_path = self.autopilot_dir / "park-requested"
        _write_json(marker_path, {"prd": self.PRD, "reason": "died"})

        proc = _run(self._park_args(), cwd=self.root)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse((self.prds_dir / "wip" / self.PRD).exists())
        self.assertTrue((self.prds_dir / "hold" / self.PRD).exists())
        self.assertFalse(marker_path.exists())

    def test_without_autopilot_dir_flag_defaults_to_state_parent(self) -> None:
        (self.prds_dir / "wip" / self.PRD).write_text("prd body", encoding="utf-8")
        marker_path = self.autopilot_dir / "park-requested"
        _write_json(marker_path, {"prd": self.PRD, "reason": "died"})

        proc = _run(
            ["park", "--state", str(self.state_path), "--prds", str(self.prds_dir)],
            cwd=self.root,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse((self.prds_dir / "wip" / self.PRD).exists())
        self.assertTrue((self.prds_dir / "hold" / self.PRD).exists())
        self.assertFalse(marker_path.exists())


class ParkExitCodeTests(_TempDirTestCase):
    """Pins exit 5 (do_stall's systemic-park breaker, see
    test_records_park.py's SystemicHaltTests for the library-level matrix)
    as a real CLI process exit, with the same fixture shape ParkTests uses."""

    PRD = "00004-feature-x.md"

    def setUp(self) -> None:
        super().setUp()
        self.autopilot_dir = self.root / "autopilot"
        self.autopilot_dir.mkdir()
        self.state_path = self.autopilot_dir / "state.json"
        self.prds_dir = self.root / "prds"
        (self.prds_dir / "wip").mkdir(parents=True)

    def test_second_consecutive_park_exits_5_and_writes_systemic_pause_reason(
        self,
    ) -> None:
        (self.prds_dir / "wip" / self.PRD).write_text("prd body", encoding="utf-8")
        marker_path = self.autopilot_dir / "park-requested"
        _write_json(
            marker_path,
            {"prd": self.PRD, "reason": "wrapper died mid-session"},
        )
        _write_json(
            self.state_path,
            _minimal_state(
                prd=self.PRD,
                batch={
                    "id": "202607300000",
                    "completed_prds": [],
                    "parks_consecutive": 1,
                },
            ),
        )

        proc = _run(
            [
                "park",
                "--state",
                str(self.state_path),
                "--prds",
                str(self.prds_dir),
                "--autopilot-dir",
                str(self.autopilot_dir),
            ],
            cwd=self.root,
        )

        self.assertEqual(proc.returncode, 5)
        self.assertFalse((self.prds_dir / "wip" / self.PRD).exists())
        self.assertTrue((self.prds_dir / "hold" / self.PRD).exists())
        content = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(content["pause_reason"]["site"], "systemic_park")
        self.assertEqual(content["batch"]["parks_consecutive"], 2)


class ResetPrdTests(_TempDirTestCase):
    def test_resets_cycle_phase_and_clears_tasks(self) -> None:
        state_path = self.root / "state.json"
        _write_json(state_path, _minimal_state())

        proc = _run(["reset-prd", "--state", str(state_path)], cwd=self.root)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        content = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(content["cycle"], 1)
        self.assertEqual(content["phase"], "build")
        self.assertNotIn("tasks", content)

    def test_corrupt_state_exits_2(self) -> None:
        state_path = self.root / "state.json"
        state_path.write_text("{not valid json", encoding="utf-8")

        proc = _run(["reset-prd", "--state", str(state_path)], cwd=self.root)

        self.assertEqual(proc.returncode, 2)

    def test_non_dict_state_root_exits_2(self) -> None:
        state_path = self.root / "state.json"
        state_path.write_text("[]", encoding="utf-8")

        proc = _run(["reset-prd", "--state", str(state_path)], cwd=self.root)

        self.assertEqual(proc.returncode, 2)

    def test_missing_state_parent_dir_exits_2(self) -> None:
        state_path = self.root / "no-such-dir" / "state.json"

        proc = _run(["reset-prd", "--state", str(state_path)], cwd=self.root)

        self.assertEqual(proc.returncode, 2)


class DeferTests(_TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.state_dir = self.root / "autopilot"
        self.state_dir.mkdir()
        self.state_path = self.state_dir / "state.json"
        _write_json(self.state_path, _minimal_state())

    def test_appends_record_stamped_with_prd_to_the_batch_deferred_log(self) -> None:
        record = {"type": "manual-defer", "reason": "test note"}

        proc = _run(
            [
                "defer",
                "--state",
                str(self.state_path),
                "--prd",
                "00007-other-feature.md",
                "--batch",
                "202607300005",
                "--json",
                json.dumps(record),
            ],
            cwd=self.root,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        deferred_path = self.state_dir / "deferred" / "202607300005-deferred.json"
        items = json.loads(deferred_path.read_text(encoding="utf-8"))["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["prd"], "00007-other-feature.md")
        self.assertEqual(items[0]["type"], "manual-defer")
        self.assertEqual(items[0]["reason"], "test note")

    def test_malformed_json_exits_1(self) -> None:
        proc = _run(
            [
                "defer",
                "--state",
                str(self.state_path),
                "--prd",
                "00007-other-feature.md",
                "--batch",
                "202607300005",
                "--json",
                "{not valid json",
            ],
            cwd=self.root,
        )

        self.assertEqual(proc.returncode, 1)

    def test_valid_json_non_dict_exits_1_and_creates_no_deferred_file(self) -> None:
        proc = _run(
            [
                "defer",
                "--state",
                str(self.state_path),
                "--prd",
                "00007-other-feature.md",
                "--batch",
                "202607300005",
                "--json",
                "42",
            ],
            cwd=self.root,
        )

        self.assertEqual(proc.returncode, 1)
        self.assertNotEqual(proc.stderr.strip(), "")
        # A one-line diagnostic (per the fix), not an uncaught-exception traceback.
        self.assertEqual(len(proc.stderr.splitlines()), 1)
        deferred_path = self.state_dir / "deferred" / "202607300005-deferred.json"
        self.assertFalse(deferred_path.exists())


class RestoreTests(_TempDirTestCase):
    def test_rolls_bak_back_over_a_changed_state(self) -> None:
        state_path = self.root / "state.json"
        bak_path = self.root / "state.json.bak"
        backup_content = _minimal_state(cycle=1)
        _write_json(state_path, _minimal_state(cycle=99))
        _write_json(bak_path, backup_content)

        proc = _run(["restore", "--state", str(state_path)], cwd=self.root)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            json.loads(state_path.read_text(encoding="utf-8")),
            backup_content,
        )

    def test_corrupt_bak_exits_8_and_leaves_state_unchanged(self) -> None:
        state_path = self.root / "state.json"
        bak_path = self.root / "state.json.bak"
        _write_json(state_path, _minimal_state())
        before = state_path.read_bytes()
        bak_path.write_text("{not valid json", encoding="utf-8")

        proc = _run(["restore", "--state", str(state_path)], cwd=self.root)

        self.assertEqual(proc.returncode, 8)
        self.assertEqual(state_path.read_bytes(), before)

    def test_missing_bak_exits_8(self) -> None:
        state_path = self.root / "state.json"
        _write_json(state_path, _minimal_state())

        proc = _run(["restore", "--state", str(state_path)], cwd=self.root)

        self.assertEqual(proc.returncode, 8)

    def test_missing_state_parent_dir_exits_2(self) -> None:
        state_path = self.root / "no-such-dir" / "state.json"

        proc = _run(["restore", "--state", str(state_path)], cwd=self.root)

        self.assertEqual(proc.returncode, 2)


class UsageErrorTests(_TempDirTestCase):
    def test_unknown_subcommand_exits_1_with_diagnostic_on_stderr(self) -> None:
        proc = _run(["bogus-subcommand"], cwd=self.root)

        self.assertEqual(proc.returncode, 1)
        self.assertNotEqual(proc.stderr.strip(), "")


class DefaultStatePathTests(_TempDirTestCase):
    def test_reset_prd_without_state_flag_resolves_by_walking_up_to_dev_local_autopilot(
        self,
    ) -> None:
        autopilot_dir = self.root / "dev" / "local" / "autopilot"
        autopilot_dir.mkdir(parents=True)
        state_path = autopilot_dir / "state.json"
        _write_json(state_path, _minimal_state())
        cwd = self.root / "sub" / "dir"
        cwd.mkdir(parents=True)

        proc = _run(["reset-prd"], cwd=cwd)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        content = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(content["cycle"], 1)
        self.assertEqual(content["phase"], "build")
        self.assertNotIn("tasks", content)

    def test_reset_prd_without_state_flag_and_no_autopilot_ancestor_exits_1(
        self,
    ) -> None:
        # self.root is a bare tmpdir with no dev/local/autopilot anywhere
        # above it (verified: the default tempdir root has no such ancestor).
        proc = _run(["reset-prd"], cwd=self.root)

        self.assertEqual(proc.returncode, 1)
        self.assertNotEqual(proc.stderr.strip(), "")


class AllSubcommandsCwdMatrixTests(unittest.TestCase):
    """The decoy regression (see CwdIndependenceTests) generalized to every
    subcommand: each of init/stall/park/reset-prd/defer/restore must succeed
    as a subprocess regardless of the caller's cwd, including a scratch dir
    shadowed by a decoy top-level `cli/` package. Every flag here is
    explicit, so cwd is irrelevant to path resolution -- this test proves
    only that the decoy package is never imported instead of the real one."""

    def _cwds(self, testcase_root: Path) -> list[Path]:
        decoy_pkg = testcase_root / "cli"
        decoy_pkg.mkdir()
        (decoy_pkg / "__init__.py").write_text(
            'raise ImportError("decoy cli package imported")\n',
            encoding="utf-8",
        )
        (decoy_pkg / "records.py").write_text(
            'raise ImportError("decoy cli package imported")\n',
            encoding="utf-8",
        )
        return [Path.home(), RUN_AUTOPILOT_DIR, Path("/"), testcase_root]

    def _case_init(self, case_dir: Path) -> tuple[list[str], callable]:
        state_path = case_dir / "state.json"
        args = ["init", "--state", str(state_path), "--prd", "00004-feature-x.md"]

        def _check() -> None:
            content = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(content["prd"], "00004-feature-x.md")

        return args, _check

    def _case_stall(self, case_dir: Path) -> tuple[list[str], callable]:
        autopilot_dir = case_dir / "autopilot"
        autopilot_dir.mkdir()
        state_path = autopilot_dir / "state.json"
        prds_dir = case_dir / "prds"
        (prds_dir / "wip").mkdir(parents=True)
        prd = "00004-feature-x.md"
        (prds_dir / "wip" / prd).write_text("prd body", encoding="utf-8")
        _write_json(
            state_path,
            _minimal_state(
                prd=prd,
                batch={
                    "id": "202607300000",
                    "completed_prds": [],
                    "parks_consecutive": 0,
                },
            ),
        )
        args = [
            "stall",
            "--state",
            str(state_path),
            "--prd",
            prd,
            "--site",
            "design_gate",
            "--detail",
            "detail text",
            "--prds",
            str(prds_dir),
        ]

        def _check() -> None:
            self.assertTrue((prds_dir / "hold" / prd).exists())

        return args, _check

    def _case_park(self, case_dir: Path) -> tuple[list[str], callable]:
        autopilot_dir = case_dir / "autopilot"
        autopilot_dir.mkdir()
        state_path = autopilot_dir / "state.json"
        prds_dir = case_dir / "prds"
        (prds_dir / "wip").mkdir(parents=True)
        prd = "00004-feature-x.md"
        (prds_dir / "wip" / prd).write_text("prd body", encoding="utf-8")
        _write_json(
            state_path,
            _minimal_state(
                prd=prd,
                batch={
                    "id": "202607300000",
                    "completed_prds": [],
                    "parks_consecutive": 0,
                },
            ),
        )
        _write_json(autopilot_dir / "park-requested", {"prd": prd, "reason": "died"})
        args = [
            "park",
            "--state",
            str(state_path),
            "--prds",
            str(prds_dir),
            "--autopilot-dir",
            str(autopilot_dir),
        ]

        def _check() -> None:
            self.assertTrue((prds_dir / "hold" / prd).exists())

        return args, _check

    def _case_reset_prd(self, case_dir: Path) -> tuple[list[str], callable]:
        state_path = case_dir / "state.json"
        _write_json(state_path, _minimal_state())
        args = ["reset-prd", "--state", str(state_path)]

        def _check() -> None:
            content = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(content["cycle"], 1)

        return args, _check

    def _case_defer(self, case_dir: Path) -> tuple[list[str], callable]:
        state_dir = case_dir / "autopilot"
        state_dir.mkdir()
        state_path = state_dir / "state.json"
        _write_json(state_path, _minimal_state())
        record = {"type": "manual-defer", "reason": "test note"}
        args = [
            "defer",
            "--state",
            str(state_path),
            "--prd",
            "00007-other-feature.md",
            "--batch",
            "202607300005",
            "--json",
            json.dumps(record),
        ]

        def _check() -> None:
            deferred_path = state_dir / "deferred" / "202607300005-deferred.json"
            self.assertTrue(deferred_path.exists())

        return args, _check

    def _case_restore(self, case_dir: Path) -> tuple[list[str], callable]:
        state_path = case_dir / "state.json"
        bak_path = case_dir / "state.json.bak"
        _write_json(state_path, _minimal_state(cycle=99))
        _write_json(bak_path, _minimal_state(cycle=1))
        args = ["restore", "--state", str(state_path)]

        def _check() -> None:
            content = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(content["cycle"], 1)

        return args, _check

    def test_every_subcommand_succeeds_as_a_subprocess_from_any_cwd(self) -> None:
        cases = {
            "init": self._case_init,
            "stall": self._case_stall,
            "park": self._case_park,
            "reset-prd": self._case_reset_prd,
            "defer": self._case_defer,
            "restore": self._case_restore,
        }
        cwds = self._cwds(_fresh_dir(self))

        for subcommand, build in cases.items():
            for cwd in cwds:
                with self.subTest(subcommand=subcommand, cwd=str(cwd)):
                    case_dir = _fresh_dir(self)
                    args, check = build(case_dir)

                    proc = _run(args, cwd=cwd)

                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    check()


class PackageIdentityTests(unittest.TestCase):
    def test_cli_package_import_resolves_under_run_autopilot_dir(self) -> None:
        sys.path.insert(0, str(RUN_AUTOPILOT_DIR))
        import cli  # the one in-process import the task brief pins as exempt

        self.assertTrue(
            Path(cli.__file__).resolve().is_relative_to(RUN_AUTOPILOT_DIR.resolve()),
        )


if __name__ == "__main__":
    unittest.main()
