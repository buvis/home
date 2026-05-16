"""Tests for autopilot_context_cap_hook.py.

Stdlib-only unittest, subprocess.run pattern (matches ~/.claude/hooks/tests/).
"""

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HOOK = Path(__file__).parent / "autopilot_context_cap_hook.py"


def _load_hook_module():
    """Load the hook as an importable module so its `main()` can be called
    in-process. Used by the perf test to time only the hook's work,
    excluding subprocess fork + Python interpreter startup."""
    spec = importlib.util.spec_from_file_location(
        "autopilot_context_cap_hook", HOOK
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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

    def test_marker_for_same_task_is_noop(self) -> None:
        """Marker carries the task id. When the in-progress task matches the
        marker, the hook is a no-op (already fired for this task)."""
        self.fx.write_state(
            phase="work",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=200_000)])
        (self.fx.autopilot_dir / ".cap-fired").write_text("task-x")
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

        marker = self.fx.autopilot_dir / ".cap-fired"
        self.assertTrue(marker.exists())
        # Marker carries the in-progress task id so the hook can self-clear
        # when the task changes between PostToolUse fires.
        self.assertEqual(marker.read_text().strip(), "task-x")

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

        # stall_reason must be set so /run-autopilot Phase 0 moves the PRD to
        # dev/local/prds/stalled/ on the next session. Without this the next
        # session re-enters Work on the same PRD and re-hits the cap.
        self.assertEqual(
            state["stall_reason"],
            {
                "stalled": "context_overrun",
                "task": "task-x",
                "total_input_tokens": 200_000,
            },
        )

        out = json.loads(result.stdout)
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("abort", out["hookSpecificOutput"]["additionalContext"].lower())
        # Abort instructions must reference stall_reason so the model knows
        # the hook already prepared the stall handoff.
        self.assertIn(
            "stall_reason", out["hookSpecificOutput"]["additionalContext"]
        )

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

    # Walk-up cases ---------------------------------------------------------

    def test_finds_autopilot_dir_when_cwd_is_subdirectory(self) -> None:
        """Hook must walk up from cwd to find dev/local/autopilot/.

        Same fix pattern as a0c5b8e09 for the stop hook: agent may cd into
        a subdirectory during work, so a relative `dev/local/autopilot`
        resolution from cwd must walk parents until found.
        """
        self.fx.write_state(
            phase="work",
            tasks=[{"id": "task-deep", "name": "x", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=200_000)])
        deep = self.fx.cwd / "src" / "modules" / "feature"
        deep.mkdir(parents=True)
        result = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps({"transcript_path": str(self.fx.transcript)}),
            capture_output=True,
            text=True,
            cwd=str(deep),
            timeout=5,
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue((self.fx.autopilot_dir / ".cap-fired").exists())
        self.assertTrue((self.fx.autopilot_dir / "task-abort").exists())

    def test_no_autopilot_ancestor_is_noop(self) -> None:
        """When cwd has no dev/local/autopilot ancestor, hook is a no-op."""
        with tempfile.TemporaryDirectory() as plain:
            plain_path = Path(plain)
            transcript = plain_path / "transcript.jsonl"
            transcript.write_text(json.dumps(self.fx.usage_line(input_tokens=200_000)) + "\n")
            result = subprocess.run(
                [sys.executable, str(HOOK)],
                input=json.dumps({"transcript_path": str(transcript)}),
                capture_output=True,
                text=True,
                cwd=plain,
                timeout=5,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "")

    def test_abort_entry_turn_is_sentinel_not_zero(self) -> None:
        """task_aborts[].turn must use -1 sentinel ('unknown') not a misleading 0.

        The transcript usage line carries no turn counter, so the hook cannot
        derive the real turn. Hardcoding 0 made every abort look like a
        first-turn failure. -1 matches the work-skill subagent_prompt_overrun
        convention for 'turn unknown'.
        """
        self.fx.write_state(phase="work")
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=200_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        abort_entry = json.loads(
            (self.fx.autopilot_dir / "task-abort").read_text().strip().splitlines()[-1]
        )
        self.assertEqual(abort_entry["turn"], -1)
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        self.assertEqual(state["task_aborts"][0]["turn"], -1)

    # Persistence-safety: hook bails on state-write failure -----------------

    def test_state_write_failure_skips_marker_log_and_envelope(self) -> None:
        """If state.json cannot be written, the hook MUST NOT emit the abort
        envelope and MUST NOT touch the .cap-fired marker.

        Otherwise the model writes task_aborted into the loop signal file
        without a corresponding state.stall_reason; the next session's
        Phase 0 finds nothing to recover, the original PRD stays in wip/,
        and the autopilot silently re-enters Work and re-hits the cap. The
        hook should rather no-op this PostToolUse and retry on the next
        one. Same hook contract as the cycle-4 stall_reason wiring: state
        write is the single source of truth for "abort has been prepared".
        """
        self.fx.write_state(
            phase="work",
            tasks=[{"id": "task-x", "name": "Big task", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([
            self.fx.usage_line(input_tokens=200_000),
        ])

        # Make state.json unwritable by removing write permission from its
        # parent directory: os.replace and Path.write_text into a 555 dir
        # both raise OSError. This is the simplest way to force
        # _atomic_write_state to fail without monkey-patching the module
        # under test. The existing state.json itself stays readable, so
        # _load_state still succeeds and the hook reaches the write step.
        original_mode = self.fx.autopilot_dir.stat().st_mode
        self.fx.autopilot_dir.chmod(0o555)
        self.addCleanup(self.fx.autopilot_dir.chmod, original_mode)

        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)

        # No abort envelope on stdout — the model never sees the abort
        # instruction, so it never writes task_aborted into the loop.
        self.assertEqual(result.stdout.strip(), "")

        # No .cap-fired marker either, so the next PostToolUse fires the
        # hook again and gets another chance to write state.
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())

        # task-abort log also untouched — abort log is only appended after
        # the state write succeeds.
        self.assertFalse((self.fx.autopilot_dir / "task-abort").exists())

        # Stderr should carry a diagnostic explaining the skip.
        self.assertIn("state.json write failed", result.stderr)

    # Race safety: merge-write preserves concurrent model edits ---------------

    def test_existing_task_aborts_preserved_on_merge_write(self) -> None:
        """Merge-write must append to existing task_aborts, not overwrite.

        If state.json already has aborts from a prior hook fire or a prior
        replan, the new entry must be appended, not the list replaced.
        """
        prior_abort = {
            "task_id": "task-prior",
            "turn": -1,
            "total_input_tokens": 100,
            "cause": "context_overrun",
        }
        self.fx.write_state(
            phase="work",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
            task_aborts=[prior_abort],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=200_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        self.assertEqual(len(state["task_aborts"]), 2)
        self.assertEqual(state["task_aborts"][0]["task_id"], "task-prior")
        self.assertEqual(state["task_aborts"][1]["task_id"], "task-x")

    def test_merge_write_preserves_non_abort_fields(self) -> None:
        """Merge-write must preserve fields the hook does not own.

        The hook writes task_aborts and stall_reason. All other fields
        (tasks_completed, tasks[].status, etc.) are owned by the model
        or /work; the hook must not overwrite them with stale values from
        its initial state read.

        Note: this test cannot simulate a true concurrent write (subprocess
        + no sync), but verifies that fields not touched by the hook survive
        the merge-write — the property the re-read achieves.
        """
        self.fx.write_state(
            phase="work",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
            tasks_completed=7,
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=200_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        self.assertEqual(state["tasks_completed"], 7)
        self.assertEqual(len(state["task_aborts"]), 1)

    # Abort-instruction robustness ------------------------------------------

    def test_abort_instructions_use_absolute_signal_path(self) -> None:
        """ABORT_INSTRUCTIONS must embed the absolute path to signal.

        The orchestrating agent may have cd'd into a subdirectory by abort
        time. A relative `dev/local/autopilot/signal` write would land in
        the wrong place and the stop-hook walk-up would miss it.
        """
        self.fx.write_state(phase="work")
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=200_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        out = json.loads(result.stdout)
        context = out["hookSpecificOutput"]["additionalContext"]
        expected = str(self.fx.autopilot_dir / "signal")
        self.assertIn(expected, context)
        # Negative: bare relative path must not appear (would still match
        # the absolute path as a substring; check the leading slash form).
        self.assertNotIn(" dev/local/autopilot/signal", context)

    def test_abort_instructions_gate_signal_on_autopilot_loop(self) -> None:
        """ABORT_INSTRUCTIONS must instruct the model to gate the signal
        write on $_AUTOPILOT_LOOP. Per SKILL.md "Loop Detection", writing
        the signal when the shell wrapper is absent SIGINTs the session
        with no restart, which surprises a manual /run-autopilot user.
        """
        self.fx.write_state(phase="work")
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=200_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        out = json.loads(result.stdout)
        context = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("$_AUTOPILOT_LOOP", context)

    # Performance ------------------------------------------------------------

    def test_hook_main_completes_under_100ms_in_process(self) -> None:
        """PRD 00024 sets a <100ms target on the hook itself. Time only the
        in-process `main()` work so the threshold tracks hook logic, not
        the ~50-80ms Python interpreter cold-start that a subprocess fork
        would add. A regression that scanned the full transcript instead of
        the 64KB tail would balloon the timing here even at this scale.

        The transcript is ~4.8 MB of noise followed by one **over-threshold**
        usage line at the tail. Using an over-threshold value lets the test
        assert that the hook actually parsed the tail and emitted the abort
        envelope — a regression that bailed out before reading the
        transcript would produce empty stdout and fail the assertion,
        regardless of how fast it ran.
        """
        self.fx.write_state(phase="work")
        line_blob = json.dumps({"type": "noise", "padding": "x" * 4_000}) + "\n"
        with self.fx.transcript.open("w") as f:
            for _ in range(1_200):
                f.write(line_blob)
            f.write(json.dumps(self.fx.usage_line(input_tokens=200_000)) + "\n")

        module = _load_hook_module()
        payload = json.dumps({"transcript_path": str(self.fx.transcript)})
        prev_stdin, prev_stdout, prev_cwd = sys.stdin, sys.stdout, os.getcwd()
        sys.stdin = io.StringIO(payload)
        captured_stdout = io.StringIO()
        sys.stdout = captured_stdout
        os.chdir(self.fx.cwd)
        try:
            start = time.perf_counter()
            module.main()
            elapsed_ms = (time.perf_counter() - start) * 1_000
        finally:
            sys.stdin = prev_stdin
            sys.stdout = prev_stdout
            os.chdir(prev_cwd)

        self.assertLess(elapsed_ms, 100, f"hook took {elapsed_ms:.0f}ms")
        # Proves the tail-read + parse code path actually ran. A regression
        # that bailed out before reading the transcript would leave stdout
        # empty and fail here, not on the timing assertion above.
        emitted = captured_stdout.getvalue()
        self.assertIn("hookSpecificOutput", emitted)
        self.assertIn("Context cap reached", emitted)


    # Marker self-clearing -------------------------------------------------

    def test_stale_marker_for_different_task_is_cleared_and_hook_fires(self) -> None:
        """When the in-progress task differs from the marker's task id, the
        hook must clear the stale marker and process the overrun. Otherwise
        a missed `/work` step-2 Bash clear would silently disable the cap
        for every task in the phase after the first abort.
        """
        self.fx.write_state(
            phase="work",
            tasks=[{"id": "task-new", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=200_000)])
        (self.fx.autopilot_dir / ".cap-fired").write_text("task-old")

        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)

        marker = self.fx.autopilot_dir / ".cap-fired"
        self.assertTrue(marker.exists())
        self.assertEqual(marker.read_text().strip(), "task-new")
        out = json.loads(result.stdout)
        self.assertIn("hookSpecificOutput", out)

    def test_marker_with_empty_contents_is_cleared(self) -> None:
        """A marker file from a pre-self-clearing version (touched, no
        contents) must not block the hook. Cleared and re-fired on a real
        overrun."""
        self.fx.write_state(
            phase="work",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=200_000)])
        (self.fx.autopilot_dir / ".cap-fired").touch()

        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        marker = self.fx.autopilot_dir / ".cap-fired"
        self.assertEqual(marker.read_text().strip(), "task-x")

    # Reverse-chunk tail search --------------------------------------------

    def test_finds_usage_line_after_large_tool_result(self) -> None:
        """A single large tool result (> 64KB) between the latest usage line
        and EOF used to push the usage line out of the fixed 64KB tail
        window, causing the cap to silently disengage. The chunked reverse
        scan keeps reading until a usage line is found.
        """
        self.fx.write_state(phase="work")
        # 200KB of noise (mixture of valid-shape lines and junk), then the
        # latest over-threshold usage line at EOF. Old TAIL_BYTES=64KB
        # would miss the usage line because the 200KB noise block precedes
        # it; with reverse-chunk reads the hook walks back until found.
        lines = []
        big_payload = "x" * 200_000
        lines.append({"type": "noise", "padding": big_payload})
        lines.append(self.fx.usage_line(input_tokens=200_000))
        self.fx.write_transcript_lines(lines)

        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertTrue((self.fx.autopilot_dir / ".cap-fired").exists())
        out = json.loads(result.stdout)
        self.assertIn("hookSpecificOutput", out)

    def test_reverse_scan_bounded_by_max_tail_bytes(self) -> None:
        """If the transcript is many MB and the latest usage line is buried
        deep, the hook still completes (it gives up at MAX_TAIL_BYTES). It
        should not crash, hang, or read the entire file. Verifies the cap
        is bounded.
        """
        self.fx.write_state(phase="work")
        with self.fx.transcript.open("w") as f:
            # The first line is the only usage line; everything after is
            # noise that pushes the usage line out of MAX_TAIL_BYTES.
            f.write(json.dumps(self.fx.usage_line(input_tokens=200_000)) + "\n")
            noise = json.dumps({"type": "noise", "padding": "x" * 100_000}) + "\n"
            # ~5MB of noise — more than MAX_TAIL_BYTES (4MB).
            for _ in range(50):
                f.write(noise)

        module = _load_hook_module()
        payload = json.dumps({"transcript_path": str(self.fx.transcript)})
        prev_stdin, prev_stdout, prev_cwd = sys.stdin, sys.stdout, os.getcwd()
        sys.stdin = io.StringIO(payload)
        captured = io.StringIO()
        sys.stdout = captured
        os.chdir(self.fx.cwd)
        try:
            start = time.perf_counter()
            module.main()
            elapsed_ms = (time.perf_counter() - start) * 1_000
        finally:
            sys.stdin = prev_stdin
            sys.stdout = prev_stdout
            os.chdir(prev_cwd)

        # No abort emitted — the usage line is beyond the MAX_TAIL_BYTES
        # window, so the hook treats this turn as "no recent usage info"
        # and stays silent. The hook MUST not hang or crash trying to
        # search the whole multi-MB file.
        self.assertEqual(captured.getvalue().strip(), "")
        # Bounded read should still complete fast — well under 500ms.
        self.assertLess(elapsed_ms, 500, f"hook took {elapsed_ms:.0f}ms")


if __name__ == "__main__":
    unittest.main()
