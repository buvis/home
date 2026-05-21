"""Tests for desloppify_run.py.

Covers the pure, schema-tolerant pieces: the `--json` event summarizer,
the duration formatter, `_collect_qwen_task_ids`, and `main`'s
argument-error exits. The subprocess + heartbeat-thread orchestration is
integration-level and not exercised here.

Stdlib-only unittest.
"""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parent / "desloppify_run.py"

_spec = importlib.util.spec_from_file_location("desloppify_run", MODULE_PATH)
dr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dr)


class SummarizeEventTests(unittest.TestCase):
    def test_non_dict_input_is_stringified_and_shown(self) -> None:
        summary, show = dr.summarize_event("just a string")
        self.assertTrue(show)
        self.assertIn("just a string", summary)

    def test_token_count_event_is_silent(self) -> None:
        """High-frequency low-signal events are not echoed (but still count
        as activity — the caller updates the idle timer regardless)."""
        summary, show = dr.summarize_event({"msg": {"type": "token_count"}})
        self.assertFalse(show)
        self.assertEqual(summary, "")

    def test_reasoning_delta_event_is_silent(self) -> None:
        summary, show = dr.summarize_event(
            {"type": "agent_reasoning_delta", "text": "thinking"}
        )
        self.assertFalse(show)

    def test_exec_command_begin_renders_command(self) -> None:
        """A command-begin event names the command so a long `cargo test`
        is visible as the thing codex is blocked on."""
        summary, show = dr.summarize_event(
            {"msg": {"type": "exec_command_begin",
                     "command": ["bash", "-lc", "cargo test --workspace"]}}
        )
        self.assertTrue(show)
        self.assertIn("running:", summary)
        self.assertIn("cargo test --workspace", summary)

    def test_exec_command_end_reports_exit_code(self) -> None:
        summary, show = dr.summarize_event(
            {"msg": {"type": "exec_command_end",
                     "command": "cargo clippy", "exit_code": 0}}
        )
        self.assertTrue(show)
        self.assertIn("ran:", summary)
        self.assertIn("exit 0", summary)

    def test_item_envelope_command_execution(self) -> None:
        """The newer `{"type": "item.*", "item": {...}}` envelope is
        unwrapped the same as the `msg` envelope."""
        summary, show = dr.summarize_event(
            {"type": "item.started",
             "item": {"type": "command_execution", "command": "ls -la"}}
        )
        self.assertTrue(show)
        self.assertIn("ls -la", summary)

    def test_error_event_is_flagged(self) -> None:
        summary, show = dr.summarize_event(
            {"msg": {"type": "error", "message": "sandbox denied write"}}
        )
        self.assertTrue(show)
        self.assertIn("error", summary.lower())
        self.assertIn("sandbox denied write", summary)

    def test_agent_message_renders_text(self) -> None:
        summary, show = dr.summarize_event(
            {"msg": {"type": "agent_message", "message": "Removed 2 dead fns"}}
        )
        self.assertTrue(show)
        self.assertIn("Removed 2 dead fns", summary)

    def test_agent_message_without_text_is_silent(self) -> None:
        summary, show = dr.summarize_event({"msg": {"type": "agent_message"}})
        self.assertFalse(show)

    def test_patch_event_names_the_file(self) -> None:
        summary, show = dr.summarize_event(
            {"msg": {"type": "patch_apply", "path": "src/lib.rs"}}
        )
        self.assertTrue(show)
        self.assertIn("src/lib.rs", summary)

    def test_task_complete_is_shown(self) -> None:
        summary, show = dr.summarize_event({"msg": {"type": "task_complete"}})
        self.assertTrue(show)
        self.assertIn("task_complete", summary)

    def test_unknown_type_falls_back_to_type_name(self) -> None:
        summary, show = dr.summarize_event({"type": "some_future_event"})
        self.assertTrue(show)
        self.assertIn("some_future_event", summary)

    def test_typeless_dict_falls_back_to_compact_dump(self) -> None:
        """An event with no recognizable type still produces a non-empty
        line — the run stays observable even on an unknown schema."""
        summary, show = dr.summarize_event({"foo": "bar"})
        self.assertTrue(show)
        self.assertNotEqual(summary, "")


class FmtSecsTests(unittest.TestCase):
    def test_sub_minute(self) -> None:
        self.assertEqual(dr._fmt_secs(5), "5s")

    def test_minutes_and_seconds(self) -> None:
        self.assertEqual(dr._fmt_secs(65), "1m05s")

    def test_exact_ten_minutes(self) -> None:
        self.assertEqual(dr._fmt_secs(600), "10m00s")


class CollectQwenTaskIdsTests(unittest.TestCase):
    """`_collect_qwen_task_ids` is the QWEN_TASK_IDS-hint source for the
    batched de-slop pass — it must be honest about completed qwen attempts
    and schema-tolerant against missing/malformed state.json."""

    def _write_state(self, tmpdir: Path, state: dict) -> Path:
        autopilot_dir = tmpdir / "autopilot"
        autopilot_dir.mkdir()
        (autopilot_dir / "state.json").write_text(json.dumps(state))
        return autopilot_dir

    def test_returns_empty_when_autopilot_dir_is_none(self) -> None:
        self.assertEqual(dr._collect_qwen_task_ids(None), [])

    def test_returns_empty_when_state_json_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            autopilot_dir = Path(tmp) / "autopilot"
            autopilot_dir.mkdir()
            self.assertEqual(dr._collect_qwen_task_ids(autopilot_dir), [])

    def test_returns_empty_on_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            autopilot_dir = Path(tmp) / "autopilot"
            autopilot_dir.mkdir()
            (autopilot_dir / "state.json").write_text("{not valid json")
            self.assertEqual(dr._collect_qwen_task_ids(autopilot_dir), [])

    def test_collects_two_qwen_completed_task_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            autopilot_dir = self._write_state(Path(tmp), {
                "tasks": [
                    {"id": "1", "attempts": [
                        {"implementor": "qwen", "outcome": "completed"},
                    ]},
                    {"id": "2", "attempts": [
                        {"implementor": "claude", "outcome": "completed"},
                    ]},
                    {"id": "3", "attempts": [
                        {"implementor": "qwen", "outcome": "completed"},
                    ]},
                ],
            })
            self.assertEqual(
                dr._collect_qwen_task_ids(autopilot_dir), ["1", "3"]
            )

    def test_returns_empty_when_no_qwen_completions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            autopilot_dir = self._write_state(Path(tmp), {
                "tasks": [
                    {"id": "1", "attempts": [
                        {"implementor": "claude", "outcome": "completed"},
                    ]},
                ],
            })
            self.assertEqual(dr._collect_qwen_task_ids(autopilot_dir), [])

    def test_excludes_qwen_aborted_attempts(self) -> None:
        """A qwen attempt that failed step 5.5 (aborted outcome) should
        NOT be in the QWEN_TASK_IDS hint — an aborted qwen attempt never
        produced a commit, so there is no qwen-implemented commit range
        for the de-slop pass to scope over (the actual commits on that
        task came from a subsequent Claude re-dispatch instead)."""
        with tempfile.TemporaryDirectory() as tmp:
            autopilot_dir = self._write_state(Path(tmp), {
                "tasks": [
                    {"id": "1", "attempts": [
                        {"implementor": "qwen", "outcome": "aborted"},
                        {"implementor": "claude", "outcome": "completed"},
                    ]},
                ],
            })
            self.assertEqual(dr._collect_qwen_task_ids(autopilot_dir), [])

    def test_one_entry_per_task_even_with_multiple_qwen_completions(self) -> None:
        """The break-on-match guard prevents duplicate entries for a single
        task. Two completed qwen attempts on one task would otherwise yield
        the same id twice and inflate the QWEN_TASK_IDS hint."""
        with tempfile.TemporaryDirectory() as tmp:
            autopilot_dir = self._write_state(Path(tmp), {
                "tasks": [
                    {"id": "1", "attempts": [
                        {"implementor": "qwen", "outcome": "completed"},
                        {"implementor": "qwen", "outcome": "completed"},
                    ]},
                ],
            })
            self.assertEqual(dr._collect_qwen_task_ids(autopilot_dir), ["1"])

    def test_handles_null_attempts_field(self) -> None:
        """A state where `attempts` is explicitly null (rather than absent
        or an array) must not crash — best-effort de-slop never breaks
        the loop."""
        with tempfile.TemporaryDirectory() as tmp:
            autopilot_dir = self._write_state(Path(tmp), {
                "tasks": [
                    {"id": "1", "attempts": None},
                    {"id": "2", "attempts": [
                        {"implementor": "qwen", "outcome": "completed"},
                    ]},
                ],
            })
            self.assertEqual(dr._collect_qwen_task_ids(autopilot_dir), ["2"])

    def test_skips_non_dict_task_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            autopilot_dir = self._write_state(Path(tmp), {
                "tasks": [
                    "garbage",
                    {"id": "1", "attempts": [
                        {"implementor": "qwen", "outcome": "completed"},
                    ]},
                    None,
                ],
            })
            self.assertEqual(dr._collect_qwen_task_ids(autopilot_dir), ["1"])

    def test_skips_qwen_attempt_with_missing_task_id(self) -> None:
        """A completed qwen attempt on a task with no `id` field is
        silently dropped — the QWEN_TASK_IDS hint requires an id to scope
        the codex pass."""
        with tempfile.TemporaryDirectory() as tmp:
            autopilot_dir = self._write_state(Path(tmp), {
                "tasks": [
                    {"attempts": [
                        {"implementor": "qwen", "outcome": "completed"},
                    ]},
                    {"id": "2", "attempts": [
                        {"implementor": "qwen", "outcome": "completed"},
                    ]},
                ],
            })
            self.assertEqual(dr._collect_qwen_task_ids(autopilot_dir), ["2"])


class MainArgErrorTests(unittest.TestCase):
    def test_missing_prompt_file_arg_exits_2(self) -> None:
        self.assertEqual(dr.main(["desloppify_run.py"]), 2)

    def test_unreadable_prompt_file_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "nope.md")
            self.assertEqual(dr.main(["desloppify_run.py", missing]), 2)


if __name__ == "__main__":
    unittest.main()
