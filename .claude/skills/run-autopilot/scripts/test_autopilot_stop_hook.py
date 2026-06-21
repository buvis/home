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

    def write_transcript(self, events: list[dict]) -> Path:
        """Write a JSONL transcript (one event per line) and return its path."""
        p = self.cwd / "transcript.jsonl"
        p.write_text("\n".join(json.dumps(e) for e in events) + "\n")
        return p

    def read_state(self) -> dict:
        return json.loads((self.autopilot_dir / "state.json").read_text())

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


# ---------------------------------------------------------------------------
# Transcript event builders (synthetic; mirror the harness's JSONL shape).
# ---------------------------------------------------------------------------

LAUNCH_ACK = "Async agent launched successfully. agentId: abc123 (internal ID)"


def _ev_agent_dispatch() -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": "Agent", "input": {}}],
        },
    }


def _ev_assistant_text(text: str) -> dict:
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


def _ev_tool_result(text: str) -> dict:
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {"type": "tool_result", "content": [{"type": "text", "text": text}]}
            ],
        },
    }


def _ev_bash_background() -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "name": "Bash",
                    "input": {"command": "cargo test", "run_in_background": True},
                }
            ],
        },
    }


def _ev_bg_launch_ack(task_id: str = "b6qi55ate") -> dict:
    """A harness AUTO-BACKGROUND ack: a tool_result that starts with the launch
    phrase and carries the task id. This is what a long FOREGROUND Bash (codex,
    `cargo test`) becomes — the recorded tool_use still says foreground."""
    return _ev_tool_result(
        f"Command running in background with ID: {task_id}. Output is being "
        f"written to: /private/tmp/claude-501/proj/{task_id}.log"
    )


def _ev_schedule_wakeup() -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": "ScheduleWakeup", "input": {"delaySeconds": 90}}
            ],
        },
    }


def _ev_edit() -> dict:
    """A state-advancing Edit — the unambiguous hand-off marker."""
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "name": "Edit",
                    "input": {"file_path": "dev/local/autopilot/state.json"},
                }
            ],
        },
    }


def _ev_read(path: str = "/private/tmp/claude-501/proj/b6qi55ate.log") -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": "Read", "input": {"file_path": path}}],
        },
    }


def _ev_task_notification(task_id: str = "abc123") -> dict:
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": f"<task-notification>\n<task-id>{task_id}</task-id>\n",
        },
    }


def _ev_user_text(text: str) -> dict:
    """A user-role turn carrying arbitrary text (e.g. injected SKILL.md prose)."""
    return {"type": "user", "message": {"role": "user", "content": text}}


def _ev_agent_ack(agent_id: str) -> dict:
    """A real launch ack: a tool_result that starts with the launch phrase."""
    return _ev_tool_result(
        f"Async agent launched successfully. agentId: {agent_id} (internal ID)"
    )


def _run_hook_with_transcript(
    fx: StopHookFixture, transcript_path: Path, loop_value: str = "12345"
) -> list[int]:
    """Run the hook with a transcript_path in the stdin payload (the real Stop
    hook receives this). gate_blocks is forced to (False, "") so these tests
    isolate the background-task abstain from the review-coverage gate."""
    signalled_pids: list[int] = []

    def fake_signal_claude(pid: int) -> bool:
        signalled_pids.append(pid)
        return True

    saved = os.environ.pop("_AUTOPILOT_LOOP", None)
    try:
        os.environ["_AUTOPILOT_LOOP"] = loop_value
        stdin_payload = json.dumps(
            {"session_id": "test", "transcript_path": str(transcript_path)}
        )
        with (
            mock.patch.object(hook.Path, "cwd", return_value=fx.cwd),
            mock.patch.object(hook, "find_and_signal_claude", fake_signal_claude),
            mock.patch.object(hook.sys, "stdin", io.StringIO(stdin_payload)),
            mock.patch.object(hook, "gate_blocks", return_value=(False, "")),
        ):
            hook.main()
    finally:
        os.environ.pop("_AUTOPILOT_LOOP", None)
        if saved is not None:
            os.environ["_AUTOPILOT_LOOP"] = saved
    return signalled_pids


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


class BackgroundTaskInFlightTests(unittest.TestCase):
    """When the session ends its turn with a background task still pending (an
    async Agent dispatch, or a backgrounded Bash), the hook must abstain — write
    NO signal, NOT SIGINT, and NOT touch the thrash counter — so the harness can
    re-invoke the model on completion and the phase progresses. Regression for
    the 2026-06-19 strands: this harness backgrounds Agent dispatches and the old
    Stop hook SIGINTed on the yield turn, killing the session before the
    <task-notification> re-invoke landed (design reviewer + /work Tess/Ivan each
    stranded 3x, then the breaker halted the loop)."""

    def setUp(self) -> None:
        self.fx = StopHookFixture()
        self.addCleanup(self.fx.cleanup)

    def test_launched_agent_no_notification_abstains(self) -> None:
        """Agent dispatched, ack present, no completion yet -> still running."""
        self.fx.write_state(phase="build", next_phase="review")
        tp = self.fx.write_transcript(
            [_ev_agent_dispatch(), _ev_tool_result(LAUNCH_ACK)]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(self.fx.signal_content(), "must not signal while pending")
        self.assertEqual(pids, [], "must not SIGINT while a bg agent is pending")

    def test_unconsumed_task_notification_abstains(self) -> None:
        """Agent completed (notification arrived) but the model has not yet
        produced a turn consuming it -> the strand case; abstain so the harness
        re-invoke can be processed instead of killing the session."""
        self.fx.write_state(phase="build", next_phase="review")
        tp = self.fx.write_transcript(
            [
                _ev_agent_dispatch(),
                _ev_tool_result(LAUNCH_ACK),
                _ev_assistant_text("running in the background; I'll continue when..."),
                _ev_task_notification("abc123"),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(self.fx.signal_content())
        self.assertEqual(pids, [])

    def test_consumed_task_notification_hands_off(self) -> None:
        """Notification arrived AND the model produced a turn after it (consumed
        the result) -> nothing pending; the normal hand-off proceeds."""
        self.fx.write_state(phase="build", next_phase="review")
        tp = self.fx.write_transcript(
            [
                _ev_agent_dispatch(),
                _ev_tool_result(LAUNCH_ACK),
                _ev_task_notification("abc123"),
                _ev_assistant_text("Reviewer returned; applying fixes and advancing."),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertEqual(self.fx.signal_content(), "next")
        self.assertGreater(len(pids), 0)

    def test_inline_agent_with_no_ack_hands_off(self) -> None:
        """If the Agent ran inline (its tool_result is the real output, no launch
        ack), detection is a no-op and the hand-off proceeds — version-robust."""
        self.fx.write_state(phase="build", next_phase="review")
        tp = self.fx.write_transcript(
            [_ev_agent_dispatch(), _ev_tool_result("Here is my review: looks good.")]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertEqual(self.fx.signal_content(), "next")
        self.assertGreater(len(pids), 0)

    def test_backgrounded_bash_abstains(self) -> None:
        """A Bash tool_use flagged run_in_background with no completion yet is an
        unambiguous in-flight task -> abstain."""
        self.fx.write_state(phase="build", next_phase="review")
        tp = self.fx.write_transcript([_ev_bash_background()])
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(self.fx.signal_content())
        self.assertEqual(pids, [])

    def test_missing_transcript_path_hands_off(self) -> None:
        """No transcript_path in the payload -> fail open, behave as before."""
        self.fx.write_state(phase="build", next_phase="review")
        # _run_hook (no transcript_path) with the gate forced open.
        with mock.patch.object(hook, "gate_blocks", return_value=(False, "")):
            pids = _run_hook(self.fx)
        self.assertEqual(self.fx.signal_content(), "next")
        self.assertGreater(len(pids), 0)

    def test_abstain_does_not_increment_phase_guard(self) -> None:
        """A pending bg task is real work, not a thrash: the abstain must leave
        the thrash counter untouched (it must come before the breaker)."""
        st = _make_state(phase="build", next_phase="build")
        st["phase_guard"] = {"key": hook._progress_key(st), "count": 2}
        (self.fx.autopilot_dir / "state.json").write_text(json.dumps(st))
        tp = self.fx.write_transcript(
            [_ev_agent_dispatch(), _ev_tool_result(LAUNCH_ACK)]
        )
        _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(self.fx.signal_content())
        self.assertEqual(
            self.fx.read_state()["phase_guard"]["count"],
            2,
            "abstain must not advance the thrash counter toward a halt",
        )

    def test_phantom_notification_in_prose_does_not_mask_pending(self) -> None:
        """Round-2 regression (warden blind / playground Tess): SKILL.md text is
        injected as a user turn and MENTIONS `<task-notification>` mid-string.
        The old count-based detector counted that phantom as a real completion,
        cancelled the real launch, and SIGINTed the dispatched reviewer. Per-id,
        start-anchored matching must ignore the prose and still see the agent as
        pending. Phase is "build" (not review-gated): the pending check only runs
        outside review-gated phases now (review phases defer to the coverage
        gate), so this exercises the per-id anchoring where it actually fires."""
        self.fx.write_state(phase="build", next_phase="review")
        tp = self.fx.write_transcript(
            [
                _ev_user_text(
                    "Autopilot skill: the Stop hook keeps the session alive and "
                    "the harness re-invokes you with a `<task-notification>` when "
                    "the agent finishes."
                ),
                _ev_agent_dispatch(),
                _ev_agent_ack("a8a4f8da57ae914bb"),
                _ev_assistant_text(
                    "Blind reviewer dispatched; I'll be re-invoked with the report."
                ),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(
            self.fx.signal_content(), "a prose phantom must not mask a real launch"
        )
        self.assertEqual(pids, [])

    def test_earlier_consumed_task_does_not_mask_new_dispatch(self) -> None:
        """A completed-and-consumed earlier task must not cancel a freshly
        dispatched one: the work phase dispatches Tess, consumes her result, then
        dispatches Ivan — Ivan is still pending. (Per-id, not global counts.)"""
        self.fx.write_state(phase="build", next_phase="build")
        tp = self.fx.write_transcript(
            [
                _ev_agent_dispatch(),  # Tess
                _ev_agent_ack("1111aaaa"),
                _ev_task_notification("1111aaaa"),  # Tess completes
                _ev_assistant_text("Tess done; committing tests, dispatching Ivan."),
                _ev_agent_dispatch(),  # Ivan
                _ev_agent_ack("2222bbbb"),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(
            self.fx.signal_content(), "a new dispatch must be seen as pending"
        )
        self.assertEqual(pids, [])

    def test_orphan_launch_does_not_block_handoff(self) -> None:
        """Round-2 false positive (warden 22:21): a review session dispatches
        several reviewers; one never reports back (orphan). The model proceeds
        with the rest, consumes the LAST dispatch, and hands off. An older
        orphaned launch must NOT keep the session alive — only the most-recent
        launch decides."""
        self.fx.write_state(phase="review", next_phase="blind", phases_completed=[])
        tp = self.fx.write_transcript(
            [
                _ev_agent_dispatch(),  # reviewer A (orphan: never reports)
                _ev_agent_ack("aaaa0001"),
                _ev_agent_dispatch(),  # reviewer B
                _ev_agent_ack("bbbb0002"),
                _ev_task_notification("bbbb0002"),  # B completes; A never does
                _ev_assistant_text("Reviews in; gate passes; handing off to blind."),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertEqual(
            self.fx.signal_content(),
            "next",
            "an orphaned earlier launch must not stall the hand-off",
        )
        self.assertGreater(len(pids), 0)

    def test_orphan_latest_reviewer_in_review_phase_hands_off(self) -> None:
        """Warden PRD 00013 regression (2026-06-20): in a review-gated phase a
        parallel reviewer batch's LAST-launched reviewer never reports back, so
        it is the most-recent unconsumed launch. The model finished the whole
        phase (gate passes) and ended its turn, but the per-id detector saw that
        orphan as in-flight and the hook abstained on every Stop — no signal, no
        SIGINT — leaving the session idle at its prompt forever while the wrapper
        waited for an exit. In a review-gated phase the coverage gate (forced
        open here, mirroring a passed gate) is the keep-alive, so the pending
        check must NOT run; the hand-off proceeds."""
        self.fx.write_state(
            phase="blind", next_phase="blind", phases_completed=["review"]
        )
        tp = self.fx.write_transcript(
            [
                _ev_agent_dispatch(),  # reviewer A
                _ev_agent_ack("aaaa0001"),
                _ev_agent_dispatch(),  # reviewer B
                _ev_agent_ack("bbbb0002"),
                _ev_agent_dispatch(),  # reviewer C (orphan: latest, never reports)
                _ev_agent_ack("cccc0003"),
                _ev_task_notification("aaaa0001"),  # A completes
                _ev_task_notification("bbbb0002"),  # B completes; C never does
                _ev_assistant_text("Added regression test; coverage gate passes."),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertEqual(
            self.fx.signal_content(),
            "next",
            "a review-gated phase must defer to the gate, not stall on an "
            "orphaned latest reviewer",
        )
        self.assertGreater(len(pids), 0)


class AutoBackgroundedBashWaitTests(unittest.TestCase):
    """A long FOREGROUND Bash (codex review, `cargo test`) is silently
    AUTO-BACKGROUNDED by the harness into a tracked task; its recorded tool_use
    still says foreground, so neither the agent-launch ack nor the
    run_in_background flag fires. The doubt phase hits this every cycle and the
    review-coverage gate does NOT cover it (it gates the previous surface). The
    hook must abstain — even in a review-gated phase — while the model waits for
    the auto-backgrounded run or a scheduled wakeup. Regression for the
    2026-06-21 ddb doubt thrash-halt (`cargo test-ci` auto-backgrounded, the
    session waited via ScheduleWakeup, the hook halted on the 3rd yield).
    gate_blocks is forced open by _run_hook_with_transcript, mirroring a passed
    coverage gate for the previous surface."""

    def setUp(self) -> None:
        self.fx = StopHookFixture()
        self.addCleanup(self.fx.cleanup)

    def test_doubt_waiting_on_autobg_bash_abstains(self) -> None:
        """The ddb regression: review-gated `doubt`, an auto-backgrounded
        `cargo test` still running, model polling its output — abstain."""
        self.fx.write_state(
            phase="doubt", next_phase="doubt", phases_completed=["review", "blind"]
        )
        tp = self.fx.write_transcript(
            [
                _ev_assistant_text("Running the fast test tier for the coverage gate."),
                _ev_bg_launch_ack("b6qi55ate"),
                _ev_assistant_text("Auto-backgrounded; polling its output."),
                _ev_read(),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(
            self.fx.signal_content(),
            "must abstain while an auto-backgrounded test run is still in flight",
        )
        self.assertEqual(pids, [], "must NOT SIGINT while the bg run is pending")

    def test_doubt_schedule_wakeup_abstains(self) -> None:
        """Waiting via ScheduleWakeup (the 96e6dcdc posture) — abstain."""
        self.fx.write_state(
            phase="doubt", next_phase="doubt", phases_completed=["review", "blind"]
        )
        tp = self.fx.write_transcript(
            [
                _ev_bg_launch_ack("b6qi55ate"),
                _ev_assistant_text("I'll resume when the test tier completes."),
                _ev_schedule_wakeup(),
                _ev_assistant_text("Waiting on the scheduled wakeup."),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(self.fx.signal_content())
        self.assertEqual(pids, [])

    def test_handoff_edits_state_after_bg_run_hands_off(self) -> None:
        """The bg run finished and the model advanced state (Edit) — that is a
        real hand-off, not a wait. The most-recent Edit is AFTER the launch, so
        the hook must NOT abstain; it writes "next" and SIGINTs."""
        self.fx.write_state(
            phase="doubt", next_phase="doubt", phases_completed=["review", "blind"]
        )
        tp = self.fx.write_transcript(
            [
                _ev_bg_launch_ack("b6qi55ate"),
                _ev_task_notification("b6qi55ate"),
                _ev_assistant_text("Tests pass; recording the gate result and advancing."),
                _ev_edit(),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertEqual(
            self.fx.signal_content(),
            "next",
            "an Edit after the bg launch is a hand-off, not a wait",
        )
        self.assertGreater(len(pids), 0)

    def test_consumed_bg_run_without_pending_hands_off(self) -> None:
        """The bg run completed (notification) and was consumed, nothing else
        pending and no later wait marker — hand off normally."""
        self.fx.write_state(phase="build", next_phase="review")
        tp = self.fx.write_transcript(
            [
                _ev_bg_launch_ack("b6qi55ate"),
                _ev_task_notification("b6qi55ate"),
                _ev_assistant_text("Build done; proceeding."),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertEqual(self.fx.signal_content(), "next")
        self.assertGreater(len(pids), 0)

    def test_wait_does_not_increment_thrash_counter(self) -> None:
        """A genuine wait is real work, not a no-progress thrash: the abstain
        must leave the thrash counter untouched even in a review-gated phase."""
        st = _make_state(
            phase="doubt", next_phase="doubt", phases_completed=["review", "blind"]
        )
        st["phase_guard"] = {"key": hook._progress_key(st), "count": 2}
        (self.fx.autopilot_dir / "state.json").write_text(json.dumps(st))
        tp = self.fx.write_transcript([_ev_bg_launch_ack("b6qi55ate"), _ev_read()])
        _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(self.fx.signal_content())
        self.assertEqual(
            self.fx.read_state()["phase_guard"]["count"],
            2,
            "a wait must not advance the thrash counter toward a halt",
        )

    def test_orphan_reviewer_without_bg_marker_still_hands_off(self) -> None:
        """Guard against over-reach: a review-gated phase with only an orphaned
        AGENT (no bg-bash, no wakeup) must still hand off — _waiting_on_async
        must not fire, leaving the 2026-06-20 orphan path intact."""
        self.fx.write_state(
            phase="blind", next_phase="blind", phases_completed=["review"]
        )
        tp = self.fx.write_transcript(
            [
                _ev_agent_dispatch(),
                _ev_agent_ack("cccc0003"),
                _ev_assistant_text("Added regression test; coverage gate passes."),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertEqual(self.fx.signal_content(), "next")
        self.assertGreater(len(pids), 0)


if __name__ == "__main__":
    unittest.main()
