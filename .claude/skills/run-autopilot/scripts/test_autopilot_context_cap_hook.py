"""Tests for autopilot_context_cap_hook.py.

Stdlib-only unittest, subprocess.run pattern (matches ~/.claude/hooks/tests/).
"""

import contextlib
import importlib.util
import inspect
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


def _loop_env() -> dict[str, str]:
    """Env for a loop-wrapped session. The hook is guarded on
    $_AUTOPILOT_LOOP (2026-07-19: interactive sessions sharing a cwd tree
    with parked autopilot state must never rotate/stall it), so tests that
    exercise the firing paths must run inside a simulated loop env."""
    env = dict(os.environ)
    env["_AUTOPILOT_LOOP"] = "test-loop"
    return env


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
            "phase": "build",
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
            "cap_rotations": [],
            "replan_count": 0,
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

    def run_hook(
        self, stdin_payload: dict | None = None, *, in_loop: bool = True
    ) -> subprocess.CompletedProcess:
        if stdin_payload is None:
            stdin_payload = {
                "session_id": "test-session",
                "transcript_path": str(self.transcript),
            }
        env = _loop_env()
        if not in_loop:
            env.pop("_AUTOPILOT_LOOP", None)
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(stdin_payload),
            capture_output=True,
            text=True,
            cwd=str(self.cwd),
            timeout=5,
            env=env,
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

    def test_phase_not_build_is_noop(self) -> None:
        """The gate is the `build` phase. Over the cap on any other gate
        (here `review`) is a no-op — only `build` runs /work tasks."""
        self.fx.write_state(phase="review")
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())

    def test_noops_on_work_phase(self) -> None:
        """`work` is the now-dead pre-collapse phase name (folded into
        `build`). Over the cap with phase=="work" must NOT fire."""
        self.fx.write_state(
            phase="work",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())

    def test_marker_for_same_task_is_noop(self) -> None:
        """Marker carries the task id. When the in-progress task matches the
        marker, the hook is a no-op (already fired for this task)."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        (self.fx.autopilot_dir / ".cap-fired").write_text("task-x")
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")

    def test_usage_under_threshold_is_noop(self) -> None:
        self.fx.write_state(phase="build")
        self.fx.write_transcript_lines([
            self.fx.usage_line(input_tokens=50_000, cache_read=40_000, cache_create=10_000),
        ])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())

    def test_missing_transcript_path_field_is_noop(self) -> None:
        self.fx.write_state(phase="build")
        result = self.fx.run_hook(stdin_payload={"session_id": "x"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")

    def test_malformed_transcript_lines_is_noop(self) -> None:
        self.fx.write_state(phase="build")
        self.fx.transcript.write_text("not json\n{also not\n")
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())

    # Loop guard -------------------------------------------------------------

    def test_interactive_session_is_noop_even_over_cap(self) -> None:
        """2026-07-19 regression: without $_AUTOPILOT_LOOP the hook must not
        touch parked autopilot state, even far over the cap. An interactive
        session sharing the cwd tree with a parked batch wrote rotations and
        a bogus oversized-task stall into that batch's state.json."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        before = (self.fx.autopilot_dir / "state.json").read_text()
        result = self.fx.run_hook(in_loop=False)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")
        self.assertEqual(
            (self.fx.autopilot_dir / "state.json").read_text(), before
        )
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())
        self.assertFalse(
            (self.fx.autopilot_dir / ".handoff-requested").exists()
        )

    # Single hard cap --------------------------------------------------------

    def test_does_not_fire_below_cap(self) -> None:
        """The single hard cap is 150K; usage below it does not fire (no
        window classification — the same cap applies regardless of model)."""
        self.fx.write_state(phase="build")
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=100_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())

    def test_fires_above_cap(self) -> None:
        """Usage above the single 150K hard cap fires the rotation."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-big", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertTrue((self.fx.autopilot_dir / ".cap-fired").exists())
        out = json.loads(result.stdout)
        self.assertIn("hookSpecificOutput", out)

    # Walk-up cases ---------------------------------------------------------

    def test_finds_autopilot_dir_when_cwd_is_subdirectory(self) -> None:
        """Hook must walk up from cwd to find dev/local/autopilot/.

        Same fix pattern as a0c5b8e09 for the stop hook: agent may cd into
        a subdirectory during work, so a relative `dev/local/autopilot`
        resolution from cwd must walk parents until found.
        """
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-deep", "name": "x", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        deep = self.fx.cwd / "src" / "modules" / "feature"
        deep.mkdir(parents=True)
        result = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps({"transcript_path": str(self.fx.transcript)}),
            capture_output=True,
            text=True,
            cwd=str(deep),
            timeout=5,
            env=_loop_env(),
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue((self.fx.autopilot_dir / ".cap-fired").exists())
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        self.assertEqual(state["cap_rotations"][-1]["task_id"], "task-deep")

    def test_no_autopilot_ancestor_is_noop(self) -> None:
        """When cwd has no dev/local/autopilot ancestor, hook is a no-op."""
        with tempfile.TemporaryDirectory() as plain:
            plain_path = Path(plain)
            transcript = plain_path / "transcript.jsonl"
            transcript.write_text(json.dumps(self.fx.usage_line(input_tokens=600_000)) + "\n")
            result = subprocess.run(
                [sys.executable, str(HOOK)],
                input=json.dumps({"transcript_path": str(transcript)}),
                capture_output=True,
                text=True,
                cwd=plain,
                timeout=5,
                env=_loop_env(),
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "")

    # Symlink and unreadable-path edge cases ---------------------------------

    def test_dangling_symlink_at_autopilot_path_is_noop(self) -> None:
        """A dangling symlink where dev/local/autopilot/ would be must not
        be returned as the autopilot dir. is_dir() returns False on dangling
        symlinks, so the walk-up skips it and returns None, making the hook
        a no-op (no valid autopilot dir found).
        """
        with tempfile.TemporaryDirectory() as plain:
            plain_path = Path(plain)
            ap_dir = plain_path / "dev" / "local" / "autopilot"
            ap_dir.parent.mkdir(parents=True)
            os.symlink("/nonexistent/path/that/does/not/exist", str(ap_dir))
            transcript = plain_path / "t.jsonl"
            transcript.write_text(json.dumps(self.fx.usage_line(input_tokens=200_000)) + "\n")
            result = subprocess.run(
                [sys.executable, str(HOOK)],
                input=json.dumps({"transcript_path": str(transcript)}),
                capture_output=True,
                text=True,
                cwd=str(plain_path),
                timeout=5,
                env=_loop_env(),
            )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")

    def test_unreadable_transcript_path_is_noop(self) -> None:
        """When transcript_path exists but is not readable (permissions 000),
        _latest_usage_total must return None and the hook must be a no-op.
        Verifies the OSError path in _latest_usage_total.
        """
        self.fx.write_state(phase="build")
        self.fx.transcript.write_text(json.dumps(self.fx.usage_line(input_tokens=200_000)) + "\n")
        original_mode = self.fx.transcript.stat().st_mode
        self.fx.transcript.chmod(0o000)
        self.addCleanup(self.fx.transcript.chmod, original_mode)
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())

    def test_transcript_with_no_usage_lines_is_noop(self) -> None:
        """A transcript containing only non-usage JSON (no message.usage field)
        must cause the hook to return None from _latest_usage_total and be a
        no-op — no abort emitted even at very large file sizes.
        """
        self.fx.write_state(phase="build")
        lines = [
            {"type": "user", "message": {"content": "hello"}},
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
            {"type": "tool_result", "content": [{"type": "text", "text": "output"}]},
        ]
        self.fx.write_transcript_lines(lines)
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())

    def test_transcript_truncated_mid_line_is_noop(self) -> None:
        """A transcript whose last line is truncated mid-JSON (no closing brace)
        must not crash the hook. Partial lines are silently skipped by the
        JSON parser, and if no complete usage line is found, returns None.
        """
        self.fx.write_state(phase="build")
        with self.fx.transcript.open("w") as f:
            f.write(json.dumps(self.fx.usage_line(input_tokens=50_000)) + "\n")
            # Write a partial line (truncated JSON object, no newline)
            f.write('{"message": {"usage": {"input_tokens": 999999')
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        # The truncated line has the high-token data but is unparseable;
        # the hook should pick up the complete 50K line (under threshold).
        self.assertEqual(result.stdout.strip(), "")
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())

    # Performance ------------------------------------------------------------

    def test_hook_main_completes_under_100ms_in_process(self) -> None:
        """PRD 00024 sets a <100ms target on the hook itself. Time only the
        in-process `main()` work so the threshold tracks hook logic, not
        the ~50-80ms Python interpreter cold-start that a subprocess fork
        would add. A regression that scanned the full transcript instead of
        the 64KB tail would balloon the timing here even at this scale.

        The transcript is ~4.8 MB of noise followed by one **over-threshold**
        usage line at the tail. Using an over-threshold value lets the test
        assert that the hook actually parsed the tail and emitted the
        rotation envelope — a regression that bailed out before reading the
        transcript would produce empty stdout and fail the assertion,
        regardless of how fast it ran.
        """
        self.fx.write_state(phase="build")
        line_blob = json.dumps({"type": "noise", "padding": "x" * 4_000}) + "\n"
        with self.fx.transcript.open("w") as f:
            for _ in range(1_200):
                f.write(line_blob)
            f.write(json.dumps(self.fx.usage_line(input_tokens=600_000)) + "\n")

        module = _load_hook_module()
        payload = json.dumps({"transcript_path": str(self.fx.transcript)})
        prev_stdin, prev_stdout, prev_cwd = sys.stdin, sys.stdout, os.getcwd()
        prev_loop = os.environ.get("_AUTOPILOT_LOOP")
        os.environ["_AUTOPILOT_LOOP"] = "test-loop"
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
            if prev_loop is None:
                os.environ.pop("_AUTOPILOT_LOOP", None)
            else:
                os.environ["_AUTOPILOT_LOOP"] = prev_loop

        self.assertLess(elapsed_ms, 100, f"hook took {elapsed_ms:.0f}ms")
        # Proves the tail-read + parse code path actually ran. A regression
        # that bailed out before reading the transcript would leave stdout
        # empty and fail here, not on the timing assertion above.
        emitted = captured_stdout.getvalue()
        self.assertIn("hookSpecificOutput", emitted)
        self.assertIn("context cap reached", emitted.lower())


    # Marker self-clearing -------------------------------------------------

    def test_stale_marker_for_different_task_is_cleared_and_hook_fires(self) -> None:
        """When the in-progress task differs from the marker's task id, the
        hook must clear the stale marker and process the overrun. Otherwise
        a missed `/work` step-2 Bash clear would silently disable the cap
        for every task in the phase after the first abort.
        """
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-new", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
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
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
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
        self.fx.write_state(phase="build")
        # 200KB of noise (mixture of valid-shape lines and junk), then the
        # latest over-threshold usage line at EOF. Old TAIL_BYTES=64KB
        # would miss the usage line because the 200KB noise block precedes
        # it; with reverse-chunk reads the hook walks back until found.
        lines = []
        big_payload = "x" * 200_000
        lines.append({"type": "noise", "padding": big_payload})
        lines.append(self.fx.usage_line(input_tokens=600_000))
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
        self.fx.write_state(phase="build")
        with self.fx.transcript.open("w") as f:
            # The first line is the only usage line; everything after is
            # noise that pushes the usage line out of MAX_TAIL_BYTES.
            f.write(json.dumps(self.fx.usage_line(input_tokens=600_000)) + "\n")
            noise = json.dumps({"type": "noise", "padding": "x" * 100_000}) + "\n"
            # ~5MB of noise — more than MAX_TAIL_BYTES (4MB).
            for _ in range(50):
                f.write(noise)

        module = _load_hook_module()
        payload = json.dumps({"transcript_path": str(self.fx.transcript)})
        prev_stdin, prev_stdout, prev_cwd = sys.stdin, sys.stdout, os.getcwd()
        prev_loop = os.environ.get("_AUTOPILOT_LOOP")
        os.environ["_AUTOPILOT_LOOP"] = "test-loop"
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
            if prev_loop is None:
                os.environ.pop("_AUTOPILOT_LOOP", None)
            else:
                os.environ["_AUTOPILOT_LOOP"] = prev_loop

        # No abort emitted — the usage line is beyond the MAX_TAIL_BYTES
        # window, so the hook treats this turn as "no recent usage info"
        # and stays silent. The hook MUST not hang or crash trying to
        # search the whole multi-MB file.
        self.assertEqual(captured.getvalue().strip(), "")
        # Bounded read should still complete fast — well under 500ms.
        self.assertLess(elapsed_ms, 500, f"hook took {elapsed_ms:.0f}ms")


    # Soft-threshold handoff ------------------------------------------------

    def test_soft_threshold_writes_handoff_marker(self) -> None:
        """Usage between the single soft (120K) and hard (150K) caps writes
        `.handoff-requested` carrying the in-progress task id. The path is
        non-destructive — no `.cap-fired`, no rotation, no state mutation.
        No `context_window` is set: the threshold is a single constant."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=130_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")

        handoff = self.fx.autopilot_dir / ".handoff-requested"
        self.assertTrue(handoff.exists())
        self.assertEqual(handoff.read_text().strip(), "task-x")

        # Non-destructive: hard-cap artifacts must NOT appear.
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        self.assertEqual(state["cap_rotations"], [])
        self.assertNotIn("stall_reason", state)

    def test_below_soft_threshold_writes_no_marker(self) -> None:
        """Usage under the soft cap writes neither marker."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=80_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")
        self.assertFalse((self.fx.autopilot_dir / ".handoff-requested").exists())
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())

    def test_hard_cap_overrun_writes_no_handoff_marker(self) -> None:
        """A hard-cap overrun takes the rotation path and must NOT also write
        `.handoff-requested` — the two paths are mutually exclusive."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=600_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertTrue((self.fx.autopilot_dir / ".cap-fired").exists())
        self.assertFalse((self.fx.autopilot_dir / ".handoff-requested").exists())

    def test_handoff_marker_same_task_not_rewritten(self) -> None:
        """When `.handoff-requested` already names the in-progress task, a
        redundant PostToolUse fire is a no-op (one-shot per task)."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=130_000)])
        (self.fx.autopilot_dir / ".handoff-requested").write_text("task-x")
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")
        self.assertEqual(
            (self.fx.autopilot_dir / ".handoff-requested").read_text().strip(),
            "task-x",
        )

    def test_handoff_marker_stale_task_overwritten(self) -> None:
        """A `.handoff-requested` marker naming an earlier task is rewritten
        with the current task id, so the handoff request stays current after
        the session advances."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-new", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=130_000)])
        (self.fx.autopilot_dir / ".handoff-requested").write_text("task-old")
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            (self.fx.autopilot_dir / ".handoff-requested").read_text().strip(),
            "task-new",
        )

    def test_cap_fired_marker_for_same_task_blocks_soft_path(self) -> None:
        """When `.cap-fired` already named the in-progress task (a rotation
        already fired), the hook early-returns before the soft check — no
        `.handoff-requested` is written for that task."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=400_000)])
        (self.fx.autopilot_dir / ".cap-fired").write_text("task-x")
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")
        self.assertFalse((self.fx.autopilot_dir / ".handoff-requested").exists())


class InstructionBuilderContractTests(unittest.TestCase):
    """C1: instruction builders must not take signal_path and must not emit
    any signal-write directive. The Stop hook now owns the signal write."""

    def setUp(self) -> None:
        self.module = _load_hook_module()

    # AC1: _rotation_instructions signature -----------------------------------

    def test_rotation_instructions_takes_only_limit_parameter(self) -> None:
        """_rotation_instructions must accept exactly one parameter named
        `limit` — no signal_path."""
        sig = inspect.signature(self.module._rotation_instructions)
        self.assertEqual(list(sig.parameters), ["limit"])

    # AC2: _oversized_stall_instructions signature ----------------------------

    def test_oversized_stall_instructions_takes_only_task_id_parameter(self) -> None:
        """_oversized_stall_instructions must accept exactly one parameter
        named `task_id` — no signal_path."""
        sig = inspect.signature(self.module._oversized_stall_instructions)
        self.assertEqual(list(sig.parameters), ["task_id"])

    # AC3: rotation text has no signal-write directive ------------------------

    def test_rotation_text_has_no_signal_write_directive(self) -> None:
        """_rotation_instructions must not emit any signal-write directive."""
        text = self.module._rotation_instructions(500_000)
        self.assertNotIn("write 'next'", text)
        self.assertNotIn("$_AUTOPILOT_LOOP", text)
        self.assertNotIn("signal", text.lower())

    # AC4: stall text has no signal-write directive ---------------------------

    def test_stall_text_has_no_signal_write_directive(self) -> None:
        """_oversized_stall_instructions must not emit any signal-write
        directive."""
        text = self.module._oversized_stall_instructions("task-abc")
        self.assertNotIn("write 'next'", text)
        self.assertNotIn("$_AUTOPILOT_LOOP", text)
        self.assertNotIn("signal", text.lower())

    # AC5: rotation text still describes a rotation and a stop ----------------

    def test_rotation_text_still_describes_rotation_and_stop(self) -> None:
        """_rotation_instructions must still say ROTATION, STOP, and
        reference build as the next_phase — guards against the builder
        being gutted entirely."""
        text = self.module._rotation_instructions(500_000)
        self.assertIn("rotation", text.lower())
        self.assertIn("stop", text.lower())
        self.assertIn("build", text.lower())

    # AC6: stall text still names the oversized stall and stalled state -------

    def test_stall_text_still_describes_oversized_stall(self) -> None:
        """_oversized_stall_instructions must still reference 'oversized' and
        the stall_reason 'stalled' state marker."""
        text = self.module._oversized_stall_instructions("task-abc")
        self.assertIn("oversized", text.lower())
        self.assertIn("stalled", text.lower())


class MarkerStateAtomicityTests(unittest.TestCase):
    """C2: marker-first + rollback. The `.cap-fired` marker is present iff the
    rotation/stall is recorded, so a marker-write OSError can never leave a
    state record that the next PostToolUse misreads as a second consecutive
    rotation (a false-livelock oversized-task stall)."""

    def setUp(self) -> None:
        self.module = _load_hook_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ap = Path(self.tmp.name)

    def _write_state(self) -> None:
        state = {
            "phase": "build",
            "cycle": 1,
            "cap_rotations": [],
            "tasks": [{"id": "task-x", "name": "y", "status": "in_progress"}],
        }
        (self.ap / "state.json").write_text(json.dumps(state))

    def test_marker_write_failure_during_rotation_leaves_cap_rotations_unchanged(
        self,
    ) -> None:
        """If the marker write fails, _handle_rotation must not record a rotation
        in state.cap_rotations — a rotation-without-marker re-fires as a false
        livelock. (A directory at the marker path makes write_text raise
        IsADirectoryError, an OSError.)"""
        self._write_state()
        marker = self.ap / ".cap-fired"
        marker.mkdir()
        self.module._handle_rotation(self.ap, marker, "task-x", 500_000)
        after = json.loads((self.ap / "state.json").read_text())
        self.assertEqual(
            after.get("cap_rotations"),
            [],
            "a marker-write failure must leave cap_rotations unchanged",
        )

    def test_marker_write_failure_during_livelock_leaves_stall_unset(self) -> None:
        """Same invariant on the livelock path: a marker-write failure must not
        record an oversized-task stall."""
        self._write_state()
        marker = self.ap / ".cap-fired"
        marker.mkdir()
        self.module._handle_livelock(self.ap, marker, "task-x", 600_000)
        after = json.loads((self.ap / "state.json").read_text())
        self.assertNotIn(
            "stall_reason",
            after,
            "a marker-write failure must not record an oversized-task stall",
        )

    def test_state_append_failure_during_rotation_rolls_back_marker(self) -> None:
        """C2 rollback path (the other half of the invariant): when the marker
        write SUCCEEDS but the cap_rotations state append FAILS, _handle_rotation
        must unlink the marker and emit no envelope. Otherwise a
        marker-without-rotation would block the cap forever (the next fire sees
        the marker and no-ops). The existing marker-write-failure test covers
        only the marker-FIRST failure; this covers the unlink rollback."""
        self._write_state()
        marker = self.ap / ".cap-fired"
        # Marker write succeeds (writable temp dir); force the state append to
        # fail so the rollback branch runs.
        self.module._append_rotation_to_state = lambda *a, **k: False
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            self.module._handle_rotation(self.ap, marker, "task-x", 500_000)
        self.assertFalse(
            marker.exists(),
            "a state-append failure must roll back (unlink) the marker",
        )
        after = json.loads((self.ap / "state.json").read_text())
        self.assertEqual(
            after.get("cap_rotations"),
            [],
            "no rotation may be recorded when the state append fails",
        )
        self.assertEqual(
            captured.getvalue().strip(),
            "",
            "no rotation envelope may be emitted when the state append fails",
        )

    def test_state_write_failure_during_livelock_rolls_back_marker(self) -> None:
        """C2 rollback path on the livelock branch: marker write succeeds, the
        oversized-stall state write fails -> _handle_livelock unlinks the marker
        and emits no envelope, leaving no stall_reason for the next fire to act
        on spuriously."""
        self._write_state()
        marker = self.ap / ".cap-fired"
        self.module._set_oversized_stall = lambda *a, **k: False
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            self.module._handle_livelock(self.ap, marker, "task-x", 600_000)
        self.assertFalse(
            marker.exists(),
            "a state-write failure must roll back (unlink) the marker",
        )
        after = json.loads((self.ap / "state.json").read_text())
        self.assertNotIn(
            "stall_reason",
            after,
            "no oversized-task stall may be recorded when the state write fails",
        )
        self.assertEqual(
            captured.getvalue().strip(),
            "",
            "no stall envelope may be emitted when the state write fails",
        )


class PinnedCapAndTripwireTests(unittest.TestCase):
    """PRD 00073: 150K/120K pin + 300-tool-call turn tripwire."""

    def setUp(self) -> None:
        self.fx = HookFixture()
        self.addCleanup(self.fx.cleanup)
        self.module = _load_hook_module()

    def test_constants_pinned_to_new_values(self) -> None:
        self.assertEqual(self.module.USAGE_CAP, 150_000)
        self.assertEqual(self.module.SOFT_CAP, 120_000)
        self.assertEqual(self.module.TURN_TRIPWIRE, 300)
        self.assertLess(self.module.SOFT_CAP, self.module.USAGE_CAP)

    def test_cap_fires_above_150k(self) -> None:
        """160K is over the new hard cap (was under the old 500K). Rotation."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=160_000)])
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertTrue((self.fx.autopilot_dir / ".cap-fired").exists())
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        self.assertEqual(state["cap_rotations"][-1]["task_id"], "task-x")

    def test_130k_is_soft_not_hard(self) -> None:
        """130K sits between the new soft (120K) and hard (150K): handoff, no rotation."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=130_000)])
        self.fx.run_hook()
        self.assertTrue((self.fx.autopilot_dir / ".handoff-requested").exists())
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())

    def _seed_counter(self, session_id: str, count: int) -> None:
        (self.fx.autopilot_dir / ".turn-counts.json").write_text(
            json.dumps({"counts": {session_id: count}, "fired": []})
        )

    def test_tripwire_fires_at_300(self) -> None:
        """A session at 299 counted calls that takes its 300th (with usage well
        under the cap) is force-handed-off via the rotation path."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=40_000)])
        self._seed_counter("test-session", 299)
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertTrue((self.fx.autopilot_dir / ".cap-fired").exists())
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        self.assertEqual(state["cap_rotations"][-1]["task_id"], "task-x")

    def test_tripwire_does_not_fire_at_299(self) -> None:
        """At the 299th call (seeded 298), no forced hand-off; usage is under cap."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=40_000)])
        self._seed_counter("test-session", 298)
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())
        state = json.loads((self.fx.autopilot_dir / "state.json").read_text())
        self.assertEqual(state["cap_rotations"], [])

    def test_tripwire_counter_corruption_resets_without_crashing(self) -> None:
        """A corrupt counter file resets to 0 and the hook still exits 0."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=40_000)])
        (self.fx.autopilot_dir / ".turn-counts.json").write_text("{not json")
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())

    def test_tripwire_valid_json_bad_count_value_does_not_crash(self) -> None:
        """A valid-JSON counter file with a non-int count (null / string) must
        reset that entry and exit 0, never raise (never-crash contract)."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=40_000)])
        (self.fx.autopilot_dir / ".turn-counts.json").write_text(
            json.dumps({"counts": {"test-session": None}, "fired": []})
        )
        result = self.fx.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())
        # a wrong-shape file (counts not a dict) also resets cleanly
        (self.fx.autopilot_dir / ".turn-counts.json").write_text(
            json.dumps({"counts": "nope"})
        )
        result2 = self.fx.run_hook()
        self.assertEqual(result2.returncode, 0)

    def test_tripwire_exempt_for_interactive_session(self) -> None:
        """No $_AUTOPILOT_LOOP: even a seeded 299 counter must not fire."""
        self.fx.write_state(
            phase="build",
            tasks=[{"id": "task-x", "name": "y", "status": "in_progress"}],
        )
        self.fx.write_transcript_lines([self.fx.usage_line(input_tokens=40_000)])
        self._seed_counter("test-session", 299)
        result = self.fx.run_hook(in_loop=False)
        self.assertEqual(result.returncode, 0)
        self.assertFalse((self.fx.autopilot_dir / ".cap-fired").exists())


if __name__ == "__main__":
    unittest.main()
