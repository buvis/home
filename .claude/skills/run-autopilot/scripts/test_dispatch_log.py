"""Tests for _dispatch_log.py — shared helper: percentile, load_entries, find_dispatch_log.

Covers:
  - percentile: empty data, known values, p50 vs p95 distinction
  - load_entries: missing file, empty file, blank lines, malformed JSON, valid JSONL
  - find_dispatch_log: always returns a Path; name is "dispatch-log.jsonl"
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _dispatch_log import find_dispatch_log, load_entries, percentile


# ---------------------------------------------------------------------------
# percentile
# ---------------------------------------------------------------------------

class TestPercentileEmptyData(unittest.TestCase):
    def test_empty_list_p95_returns_zero(self) -> None:
        self.assertEqual(percentile([], 95), 0.0)

    def test_empty_list_p50_returns_zero(self) -> None:
        self.assertEqual(percentile([], 50), 0.0)


class TestPercentileContractExamples(unittest.TestCase):
    def test_p95_of_five_ascending_values(self) -> None:
        # Spec: percentile([10,20,30,40,50], 95) → 50.0
        self.assertEqual(percentile([10.0, 20.0, 30.0, 40.0, 50.0], 95), 50.0)

    def test_p50_of_five_ascending_values(self) -> None:
        # Spec: percentile([10,20,30,40,50], 50) → 30.0
        self.assertEqual(percentile([10.0, 20.0, 30.0, 40.0, 50.0], 50), 30.0)

    def test_single_element_returns_that_value_for_any_percentile(self) -> None:
        for pct in (0.0, 50.0, 95.0, 100.0):
            with self.subTest(pct=pct):
                self.assertEqual(percentile([42.0], pct), 42.0)

    def test_p100_returns_max(self) -> None:
        self.assertEqual(percentile([1.0, 2.0, 3.0, 4.0, 5.0], 100), 5.0)

    def test_return_type_is_float(self) -> None:
        self.assertIsInstance(percentile([10.0, 20.0, 30.0], 50), float)


class TestPercentileNearestRank(unittest.TestCase):
    def test_p95_not_blown_up_by_single_outlier(self) -> None:
        # 99×100.0 + 1×10000.0 → nearest-rank p95 index=95 → sorted[95]=100.0
        data = [100.0] * 99 + [10000.0]
        result = percentile(data, 95)
        self.assertLessEqual(result, 200.0, "p95 must not be the outlier value")

    def test_p95_greater_than_p50_on_skewed_data(self) -> None:
        data = [10.0, 11.0, 12.0, 300.0]
        self.assertGreater(percentile(data, 95), percentile(data, 50))

    def test_unsorted_input_same_as_sorted_input(self) -> None:
        # Implementation must sort before applying the formula.
        asc = [10.0, 20.0, 30.0, 40.0, 50.0]
        desc = [50.0, 40.0, 30.0, 20.0, 10.0]
        self.assertEqual(percentile(asc, 95), percentile(desc, 95))
        self.assertEqual(percentile(asc, 50), percentile(desc, 50))


# ---------------------------------------------------------------------------
# load_entries — missing file
# ---------------------------------------------------------------------------

class TestLoadEntriesFileMissing(unittest.TestCase):
    def test_nonexistent_file_returns_empty_list(self) -> None:
        self.assertEqual(load_entries(Path("/tmp/dispatch-log-absent-abc123.jsonl")), [])

    def test_nonexistent_file_raises_no_exception(self) -> None:
        raised: Exception | None = None
        try:
            load_entries(Path("/tmp/dispatch-log-absent-xyz987.jsonl"))
        except Exception as exc:
            raised = exc
        self.assertIsNone(raised, f"load_entries raised unexpectedly: {raised}")


# ---------------------------------------------------------------------------
# load_entries — valid JSONL
# ---------------------------------------------------------------------------

class TestLoadEntriesValidJsonl(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_empty_file_returns_empty_list(self) -> None:
        p = Path(self.tmp) / "log.jsonl"
        p.write_text("")
        self.assertEqual(load_entries(p), [])

    def test_single_entry_round_trips(self) -> None:
        entry = {"ts": "2026-01-01T00:00:00Z", "outcome": "completed", "duration_s": 10.0}
        p = Path(self.tmp) / "log.jsonl"
        p.write_text(json.dumps(entry) + "\n")
        self.assertEqual(load_entries(p), [entry])

    def test_three_entries_returned_in_order(self) -> None:
        entries = [
            {"ts": "2026-01-01T00:00:00Z", "outcome": "completed"},
            {"ts": "2026-01-01T00:01:00Z", "outcome": "hung"},
            {"ts": "2026-01-01T00:02:00Z", "outcome": "error"},
        ]
        p = Path(self.tmp) / "log.jsonl"
        p.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        self.assertEqual(load_entries(p), entries)

    def test_result_is_list_of_dicts(self) -> None:
        p = Path(self.tmp) / "log.jsonl"
        p.write_text(json.dumps({"k": "v"}) + "\n")
        result = load_entries(p)
        self.assertIsInstance(result, list)
        self.assertIsInstance(result[0], dict)


# ---------------------------------------------------------------------------
# load_entries — blank / whitespace lines
# ---------------------------------------------------------------------------

class TestLoadEntriesBlankLines(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_blank_lines_around_entry_are_skipped(self) -> None:
        entry = {"outcome": "completed"}
        p = Path(self.tmp) / "log.jsonl"
        p.write_text("\n" + json.dumps(entry) + "\n\n")
        self.assertEqual(load_entries(p), [entry])

    def test_whitespace_only_lines_are_skipped(self) -> None:
        entry = {"outcome": "completed"}
        p = Path(self.tmp) / "log.jsonl"
        p.write_text("   \n" + json.dumps(entry) + "\n\t\n")
        self.assertEqual(len(load_entries(p)), 1)

    def test_file_of_only_blanks_returns_empty_list(self) -> None:
        p = Path(self.tmp) / "log.jsonl"
        p.write_text("\n\n   \n\t\n")
        self.assertEqual(load_entries(p), [])


# ---------------------------------------------------------------------------
# load_entries — malformed JSON
# ---------------------------------------------------------------------------

class TestLoadEntriesMalformedJson(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_malformed_only_line_does_not_raise(self) -> None:
        p = Path(self.tmp) / "log.jsonl"
        p.write_text("not valid json\n")
        raised: Exception | None = None
        try:
            load_entries(p)
        except Exception as exc:
            raised = exc
        self.assertIsNone(raised, f"load_entries raised on malformed JSON: {raised}")

    def test_malformed_only_line_returns_empty_list(self) -> None:
        p = Path(self.tmp) / "log.jsonl"
        p.write_text("not valid json\n")
        self.assertEqual(load_entries(p), [])

    def test_valid_entry_surrounded_by_bad_lines_still_returned(self) -> None:
        valid = {"outcome": "completed", "duration_s": 42.0}
        p = Path(self.tmp) / "log.jsonl"
        p.write_text("bad json\n" + json.dumps(valid) + "\n{also bad\n")
        self.assertEqual(load_entries(p), [valid])

    def test_all_malformed_returns_empty_list(self) -> None:
        p = Path(self.tmp) / "log.jsonl"
        p.write_text("bad1\nbad2\n{bad3\n")
        self.assertEqual(load_entries(p), [])

    def test_malformed_first_valid_last(self) -> None:
        valid = {"x": 1}
        p = Path(self.tmp) / "log.jsonl"
        p.write_text("not json\n" + json.dumps(valid) + "\n")
        self.assertEqual(load_entries(p), [valid])

    def test_valid_first_malformed_last(self) -> None:
        valid = {"x": 2}
        p = Path(self.tmp) / "log.jsonl"
        p.write_text(json.dumps(valid) + "\nnot json\n")
        self.assertEqual(load_entries(p), [valid])


# ---------------------------------------------------------------------------
# find_dispatch_log
# ---------------------------------------------------------------------------

class TestFindDispatchLog(unittest.TestCase):
    def test_return_value_is_path_instance(self) -> None:
        self.assertIsInstance(find_dispatch_log(), Path)

    def test_returned_path_name_is_dispatch_log_jsonl(self) -> None:
        self.assertEqual(find_dispatch_log().name, "dispatch-log.jsonl")

    def test_return_value_is_not_none(self) -> None:
        self.assertIsNotNone(find_dispatch_log())


if __name__ == "__main__":
    unittest.main()
