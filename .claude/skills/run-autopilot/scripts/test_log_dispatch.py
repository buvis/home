"""Tests for log_dispatch.py — schema validity, env-var gating, atomicity, always-exit-0."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = Path(__file__).parent / "log_dispatch.py"

VALID_FIELDS = {"ts", "prd", "task_id", "task_name", "dispatch_type", "model", "outcome", "duration_s", "attempt"}
VALID_DISPATCH_TYPES = {"tess", "ivan", "devon", "reviewer", "codex", "gemini"}
VALID_OUTCOMES = {"completed", "hung", "timeout", "context_overrun", "subagent_prompt_overrun", "error", "infra_failure"}

BASE_ARGS = [
    "--prd", "00001-test.md",
    "--task-id", "T1",
    "--task-name", "Write tests",
    "--dispatch-type", "codex",
    "--model", "o3",
    "--outcome", "completed",
    "--duration-s", "42.5",
    "--attempt", "1",
]


def _make_tree() -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "dev" / "local" / "autopilot").mkdir(parents=True)
    return root


def _invoke(
    root: Path,
    loop_value: str | None = "1",
    extra_args: list[str] | None = None,
    args: list[str] | None = None,
) -> subprocess.CompletedProcess:
    """Run log_dispatch.py from root; set _AUTOPILOT_LOOP to loop_value (None = unset).

    When `args` is given it replaces BASE_ARGS entirely; otherwise BASE_ARGS plus
    any `extra_args` are used.
    """
    env = {k: v for k, v in os.environ.items() if k != "_AUTOPILOT_LOOP"}
    if loop_value is not None:
        env["_AUTOPILOT_LOOP"] = loop_value
    cmd_args = args if args is not None else BASE_ARGS + (extra_args or [])
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + cmd_args,
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
    )


def _log_file(root: Path) -> Path:
    return root / "dev" / "local" / "autopilot" / "dispatch-log.jsonl"


class TestLoopGating(unittest.TestCase):
    def setUp(self) -> None:
        self._root = _make_tree()

    def tearDown(self) -> None:
        shutil.rmtree(str(self._root), ignore_errors=True)

    def test_noop_when_loop_unset(self) -> None:
        result = _invoke(self._root, loop_value=None)
        self.assertEqual(result.returncode, 0)
        self.assertFalse(
            _log_file(self._root).exists(),
            "log must not be created when _AUTOPILOT_LOOP is unset",
        )

    def test_noop_when_loop_empty_string(self) -> None:
        result = _invoke(self._root, loop_value="")
        self.assertEqual(result.returncode, 0)
        self.assertFalse(
            _log_file(self._root).exists(),
            "log must not be created when _AUTOPILOT_LOOP is empty",
        )

    def test_appends_one_line_when_loop_set(self) -> None:
        result = _invoke(self._root, loop_value="12345")
        self.assertEqual(result.returncode, 0)
        log = _log_file(self._root)
        self.assertTrue(log.exists(), "log file must be created when _AUTOPILOT_LOOP is set")
        lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1, "exactly one line must be appended per invocation")


class TestSchemaValidity(unittest.TestCase):
    def setUp(self) -> None:
        self._root = _make_tree()

    def tearDown(self) -> None:
        shutil.rmtree(str(self._root), ignore_errors=True)

    def _get_record(self) -> dict:
        _invoke(self._root, loop_value="1")
        line = _log_file(self._root).read_text().strip()
        return json.loads(line)

    def test_record_has_exactly_nine_fields(self) -> None:
        record = self._get_record()
        self.assertEqual(
            set(record.keys()),
            VALID_FIELDS,
            f"field mismatch: {set(record.keys()) ^ VALID_FIELDS}",
        )

    def test_ts_is_iso8601_utc_string(self) -> None:
        before = datetime.now(timezone.utc)
        record = self._get_record()
        after = datetime.now(timezone.utc)

        ts_raw: str = record["ts"]
        self.assertIsInstance(ts_raw, str)
        self.assertTrue(
            ts_raw.endswith("Z") or ts_raw.endswith("+00:00"),
            f"ts must be ISO 8601 UTC, got: {ts_raw!r}",
        )

        # Normalise trailing Z so fromisoformat can parse it (Python < 3.11 rejects Z).
        ts_normalized = ts_raw.replace("Z", "+00:00")
        try:
            ts_dt = datetime.fromisoformat(ts_normalized)
        except ValueError as exc:
            self.fail(f"ts is not a valid ISO 8601 string: {ts_raw!r} — {exc}")

        # The timestamp must be recent, not a hardcoded sentinel like 2000-01-01.
        # Allow 5 s of slack for slow CI environments.
        slack = 5.0
        self.assertGreaterEqual(
            ts_dt.timestamp(),
            before.timestamp() - slack,
            f"ts {ts_raw!r} predates invocation by more than {slack} s — looks hardcoded",
        )
        self.assertLessEqual(
            ts_dt.timestamp(),
            after.timestamp() + slack,
            f"ts {ts_raw!r} is in the future relative to invocation",
        )

    def test_dispatch_type_is_valid_enum(self) -> None:
        record = self._get_record()
        self.assertIn(record["dispatch_type"], VALID_DISPATCH_TYPES)

    def test_outcome_is_valid_enum(self) -> None:
        record = self._get_record()
        self.assertIn(record["outcome"], VALID_OUTCOMES)

    def test_duration_s_is_positive_number(self) -> None:
        record = self._get_record()
        self.assertIsInstance(record["duration_s"], (int, float))
        self.assertGreater(record["duration_s"], 0)

    def test_attempt_is_integer(self) -> None:
        record = self._get_record()
        self.assertIsInstance(record["attempt"], int)

    def test_field_values_match_args(self) -> None:
        record = self._get_record()
        self.assertEqual(record["prd"], "00001-test.md")
        self.assertEqual(record["task_id"], "T1")
        self.assertEqual(record["task_name"], "Write tests")
        self.assertEqual(record["dispatch_type"], "codex")
        self.assertEqual(record["model"], "o3")
        self.assertEqual(record["outcome"], "completed")
        self.assertAlmostEqual(float(record["duration_s"]), 42.5, places=3)
        self.assertEqual(record["attempt"], 1)

    def test_field_values_round_trip_distinct_args(self) -> None:
        """All nine arg-derived fields must reflect the actual CLI args, not hardcoded defaults."""
        distinct_args = [
            "--prd", "99999-other.md",
            "--task-id", "T-XYZ",
            "--task-name", "A Different Name",
            "--dispatch-type", "gemini",
            "--model", "claude-sentinel-42",
            "--outcome", "hung",
            "--duration-s", "7.25",
            "--attempt", "3",
        ]
        result = _invoke(self._root, loop_value="1", args=distinct_args)
        self.assertEqual(result.returncode, 0, f"stderr={result.stderr!r}")
        line = _log_file(self._root).read_text().strip()
        record = json.loads(line)
        self.assertEqual(record["prd"], "99999-other.md")
        self.assertEqual(record["task_id"], "T-XYZ")
        self.assertEqual(record["task_name"], "A Different Name")
        self.assertEqual(record["dispatch_type"], "gemini")
        self.assertEqual(record["model"], "claude-sentinel-42")
        self.assertEqual(record["outcome"], "hung")
        self.assertAlmostEqual(float(record["duration_s"]), 7.25, places=3)
        self.assertEqual(record["attempt"], 3)


class TestWalkUpResolution(unittest.TestCase):
    """log_dispatch must walk up from cwd to find dev/local/autopilot/, not hard-code Path.cwd()."""

    def setUp(self) -> None:
        self._root = _make_tree()
        # Nested subdir that does NOT itself contain dev/local/autopilot.
        nested = self._root / "a" / "b" / "c"
        nested.mkdir(parents=True)
        self._nested = nested

    def tearDown(self) -> None:
        shutil.rmtree(str(self._root), ignore_errors=True)

    def test_appends_to_log_when_cwd_is_nested_subdir(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "_AUTOPILOT_LOOP"}
        env["_AUTOPILOT_LOOP"] = "1"
        result = subprocess.run(
            [sys.executable, str(SCRIPT)] + BASE_ARGS,
            cwd=str(self._nested),
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, f"stderr={result.stderr!r}")

        log = _log_file(self._root)
        self.assertTrue(
            log.exists(),
            "dispatch-log.jsonl must be written to the ancestor's dev/local/autopilot/, not cwd",
        )
        lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1, "exactly one line must be appended")
        record = json.loads(lines[0])
        self.assertEqual(set(record.keys()), VALID_FIELDS)


class TestMultipleAppends(unittest.TestCase):
    def setUp(self) -> None:
        self._root = _make_tree()

    def tearDown(self) -> None:
        shutil.rmtree(str(self._root), ignore_errors=True)

    def test_two_sequential_appends_produce_two_lines(self) -> None:
        env = {**os.environ, "_AUTOPILOT_LOOP": "1"}
        first_args = [
            "--prd", "00001-test.md", "--task-id", "T1",
            "--task-name", "first-task",
            "--dispatch-type", "codex", "--model", "o3",
            "--outcome", "completed", "--duration-s", "1.0", "--attempt", "1",
        ]
        second_args = [
            "--prd", "00001-test.md", "--task-id", "T2",
            "--task-name", "second-task",
            "--dispatch-type", "codex", "--model", "o3",
            "--outcome", "completed", "--duration-s", "2.0", "--attempt", "1",
        ]
        subprocess.run([sys.executable, str(SCRIPT)] + first_args, cwd=str(self._root), env=env, capture_output=True, text=True)
        subprocess.run([sys.executable, str(SCRIPT)] + second_args, cwd=str(self._root), env=env, capture_output=True, text=True)
        lines = [ln for ln in _log_file(self._root).read_text().splitlines() if ln.strip()]
        self.assertEqual(len(lines), 2)
        records = [json.loads(ln) for ln in lines]
        for record in records:
            self.assertEqual(set(record.keys()), VALID_FIELDS)
        self.assertEqual(records[0]["task_name"], "first-task")
        self.assertEqual(records[1]["task_name"], "second-task")


class TestConcurrentWrites(unittest.TestCase):
    def setUp(self) -> None:
        self._root = _make_tree()

    def tearDown(self) -> None:
        shutil.rmtree(str(self._root), ignore_errors=True)

    def test_two_concurrent_writers_produce_two_intact_lines(self) -> None:
        env = {**os.environ, "_AUTOPILOT_LOOP": "99"}
        cmd = [sys.executable, str(SCRIPT)] + BASE_ARGS

        p1 = subprocess.Popen(cmd, cwd=str(self._root), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p2 = subprocess.Popen(cmd, cwd=str(self._root), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p1.wait()
        p2.wait()

        self.assertEqual(p1.returncode, 0)
        self.assertEqual(p2.returncode, 0)

        log = _log_file(self._root)
        self.assertTrue(log.exists())
        lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
        self.assertEqual(len(lines), 2, f"expected 2 lines, got {len(lines)}")

        for line in lines:
            record = json.loads(line)  # raises on truncation/interleaving
            self.assertEqual(set(record.keys()), VALID_FIELDS)

    def test_many_concurrent_writers_produce_all_intact_lines(self) -> None:
        """30 concurrent writers produce exactly 30 valid JSON lines — real locking required."""
        n = 30
        env = {**os.environ, "_AUTOPILOT_LOOP": "99"}
        cmd = [sys.executable, str(SCRIPT)] + BASE_ARGS

        procs = [
            subprocess.Popen(cmd, cwd=str(self._root), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for _ in range(n)
        ]
        for p in procs:
            p.wait()

        for i, p in enumerate(procs):
            self.assertEqual(p.returncode, 0, f"process {i} exited non-zero: {p.returncode}")

        log = _log_file(self._root)
        self.assertTrue(log.exists())
        lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
        self.assertEqual(len(lines), n, f"expected {n} lines, got {len(lines)}")

        for i, line in enumerate(lines):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                self.fail(f"line {i} is not valid JSON (truncated/interleaved?): {exc}\n{line!r}")
            self.assertEqual(
                set(record.keys()),
                VALID_FIELDS,
                f"line {i} has wrong fields: {set(record.keys()) ^ VALID_FIELDS}",
            )


class TestAlwaysExitsZero(unittest.TestCase):
    def setUp(self) -> None:
        self._root = _make_tree()

    def tearDown(self) -> None:
        shutil.rmtree(str(self._root), ignore_errors=True)

    def test_exits_zero_on_malformed_duration(self) -> None:
        env = {**os.environ, "_AUTOPILOT_LOOP": "1"}
        bad_args = [
            "--prd", "x", "--task-id", "T1", "--task-name", "N",
            "--dispatch-type", "codex", "--model", "m",
            "--outcome", "completed", "--duration-s", "not-a-number",
            "--attempt", "1",
        ]
        result = subprocess.run(
            [sys.executable, str(SCRIPT)] + bad_args,
            cwd=str(self._root),
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, f"must exit 0 on bad arg; stderr={result.stderr!r}")

        # CONTRACT: malformed argument -> exit 0 AND no line written.
        log = _log_file(self._root)
        if log.exists():
            lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
            self.assertEqual(
                len(lines),
                0,
                "malformed duration must not append any line to the log",
            )

    def test_exits_zero_on_invalid_dispatch_type_enum(self) -> None:
        """Unrecognised dispatch-type is malformed: exit 0, no line written."""
        env = {**os.environ, "_AUTOPILOT_LOOP": "1"}
        bad_args = [
            "--prd", "x", "--task-id", "T1", "--task-name", "N",
            "--dispatch-type", "bogus",
            "--model", "m",
            "--outcome", "completed", "--duration-s", "1.0",
            "--attempt", "1",
        ]
        result = subprocess.run(
            [sys.executable, str(SCRIPT)] + bad_args,
            cwd=str(self._root),
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, f"must exit 0 on invalid enum; stderr={result.stderr!r}")

        log = _log_file(self._root)
        if log.exists():
            lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
            self.assertEqual(len(lines), 0, "invalid dispatch-type must not append any line")

    def test_exits_zero_on_invalid_outcome_enum(self) -> None:
        """Unrecognised outcome is malformed: exit 0, no line written."""
        env = {**os.environ, "_AUTOPILOT_LOOP": "1"}
        bad_args = [
            "--prd", "x", "--task-id", "T1", "--task-name", "N",
            "--dispatch-type", "codex",
            "--model", "m",
            "--outcome", "not_a_real_outcome", "--duration-s", "1.0",
            "--attempt", "1",
        ]
        result = subprocess.run(
            [sys.executable, str(SCRIPT)] + bad_args,
            cwd=str(self._root),
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, f"must exit 0 on invalid enum; stderr={result.stderr!r}")

        log = _log_file(self._root)
        if log.exists():
            lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
            self.assertEqual(len(lines), 0, "invalid outcome must not append any line")

    def test_exits_zero_when_loop_unset(self) -> None:
        result = _invoke(self._root, loop_value=None)
        self.assertEqual(result.returncode, 0)

    def test_exits_zero_when_loop_empty(self) -> None:
        result = _invoke(self._root, loop_value="")
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
