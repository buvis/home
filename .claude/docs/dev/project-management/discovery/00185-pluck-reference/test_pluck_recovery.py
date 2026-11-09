# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Regression coverage for the recovery review findings."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pluck
import pluck_transcripts as transcripts


class RecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def test_complete_final_record_and_blank_lines(self) -> None:
        path = self.root / "a.jsonl"
        path.write_bytes(b'{}\n\n{"complete": true}')
        self.assertEqual(transcripts._read_jsonl(path), [{}, {"complete": True}])

    def test_unreadable_metadata_is_actionable(self) -> None:
        with self.assertRaisesRegex(pluck.PluckError, "cannot read.*missing"):
            pluck.read_session_metadata(self.root / "missing", "claude")

    def test_unknown_home_names_config_key(self) -> None:
        (self.root / "pluck.toml").write_text('pi_root = "~pluck_nonexistent_user"')
        with self.assertRaisesRegex(pluck.PluckError, "pi_root"):
            pluck.load_config(str(self.root))

    def test_disappearing_candidate_is_actionable(self) -> None:
        snap = pluck.PaneSnapshot("p", "claude", "/work", None, None)
        resolution = pluck.Resolution(
            pluck.ResolutionKind.HEURISTIC, None, (self.root / "gone",), "claude", snap
        )
        with self.assertRaisesRegex(pluck.PluckError, "cannot inspect.*gone"):
            pluck._resolve_heuristic_candidate(resolution, "fzf")

    def test_non_shell_fence_does_not_extract_prompts(self) -> None:
        entries = [transcripts.TranscriptEntry("```text\n$ not a command\n```", 0, 0)]
        self.assertEqual(pluck.extract_snippets(entries), [])

    def test_indented_fence_preserves_relative_indentation(self) -> None:
        entries = [
            transcripts.TranscriptEntry(
                "  ```sh\n  echo one\n    echo two\n  ```", 0, 0
            )
        ]
        self.assertEqual(pluck.extract_snippets(entries)[0].raw, "echo one\n  echo two")

    def test_run_cue_is_consumed_by_one_block(self) -> None:
        entries = [
            transcripts.TranscriptEntry(
                "Run this:\n```console\n$ one\n```\n```console\n$ two\n```", 0, 0
            )
        ]
        self.assertEqual([s.rank_tier for s in pluck.extract_snippets(entries)], [1, 2])

    def test_unicode_display_separators_are_removed(self) -> None:
        self.assertEqual(transcripts.render_single_line("a\u2028b\u2029c"), "abc")

    def test_surrogate_never_invokes_clipboard(self) -> None:
        with mock.patch("pluck.subprocess.run") as run:
            with self.assertRaises(pluck.PluckError):
                pluck.copy_to_clipboard("\ud800", "pbcopy")
        run.assert_not_called()

    def test_tempfile_write_failure_cleans_up(self) -> None:
        with (
            mock.patch("pluck.tempfile.tempdir", str(self.root)),
            mock.patch("pluck.json.dump", side_effect=OSError("disk full")),
        ):
            with self.assertRaises(pluck.PluckError):
                pluck.run_fzf([], "fzf")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_open_rejects_non_object_and_invalid_pane(self) -> None:
        for context in ([], None, {"focused_pane_id": []}, {"focused_pane_id": " "}):
            with (
                self.subTest(context=context),
                mock.patch("pluck.os.execvp") as execute,
            ):
                with mock.patch("sys.stderr", new_callable=io.StringIO):
                    self.assertEqual(
                        pluck.main_open(
                            {"HERDR_PLUGIN_CONTEXT_JSON": json.dumps(context)}
                        ),
                        1,
                    )
                execute.assert_not_called()

    def test_open_exec_failure_is_actionable(self) -> None:
        with (
            mock.patch("pluck.os.execvp", side_effect=OSError("missing")),
            mock.patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            self.assertEqual(
                pluck.main_open(
                    {"HERDR_PLUGIN_CONTEXT_JSON": '{"focused_pane_id": "p"}'}
                ),
                1,
            )
        self.assertIn("cannot open", err.getvalue())

    def test_unreadable_duplicate_aborts_native_resolution(self) -> None:
        first = self.root / "a.jsonl"
        second = self.root / "b.jsonl"
        first.write_text('{"sessionId":"same","cwd":"/work"}\n')
        second.write_text(first.read_text())
        snap = pluck.PaneSnapshot(
            "p",
            "claude",
            "/work",
            None,
            pluck.AgentSessionRef("herdr:claude", "claude", "id", "same"),
        )
        real_open = open

        def guarded_open(path: Path, **kwargs: object) -> object:
            if path == second:
                raise PermissionError("unreadable duplicate")
            return real_open(path, **kwargs)

        with (
            mock.patch("pluck.open", side_effect=guarded_open),
            mock.patch("pluck.subprocess.run") as run,
        ):
            with self.assertRaisesRegex(pluck.PluckError, "unreadable duplicate"):
                pluck.resolve(snap, pluck.ClaudePiRoots(self.root, self.root, 20))
        run.assert_not_called()

    def test_scan_failure_does_not_hide_possible_duplicates(self) -> None:
        with mock.patch(
            "pluck.os.scandir", side_effect=PermissionError("blocked directory")
        ):
            with self.assertRaisesRegex(pluck.PluckError, "cannot scan"):
                pluck.list_candidate_files(self.root)

    def test_tempfile_creation_failure_is_actionable(self) -> None:
        with mock.patch("pluck.tempfile.mkstemp", side_effect=OSError("no space")):
            with self.assertRaisesRegex(pluck.PluckError, "no space"):
                pluck.run_fzf([], "fzf")

    def test_preview_removes_unicode_separators(self) -> None:
        path = self.root / "preview.json"
        path.write_text(json.dumps({"s": "a\u2028b\u2029c\nnext"}))
        with (
            mock.patch.dict("os.environ", {"PLUCK_SNIPPETS_FILE": str(path)}),
            mock.patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            pluck._preview("s")
        self.assertEqual(out.getvalue(), "abc\nnext\n")

    def test_error_stays_visible_until_acknowledged(self) -> None:
        err = io.StringIO()
        err.isatty = lambda: True
        with (
            mock.patch("sys.stdin.isatty", return_value=True),
            mock.patch("builtins.input") as acknowledge,
            mock.patch("sys.stderr", err),
        ):
            pluck._show_error(pluck.PluckError("cannot read \x1b[31mtranscript"))
        self.assertIn("cannot read [31mtranscript", err.getvalue())
        self.assertNotIn("\x1b", err.getvalue())
        acknowledge.assert_called_once_with("Press Enter to close.")

    def test_captured_error_never_waits_for_input(self) -> None:
        with (
            mock.patch("sys.stdin.isatty", return_value=True),
            mock.patch("builtins.input") as acknowledge,
            mock.patch("sys.stderr", new_callable=io.StringIO),
        ):
            pluck._show_error(pluck.PluckError("cannot read transcript"))
        acknowledge.assert_not_called()

    def test_closed_input_ends_the_hold(self) -> None:
        err = io.StringIO()
        err.isatty = lambda: True
        with (
            mock.patch("sys.stdin.isatty", return_value=True),
            mock.patch("builtins.input", side_effect=EOFError),
            mock.patch("sys.stderr", err),
        ):
            pluck._show_error(pluck.PluckError("boom"))
        self.assertIn("boom", err.getvalue())

    def test_dangling_transcript_symlink_is_actionable(self) -> None:
        (self.root / "gone.jsonl").symlink_to(self.root / "missing-target.jsonl")
        with self.assertRaisesRegex(pluck.PluckError, "cannot inspect.*gone"):
            pluck.list_candidate_files(self.root)

    def test_unreadable_transcript_root_is_actionable(self) -> None:
        with mock.patch("pathlib.Path.stat", side_effect=PermissionError("blocked")):
            with self.assertRaisesRegex(pluck.PluckError, "cannot scan.*blocked"):
                pluck.list_candidate_files(self.root)

    def test_unknown_heuristic_choice_is_actionable(self) -> None:
        path = self.root / "a.jsonl"
        path.write_text("{}\n")
        snap = pluck.PaneSnapshot("p", "claude", "/work", None, None)
        resolution = pluck.Resolution(
            pluck.ResolutionKind.HEURISTIC, None, (path,), "claude", snap
        )
        with mock.patch("pluck.run_fzf", return_value="7"):
            with self.assertRaisesRegex(pluck.PluckError, "unknown transcript id"):
                pluck._resolve_heuristic_candidate(resolution, "fzf")

    def test_tempfile_removal_failure_is_actionable(self) -> None:
        with (
            mock.patch("pluck._select_fzf", return_value=None),
            mock.patch("pathlib.Path.unlink", side_effect=PermissionError("locked")),
        ):
            with self.assertRaisesRegex(pluck.PluckError, "cannot remove.*locked"):
                pluck.run_fzf([], "fzf")

    def test_file_stat_permission_error_is_actionable(self) -> None:
        with mock.patch("pathlib.Path.stat", side_effect=PermissionError("blocked")):
            with self.assertRaisesRegex(pluck.PluckError, "cannot inspect"):
                pluck._is_file(self.root / "session.jsonl")
