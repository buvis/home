"""Tests for autopilot_context_cap_hook.py.

Stdlib-only unittest, subprocess.run pattern (matches ~/.claude/hooks/tests/).
"""

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HOOK = Path(__file__).parent / "autopilot_context_cap_hook.py"


class HookFixture:
    """Sets up a working directory with dev/local/autopilot/ and a transcript."""

    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.autopilot_dir = self.cwd / "dev" / "local" / "autopilot"
        self.autopilot_dir.mkdir(parents=True, exist_ok=True)
        self.transcript = self.cwd / "transcript.jsonl"
        self.transcript.touch()

    def write_state(self, **fields: object) -> None:
        default: dict[str, object] = {
            "prd": "00099-test.md",
            "phase": "work",
            "phases_completed": [],
            "cycle": 1,
            "tasks_total": 0,
            "tasks_completed": 0,
            "tasks": [],
            "review_cycles": [],
            "autonomous_decisions": [],
            "deferred_decisions": [],
            "doubts": [],
            "task_aborts": [],
            "needs_attention": False,
        }
        default.update(fields)
        (self.autopilot_dir / "state.json").write_text(json.dumps(default))

    def write_transcript_lines(self, lines: list[dict]) -> None:
        with self.transcript.open("w") as f:
            for entry in lines:
                f.write(json.dumps(entry) + "\n")

    def usage_line(
        self,
        *,
        input_tokens: int = 0,
        cache_read: int = 0,
        cache_create: int = 0,
    ) -> dict:
        return {
            "type": "assistant",
            "message": {
                "usage": {
                    "input_tokens": input_tokens,
                    "cache_read_input_tokens": cache_read,
                    "cache_creation_input_tokens": cache_create,
                }
            },
        }

    def run_hook(self, stdin_payload: dict | None = None) -> subprocess.CompletedProcess:
        if stdin_payload is None:
            stdin_payload = {
                "session_id": "test-session",
                "transcript_path": str(self.transcript),
            }
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(stdin_payload),
            capture_output=True,
            text=True,
            cwd=str(self.cwd),
            timeout=5,
        )

    def cleanup(self) -> None:
        self.tmp.cleanup()


class ContextCapHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = HookFixture()
        self.addCleanup(self.fx.cleanup)

    # No-op cases ------------------------------------------------------------

    def test_no_state_json_is_noop(self) -> None:
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")

    def test_phase_not_work_is_noop(self) -> None:
        self.fx.write_state(phase="review")
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=200_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())

    def test_marker_file_present_is_noop(self) -> None:
        self.fx.write_state(phase="work")
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=200_000)])
        (self.fx.autopilot_dir / ".cap-fired").touch()
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")

    def test_usage_under_threshold_is_noop(self) -> None:
        self.fx.write_state(phase="work")
        self.fx.write_transcript_lines([
            self.fx.usage_line(input_tokens=50_000, cache_read=40_000, cache_create=10_000),
        ])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())

    def test_missing_transcript_path_field_is_noop(self) -> None:
        self.fx.write_state(phase="work")
        result = self.fx.run_hook(stdin_payload={"session_id": "x"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")

    def test_malformed_transcript_lines_is_noop(self) -> None:
        self.fx.write_state(phase="work")
        self.fx.transcript.write_text("not json\n{also not\n")
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())

    # Overrun cases ----------------------------------------------------------

    def test_overrun_writes_marker_and_state_and_stdout(self) -> None:
        self.fx.write_state(
            phase="work",
            tasks=[{"id": "task-x", "name": "Big task", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([
            self.fx.usage_line(input_tokens=100_000, cache_read=80_000, cache_create=20_000),
        ])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)

        self.assertTrue((self.fx.autopilot_dir / ".cap-fired").exists())

        abort_log = self.fx.autopilot_dir / "task-abort"
        self.assertTrue(abort_log.exists())
        abort_entry = json.loads(abort_log.read_text().strip().splitlines()[-1])
        self.assertEqual(abort_entry["cause"], "context_overrun")
        self.assertEqual(abort_entry["total_input_tokens"], 200_000)
        self.assertEqual(abort_entry["task_id"], "task-x")

        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        self.assertEqual(len(state["task_aborts"]), 1)
        self.assertEqual(state["task_aborts"][0]["cause"], "context_overrun")
        self.assertEqual(state["task_aborts"][0]["total_input_tokens"], 200_000)

        out = json.loads(result.stdout)
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("abort", out["hookSpecificOutput"]["additionalContext"].lower())

    def test_overrun_uses_most_recent_usage_line(self) -> None:
        self.fx.write_state(phase="work")
        self.fx.write_transcript_lines([
            self.fx.usage_line(input_tokens=50_000),
            {"type": "user", "message": {"content": "noise"}},
            self.fx.usage_line(input_tokens=200_000),
        ])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertTrue((self.fx.autopilot_dir / ".cap-fired").exists())
        out = json.loads(result.stdout)
        self.assertIn("hookSpecificOutput", out)

    def test_overrun_with_no_in_progress_task_uses_unknown(self) -> None:
        self.fx.write_state(phase="work", tasks=[])
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=200_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        abort_entry = json.loads(
            (self.fx.autopilot_dir / "task-abort").read_text().strip().splitlines()[-1]
        )
        self.assertEqual(abort_entry["task_id"], "unknown")

    # Performance ------------------------------------------------------------

    def test_completes_quickly_on_large_transcript(self) -> None:
        self.fx.write_state(phase="work")
        line_blob = json.dumps({"type": "noise", "padding": "x" * 4_000}) + "\n"
        with self.fx.transcript.open("w") as f:
            for _ in range(1_200):
                f.write(line_blob)
            f.write(json.dumps(self.fx.usage_line(input_tokens=50_000)) + "\n")
        start = time.perf_counter()
        result = self.fx.run_hook()
        elapsed_ms = (time.perf_counter() - start) * 1_000
        self.assertEqual(result.returncode, 0)
        self.assertLess(elapsed_ms, 1_500, f"hook took {elapsed_ms:.0f}ms")


if __name__ == "__main__":
    unittest.main()
