#!/usr/bin/env python3
"""Tests for the four lifecycle subcommands: select, frontmatter, phase-done
and resume-target (cli/__main__.py, PRD 00089 Phase 1).

Every test runs the CLI as a real subprocess against a synthetic project tree,
matching test_cli_default_paths.py's pinned layout. The pure decisions are
tested in test_selection.py / test_frontmatter.py / test_transitions.py /
test_resume.py; what is bound HERE is the process contract - exit codes, what
lands on disk, and the walk-up defaults that make the bare invocations work
from anywhere in a project tree.

`phase-done`'s one-commit claim is checked the only way that distinguishes it
from the four separate writes it replaces: against the `.bak`, which holds the
PRE-transaction bytes, so a transition that landed its effects across two
commits would leave a half-advanced state there.
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


def _state(**overrides) -> dict:
    base = {
        "prd": "00089-example-v1.md",
        "phase": "build",
        "next_phase": "build",
        "cycle": 1,
        "phases_completed": [],
        "batch": {"id": "202608071200", "completed_prds": [], "parks_consecutive": 0},
    }
    base.update(overrides)
    return base


class _ProjectTestCase(unittest.TestCase):
    """A synthetic <root>/dev/local/{autopilot,prds} tree per test."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.autopilot_dir = self.root / "dev" / "local" / "autopilot"
        self.autopilot_dir.mkdir(parents=True)
        self.prds_dir = self.root / "dev" / "local" / "prds"
        for lifecycle in ("wip", "backlog", "hold"):
            (self.prds_dir / lifecycle).mkdir(parents=True)
        self.state_path = self.autopilot_dir / "state.json"

    def write_state(self, **overrides) -> None:
        self.state_path.write_text(json.dumps(_state(**overrides)), encoding="utf-8")

    def read_state(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def put_prd(self, lifecycle: str, name: str, body: str = "# PRD\n") -> Path:
        path = self.prds_dir / lifecycle / name
        path.write_text(body, encoding="utf-8")
        return path


class SelectTests(_ProjectTestCase):
    def test_picks_lowest_sequence_in_wip(self) -> None:
        self.put_prd("wip", "00095-later-v1.md")
        self.put_prd("wip", "00089-earlier-v1.md")
        proc = _run(["select", "--prds", str(self.prds_dir)], cwd=self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            json.loads(proc.stdout),
            {"prd": "00089-earlier-v1.md", "source": "wip"},
        )

    def test_falls_through_to_backlog_when_wip_is_empty(self) -> None:
        self.put_prd("backlog", "00093-b-v1.md")
        proc = _run(["select", "--prds", str(self.prds_dir)], cwd=self.root)
        self.assertEqual(
            json.loads(proc.stdout),
            {"prd": "00093-b-v1.md", "source": "backlog"},
        )

    def test_never_picks_from_hold(self) -> None:
        # hold/ holds the lowest number and both other dirs are empty; a
        # selector that scanned hold would return it.
        self.put_prd("hold", "00001-parked-v1.md")
        proc = _run(["select", "--prds", str(self.prds_dir)], cwd=self.root)
        self.assertEqual(json.loads(proc.stdout), {"prd": None, "source": "drained"})

    def test_drained_is_exit_zero_not_a_failure(self) -> None:
        proc = _run(["select", "--prds", str(self.prds_dir)], cwd=self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["source"], "drained")

    def test_absent_lifecycle_dir_is_empty_not_a_crash(self) -> None:
        proc = _run(["select", "--prds", str(self.root / "nope")], cwd=self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["source"], "drained")

    def test_bare_select_walks_up_from_a_nested_cwd(self) -> None:
        self.put_prd("wip", "00089-earlier-v1.md")
        nested = self.root / "src" / "deep" / "nested"
        nested.mkdir(parents=True)
        proc = _run(["select"], cwd=nested)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["prd"], "00089-earlier-v1.md")

    def test_select_exposes_no_hold_flag(self) -> None:
        proc = _run(
            ["select", "--prds", str(self.prds_dir), "--hold", "x"],
            cwd=self.root,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--hold", proc.stderr)


class FrontmatterTests(_ProjectTestCase):
    def test_applies_parsed_fields_to_state_and_echoes_them(self) -> None:
        self.write_state()
        prd = self.put_prd(
            "wip",
            "00089-example-v1.md",
            "---\ncatchup: skip\nrework_cap: 4\ndesign: skip\n---\n\n# PRD\n",
        )
        proc = _run(
            ["frontmatter", "--state", str(self.state_path), "--prd", str(prd)],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        echoed = json.loads(proc.stdout)
        self.assertEqual(echoed["catchup_mode"], "skip")
        self.assertEqual(echoed["rework_cap"], 4)
        state = self.read_state()
        self.assertEqual(state["catchup_mode"], "skip")
        self.assertEqual(state["rework_cap"], 4)
        self.assertEqual(state["design_mode"], "skip")
        self.assertEqual(state["doubt_reviewer"], "codex", "defaults land too")

    def test_preserves_every_sibling_field(self) -> None:
        self.write_state(work_start_sha="abc123")
        prd = self.put_prd("wip", "00089-example-v1.md", "---\ncatchup: skip\n---\n")
        _run(
            ["frontmatter", "--state", str(self.state_path), "--prd", str(prd)],
            cwd=self.root,
        )
        state = self.read_state()
        self.assertEqual(state["work_start_sha"], "abc123")
        self.assertEqual(state["batch"]["id"], "202608071200")

    def test_invalid_value_warns_on_stderr_and_still_writes_the_default(self) -> None:
        self.write_state()
        prd = self.put_prd(
            "wip",
            "00089-example-v1.md",
            "---\ncatchup: sometimes\n---\n",
        )
        proc = _run(
            ["frontmatter", "--state", str(self.state_path), "--prd", str(prd)],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("catchup", proc.stderr)
        self.assertEqual(self.read_state()["catchup_mode"], "run")

    def test_malformed_block_warns_once_and_does_not_crash_phase_zero(self) -> None:
        self.write_state()
        prd = self.put_prd("wip", "00089-example-v1.md", "# PRD with no frontmatter\n")
        proc = _run(
            ["frontmatter", "--state", str(self.state_path), "--prd", str(prd)],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(proc.stderr.strip().splitlines()), 1)
        self.assertEqual(self.read_state()["catchup_mode"], "run")

    def test_a_stale_state_prd_path_fails_loud_rather_than_writing_defaults(
        self,
    ) -> None:
        # The multi-PRD trap found in 00089's review pass: `more_prds`
        # preserves `state.prd`, and Phase 9 already moved that PRD to done/.
        # Running frontmatter against `wip/<state.prd>` before the selected
        # basename is written therefore points at a file that is not there.
        # It must exit 1, NOT quietly apply every default to the new PRD.
        self.write_state(prd="00088-previous-v1.md")
        self.put_prd("wip", "00089-example-v1.md", "---\ncatchup: skip\n---\n")
        gone = self.prds_dir / "wip" / "00088-previous-v1.md"
        proc = _run(
            ["frontmatter", "--state", str(self.state_path), "--prd", str(gone)],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertNotIn(
            "catchup_mode",
            self.read_state(),
            "a missing PRD must not write defaults for the one that was selected",
        )

    def test_missing_prd_file_is_a_usage_error(self) -> None:
        self.write_state()
        proc = _run(
            [
                "frontmatter",
                "--state",
                str(self.state_path),
                "--prd",
                str(self.prds_dir / "wip" / "nope.md"),
            ],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 1)

    def test_future_schema_state_is_refused_before_any_write(self) -> None:
        self.state_path.write_text(
            json.dumps(_state(schema_version=99)),
            encoding="utf-8",
        )
        before = self.state_path.read_bytes()
        prd = self.put_prd("wip", "00089-example-v1.md", "---\ncatchup: skip\n---\n")
        proc = _run(
            ["frontmatter", "--state", str(self.state_path), "--prd", str(prd)],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 6)
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_warns_on_stderr_when_reparse_overwrites_an_existing_value(self) -> None:
        self.write_state(rework_cap=5)
        prd = self.put_prd(
            "wip",
            "00089-example-v1.md",
            "---\nrework_cap: 2\n---\n\n# PRD\n",
        )
        proc = _run(
            ["frontmatter", "--state", str(self.state_path), "--prd", str(prd)],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            proc.stderr.strip().splitlines(),
            ["autopilot: PRD frontmatter reset rework_cap 5 -> 2"],
        )
        self.assertEqual(self.read_state()["rework_cap"], 2)

    def test_no_warning_when_a_field_has_no_prior_value(self) -> None:
        self.write_state()
        prd = self.put_prd(
            "wip",
            "00089-example-v1.md",
            "---\nrework_cap: 2\n---\n\n# PRD\n",
        )
        proc = _run(
            ["frontmatter", "--state", str(self.state_path), "--prd", str(prd)],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "", "an initial set is not an overwrite")
        self.assertEqual(self.read_state()["rework_cap"], 2)

    def test_no_warning_when_the_reparsed_value_is_unchanged(self) -> None:
        self.write_state(rework_cap=5)
        prd = self.put_prd(
            "wip",
            "00089-example-v1.md",
            "---\nrework_cap: 5\n---\n\n# PRD\n",
        )
        proc = _run(
            ["frontmatter", "--state", str(self.state_path), "--prd", str(prd)],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "", "no actual change is not an overwrite")
        self.assertEqual(self.read_state()["rework_cap"], 5)


class PhaseDoneTests(_ProjectTestCase):
    def test_tasks_done_advances_the_build_gate(self) -> None:
        self.write_state(phase="build", next_phase="build")
        proc = _run(
            ["phase-done", "--state", str(self.state_path), "--outcome", "tasks_done"],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = self.read_state()
        self.assertEqual(state["phase"], "review")
        self.assertEqual(state["next_phase"], "review")
        self.assertEqual(state["phases_completed"], [])

    def test_converged_lands_phase_and_marker_in_one_commit(self) -> None:
        # The .bak holds the PRE-transaction bytes. If the phase advance and
        # the marker append were two commits, the backup would show the first
        # one already applied.
        self.write_state(phase="review", next_phase="review", cycle=2)
        before = self.state_path.read_bytes()
        proc = _run(
            ["phase-done", "--state", str(self.state_path), "--outcome", "converged"],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = self.read_state()
        self.assertEqual(state["phase"], "done")
        self.assertEqual(state["next_phase"], "done")
        self.assertEqual(state["phases_completed"], ["review"])
        self.assertEqual(Path(f"{self.state_path}.bak").read_bytes(), before)

    def test_rework_increments_cycle_and_clears_ids_in_one_commit(self) -> None:
        self.write_state(
            phase="review",
            next_phase="review",
            cycle=2,
            rework_task_ids=["7", "9"],
        )
        before = self.state_path.read_bytes()
        proc = _run(
            ["phase-done", "--state", str(self.state_path), "--outcome", "rework"],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = self.read_state()
        self.assertEqual(state["cycle"], 3)
        self.assertEqual(state["rework_task_ids"], [])
        self.assertEqual(state["phase"], "review")
        self.assertEqual(Path(f"{self.state_path}.bak").read_bytes(), before)

    def test_more_prds_applies_the_per_prd_reset(self) -> None:
        self.write_state(
            phase="done",
            next_phase="done",
            cycle=3,
            phases_completed=["review"],
            tasks=[{"id": "1", "status": "completed"}],
            work_start_sha="abc123",
        )
        proc = _run(
            ["phase-done", "--state", str(self.state_path), "--outcome", "more_prds"],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = self.read_state()
        self.assertEqual(state["phase"], "build")
        self.assertEqual(state["next_phase"], "build")
        self.assertEqual(state["phases_completed"], [])
        self.assertEqual(state["cycle"], 1)
        self.assertNotIn("work_start_sha", state)
        self.assertEqual(state["batch"]["id"], "202608071200", "batch is preserved")

    def test_drained_writes_the_empty_next_phase(self) -> None:
        self.write_state(phase="done", next_phase="done")
        proc = _run(
            ["phase-done", "--state", str(self.state_path), "--outcome", "drained"],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = self.read_state()
        self.assertEqual(state["next_phase"], "", "the wrapper reads EMPTY as drained")
        self.assertEqual(state["phase"], "done")

    def test_unknown_pair_exits_one_and_leaves_state_untouched(self) -> None:
        self.write_state(phase="build", next_phase="build")
        before = self.state_path.read_bytes()
        proc = _run(
            ["phase-done", "--state", str(self.state_path), "--outcome", "converged"],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("build", proc.stderr)
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_unrecognized_outcome_is_rejected_by_the_parser(self) -> None:
        self.write_state()
        proc = _run(
            ["phase-done", "--state", str(self.state_path), "--outcome", "sideways"],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 1)

    def test_exposes_no_phase_flag(self) -> None:
        # A caller that supplies both halves of the pair can supply a
        # mismatched one; the phase comes from the state.
        self.write_state()
        proc = _run(
            [
                "phase-done",
                "--state",
                str(self.state_path),
                "--outcome",
                "tasks_done",
                "--phase",
                "review",
            ],
            cwd=self.root,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--phase", proc.stderr)

    def test_missing_state_exits_two(self) -> None:
        proc = _run(
            ["phase-done", "--state", str(self.state_path), "--outcome", "tasks_done"],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 2)

    def test_future_schema_state_is_refused_before_any_effect(self) -> None:
        self.state_path.write_text(
            json.dumps(_state(schema_version=99)),
            encoding="utf-8",
        )
        before = self.state_path.read_bytes()
        proc = _run(
            ["phase-done", "--state", str(self.state_path), "--outcome", "tasks_done"],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 6)
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_bare_phase_done_walks_up_from_a_nested_cwd(self) -> None:
        self.write_state(phase="build", next_phase="build")
        nested = self.root / "src" / "deep"
        nested.mkdir(parents=True)
        proc = _run(["phase-done", "--outcome", "tasks_done"], cwd=nested)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read_state()["phase"], "review")


class ResumeTargetTests(_ProjectTestCase):
    def test_prints_the_documented_target(self) -> None:
        self.write_state(
            phase="build",
            tasks=[
                {"id": "t1", "status": "completed"},
                {"id": "t2", "status": "pending"},
            ],
        )
        proc = _run(["resume-target", "--state", str(self.state_path)], cwd=self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            proc.stdout.strip(),
            "/work continues at first non-completed task t2",
        )

    def test_future_schema_is_surfaced_instead_of_a_target(self) -> None:
        self.state_path.write_text(
            json.dumps(_state(schema_version=99)),
            encoding="utf-8",
        )
        proc = _run(["resume-target", "--state", str(self.state_path)], cwd=self.root)
        self.assertEqual(proc.returncode, 6)
        self.assertEqual(proc.stdout.strip(), "", "no target is printed when refused")
        self.assertIn("future-schema", proc.stderr)

    def test_missing_state_exits_two(self) -> None:
        proc = _run(["resume-target", "--state", str(self.state_path)], cwd=self.root)
        self.assertEqual(proc.returncode, 2)

    def test_reading_a_target_does_not_write_the_state(self) -> None:
        self.write_state(phase="review", cycle=2)
        before = self.state_path.read_bytes()
        proc = _run(["resume-target", "--state", str(self.state_path)], cwd=self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_bare_resume_target_walks_up_from_a_nested_cwd(self) -> None:
        self.write_state(phase="review", cycle=2)
        nested = self.root / "src" / "deep"
        nested.mkdir(parents=True)
        proc = _run(["resume-target"], cwd=nested)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "run review loop at cycle 2")


if __name__ == "__main__":
    unittest.main()
