"""Tests for hooks/_common.py."""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _common  # noqa: E402


class TestReadInput(unittest.TestCase):
    def test_returns_dict_for_valid_json(self) -> None:
        with patch("sys.stdin", io.StringIO('{"tool_name": "Edit", "tool_input": {"file_path": "/x"}}')):
            self.assertEqual(_common.read_input(), {"tool_name": "Edit", "tool_input": {"file_path": "/x"}})

    def test_returns_empty_dict_for_empty_stdin(self) -> None:
        with patch("sys.stdin", io.StringIO("")):
            self.assertEqual(_common.read_input(), {})

    def test_returns_empty_dict_for_whitespace(self) -> None:
        with patch("sys.stdin", io.StringIO("   \n\t")):
            self.assertEqual(_common.read_input(), {})

    def test_returns_empty_dict_for_invalid_json(self) -> None:
        with patch("sys.stdin", io.StringIO("not json {")):
            self.assertEqual(_common.read_input(), {})

    def test_returns_empty_dict_for_non_object_json(self) -> None:
        with patch("sys.stdin", io.StringIO('["array"]')):
            self.assertEqual(_common.read_input(), {})


class TestBlock(unittest.TestCase):
    def test_exits_with_code_2(self) -> None:
        with patch("sys.stderr", io.StringIO()) as err:
            with self.assertRaises(SystemExit) as ctx:
                _common.block("nope")
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("nope", err.getvalue())

    def test_writes_full_reason_to_stderr(self) -> None:
        msg = "BLOCKED: line 1\nline 2\nline 3"
        with patch("sys.stderr", io.StringIO()) as err:
            with self.assertRaises(SystemExit):
                _common.block(msg)
            self.assertIn("line 1", err.getvalue())
            self.assertIn("line 3", err.getvalue())


class TestAllow(unittest.TestCase):
    def test_exits_with_code_0(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            _common.allow()
        self.assertEqual(ctx.exception.code, 0)


class TestLogPath(unittest.TestCase):
    def test_resolves_under_claude_hooks(self) -> None:
        p = _common.log_path("notify.log")
        self.assertTrue(str(p).endswith("/.claude/hooks/notify.log"))
        self.assertTrue(str(p).startswith(str(Path.home())))

    def test_returns_path_instance(self) -> None:
        self.assertIsInstance(_common.log_path("x"), Path)


class TestSecretPath(unittest.TestCase):
    def test_resolves_under_claude_secrets(self) -> None:
        p = _common.secret_path("token")
        self.assertTrue(str(p).endswith("/.claude/secrets/token"))
        self.assertTrue(str(p).startswith(str(Path.home())))


class TestAppendJsonlRow(unittest.TestCase):
    def test_creates_file_and_writes_one_line_when_path_does_not_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics.jsonl"
            self.assertFalse(path.exists())
            _common.append_jsonl_row(path, '{"a": 1}')
            self.assertEqual(path.read_text(), '{"a": 1}\n')

    def test_treats_empty_existing_file_as_not_needing_leading_newline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics.jsonl"
            path.write_text("")
            self.assertTrue(path.exists())
            _common.append_jsonl_row(path, '{"a": 1}')
            self.assertEqual(path.read_text(), '{"a": 1}\n')

    def test_appends_cleanly_without_extra_blank_line_when_file_ends_in_newline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics.jsonl"
            path.write_text('{"a": 1}\n')
            _common.append_jsonl_row(path, '{"b": 2}')
            self.assertEqual(path.read_text(), '{"a": 1}\n{"b": 2}\n')
            lines = path.read_text().split("\n")
            self.assertEqual(lines[-1], "")
            self.assertEqual(lines[:-1], ['{"a": 1}', '{"b": 2}'])

    def test_writes_leading_newline_and_keeps_both_rows_parseable_when_last_line_lacks_newline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics.jsonl"
            path.write_text('{"a": 1}')  # crash before the trailing newline was flushed
            _common.append_jsonl_row(path, '{"b": 2}')
            self.assertEqual(path.read_text(), '{"a": 1}\n{"b": 2}\n')
            lines = path.read_text().split("\n")
            self.assertEqual(lines[-1], "")
            lines = lines[:-1]
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0]), {"a": 1})
            self.assertEqual(json.loads(lines[1]), {"b": 2})


class TestParseTranscriptEntries(unittest.TestCase):
    def setUp(self) -> None:
        _common._TRANSCRIPT_CACHE.clear()

    def tearDown(self) -> None:
        _common._TRANSCRIPT_CACHE.clear()

    def test_reads_file_at_most_once_across_two_calls_with_same_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            path.write_text(json.dumps({"type": "assistant", "n": 1}) + "\n", encoding="utf-8")

            calls: list[Path] = []
            original_read_text = Path.read_text

            def counting_read_text(self_path, *args, **kwargs):
                calls.append(self_path)
                return original_read_text(self_path, *args, **kwargs)

            with patch.object(Path, "read_text", counting_read_text):
                first = _common.parse_transcript_entries(path)
                second = _common.parse_transcript_entries(path)

            self.assertEqual(len(calls), 1)
            self.assertEqual(first, [{"type": "assistant", "n": 1}])
            self.assertEqual(first, second)

    def test_missing_file_returns_empty_list_without_raising(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.jsonl"
            self.assertEqual(_common.parse_transcript_entries(missing), [])

    def test_skips_malformed_json_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            path.write_text(
                "not json\n" + json.dumps({"type": "assistant", "n": 2}) + "\n",
                encoding="utf-8",
            )
            result = _common.parse_transcript_entries(path)
            self.assertEqual(result, [{"type": "assistant", "n": 2}])

    def test_skips_non_dict_json_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            path.write_text(
                json.dumps([1, 2, 3]) + "\n" + json.dumps({"type": "user"}) + "\n",
                encoding="utf-8",
            )
            result = _common.parse_transcript_entries(path)
            self.assertEqual(result, [{"type": "user"}])


if __name__ == "__main__":
    unittest.main()
