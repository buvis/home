#!/usr/bin/env python3
"""Tests for the two re-export shims left by PRD 00089.

`scripts/statectl.py` and `scripts/resume_target.py` keep their paths because
~100 call sites name them, but their implementations moved into `cli/`. Two
things need pinning that the existing suites cannot see:

1. Every re-exported name is the SAME OBJECT as its `cli` counterpart, not a
   copy. Identity is the assertion that matters for the exception classes: if
   the shim defined its own `StateError`, `except StateError` in a caller
   would silently miss the one the boundary raises, and an exit-2 failure
   would surface as an uncaught traceback.
2. The rejection the move introduced - a mutation whose OWN field value is
   malformed - together with the thing that must NOT have changed: an
   unrelated pre-existing odd field still blocks nothing.

The regression gate on the shims proper is that `test_statectl.py`,
`test_autopilot_resume.py` and `test_golden_contracts.py` all pass unmodified.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPTS.parent
STATECTL = SCRIPTS / "statectl.py"

sys.path.insert(0, str(SKILL_ROOT))

from cli import resume as cli_resume
from cli import schema as cli_schema
from cli import state as cli_state
from cli import statectl as cli_statectl


def _load(name: str, path: Path):
    """Import a helper module by file path, the way test_golden_contracts.py
    does - so the shim is exercised through the same entry a caller uses."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


statectl = _load("statectl_shim", STATECTL)
resume_target = _load("resume_target_shim", SCRIPTS / "resume_target.py")


class StatectlShimSymbolTests(unittest.TestCase):
    def test_every_documented_symbol_is_re_exported(self) -> None:
        # The PRD names these seven as the shim's surface; fablectl imports
        # atomic_write, test_golden_contracts imports read_and_parse.
        for name in (
            "read_and_parse",
            "atomic_write",
            "mutate",
            "parse_path",
            "get_value",
            "StateError",
            "UsageError",
        ):
            with self.subTest(name=name):
                self.assertTrue(hasattr(statectl, name), f"shim lost {name}")

    def test_each_re_export_is_the_same_object_not_a_copy(self) -> None:
        for name in statectl.__all__:
            with self.subTest(name=name):
                self.assertIs(getattr(statectl, name), getattr(cli_statectl, name))

    def test_state_error_is_the_boundary_class_itself(self) -> None:
        # A parallel class here would make `except StateError` miss the real
        # one and turn an exit-2 into a traceback.
        self.assertIs(statectl.StateError, cli_state.StateError)

    def test_atomic_write_stays_schema_free_for_non_state_callers(self) -> None:
        # fablectl writes its own ledger with this. It must not be stamped
        # with schema_version or run through a state validator.
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.json"
            payload = {"00089-x.md": {"status": "requested"}}
            statectl.atomic_write(ledger, payload)
            written = json.loads(ledger.read_text(encoding="utf-8"))
        self.assertEqual(written, payload)
        self.assertNotIn("schema_version", written)

    def test_every_usage_line_appears_in_the_shim_docstring(self) -> None:
        # Bidirectional: substring-in-docstring only proves every USAGE form
        # is documented, it cannot catch an EXTRA form the docstring lists
        # that USAGE (the CLI's real verb set) does not - so drift in either
        # direction must fail, not just the "something's missing" direction.
        usage_forms = {
            line.split("statectl.py ", 1)[1] for line in cli_statectl.USAGE.splitlines()
        }
        docstring_forms = {
            line.split("statectl.py ", 1)[1]
            for line in statectl.__doc__.splitlines()
            if "python3 statectl.py " in line
        }
        self.assertEqual(usage_forms, docstring_forms)


class ResumeTargetShimSymbolTests(unittest.TestCase):
    def test_both_functions_are_the_absorbed_objects(self) -> None:
        self.assertIs(resume_target.resume_target, cli_resume.resume_target)
        self.assertIs(resume_target.park_decision, cli_resume.park_decision)

    def test_importing_the_shim_does_not_shadow_the_real_cli_package(self) -> None:
        # The shim inserts the skill root at the FRONT of sys.path; the module
        # it resolves must be the one beside it, not some other `cli`.
        self.assertEqual(
            Path(cli_resume.__file__).resolve().parent.parent,
            SKILL_ROOT,
        )


class ShimValidationTests(unittest.TestCase):
    """The behavior the move introduced, through the real CLI process."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name) / "state.json"

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(STATECTL), str(self.state), *args],
            capture_output=True,
            text=True,
        )

    def write(self, obj: dict) -> None:
        self.state.write_text(json.dumps(obj), encoding="utf-8")

    def test_malformed_value_for_the_targeted_field_is_rejected_loudly(self) -> None:
        self.write({"phase": "build"})
        before = self.state.read_bytes()
        result = self.run_cli("set", "phase", json.dumps("nonsense"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("phase", result.stderr)
        self.assertEqual(
            self.state.read_bytes(),
            before,
            "a rejected write must change nothing",
        )

    def test_unrelated_pre_existing_odd_field_blocks_nothing(self) -> None:
        # The forensic hand-edit case. One bad field must not wedge every
        # later write, which whole-state validation would do.
        self.write({"cycle": "not-an-int", "phase": "build"})
        result = self.run_cli("set", "phase", json.dumps("review"))
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(state["phase"], "review")
        self.assertEqual(state["cycle"], "not-an-int", "left exactly as found")

    def test_deleting_a_field_still_works(self) -> None:
        # Every schema rule is "if present, must match"; `del` must stay legal.
        self.write({"phase": "build", "keep": 1})
        self.assertEqual(self.run_cli("del", "phase").returncode, 0)
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertNotIn("phase", state)
        self.assertEqual(state["keep"], 1)

    def test_a_valid_value_for_a_schema_field_still_lands(self) -> None:
        self.write({"phase": "build", "cycle": 1})
        self.assertEqual(self.run_cli("set", "cycle", "3").returncode, 0)
        self.assertEqual(
            json.loads(self.state.read_text(encoding="utf-8"))["cycle"],
            3,
        )

    def test_unvalidated_fields_pass_through_untouched(self) -> None:
        # stall_reason and contract_card carry no schema rule; the live prose
        # writes both, and neither may start failing.
        self.write({"phase": "build"})
        payload = json.dumps({"stalled": "oversized_task", "task": "t1"})
        result = self.run_cli("set", "stall_reason", payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(self.state.read_text(encoding="utf-8"))["stall_reason"],
            json.loads(payload),
        )

    def test_future_schema_version_is_refused_with_exit_code_6_and_leaves_state_untouched(
        self,
    ) -> None:
        # 999 is greater than cli.schema.SCHEMA_VERSION (currently 1), so
        # this state is "future" by cli.schema.version_status().
        self.write({"schema_version": 999, "phase": "build", "cycle": 3})
        before = self.state.read_bytes()
        bak_path = Path(f"{self.state}.bak")

        result = self.run_cli("set", "phase", json.dumps("review"))

        self.assertEqual(result.returncode, 6, result.stderr)
        # Both writers of state.json now refuse a future schema with exit
        # code 6; they must print the SAME wording. Assert it EXACTLY, not
        # by substring -- a substring check still passes on a message with
        # the right pieces in the wrong order or padded with noise, which
        # is what let the two writers diverge in the first place.
        self.assertEqual(
            result.stderr,
            f"autopilot: future-schema state.json ({self.state}): "
            f"v999 > v{cli_schema.SCHEMA_VERSION}, refusing\n",
        )
        self.assertEqual(
            self.state.read_bytes(),
            before,
            "a future-schema state must not be mutated",
        )
        self.assertFalse(
            bak_path.exists(),
            "a future-schema refusal must not write a new .bak file",
        )

    def test_rejection_raises_the_schema_error_class(self) -> None:
        # Pinned in-process too, so the exit-1 mapping above cannot be the
        # only thing holding the contract up.
        self.write({"phase": "build"})
        with self.assertRaises(cli_schema.SchemaError):
            statectl.mutate(
                self.state,
                lambda data: data.__setitem__("phase", "nonsense"),
            )


FABLECTL = SCRIPTS / "fablectl.py"

# fablectl.py has no counterpart import in this file (unlike cli_statectl); the
# task notes a literal comparison is an acceptable alternative to importing
# it, and importing it here would need SCRIPTS on sys.path too - fablectl.py
# does `from statectl import atomic_write`, a bare top-level import that only
# resolves when the scripts/ dir itself is on the path, not just its parent.
FABLECTL_USAGE = (
    "usage: fablectl.py <ledger> "
    "request <prd> <task_id> <task_name> <batch_id> <json>"
    " | decide <prd> approved|rejected | consume <prd> | show <prd>"
)


class ShimHelpFlagTests(unittest.TestCase):
    """`-h`/`--help` handling added to statectl.py and fablectl.py's `main()`.

    Both checks are scoped to argv[0] specifically, not "argv contains
    -h/--help anywhere" - so a flag that lands anywhere but first must keep
    falling through to the existing verb/arity handling, untouched.
    """

    def test_statectl_long_help_flag_exits_zero_with_usage_on_stdout_and_silent_stderr(
        self,
    ) -> None:
        result = subprocess.run(
            [sys.executable, str(STATECTL), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, cli_statectl.USAGE + "\n")
        self.assertEqual(result.stderr, "")

    def test_statectl_short_help_flag_exits_zero_with_usage_on_stdout_and_silent_stderr(
        self,
    ) -> None:
        result = subprocess.run(
            [sys.executable, str(STATECTL), "-h"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, cli_statectl.USAGE + "\n")
        self.assertEqual(result.stderr, "")

    def test_statectl_zero_args_still_exits_one_with_usage_on_stderr_and_silent_stdout(
        self,
    ) -> None:
        # Regression pin: the too-few-args path must not have moved.
        result = subprocess.run(
            [sys.executable, str(STATECTL)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, cli_statectl.USAGE + "\n")
        self.assertEqual(result.stdout, "")

    def test_statectl_help_flag_in_non_first_position_does_not_trigger_help_path(
        self,
    ) -> None:
        # argv[0] here is a state path, not "--help"; the check is scoped to
        # the first argument only, so this must fall through to the ordinary
        # too-few-args handling (exit 1, USAGE on stderr) rather than the
        # help path (exit 0, USAGE on stdout).
        result = subprocess.run(
            [sys.executable, str(STATECTL), "/tmp/does-not-matter.json", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, cli_statectl.USAGE + "\n")

    def test_fablectl_long_help_flag_exits_zero_with_usage_on_stdout_and_silent_stderr(
        self,
    ) -> None:
        result = subprocess.run(
            [sys.executable, str(FABLECTL), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, FABLECTL_USAGE + "\n")
        self.assertEqual(result.stderr, "")

    def test_fablectl_short_help_flag_exits_zero_with_usage_on_stdout_and_silent_stderr(
        self,
    ) -> None:
        result = subprocess.run(
            [sys.executable, str(FABLECTL), "-h"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, FABLECTL_USAGE + "\n")
        self.assertEqual(result.stderr, "")

    def test_fablectl_zero_args_still_exits_one_with_usage_on_stderr_and_silent_stdout(
        self,
    ) -> None:
        result = subprocess.run(
            [sys.executable, str(FABLECTL)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, FABLECTL_USAGE + "\n")
        self.assertEqual(result.stdout, "")

    def test_fablectl_help_flag_in_non_first_position_does_not_trigger_help_path(
        self,
    ) -> None:
        # argv[0] is a ledger path here, so this must fall through to the
        # ordinary verb-lookup path ("--help" is not a known verb) rather
        # than the help path.
        result = subprocess.run(
            [sys.executable, str(FABLECTL), "/tmp/does-not-matter.json", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("unsupported verb", result.stderr)


if __name__ == "__main__":
    unittest.main()
