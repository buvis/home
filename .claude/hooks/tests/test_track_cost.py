"""Tests for hooks/track_cost.py.

Covers tier detection, dedup-by-message-id, aggregation, cost arithmetic, and
end-to-end JSONL row emission. Subprocess-based end-to-end tests override HOME
so the hook writes to an isolated temp dir.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import track_cost

HOOK = Path(__file__).resolve().parents[1] / "track_cost.py"


def write_transcript(path: Path, entries: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


def assistant_entry(*, mid: str, model: str, in_tok: int = 0, cw: int = 0, cr: int = 0, out: int = 0) -> dict:
    return {
        "type": "assistant",
        "message": {
            "id": mid,
            "model": model,
            "usage": {
                "input_tokens": in_tok,
                "cache_creation_input_tokens": cw,
                "cache_read_input_tokens": cr,
                "output_tokens": out,
            },
        },
    }


def run_hook(payload: dict, home: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "HOME": str(home)}
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )


def read_costs(home: Path) -> list[dict]:
    f = home / ".claude" / "metrics" / "costs.jsonl"
    if not f.is_file():
        return []
    return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]


class TestDetectTier(unittest.TestCase):
    def test_opus(self) -> None:
        self.assertEqual(track_cost.detect_tier("claude-opus-4-7"), "opus")

    def test_haiku(self) -> None:
        self.assertEqual(track_cost.detect_tier("claude-haiku-4-5-20251001"), "haiku")

    def test_sonnet_default(self) -> None:
        self.assertEqual(track_cost.detect_tier("claude-sonnet-4-6"), "sonnet")

    def test_unknown_falls_back_to_sonnet(self) -> None:
        self.assertEqual(track_cost.detect_tier("mystery-model"), "sonnet")


class TestCostUsd(unittest.TestCase):
    def test_opus_cost(self) -> None:
        self.assertEqual(track_cost.cost_usd(600, 200, 3000, 150, "opus"), "0.02850")

    def test_sonnet_cost(self) -> None:
        self.assertEqual(track_cost.cost_usd(1000, 0, 0, 500, "sonnet"), "0.01050")

    def test_haiku_cost(self) -> None:
        self.assertEqual(track_cost.cost_usd(2000, 500, 10000, 1000, "haiku"), "0.00690")

    def test_zero(self) -> None:
        self.assertEqual(track_cost.cost_usd(0, 0, 0, 0, "sonnet"), "0.00000")


class TestDeduplicate(unittest.TestCase):
    def test_keeps_last_for_each_id(self) -> None:
        a = assistant_entry(mid="m1", model="claude-opus-4-7", in_tok=10)
        b = assistant_entry(mid="m1", model="claude-opus-4-7", in_tok=20)
        c = assistant_entry(mid="m2", model="claude-opus-4-7", in_tok=5)
        result = track_cost.deduplicate([a, b, c])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["message"]["usage"]["input_tokens"], 20)
        self.assertEqual(result[1]["message"]["usage"]["input_tokens"], 5)

    def test_drops_entries_without_id(self) -> None:
        no_id = {"type": "assistant", "message": {"model": "x", "usage": {"input_tokens": 1}}}
        result = track_cost.deduplicate([no_id])
        self.assertEqual(result, [])


class TestAggregate(unittest.TestCase):
    def test_sums_token_counts(self) -> None:
        entries = [
            assistant_entry(mid="a", model="claude-opus-4-7", in_tok=100, cw=10, cr=50, out=20),
            assistant_entry(mid="b", model="claude-opus-4-7", in_tok=200, cw=5, cr=30, out=15),
        ]
        model, in_tok, cw, cr, out = track_cost.aggregate(entries)
        self.assertEqual(model, "claude-opus-4-7")
        self.assertEqual((in_tok, cw, cr, out), (300, 15, 80, 35))

    def test_picks_last_non_empty_model(self) -> None:
        entries = [
            assistant_entry(mid="a", model="claude-sonnet-4-6"),
            assistant_entry(mid="b", model=""),
            assistant_entry(mid="c", model="claude-opus-4-7"),
        ]
        model, *_ = track_cost.aggregate(entries)
        self.assertEqual(model, "claude-opus-4-7")

    def test_empty_returns_blank_model(self) -> None:
        model, in_tok, cw, cr, out = track_cost.aggregate([])
        self.assertEqual(model, "")
        self.assertEqual((in_tok, cw, cr, out), (0, 0, 0, 0))


class TestParseTranscript(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_filters_to_assistant_with_usage(self) -> None:
        path = self.tmp / "t.jsonl"
        write_transcript(path, [
            {"type": "user", "message": {"id": "u1"}},
            {"type": "assistant", "message": {"id": "a1"}},
            assistant_entry(mid="a2", model="claude-opus-4-7", in_tok=10),
        ])
        result = track_cost.parse_transcript(path)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["message"]["id"], "a2")

    def test_skips_invalid_json_lines(self) -> None:
        path = self.tmp / "t.jsonl"
        path.write_text(
            "not json\n"
            + json.dumps(assistant_entry(mid="a1", model="claude-opus-4-7", in_tok=5))
            + "\n",
            encoding="utf-8",
        )
        result = track_cost.parse_transcript(path)
        self.assertEqual(len(result), 1)

    def test_missing_file_returns_empty(self) -> None:
        self.assertEqual(track_cost.parse_transcript(self.tmp / "nope.jsonl"), [])


class TestEndToEnd(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.home)

    def test_opus_dedup_and_aggregation(self) -> None:
        transcript = self.home / "transcript.jsonl"
        write_transcript(transcript, [
            assistant_entry(mid="msg_001", model="claude-opus-4-7", in_tok=300, cw=100, cr=1500, out=75),
            assistant_entry(mid="msg_001", model="claude-opus-4-7", in_tok=300, cw=100, cr=1500, out=75),
            assistant_entry(mid="msg_002", model="claude-opus-4-7", in_tok=300, cw=100, cr=1500, out=75),
        ])
        proc = run_hook(
            {"session_id": "test-001", "transcript_path": str(transcript), "hook_event_name": "Stop"},
            self.home,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        rows = read_costs(self.home)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["sid"], "test-001")
        self.assertEqual(row["model"], "claude-opus-4-7")
        self.assertEqual(row["tier"], "opus")
        self.assertEqual(row["in"], 600)
        self.assertEqual(row["cache_write"], 200)
        self.assertEqual(row["cache_read"], 3000)
        self.assertEqual(row["out"], 150)
        self.assertEqual(row["cost_usd"], 0.02850)

    def test_empty_transcript_path_writes_nothing(self) -> None:
        proc = run_hook(
            {"session_id": "x", "transcript_path": "", "hook_event_name": "Stop"},
            self.home,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(read_costs(self.home), [])

    def test_missing_transcript_file_writes_nothing(self) -> None:
        proc = run_hook(
            {"session_id": "x", "transcript_path": str(self.home / "nope.jsonl"), "hook_event_name": "Stop"},
            self.home,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(read_costs(self.home), [])

    def test_sonnet_detection(self) -> None:
        transcript = self.home / "t.jsonl"
        write_transcript(transcript, [
            assistant_entry(mid="m", model="claude-sonnet-4-6", in_tok=1000, out=500),
        ])
        run_hook({"session_id": "s", "transcript_path": str(transcript)}, self.home)
        rows = read_costs(self.home)
        self.assertEqual(rows[0]["tier"], "sonnet")
        self.assertEqual(rows[0]["cost_usd"], 0.01050)

    def test_haiku_detection(self) -> None:
        transcript = self.home / "t.jsonl"
        write_transcript(transcript, [
            assistant_entry(mid="m", model="claude-haiku-4-5-20251001", in_tok=2000, cw=500, cr=10000, out=1000),
        ])
        run_hook({"session_id": "s", "transcript_path": str(transcript)}, self.home)
        rows = read_costs(self.home)
        self.assertEqual(rows[0]["tier"], "haiku")
        self.assertEqual(rows[0]["cost_usd"], 0.00690)

    def test_two_invocations_append_rows(self) -> None:
        t1 = self.home / "t1.jsonl"
        t2 = self.home / "t2.jsonl"
        write_transcript(t1, [
            assistant_entry(mid="a", model="claude-sonnet-4-6", in_tok=1000, out=500),
        ])
        write_transcript(t2, [
            assistant_entry(mid="b", model="claude-haiku-4-5-20251001", in_tok=2000, cw=500, cr=10000, out=1000),
        ])
        run_hook({"session_id": "s1", "transcript_path": str(t1)}, self.home)
        run_hook({"session_id": "s2", "transcript_path": str(t2)}, self.home)
        rows = read_costs(self.home)
        self.assertEqual(len(rows), 2)
        total = sum(r["cost_usd"] for r in rows)
        self.assertAlmostEqual(total, 0.01740, places=5)


if __name__ == "__main__":
    unittest.main()
