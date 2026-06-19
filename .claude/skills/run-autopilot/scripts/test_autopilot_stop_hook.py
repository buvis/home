"""Tests for the autopilot Stop hook contract.

The hook reads state.json and $_AUTOPILOT_LOOP, then WRITES the signal file
itself (PRD 00043). It does not react to a pre-existing signal. These tests are
green against the shipped hook; they pin the decision table below.

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


def _run_hook_capturing(
    fx: StopHookFixture, loop_value: str | None = "12345"
) -> tuple[int | None, list[int], str]:
    """Like _run_hook_with_env, but also returns main()'s exit code and stderr."""
    signalled_pids: list[int] = []

    def fake_signal_claude(pid: int) -> bool:
        signalled_pids.append(pid)
        return True

    saved = os.environ.pop("_AUTOPILOT_LOOP", None)
    stderr = io.StringIO()
    try:
        if loop_value is not None:
            os.environ["_AUTOPILOT_LOOP"] = loop_value
        stdin_payload = json.dumps({"session_id": "test-session"})
        with (
            mock.patch.object(hook.Path, "cwd", return_value=fx.cwd),
            mock.patch.object(hook, "find_and_signal_claude", fake_signal_claude),
            mock.patch.object(hook.sys, "stdin", io.StringIO(stdin_payload)),
            mock.patch.object(hook.sys, "stderr", stderr),
        ):
            rc = hook.main()
    finally:
        os.environ.pop("_AUTOPILOT_LOOP", None)
        if saved is not None:
            os.environ["_AUTOPILOT_LOOP"] = saved

    return rc, signalled_pids, stderr.getvalue()


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


class ReviewGateSuppressionTests(unittest.TestCase):
    """At a review-gated handoff the signal + SIGINT must defer to the shared
    review-coverage gate (gate_blocks). If the gate blocks, the hook writes NO
    signal and does NOT SIGINT, so the session stays alive for the coverage
    hook to inject its feedback. Regression for the 2026-06-11/12 deaths where
    the SIGINT killed a session the coverage gate meant to keep alive, leaving
    the loop reporting "ended without a signal"."""

    def setUp(self) -> None:
        self.fx = StopHookFixture()
        self.addCleanup(self.fx.cleanup)

    def test_gate_block_suppresses_signal(self) -> None:
        self.fx.write_state(phase="blind", next_phase="blind")
        with mock.patch.object(
            hook, "gate_blocks", return_value=(True, "review coverage gap [...]")
        ):
            _run_hook(self.fx)
        self.assertIsNone(
            self.fx.signal_content(),
            "no signal may be written when the review-coverage gate blocks",
        )

    def test_gate_block_suppresses_sigint(self) -> None:
        self.fx.write_state(phase="blind", next_phase="blind")
        with mock.patch.object(hook, "gate_blocks", return_value=(True, "gap")):
            pids = _run_hook(self.fx)
        self.assertEqual(
            pids, [], "must NOT SIGINT the session when the review gate blocks"
        )

    def test_gate_block_preserves_state_on_done(self) -> None:
        """A blocking doubt-review gate at batch end must suppress BOTH the
        'done' signal and the state.json deletion — otherwise an incomplete
        final review would be sealed and the batch state lost."""
        self.fx.write_state(phase="done", next_phase="")
        with mock.patch.object(hook, "gate_blocks", return_value=(True, "gap")):
            _run_hook(self.fx)
        self.assertIsNone(self.fx.signal_content())
        self.assertTrue(
            (self.fx.autopilot_dir / "state.json").exists(),
            "state.json must survive when the gate blocks the 'done' handoff",
        )

    def test_gate_pass_writes_signal_and_sigints(self) -> None:
        self.fx.write_state(phase="blind", next_phase="blind")
        with mock.patch.object(hook, "gate_blocks", return_value=(False, "")):
            pids = _run_hook(self.fx)
        self.assertEqual(self.fx.signal_content(), "next")
        self.assertGreater(len(pids), 0)

    def test_gate_consulted_with_autopilot_dir_and_state(self) -> None:
        self.fx.write_state(phase="blind", next_phase="blind")
        gate = mock.MagicMock(return_value=(False, ""))
        with mock.patch.object(hook, "gate_blocks", gate):
            _run_hook(self.fx)
        gate.assert_called_once()
        args = gate.call_args[0]
        self.assertEqual(Path(args[0]).name, "autopilot")
        self.assertEqual(args[1].get("phase"), "blind")

    def test_gate_error_fails_open_writes_signal(self) -> None:
        """If gate_blocks raises, the hook falls open (proceeds with the
        hand-off) and logs to stderr — the coverage hook runs the same gate
        and likewise won't block, so there is no SIGINT race."""
        self.fx.write_state(phase="blind", next_phase="blind")
        with mock.patch.object(
            hook, "gate_blocks", side_effect=RuntimeError("boom")
        ):
            rc, pids, stderr = _run_hook_capturing(self.fx)
        self.assertEqual(self.fx.signal_content(), "next")
        self.assertGreater(len(pids), 0)
        self.assertIn("fail open", stderr)


class PhaseThrashCircuitBreakerTests(unittest.TestCase):
    """A review/build phase that hands off "next" with no forward progress,
    repeated PHASE_THRASH_LIMIT times, is a thrash. The hook must withhold the
    signal (so the wrapper loop exits cleanly, same halt as a PAUSE), flag
    needs_attention, and record a thrash_halt marker. Regression for the
    2026-06-17 blind-review thrash (PRD 00157): the blind phase dispatched an
    async reviewer and yielded before the result landed, so the phase never
    recorded completion and the loop re-entered it 18 times with zero progress.
    gate_blocks is mocked to (False, "") so these tests isolate the breaker from
    the review-coverage gate."""

    def setUp(self) -> None:
        self.fx = StopHookFixture()
        self.addCleanup(self.fx.cleanup)

    def _state_path(self) -> Path:
        return self.fx.autopilot_dir / "state.json"

    def _read_state(self) -> dict:
        return json.loads(self._state_path().read_text())

    def _seed(self, guard_count: int | None = None, **fields) -> dict:
        st = _make_state(**fields)
        if guard_count is not None:
            st["phase_guard"] = {"key": hook._progress_key(st), "count": guard_count}
        self._state_path().write_text(json.dumps(st))
        return st

    def _run_no_gate(self) -> list[int]:
        with mock.patch.object(hook, "gate_blocks", return_value=(False, "")):
            return _run_hook(self.fx)

    def test_first_handoff_writes_next_and_seeds_guard(self) -> None:
        self._seed(phase="blind", next_phase="blind", phases_completed=["review"])
        self._run_no_gate()
        self.assertEqual(self.fx.signal_content(), "next")
        self.assertEqual(self._read_state()["phase_guard"]["count"], 1)

    def test_repeat_below_limit_still_writes_next(self) -> None:
        self._seed(
            guard_count=hook.PHASE_THRASH_LIMIT - 2,
            phase="blind",
            next_phase="blind",
            phases_completed=["review"],
        )
        self._run_no_gate()
        self.assertEqual(self.fx.signal_content(), "next")

    def test_limit_reached_withholds_signal(self) -> None:
        self._seed(
            guard_count=hook.PHASE_THRASH_LIMIT - 1,
            phase="blind",
            next_phase="blind",
            phases_completed=["review"],
        )
        self._run_no_gate()
        self.assertIsNone(
            self.fx.signal_content(), "a thrash trip must withhold the loop signal"
        )

    def test_limit_reached_sigints_to_exit_loop(self) -> None:
        """On trip the hook SIGINTs (exits the session) but writes no signal, so
        the wrapper reads an empty signal, hits its `*)` case and breaks the
        loop — a deterministic halt rather than an idle live session."""
        self._seed(
            guard_count=hook.PHASE_THRASH_LIMIT - 1,
            phase="blind",
            next_phase="blind",
            phases_completed=["review"],
        )
        pids = self._run_no_gate()
        self.assertGreater(len(pids), 0, "trip must SIGINT to exit the session")
        self.assertIsNone(self.fx.signal_content(), "trip must write no signal")

    def test_limit_reached_sets_attention_and_halt_marker(self) -> None:
        self._seed(
            guard_count=hook.PHASE_THRASH_LIMIT - 1,
            phase="blind",
            next_phase="blind",
            phases_completed=["review"],
        )
        self._run_no_gate()
        state = self._read_state()
        self.assertTrue(state.get("needs_attention"))
        self.assertEqual(state["thrash_halt"]["phase"], "blind")
        self.assertGreaterEqual(
            state["thrash_halt"]["repeats"], hook.PHASE_THRASH_LIMIT
        )

    def test_progress_resets_counter(self) -> None:
        """Stored count is high, but the state advanced (different key): the
        counter resets and the hand-off proceeds normally."""
        st = _make_state(
            phase="blind", next_phase="doubt", phases_completed=["review", "blind"]
        )
        st["phase_guard"] = {"key": "stale-key", "count": hook.PHASE_THRASH_LIMIT + 5}
        self._state_path().write_text(json.dumps(st))
        self._run_no_gate()
        self.assertEqual(self.fx.signal_content(), "next")
        self.assertEqual(self._read_state()["phase_guard"]["count"], 1)

    def test_breaker_scoped_to_next_not_done(self) -> None:
        """The breaker only governs the "next" hand-off; batch end ("done")
        is bounded separately and must never be withheld."""
        st = _make_state(phase="done", next_phase="")
        st["phase_guard"] = {"key": "whatever", "count": hook.PHASE_THRASH_LIMIT + 9}
        self._state_path().write_text(json.dumps(st))
        self._run_no_gate()
        self.assertEqual(self.fx.signal_content(), "done")


if __name__ == "__main__":
    unittest.main()
