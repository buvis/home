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
import time
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
            mock.patch.object(hook, "_foreign_stop_event", return_value=False),
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
            mock.patch.object(hook, "_foreign_stop_event", return_value=False),
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


def _ev_attachment_notification(task_id: str = "abc123") -> dict:
    """A completion delivered while the session was ACTIVE: the harness records it
    as a `type: "attachment"` entry whose text lives under attachment.prompt —
    NOT a user message turn, so message.content is absent. Regression fixture for
    the 2026-06-22 loop stall (the hook only read message.content and never paired
    the completion with its launch)."""
    return {
        "type": "attachment",
        "attachment": {
            "prompt": f"<task-notification>\n<task-id>{task_id}</task-id>\n",
            "commandMode": "task-notification",
        },
    }


def _ev_queueop_notification(task_id: str = "abc123") -> dict:
    """The queue-operation mirror of an active-session completion: the
    <task-notification> text is under the top-level `content`, message absent."""
    return {
        "type": "queue-operation",
        "operation": "task-notification",
        "content": f"<task-notification>\n<task-id>{task_id}</task-id>\n",
    }


def _ev_user_text(text: str) -> dict:
    """A user-role turn carrying arbitrary text (e.g. injected SKILL.md prose)."""
    return {"type": "user", "message": {"role": "user", "content": text}}


def _ev_agent_ack(agent_id: str) -> dict:
    """A real launch ack: a tool_result that starts with the launch phrase."""
    return _ev_tool_result(
        f"Async agent launched successfully. agentId: {agent_id} (internal ID)"
    )


def _ev_agent_ack_with_output(agent_id: str, output_file: str) -> dict:
    """A real launch ack that also carries the `output_file:` line (a symlink to
    the subagent JSONL), exactly as the harness emits it. Its mtime is the
    liveness signal the hook stats to tell a slow-but-alive reviewer from a dead
    orphan."""
    return _ev_tool_result(
        "Async agent launched successfully.\n"
        f"agentId: {agent_id} (internal ID - do not mention to user.)\n"
        "The agent is working in the background.\n"
        f"output_file: {output_file}\n"
        "Do NOT Read or tail this file via the shell tool."
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
            mock.patch.object(hook, "_foreign_stop_event", return_value=False),
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
                mock.patch.object(hook, "_foreign_stop_event", return_value=False),
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

    def test_guard_persists_when_cap_hook_import_unavailable(self) -> None:
        """Audit #7: if the cap-hook import failed (_atomic_write_state is None),
        the guard must STILL be persisted via _persist_state's local fallback —
        otherwise the count resets every session and the runaway breaker silently
        never trips."""
        self._seed(
            guard_count=hook.PHASE_THRASH_LIMIT - 1,
            phase="blind",
            next_phase="blind",
            phases_completed=["review"],
        )
        with mock.patch.object(hook, "_atomic_write_state", None):
            self._run_no_gate()
        state = self._read_state()
        self.assertEqual(
            state["thrash_halt"]["repeats"],
            hook.PHASE_THRASH_LIMIT,
            "the thrash halt must persist even without the shared atomic writer",
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

    def test_rework_and_doubt_signals_count_as_progress(self) -> None:
        """Audit 2026-06-23: the fingerprint must move when a task is queued for
        rework or a doubt is recorded — real progress the coarse counters miss —
        so a genuinely-advancing phase is not mistaken for a no-progress thrash.
        Each field is append-only, so it cannot DEFEAT the breaker when stuck."""
        base = _make_state(phase="review", next_phase="review")
        k0 = hook._progress_key(base)
        self.assertNotEqual(
            k0, hook._progress_key({**base, "rework_task_ids": ["t1"]})
        )
        self.assertNotEqual(k0, hook._progress_key({**base, "doubts": [{"q": "x"}]}))
        self.assertNotEqual(
            k0, hook._progress_key({**base, "doubts_rubric_verdicts": [{"r": 1}]})
        )

    def test_breaker_still_trips_when_rework_and_doubts_stable(self) -> None:
        """The widened key must NOT defeat the breaker: a phase re-entering with
        rework_task_ids/doubts UNCHANGED still trips at the limit."""
        self._seed(
            guard_count=hook.PHASE_THRASH_LIMIT - 1,
            phase="review",
            next_phase="review",
            rework_task_ids=["t1"],
            doubts=[{"q": "x"}],
        )
        self._run_no_gate()
        self.assertIsNone(
            self.fx.signal_content(),
            "unchanged rework/doubt signals must not reset the breaker",
        )

    def test_breaker_scoped_to_next_not_done(self) -> None:
        """The breaker only governs the "next" hand-off; batch end ("done")
        is bounded separately and must never be withheld."""
        st = _make_state(phase="done", next_phase="")
        st["phase_guard"] = {"key": "whatever", "count": hook.PHASE_THRASH_LIMIT + 9}
        self._state_path().write_text(json.dumps(st))
        self._run_no_gate()
        self.assertEqual(self.fx.signal_content(), "done")

    # -- review-file count as a durable progress signal (thin-B, warden 00020) --

    def _reviews_dir(self) -> Path:
        d = self.fx.cwd / "dev" / "local" / "reviews"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_review_cycle_count_counts_only_numbered_cycle_files(self) -> None:
        """_review_cycle_count counts `<prd>-review-<N>.md` for THIS prd only,
        excluding blind/doubt/audit renders and other PRDs' review files."""
        reviews = self._reviews_dir()
        for name in (
            "00099-test-review-1.md",
            "00099-test-review-2.md",
            "00099-test-blind-review.md",  # excluded: not numbered
            "00099-test-doubt-review.md",  # excluded: not numbered
            "00099-test-audit.md",  # excluded: not a review file
            "00098-other-review-1.md",  # excluded: different prd
        ):
            (reviews / name).write_text("x")
        st = _make_state(prd="00099-test.md")
        self.assertEqual(hook._review_cycle_count(self.fx.autopilot_dir, st), 2)

    def test_review_cycle_count_fails_open_when_dir_missing(self) -> None:
        """No reviews/ dir yet (first cycle in flight) returns 0, not an error."""
        st = _make_state(prd="00099-test.md")
        self.assertEqual(hook._review_cycle_count(self.fx.autopilot_dir, st), 0)

    def test_progress_key_moves_with_review_file_count(self) -> None:
        """A new durable review file is real progress: the fingerprint must move
        as the on-disk count rises (warden 00020: cycles ran but state.cycle
        never moved, so the coarse key looked frozen)."""
        base = _make_state(phase="review", next_phase="review")
        self.assertNotEqual(hook._progress_key(base, 0), hook._progress_key(base, 1))
        self.assertNotEqual(hook._progress_key(base, 1), hook._progress_key(base, 2))

    def test_new_review_file_resets_thrash_counter(self) -> None:
        """End-to-end: a review session at the limit that landed a NEW review
        file since the last hand-off is progressing, not thrashing. main() must
        reset the counter and write "next", not halt. This is the warden-00020
        fix: the durable on-disk review count is the progress signal the guard
        reads when the model forgot to bump state.cycle."""
        st = _make_state(phase="review", next_phase="review", prd="00099-test.md")
        # Guard already at the limit, keyed at the PREVIOUS count (0 files).
        st["phase_guard"] = {
            "key": hook._progress_key(st, 0),
            "count": hook.PHASE_THRASH_LIMIT - 1,
        }
        self._state_path().write_text(json.dumps(st))
        # A new review cycle landed its file on disk before this hand-off.
        (self._reviews_dir() / "00099-test-review-1.md").write_text("findings")
        self._run_no_gate()
        self.assertEqual(self.fx.signal_content(), "next")
        state = self._read_state()
        self.assertEqual(state["phase_guard"]["count"], 1)
        self.assertNotIn("thrash_halt", state)

    def test_stable_review_file_count_still_trips(self) -> None:
        """The on-disk count must NOT defeat the breaker: a review re-entering
        with the SAME review-file count (no new cycle landed) still trips. This
        is the 00020 case itself, where zero durable artifacts were produced
        across re-entries: halting for inspection is correct."""
        (self._reviews_dir() / "00099-test-review-1.md").write_text("findings")
        st = _make_state(phase="review", next_phase="review", prd="00099-test.md")
        st["phase_guard"] = {
            "key": hook._progress_key(st, 1),  # keyed at the SAME count main sees
            "count": hook.PHASE_THRASH_LIMIT - 1,
        }
        self._state_path().write_text(json.dumps(st))
        self._run_no_gate()
        self.assertIsNone(self.fx.signal_content())
        self.assertGreaterEqual(
            self._read_state()["thrash_halt"]["repeats"], hook.PHASE_THRASH_LIMIT
        )


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

    def test_consumed_attachment_notification_hands_off(self) -> None:
        """2026-06-22 stall regression. A task that completes while the session is
        ACTIVE (the common case: the model overlaps work after dispatching) arrives
        as a `type: "attachment"` entry, NOT a user <task-notification> turn. The
        hook must still pair it with its launch and hand off. Before the
        _notif_text fix the completion was invisible (only message.content was
        read), the launch looked forever pending, and the loop never advanced."""
        self.fx.write_state(phase="build", next_phase="review")
        tp = self.fx.write_transcript(
            [
                _ev_agent_dispatch(),
                _ev_tool_result(LAUNCH_ACK),
                _ev_attachment_notification("abc123"),
                _ev_assistant_text("Reviewer returned; advancing."),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertEqual(self.fx.signal_content(), "next")
        self.assertGreater(len(pids), 0)

    def test_consumed_queueop_notification_hands_off(self) -> None:
        """The queue-operation mirror of an active-session completion must also
        pair with its launch and hand off."""
        self.fx.write_state(phase="build", next_phase="review")
        tp = self.fx.write_transcript(
            [
                _ev_agent_dispatch(),
                _ev_tool_result(LAUNCH_ACK),
                _ev_queueop_notification("abc123"),
                _ev_assistant_text("Reviewer returned; advancing."),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertEqual(self.fx.signal_content(), "next")
        self.assertGreater(len(pids), 0)

    def test_unconsumed_attachment_notification_abstains(self) -> None:
        """An attachment-shaped completion that arrived but has not yet been
        consumed (no assistant turn after it) must still abstain, exactly like the
        user-turn shape — the keep-alive for a real in-flight result."""
        self.fx.write_state(phase="build", next_phase="review")
        tp = self.fx.write_transcript(
            [
                _ev_agent_dispatch(),
                _ev_tool_result(LAUNCH_ACK),
                _ev_assistant_text("dispatched; overlapping other work..."),
                _ev_attachment_notification("abc123"),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(self.fx.signal_content())
        self.assertEqual(pids, [])

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
        waited for an exit. In a review-gated phase the pending check now runs in
        LIVENESS-ONLY mode (the coverage gate, forced open here, covers the
        previous surface): these acks carry NO output_file, so the orphan is not
        provably alive and the hand-off proceeds — the 2026-06-20 fix preserved
        through the liveness refactor."""
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

    def test_review_three_unconsumed_bg_reviewers_abstains(self) -> None:
        """PRD 00034: Phase-4 work-completion launches Bob, Carl, and Diana as
        three background-Bash reviewers in ONE turn and yields with NO
        reviewer-output write. All three launches are unconsumed and there is no
        later Edit, so _waiting_on_async must abstain — the same count-based path
        as the single-launch cases, now exercised over three launches. This is
        the jink-00025 orphan-strand class the PRD converts Diana to avoid."""
        self.fx.write_state(phase="review", next_phase="review", phases_completed=[])
        tp = self.fx.write_transcript(
            [
                _ev_assistant_text("Launching Bob, Carl, and Diana as background Bash."),
                _ev_bg_launch_ack("bob4x9k2a"),
                _ev_bg_launch_ack("carl7m3p1"),
                _ev_bg_launch_ack("diana8q5z"),
                _ev_assistant_text("All three reviewers running; awaiting their output files."),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(
            self.fx.signal_content(),
            "must abstain while all three bg-Bash reviewers are still in flight",
        )
        self.assertEqual(pids, [], "must NOT SIGINT while any reviewer is pending")

    def test_review_two_of_three_reviewers_reported_still_abstains(self) -> None:
        """"Until ALL report": Bob and Carl have completed and been consumed, but
        Diana's launch is still unconsumed with no later Edit. One unconsumed
        launch is enough to keep the session alive — a hook that handed off as
        soon as the first reviewer reported would SIGINT-strand the still-running
        Diana. Abstain."""
        self.fx.write_state(phase="review", next_phase="review", phases_completed=[])
        tp = self.fx.write_transcript(
            [
                _ev_assistant_text("Launching Bob, Carl, and Diana as background Bash."),
                _ev_bg_launch_ack("bob4x9k2a"),
                _ev_bg_launch_ack("carl7m3p1"),
                _ev_bg_launch_ack("diana8q5z"),
                _ev_task_notification("bob4x9k2a"),
                _ev_task_notification("carl7m3p1"),
                _ev_assistant_text("Bob and Carl reported; Diana still running."),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(
            self.fx.signal_content(),
            "one still-running reviewer (Diana) must keep the session alive",
        )
        self.assertEqual(pids, [], "must NOT SIGINT while Diana is still pending")

    def test_review_mixed_agent_and_bash_turn_all_pending_abstains(self) -> None:
        """PRD 00034 "Mixed turn": Phase-4 work-completion launches Alice as a
        Task Agent (hex agentId) AND Bob/Carl/Diana as three background-Bash
        reviewers (base-36 bash ids) in ONE turn, then yields. With all four
        launches unconsumed and no later Edit, the hook must abstain. Guards the
        id-namespace discrimination: the hex agent ack sharing the turn must not
        break the base-36 bg-launch detection (_waiting_on_async) that keeps the
        session alive — the mixed dispatch shape the PRD mandates but that the
        bash-only and agent-only tests never exercise together."""
        self.fx.write_state(phase="review", next_phase="review", phases_completed=[])
        tp = self.fx.write_transcript(
            [
                _ev_assistant_text("Launching Alice (Agent) + Bob/Carl/Diana (bg-Bash) in one turn."),
                _ev_agent_ack("a11ceface"),
                _ev_bg_launch_ack("bob4x9k2a"),
                _ev_bg_launch_ack("carl7m3p1"),
                _ev_bg_launch_ack("diana8q5z"),
                _ev_assistant_text("All four reviewers running; awaiting their output files."),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(
            self.fx.signal_content(),
            "a mixed 3-bash + 1-agent turn must abstain while any reviewer is in flight",
        )
        self.assertEqual(
            pids, [], "must NOT SIGINT while any of the four reviewers is pending"
        )

    def test_review_mixed_agent_and_bash_turn_all_reported_hands_off(self) -> None:
        """PRD 00034 "Mixed turn", the hand-off direction: each of the four
        reviewers emits its own paired <task-notification> — base-36 ids for the
        three bg-Bash reviewers, the hex agentId for Alice — and all are consumed.
        With nothing left in flight and no wait marker, the hook hands off (writes
        "next", SIGINTs). Confirms the two id namespaces are consumed
        independently within a single turn (autopilot_stop_hook.py:137-138)."""
        self.fx.write_state(phase="review", next_phase="review", phases_completed=[])
        tp = self.fx.write_transcript(
            [
                _ev_assistant_text("Launching Alice (Agent) + Bob/Carl/Diana (bg-Bash) in one turn."),
                _ev_agent_ack("a11ceface"),
                _ev_bg_launch_ack("bob4x9k2a"),
                _ev_bg_launch_ack("carl7m3p1"),
                _ev_bg_launch_ack("diana8q5z"),
                _ev_task_notification("bob4x9k2a"),
                _ev_task_notification("carl7m3p1"),
                _ev_task_notification("diana8q5z"),
                _ev_task_notification("a11ceface"),
                _ev_assistant_text("All four reviewers reported; consolidating findings."),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertEqual(
            self.fx.signal_content(),
            "next",
            "once all four reviewers (3 bg-Bash + Alice) report, the hook hands off",
        )
        self.assertGreater(len(pids), 0)


class LivenessAwareReviewBatchTests(unittest.TestCase):
    """A parallel reviewer batch can complete OUT OF launch order: a slow reviewer
    launched FIRST (e.g. a codex run) may still be working when a later-launched
    sibling has already finished and been consumed. The launch-order heuristic
    read that as "all done" and SIGINT-stranded the live reviewer — it never
    reported, the review never consolidated, and the loop thrash-halted (the jink
    2026-06-22 death). The hook must instead consult each in-flight launch's
    output_file: a still-growing one means the model is genuinely waiting
    (abstain); a frozen or unstattable one is a dead orphan (hand off). Phase is
    "review" — non-review-gated, so _pending_background_task actually runs."""

    def setUp(self) -> None:
        self.fx = StopHookFixture()
        self.addCleanup(self.fx.cleanup)

    def _output_file(self, agent_id: str, age_secs: float) -> str:
        """Create a real file standing in for the subagent JSONL, with an mtime
        age_secs in the past, and return its path."""
        p = self.fx.cwd / f"{agent_id}.output"
        p.write_text("subagent transcript ...\n")
        ts = time.time() - age_secs
        os.utime(p, (ts, ts))
        return str(p)

    def test_alive_earlier_launch_abstains_when_later_consumed(self) -> None:
        """jink regression: A (launched first) is still running with a FRESH
        output_file; B and C finished and C (the latest launch) was consumed. The
        launch-order rule would hand off and strand A — the hook must abstain on
        A's liveness instead."""
        self.fx.write_state(phase="review", next_phase="review", phases_completed=[])
        a_out = self._output_file("aaaa0001", age_secs=3)  # fresh -> alive
        b_out = self._output_file("bbbb0002", age_secs=3)
        c_out = self._output_file("cccc0003", age_secs=3)
        tp = self.fx.write_transcript(
            [
                _ev_agent_dispatch(),
                _ev_agent_ack_with_output("aaaa0001", a_out),  # A: stays running
                _ev_agent_dispatch(),
                _ev_agent_ack_with_output("bbbb0002", b_out),
                _ev_agent_dispatch(),
                _ev_agent_ack_with_output("cccc0003", c_out),  # C: latest launch
                _ev_task_notification("bbbb0002"),
                _ev_task_notification("cccc0003"),  # C completes, consumed below
                _ev_assistant_text("Saved C's review; still waiting on A."),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(
            self.fx.signal_content(),
            "a still-alive earlier reviewer must keep the session alive",
        )
        self.assertEqual(
            pids, [], "must NOT SIGINT while an earlier reviewer is still alive"
        )

    def test_frozen_earlier_launch_hands_off(self) -> None:
        """A truly dead/orphaned earlier launch (FROZEN output_file) must not keep
        the session alive: with the latest launch consumed, the hand-off proceeds
        — the 2026-06-20 orphan path stays intact."""
        self.fx.write_state(phase="review", next_phase="blind", phases_completed=[])
        a_out = self._output_file("aaaa0001", age_secs=24 * 3600)  # frozen -> dead
        c_out = self._output_file("cccc0003", age_secs=24 * 3600)
        tp = self.fx.write_transcript(
            [
                _ev_agent_dispatch(),
                _ev_agent_ack_with_output("aaaa0001", a_out),  # A: orphan, frozen
                _ev_agent_dispatch(),
                _ev_agent_ack_with_output("cccc0003", c_out),  # C: latest
                _ev_task_notification("cccc0003"),
                _ev_assistant_text("Reviews in; gate passes; handing off to blind."),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertEqual(
            self.fx.signal_content(),
            "next",
            "a frozen orphan must not stall the hand-off",
        )
        self.assertGreater(len(pids), 0)

    def test_unstattable_output_file_falls_back_to_launch_order(self) -> None:
        """An output_file path that does not exist (task dir already reaped) is
        not alive; detection degrades to the launch-order rule, which hands off on
        a consumed latest launch rather than abstaining on nothing."""
        self.fx.write_state(phase="review", next_phase="blind", phases_completed=[])
        missing = str(self.fx.cwd / "gone" / "aaaa0001.output")
        c_out = self._output_file("cccc0003", age_secs=3)  # fresh but consumed
        tp = self.fx.write_transcript(
            [
                _ev_agent_dispatch(),
                _ev_agent_ack_with_output("aaaa0001", missing),  # A: file gone
                _ev_agent_dispatch(),
                _ev_agent_ack_with_output("cccc0003", c_out),
                _ev_task_notification("cccc0003"),
                _ev_assistant_text("Reviews in; handing off."),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertEqual(self.fx.signal_content(), "next")
        self.assertGreater(len(pids), 0)


class ReviewGatedInFlightWorkKeepAliveTests(unittest.TestCase):
    """The 2026-06-23 thrash-halt fix (warden 00018 blind, playground 00005
    doubt). A review-gated phase (blind/doubt) does its OWN in-flight work — the
    blind phase dispatches [BLIND] /work, the doubt phase dispatches [DOUBT]
    /work or the Claude-fallback reviewer — as a background Agent. The coverage
    gate keeps the session alive only for the PREVIOUS surface, and the earlier
    blanket SKIP of the pending check meant that current-phase Agent had NO
    keep-alive: it was SIGINT-stranded on the yield, the phase never recorded
    completion, and the breaker thrash-halted the loop. The pending check now
    runs in LIVENESS-ONLY mode in review-gated phases: a provably-alive in-flight
    launch (fresh output_file) abstains; a frozen/unstattable orphan hands off
    (the 2026-06-20 fix). gate_blocks is forced open by _run_hook_with_transcript,
    mirroring a passed gate for the previous surface."""

    def setUp(self) -> None:
        self.fx = StopHookFixture()
        self.addCleanup(self.fx.cleanup)

    def _output_file(self, agent_id: str, age_secs: float) -> str:
        p = self.fx.cwd / f"{agent_id}.output"
        p.write_text("subagent transcript ...\n")
        ts = time.time() - age_secs
        os.utime(p, (ts, ts))
        return str(p)

    def test_blind_inflight_work_with_fresh_output_abstains(self) -> None:
        """Warden 00018 regression: blind phase, a [BLIND] /work Agent dispatched
        with a FRESH output_file and not yet consumed, the model waiting. Before
        the liveness refactor the review-gated SKIP let the hook SIGINT this
        live worker (task 7 stayed in_progress with zero attempts) and thrash-
        halt. It must now abstain."""
        self.fx.write_state(
            phase="blind", next_phase="blind", phases_completed=["review"]
        )
        out = self._output_file("d00d0001", age_secs=3)  # fresh -> alive
        tp = self.fx.write_transcript(
            [
                _ev_agent_dispatch(),  # /work dispatches the [BLIND] task
                _ev_agent_ack_with_output("d00d0001", out),
                _ev_assistant_text("[BLIND] task dispatched; waiting for the worker."),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(
            self.fx.signal_content(),
            "a live in-flight [BLIND] /work dispatch must keep the session alive",
        )
        self.assertEqual(
            pids, [], "must NOT SIGINT while the blind-phase worker is still alive"
        )

    def test_doubt_inflight_reviewer_with_fresh_output_abstains(self) -> None:
        """Playground 00005 regression: doubt phase, an in-flight reviewer /
        [DOUBT] worker Agent with a FRESH output_file, unconsumed -> abstain so
        the phase can reach phases_completed instead of thrash-halting."""
        self.fx.write_state(
            phase="doubt", next_phase="doubt", phases_completed=["review", "blind"]
        )
        out = self._output_file("d0bd0002", age_secs=5)  # fresh -> alive
        tp = self.fx.write_transcript(
            [
                _ev_agent_dispatch(),
                _ev_agent_ack_with_output("d0bd0002", out),
                _ev_assistant_text("Doubt reviewer dispatched; awaiting the report."),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(self.fx.signal_content())
        self.assertEqual(pids, [])

    def test_blind_frozen_orphan_hands_off(self) -> None:
        """2026-06-20 orphan path preserved: a blind-phase Agent whose output_file
        is FROZEN (dead/orphaned) is not provably alive, so liveness-only falls
        through and the hand-off proceeds — no idle deadlock."""
        self.fx.write_state(
            phase="blind", next_phase="blind", phases_completed=["review"]
        )
        out = self._output_file("dead0003", age_secs=24 * 3600)  # frozen -> dead
        tp = self.fx.write_transcript(
            [
                _ev_agent_dispatch(),
                _ev_agent_ack_with_output("dead0003", out),
                _ev_assistant_text("Reviewer orphaned; phase complete, handing off."),
            ]
        )
        pids = _run_hook_with_transcript(self.fx, tp)
        self.assertEqual(
            self.fx.signal_content(),
            "next",
            "a frozen orphan in a review-gated phase must hand off, not stall",
        )
        self.assertGreater(len(pids), 0)

    def test_review_gated_liveness_abstain_preserves_thrash_counter(self) -> None:
        """A live in-flight worker is real work, not a no-progress thrash: the
        abstain must leave the phase_guard counter untouched even in a review-
        gated phase, so a genuinely-progressing phase is never pushed toward a
        false halt."""
        st = _make_state(
            phase="blind", next_phase="blind", phases_completed=["review"]
        )
        st["phase_guard"] = {"key": hook._progress_key(st), "count": 2}
        (self.fx.autopilot_dir / "state.json").write_text(json.dumps(st))
        out = self._output_file("d00d0004", age_secs=3)
        tp = self.fx.write_transcript(
            [_ev_agent_dispatch(), _ev_agent_ack_with_output("d00d0004", out)]
        )
        _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(self.fx.signal_content())
        self.assertEqual(
            self.fx.read_state()["phase_guard"]["count"],
            2,
            "a liveness abstain must not advance the thrash counter",
        )


class YieldMarkerStampTests(unittest.TestCase):
    """The Stop hook must stamp <autopilot_dir>/.yielded-waiting when it abstains
    because a background task is in flight, and must NOT stamp it on any real
    hand-off or on the paused-phase early-return. Regression guard for the
    yield-marker feature."""

    def setUp(self) -> None:
        self.fx = StopHookFixture()
        self.addCleanup(self.fx.cleanup)

    def _marker(self) -> Path:
        return self.fx.autopilot_dir / ".yielded-waiting"

    # ------------------------------------------------------------------
    # 1. Marker IS created on in-flight-Agent abstain
    # ------------------------------------------------------------------

    def test_marker_created_on_inflight_agent_abstain(self) -> None:
        """_pending_background_task abstain stamps .yielded-waiting and writes no signal."""
        self.fx.write_state(phase="build", next_phase="review")
        tp = self.fx.write_transcript(
            [_ev_agent_dispatch(), _ev_tool_result(LAUNCH_ACK)]
        )
        _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(
            self.fx.signal_content(),
            "abstain must write no signal",
        )
        self.assertTrue(
            self._marker().exists(),
            ".yielded-waiting must be created on an in-flight-Agent abstain",
        )

    # ------------------------------------------------------------------
    # 2. Marker IS created on auto-backgrounded-Bash abstain
    # ------------------------------------------------------------------

    def test_marker_created_on_autobg_bash_abstain(self) -> None:
        """_waiting_on_async abstain stamps .yielded-waiting and writes no signal."""
        self.fx.write_state(
            phase="doubt", next_phase="doubt", phases_completed=["review", "blind"]
        )
        tp = self.fx.write_transcript([_ev_bg_launch_ack("b6qi55ate"), _ev_read()])
        _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(
            self.fx.signal_content(),
            "abstain must write no signal",
        )
        self.assertTrue(
            self._marker().exists(),
            ".yielded-waiting must be created on an auto-backgrounded-Bash abstain",
        )

    # ------------------------------------------------------------------
    # 3. Marker NOT created on a "next" hand-off
    # ------------------------------------------------------------------

    def test_marker_not_created_on_next_handoff(self) -> None:
        """A normal "next" hand-off writes the signal but must not stamp the marker."""
        self.fx.write_state(phase="build", next_phase="review")
        with mock.patch.object(hook, "gate_blocks", return_value=(False, "")):
            _run_hook(self.fx)
        self.assertEqual(self.fx.signal_content(), "next")
        self.assertFalse(
            self._marker().exists(),
            ".yielded-waiting must NOT be created on a next hand-off",
        )

    # ------------------------------------------------------------------
    # 4. Marker NOT created on a "done" hand-off
    # ------------------------------------------------------------------

    def test_marker_not_created_on_done_handoff(self) -> None:
        """Batch-end "done" hand-off must not stamp the marker."""
        self.fx.write_state(phase="build", next_phase="")
        _run_hook(self.fx)
        self.assertEqual(self.fx.signal_content(), "done")
        self.assertFalse(
            self._marker().exists(),
            ".yielded-waiting must NOT be created on a done hand-off",
        )

    # ------------------------------------------------------------------
    # 5. Marker NOT created on a "task_aborted" hand-off
    # ------------------------------------------------------------------

    def test_marker_not_created_on_task_aborted_handoff(self) -> None:
        """stall_reason.stalled == subagent_prompt_overrun hand-off must not stamp
        the marker."""
        self.fx.write_state(
            phase="build",
            next_phase="review",
            stall_reason={"stalled": "subagent_prompt_overrun", "task": "t1"},
        )
        _run_hook(self.fx)
        self.assertEqual(self.fx.signal_content(), "task_aborted")
        self.assertFalse(
            self._marker().exists(),
            ".yielded-waiting must NOT be created on a task_aborted hand-off",
        )

    # ------------------------------------------------------------------
    # 6. Marker NOT created when phase == "paused"
    # ------------------------------------------------------------------

    def test_marker_not_created_on_paused_phase(self) -> None:
        """phase == paused exits before the abstain sites; no signal, no marker."""
        self.fx.write_state(
            phase="paused", cap_pause_reason="budget exhausted", next_phase="review"
        )
        _run_hook(self.fx)
        self.assertIsNone(
            self.fx.signal_content(),
            "paused phase must write no signal",
        )
        self.assertFalse(
            self._marker().exists(),
            ".yielded-waiting must NOT be created when phase == paused",
        )

    # ------------------------------------------------------------------
    # 7. Fail-open: OSError from Path.touch must not propagate; abstain unchanged
    # ------------------------------------------------------------------

    def test_touch_oserror_does_not_propagate_and_abstain_unchanged(self) -> None:
        """If Path.touch raises OSError the abstain still returns (no signal written)
        and main() does not raise."""
        self.fx.write_state(phase="build", next_phase="review")
        tp = self.fx.write_transcript(
            [_ev_agent_dispatch(), _ev_tool_result(LAUNCH_ACK)]
        )
        with mock.patch.object(hook.Path, "touch", side_effect=OSError("disk full")):
            # Must not raise.
            _run_hook_with_transcript(self.fx, tp)
        self.assertIsNone(
            self.fx.signal_content(),
            "abstain must still write no signal even when touch raises OSError",
        )


class NestedAgentStopEventTests(unittest.TestCase):
    """Stop events fired by NESTED agents must not drive the loop.

    2026-07-02 (PRD 00034 review, twice): the codex reviewer's own Stop hook
    chain (~/.codex/hooks.json mirrors claude's and included this hook) ran
    with the loop's inherited _AUTOPILOT_LOOP and cwd. The hook computed
    "next" off live state, ghost-incremented phase_guard, and
    find_and_signal_claude walked up from codex to the MAIN session and
    SIGINT-killed it mid-review. Two ghost hand-offs plus the work session's
    real one tripped the thrash breaker; the wrapper halted with the backlog
    unprocessed. The same applies to a nested `claude -p` reviewer (Diana):
    its Stop event sees a SECOND claude ancestor (the main session) above
    itself and must be ignored too.
    """

    def setUp(self) -> None:
        self.fx = StopHookFixture()
        self.addCleanup(self.fx.cleanup)
        # Hand-off-ready state: without the provenance guard this writes
        # "next", bumps phase_guard, and calls find_and_signal_claude.
        self.fx.write_state(phase="build", next_phase="review")

    def _run(
        self,
        transcript_path: str | None = None,
        tree: dict[int, tuple[str, int]] | None = None,
    ) -> list[int]:
        """Run main() with an optional stdin transcript_path and an optional
        fake process tree {pid: (comm, ppid)} rooted at the REAL os.getppid()."""
        signalled: list[int] = []

        def fake_signal_claude(pid: int) -> bool:
            signalled.append(pid)
            return True

        payload: dict = {"session_id": "test"}
        if transcript_path is not None:
            payload["transcript_path"] = transcript_path

        patches = [
            mock.patch.object(hook.Path, "cwd", return_value=self.fx.cwd),
            mock.patch.object(hook, "find_and_signal_claude", fake_signal_claude),
            mock.patch.object(hook.sys, "stdin", io.StringIO(json.dumps(payload))),
        ]
        if tree is not None:
            comms = {pid: comm for pid, (comm, _) in tree.items()}
            parents = {pid: ppid for pid, (_, ppid) in tree.items()}
            patches.append(
                mock.patch.object(hook, "comm_for", lambda pid: comms.get(pid, ""))
            )
            patches.append(
                mock.patch.object(hook, "parent_of", lambda pid: parents.get(pid, 0))
            )

        saved = os.environ.pop("_AUTOPILOT_LOOP", None)
        try:
            os.environ["_AUTOPILOT_LOOP"] = "12345"
            with mock.patch.object(hook, "gate_blocks", return_value=(False, "")):
                for p in patches:
                    p.start()
                    self.addCleanup(p.stop)
                hook.main()
        finally:
            os.environ.pop("_AUTOPILOT_LOOP", None)
            if saved is not None:
                os.environ["_AUTOPILOT_LOOP"] = saved
        return signalled

    def _assert_ignored(self, pids: list[int]) -> None:
        self.assertIsNone(
            self.fx.signal_content(), "foreign Stop event must not write a signal"
        )
        self.assertEqual(
            pids, [], "foreign Stop event must not SIGINT any claude process"
        )
        self.assertNotIn(
            "phase_guard",
            self.fx.read_state(),
            "foreign Stop event must not touch the thrash guard",
        )

    def test_codex_stop_event_is_ignored(self) -> None:
        """A codex rollout transcript_path marks a foreign CLI's Stop event."""
        pids = self._run(
            transcript_path=(
                "/Users/bob/.codex/sessions/2026/07/02/rollout-2026-07-02.jsonl"
            )
        )
        self._assert_ignored(pids)

    def test_gemini_stop_event_is_ignored(self) -> None:
        """Same guard for a gemini-style transcript path."""
        pids = self._run(
            transcript_path="/Users/bob/.gemini/tmp/session-transcript.jsonl"
        )
        self._assert_ignored(pids)

    def test_nested_claude_reviewer_stop_event_is_ignored(self) -> None:
        """Two claude ancestors == a claude -p reviewer inside the loop session."""
        ppid = os.getppid()
        tree = {
            ppid: ("claude", 800),  # the -p reviewer that fired this Stop
            800: ("bash", 801),  # sonnet-run.sh / Bash tool subprocess
            801: ("claude", 802),  # the MAIN autopilot session
            802: ("bash", 1),  # the wrapper shell
        }
        pids = self._run(tree=tree)
        self._assert_ignored(pids)

    def test_main_session_single_claude_ancestor_still_hands_off(self) -> None:
        """Control: exactly one claude ancestor is the main session itself."""
        ppid = os.getppid()
        tree = {
            ppid: ("claude", 900),  # the main session that fired this Stop
            900: ("bash", 1),  # the wrapper shell
        }
        pids = self._run(tree=tree)
        self.assertEqual(self.fx.signal_content(), "next")
        self.assertGreater(len(pids), 0, "main session hand-off must auto-exit")


if __name__ == "__main__":
    unittest.main()
