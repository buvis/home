"""Tests for the FUTURE autopilot Stop hook contract.

The FUTURE hook reads state.json and $_AUTOPILOT_LOOP, then WRITES the signal
file itself. It no longer reacts to a pre-existing signal. These tests are
intentionally RED against the current hook, which only SIGINTs claude when it
finds a pre-existing signal and never reads state or env.

Decision table (verbatim from the task spec):
- _AUTOPILOT_LOOP unset -> no signal, no auto-exit (interactive).
- phase == "paused" -> no signal (cap-pause and PAUSE sites stay interactive).
- Batch end (next_phase "" after batch-end review) -> "done".
- Fresh stall_reason.stalled == "subagent_prompt_overrun" -> "task_aborted".
- Otherwise, next_phase set and more work pending -> "next".
- Idempotent: if signal file already has the same value, leave it.
- Hook never signals when state file is absent or corrupt (fail open).

Driving strategy: import the module directly, monkeypatch Path.cwd to a tmp
dir containing dev/local/autopilot/state.json, set/unset _AUTOPILOT_LOOP via
os.environ manipulation, patch find_and_signal_claude to prevent SIGINT of
the test runner, call hook.main().
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).parent

# Ensure _walk_up is importable (hook imports it at module level).
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

HOOK_PATH = SCRIPTS_DIR / "autopilot_stop_hook.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "autopilot_stop_hook_under_test", HOOK_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load_module()


def _make_state(**fields) -> dict:
    base: dict = {
        "prd": "00099-test.md",
        "phase": "build",
        "phases_completed": [],
        "cycle": 1,
        "tasks_total": 1,
        "tasks_completed": 0,
        "tasks": [],
        "next_phase": "review",
        "task_aborts": [],
        "cap_rotations": [],
        "replan_count": 0,
    }
    base.update(fields)
    return base


class StopHookFixture:
    """Tmp autopilot dir + helpers."""

    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.autopilot_dir = self.cwd / "dev" / "local" / "autopilot"
        self.autopilot_dir.mkdir(parents=True)

    @property
    def signal_path(self) -> Path:
        return self.autopilot_dir / "signal"

    def write_state(self, **fields) -> None:
        state = _make_state(**fields)
        (self.autopilot_dir / "state.json").write_text(json.dumps(state))

    def signal_content(self) -> str | None:
        if self.signal_path.exists():
            return self.signal_path.read_text().strip()
        return None

    def cleanup(self) -> None:
        self.tmp.cleanup()


def _run_hook_with_env(fx: StopHookFixture, loop_value: str | None) -> list[int]:
    """Invoke hook.main() with controlled _AUTOPILOT_LOOP value.

    loop_value=None means the env var is absent.
    Returns list of PIDs passed to find_and_signal_claude.
    """
    signalled_pids: list[int] = []

    def fake_signal_claude(pid: int) -> bool:
        signalled_pids.append(pid)
        return True

    saved = os.environ.pop("_AUTOPILOT_LOOP", None)
    try:
        if loop_value is not None:
            os.environ["_AUTOPILOT_LOOP"] = loop_value
        stdin_payload = json.dumps({"session_id": "test-session"})
        with (
            mock.patch.object(hook.Path, "cwd", return_value=fx.cwd),
            mock.patch.object(hook, "find_and_signal_claude", fake_signal_claude),
            mock.patch.object(hook.sys, "stdin", io.StringIO(stdin_payload)),
        ):
            hook.main()
    finally:
        os.environ.pop("_AUTOPILOT_LOOP", None)
        if saved is not None:
            os.environ["_AUTOPILOT_LOOP"] = saved

    return signalled_pids


def _run_hook(fx: StopHookFixture) -> list[int]:
    """Run hook with _AUTOPILOT_LOOP set (normal autopilot session)."""
    return _run_hook_with_env(fx, "12345")


# ===========================================================================
# Decision table tests.
# ===========================================================================


class HappyPathNextSignalTests(unittest.TestCase):
    """next_phase set + loop active -> hook writes "next", calls auto-exit."""

    def setUp(self) -> None:
        self.fx = StopHookFixture()
        self.addCleanup(self.fx.cleanup)

    def test_build_session_finishes_hook_writes_next(self) -> None:
        """Happy path: build session ends with next_phase "review" -> "next"."""
        self.fx.write_state(phase="build", next_phase="review")
        _run_hook(self.fx)
        self.assertEqual(self.fx.signal_content(), "next")

    def test_auto_exit_called_when_signal_written(self) -> None:
        """When a signal is written, find_and_signal_claude must be called."""
        self.fx.write_state(phase="build", next_phase="review")
        pids = _run_hook(self.fx)
        self.assertGreater(len(pids), 0, "find_and_signal_claude must be called")

    def test_model_crash_before_banner_hook_still_writes_next(self) -> None:
        """State alone (no banner) is sufficient for the hook to write "next"."""
        self.fx.write_state(phase="build", next_phase="review")
        _run_hook(self.fx)
        self.assertEqual(self.fx.signal_content(), "next")


class InteractiveSessionTests(unittest.TestCase):
    """_AUTOPILOT_LOOP unset -> no signal, no auto-exit."""

    def setUp(self) -> None:
        self.fx = StopHookFixture()
        self.addCleanup(self.fx.cleanup)

    def test_no_loop_env_no_signal_written(self) -> None:
        self.fx.write_state(phase="build", next_phase="review")
        _run_hook_with_env(self.fx, loop_value=None)
        self.assertIsNone(self.fx.signal_content())

    def test_no_loop_env_no_auto_exit(self) -> None:
        self.fx.write_state(phase="build", next_phase="review")
        pids = _run_hook_with_env(self.fx, loop_value=None)
        self.assertEqual(pids, [], "find_and_signal_claude must NOT be called")


class CapPauseTests(unittest.TestCase):
    """phase == "paused" -> no signal, stay interactive."""

    def setUp(self) -> None:
        self.fx = StopHookFixture()
        self.addCleanup(self.fx.cleanup)

    def test_cap_pause_no_signal(self) -> None:
        self.fx.write_state(
            phase="paused",
            cap_pause_reason="budget exhausted",
            next_phase="review",
        )
        _run_hook(self.fx)
        self.assertIsNone(self.fx.signal_content())

    def test_cap_pause_no_auto_exit(self) -> None:
        self.fx.write_state(
            phase="paused",
            cap_pause_reason="budget exhausted",
            next_phase="review",
        )
        pids = _run_hook(self.fx)
        self.assertEqual(pids, [])

    def test_paused_without_cap_reason_no_signal(self) -> None:
        """phase == "paused" without cap_pause_reason is still interactive."""
        self.fx.write_state(phase="paused", next_phase="review")
        _run_hook(self.fx)
        self.assertIsNone(self.fx.signal_content())


class BatchEndDoneTests(unittest.TestCase):
    """next_phase "" (empty string) -> "done"."""

    def setUp(self) -> None:
        self.fx = StopHookFixture()
        self.addCleanup(self.fx.cleanup)

    def test_empty_next_phase_writes_done(self) -> None:
        self.fx.write_state(phase="build", next_phase="")
        _run_hook(self.fx)
        self.assertEqual(self.fx.signal_content(), "done")

    def test_done_signal_calls_auto_exit(self) -> None:
        self.fx.write_state(phase="build", next_phase="")
        pids = _run_hook(self.fx)
        self.assertGreater(len(pids), 0)

    def test_done_deletes_state_for_clean_next_batch(self) -> None:
        self.fx.write_state(phase="build", next_phase="")
        _run_hook(self.fx)
        self.assertFalse(
            (self.fx.autopilot_dir / "state.json").exists(),
            "state.json must be removed after 'done' so the next batch starts clean",
        )


class SubagentPromptOverrunTests(unittest.TestCase):
    """stall_reason.stalled == "subagent_prompt_overrun" -> "task_aborted"."""

    def setUp(self) -> None:
        self.fx = StopHookFixture()
        self.addCleanup(self.fx.cleanup)

    def test_subagent_prompt_overrun_writes_task_aborted(self) -> None:
        self.fx.write_state(
            phase="build",
            next_phase="review",
            stall_reason={"stalled": "subagent_prompt_overrun", "task": "t1"},
        )
        _run_hook(self.fx)
        self.assertEqual(self.fx.signal_content(), "task_aborted")

    def test_overrun_stall_wins_over_next_phase(self) -> None:
        """stall row takes precedence even when next_phase is also set."""
        self.fx.write_state(
            phase="build",
            next_phase="review",
            stall_reason={"stalled": "subagent_prompt_overrun"},
        )
        _run_hook(self.fx)
        # Must be "task_aborted", NOT "next".
        self.assertEqual(self.fx.signal_content(), "task_aborted")

    def test_other_stall_with_next_phase_writes_next(self) -> None:
        """A stall value other than subagent_prompt_overrun + next_phase -> "next"."""
        self.fx.write_state(
            phase="build",
            next_phase="review",
            stall_reason={"stalled": "oversized_task", "task": "t1"},
        )
        _run_hook(self.fx)
        self.assertEqual(self.fx.signal_content(), "next")


class IdempotencyTests(unittest.TestCase):
    """Pre-existing signal with the computed value -> leave it unchanged."""

    def setUp(self) -> None:
        self.fx = StopHookFixture()
        self.addCleanup(self.fx.cleanup)

    def test_idempotent_next_unchanged(self) -> None:
        self.fx.write_state(phase="build", next_phase="review")
        self.fx.signal_path.write_text("next\n")
        mtime_before = self.fx.signal_path.stat().st_mtime_ns
        _run_hook(self.fx)
        mtime_after = self.fx.signal_path.stat().st_mtime_ns
        self.assertEqual(self.fx.signal_content(), "next")
        self.assertEqual(
            mtime_before,
            mtime_after,
            "signal file must not be rewritten when value is identical",
        )

    def test_idempotent_done_unchanged(self) -> None:
        self.fx.write_state(phase="build", next_phase="")
        self.fx.signal_path.write_text("done\n")
        mtime_before = self.fx.signal_path.stat().st_mtime_ns
        _run_hook(self.fx)
        self.assertEqual(self.fx.signal_content(), "done")
        mtime_after = self.fx.signal_path.stat().st_mtime_ns
        self.assertEqual(mtime_before, mtime_after)


class FailOpenTests(unittest.TestCase):
    """state.json absent or corrupt -> exit 0, NO signal, even with loop set."""

    def setUp(self) -> None:
        self.fx = StopHookFixture()
        self.addCleanup(self.fx.cleanup)

    def test_absent_state_json_no_signal(self) -> None:
        # autopilot_dir exists but state.json is absent.
        _run_hook(self.fx)
        self.assertIsNone(self.fx.signal_content())

    def test_absent_state_json_no_auto_exit(self) -> None:
        pids = _run_hook(self.fx)
        self.assertEqual(pids, [])

    def test_corrupt_state_json_no_signal(self) -> None:
        (self.fx.autopilot_dir / "state.json").write_text("not valid json {{{{")
        _run_hook(self.fx)
        self.assertIsNone(self.fx.signal_content())

    def test_corrupt_state_json_no_auto_exit(self) -> None:
        (self.fx.autopilot_dir / "state.json").write_text("not valid json {{{{")
        pids = _run_hook(self.fx)
        self.assertEqual(pids, [])

    def test_absent_state_with_loop_set_still_no_signal(self) -> None:
        """Fail-open holds even when _AUTOPILOT_LOOP is set."""
        _run_hook(self.fx)
        self.assertIsNone(self.fx.signal_content())


class NonAutopilotSessionTests(unittest.TestCase):
    """No dev/local/autopilot dir in ancestors -> hook does nothing."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.plain_cwd = Path(self.tmp.name)

    def test_no_autopilot_dir_no_signal_no_auto_exit(self) -> None:
        signalled_pids: list[int] = []

        def fake_signal_claude(pid: int) -> bool:
            signalled_pids.append(pid)
            return True

        saved = os.environ.pop("_AUTOPILOT_LOOP", None)
        os.environ["_AUTOPILOT_LOOP"] = "99999"
        try:
            stdin_payload = json.dumps({"session_id": "non-autopilot"})
            with (
                mock.patch.object(hook.Path, "cwd", return_value=self.plain_cwd),
                mock.patch.object(hook, "find_and_signal_claude", fake_signal_claude),
                mock.patch.object(hook.sys, "stdin", io.StringIO(stdin_payload)),
            ):
                hook.main()
        finally:
            del os.environ["_AUTOPILOT_LOOP"]
            if saved is not None:
                os.environ["_AUTOPILOT_LOOP"] = saved

        signal_candidates = list(self.plain_cwd.rglob("signal"))
        self.assertEqual(signal_candidates, [])
        self.assertEqual(signalled_pids, [])


if __name__ == "__main__":
    unittest.main()
