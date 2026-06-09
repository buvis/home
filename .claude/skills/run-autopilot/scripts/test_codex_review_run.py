"""Tests for codex_review_run.py.

Covers the pure, schema-tolerant pieces: the `--json` event summarizer,
the duration formatter, `_collect_qwen_task_ids`, `main`'s argument-error
exits, and the exit contract (3=codex unavailable, 4=ran but failed) the
doubt phase relies on for its Claude fallback.

Stdlib-only unittest.
"""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parent / "codex_review_run.py"

_spec = importlib.util.spec_from_file_location("codex_review_run", MODULE_PATH)
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
        """A qwen attempt with outcome=aborted is excluded from the
        QWEN_TASK_IDS hint by the outcome=="completed" filter.

        Note: step 5 (commit) precedes step 5.5 (verify) in the work
        skill, so an aborted qwen pass CAN leave a qwen-authored commit
        in HEAD. The exclusion is still correct via additive scope —
        the de-slop pass scans the full `CLEANUP_SINCE..HEAD` diff so no
        commit slips through; the hint just doesn't flag this task for
        special qwen attention. Aborted qwen entries always sit beside
        a successful Phase-6 rework entry (Claude) on the same task, so
        the cleanup of any residual qwen code still happens via the
        diff-wide pass."""
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

    def test_handles_null_tasks_field(self) -> None:
        """A state where the top-level `tasks` key is explicitly null
        (rather than absent or an array) must not crash — best-effort
        de-slop never breaks the loop, and JSON permits null at any key."""
        with tempfile.TemporaryDirectory() as tmp:
            autopilot_dir = self._write_state(Path(tmp), {"tasks": None})
            self.assertEqual(dr._collect_qwen_task_ids(autopilot_dir), [])

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


class ExitContractTests(unittest.TestCase):
    """The doubt phase relies on an honest exit contract so it can fall back
    to a Claude review: 0=ok, 3=codex unavailable, 4=codex ran but failed
    (nonzero exit OR a usage-limit/quota/error event in the stream). The old
    behavior returned 0 on a quota-blocked run — a silent no-op recorded as
    success — which is the bug this fixes.
    """

    def _run_with_fake_codex(self, body: str, cwd: Path | None = None) -> int:
        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            shim = tmpp / "codex"
            shim.write_text("#!/usr/bin/env bash\n" + body + "\n")
            shim.chmod(0o755)
            prompt = tmpp / "p.md"
            prompt.write_text("review this diff")
            old_path = os.environ.get("PATH", "")
            old_cwd = os.getcwd()
            os.environ["PATH"] = str(tmpp) + os.pathsep + old_path
            # Isolate cwd so find_autopilot_dir does not resolve to a real
            # dev/local/autopilot up the tree (which would pollute it).
            os.chdir(str(cwd) if cwd else str(tmpp))
            try:
                return dr.main(["codex_review_run.py", str(prompt)])
            finally:
                os.environ["PATH"] = old_path
                os.chdir(old_cwd)

    def test_missing_codex_returns_3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prompt = Path(tmp) / "p.md"
            prompt.write_text("x")
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = tmp  # empty dir: no codex on PATH
            try:
                self.assertEqual(
                    dr.main(["codex_review_run.py", str(prompt)]), 3
                )
            finally:
                os.environ["PATH"] = old_path

    def test_usage_limit_event_returns_4(self) -> None:
        body = ("printf '%s\\n' "
                "'{\"message\":\"You have hit your usage limit\"}'\nexit 0")
        self.assertEqual(self._run_with_fake_codex(body), 4)

    def test_codex_nonzero_exit_returns_4(self) -> None:
        body = ("printf '%s\\n' "
                "'{\"msg\":{\"type\":\"agent_message\",\"message\":\"hi\"}}'"
                "\nexit 7")
        self.assertEqual(self._run_with_fake_codex(body), 4)

    def test_clean_run_returns_0(self) -> None:
        body = ("printf '%s\\n' "
                "'{\"msg\":{\"type\":\"agent_message\",\"message\":\"ok\"}}'"
                "\nexit 0")
        self.assertEqual(self._run_with_fake_codex(body), 0)

    def test_clean_run_captures_review_output_to_file(self) -> None:
        # codex's final agent_message (the review text) must be written to
        # <autopilot_dir>/codex-review-output.md so the doubt phase can read
        # it back as the reviewer's findings + verdicts + coverage block.
        with tempfile.TemporaryDirectory() as work:
            ap = Path(work) / "dev" / "local" / "autopilot"
            ap.mkdir(parents=True)
            body = ("printf '%s\\n' "
                    "'{\"msg\":{\"type\":\"agent_message\",\"message\":"
                    "\"FIX:\\n- none\\nR1: pass\"}}'\nexit 0")
            rc = self._run_with_fake_codex(body, cwd=Path(work))
            self.assertEqual(rc, 0)
            out = ap / "codex-review-output.md"
            self.assertTrue(out.exists())
            self.assertIn("R1: pass", out.read_text())


if __name__ == "__main__":
    unittest.main()
