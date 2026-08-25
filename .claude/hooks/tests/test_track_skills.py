"""Tests for hooks/track_skills.py (PRD 00086 R2 compliance counter)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import track_cost
import track_skills

HOOK = Path(__file__).resolve().parents[1] / "track_skills.py"


def skill_use(tool_id: str, skill: str) -> dict:
    return {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "invoking"},
                {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": "Skill",
                    "input": {"skill": skill},
                },
            ],
        },
    }


def write_transcript(path: Path, entries: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


def run_hook(payload: dict, home: Path, extra_env: dict | None = None):
    env = {**os.environ, "HOME": str(home)}
    env.pop("_AUTOPILOT_LOOP", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )


def read_rows(home: Path) -> list[dict]:
    f = home / ".local" / "share" / "agents" / "metrics" / "skills.jsonl"
    if not f.is_file():
        return []
    rows = []
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


class ParseTests(unittest.TestCase):
    def test_extracts_skill_names_and_ids(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = Path(td) / "t.jsonl"
            write_transcript(
                t,
                [
                    skill_use("toolu_1", "review-work-completion"),
                    {"type": "user", "message": {"content": "hi"}},
                    skill_use("toolu_2", "plan-tasks"),
                ],
            )
            got = track_skills.skill_invocations(t)
            self.assertEqual(
                got, [("toolu_1", "review-work-completion"), ("toolu_2", "plan-tasks")]
            )

    def test_dedups_repeated_tool_use_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = Path(td) / "t.jsonl"
            write_transcript(
                t, [skill_use("toolu_1", "brush"), skill_use("toolu_1", "brush")]
            )
            self.assertEqual(track_skills.skill_invocations(t), [("toolu_1", "brush")])

    def test_ignores_non_skill_tool_use(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = Path(td) / "t.jsonl"
            write_transcript(
                t,
                [
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "id": "b1",
                                    "name": "Bash",
                                    "input": {"command": "ls"},
                                }
                            ]
                        },
                    }
                ],
            )
            self.assertEqual(track_skills.skill_invocations(t), [])

    def test_unreadable_transcript_returns_empty(self) -> None:
        self.assertEqual(track_skills.skill_invocations(Path("/nope/x.jsonl")), [])


class SharedTranscriptCacheTests(unittest.TestCase):
    """Regression for PRD 00133 finding 29: track_cost.parse_transcript
    reading a transcript first (shared per-process parse cache) must not
    change track_skills.skill_invocations's output for the same file.
    """

    def test_output_unchanged_when_parse_transcript_reads_the_same_file_first(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = Path(td) / "shared.jsonl"
            write_transcript(
                t,
                [
                    {"type": "user", "message": {"id": "u1"}},
                    {
                        "type": "assistant",
                        "message": {
                            "id": "a1",
                            "model": "claude-opus-4-7",
                            "usage": {"input_tokens": 10, "output_tokens": 3},
                        },
                    },
                    skill_use("toolu_1", "brush"),
                ],
            )

            cost_rows = track_cost.parse_transcript(t)
            self.assertEqual(len(cost_rows), 1)
            self.assertEqual(cost_rows[0]["message"]["id"], "a1")

            result = track_skills.skill_invocations(t)
            self.assertEqual(result, [("toolu_1", "brush")])


class EndToEndTests(unittest.TestCase):
    def test_writes_rows_with_source_and_session(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            t = home / "t.jsonl"
            write_transcript(t, [skill_use("toolu_1", "survey")])
            r = run_hook(
                {"transcript_path": str(t), "session_id": "sess-A"},
                home,
                extra_env={"_AUTOPILOT_LOOP": "test-loop"},
            )
            self.assertEqual(r.returncode, 0)
            rows = read_rows(home)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["skill"], "survey")
            self.assertEqual(rows[0]["session_id"], "sess-A")
            self.assertEqual(rows[0]["source"], "loop")
            self.assertIn("ts", rows[0])

    def test_interactive_source_when_not_in_loop(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            t = home / "t.jsonl"
            write_transcript(t, [skill_use("toolu_1", "create-prd")])
            run_hook({"transcript_path": str(t), "session_id": "s"}, home)
            self.assertEqual(read_rows(home)[0]["source"], "interactive")

    def test_rerun_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            t = home / "t.jsonl"
            write_transcript(t, [skill_use("toolu_1", "work")])
            payload = {"transcript_path": str(t), "session_id": "s"}
            run_hook(payload, home)
            run_hook(payload, home)
            self.assertEqual(len(read_rows(home)), 1)

    def test_no_skill_invocations_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            t = home / "t.jsonl"
            write_transcript(t, [{"type": "user", "message": {"content": "hi"}}])
            run_hook({"transcript_path": str(t), "session_id": "s"}, home)
            self.assertEqual(read_rows(home), [])

    def test_appends_cleanly_after_truncated_tail_from_prior_crash(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            metrics_dir = home / ".local" / "share" / "agents" / "metrics"
            metrics_dir.mkdir(parents=True)
            skills_file = metrics_dir / "skills.jsonl"
            prior_row = json.dumps(
                {
                    "skill": "brush",
                    "session_id": "sess-prior",
                    "ts": "2026-01-01T00:00:00+00:00",
                    "source": "interactive",
                    "tool_use_id": "toolu_prior",
                }
            )
            skills_file.write_text(prior_row, encoding="utf-8")  # no trailing newline

            t = home / "t.jsonl"
            write_transcript(t, [skill_use("toolu_new", "work")])
            r = run_hook({"transcript_path": str(t), "session_id": "sess-new"}, home)

            self.assertEqual(r.returncode, 0)
            rows = read_rows(home)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["tool_use_id"], "toolu_prior")
            self.assertEqual(rows[1]["tool_use_id"], "toolu_new")
            self.assertEqual(rows[1]["skill"], "work")

    def test_dedup_survives_corrupted_neighbour_from_prior_crash(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            metrics_dir = home / ".local" / "share" / "agents" / "metrics"
            metrics_dir.mkdir(parents=True)
            skills_file = metrics_dir / "skills.jsonl"
            truncated_a = (
                '{"skill": "brush", "session_id": "sess-dedup", '
                '"ts": "2026-01-01T00:00:00+00:00", "source": "interactive", '
                '"tool_use_id": "toolu_A"'
            )
            skills_file.write_text(truncated_a, encoding="utf-8")  # no trailing newline

            session_id = "sess-dedup"
            t1 = home / "t1.jsonl"
            write_transcript(t1, [skill_use("toolu_B", "work")])
            r1 = run_hook({"transcript_path": str(t1), "session_id": session_id}, home)
            self.assertEqual(r1.returncode, 0)

            t2 = home / "t2.jsonl"
            write_transcript(
                t2, [skill_use("toolu_B", "work"), skill_use("toolu_C", "plan-tasks")]
            )
            r2 = run_hook({"transcript_path": str(t2), "session_id": session_id}, home)
            self.assertEqual(r2.returncode, 0)

            # B's original write (step 1's hook run) lands glued to A's truncated,
            # unparseable fragment pre-fix, so it can never surface as a parsed
            # dict again — read_rows() alone can't tell "deduped" from "duplicate
            # entombed in corruption" apart, since both leave exactly one
            # *parseable* B row. Count raw occurrences of B's id in the file text
            # instead: pre-fix, dedup fails to recognize the entombed B and
            # re-appends a second, parseable copy, so the id appears twice (once
            # unparseable, once clean); post-fix it appears exactly once.
            raw_text = skills_file.read_text(encoding="utf-8")
            self.assertEqual(raw_text.count('"tool_use_id": "toolu_B"'), 1)

            rows = read_rows(home)
            c_rows = [row for row in rows if row.get("tool_use_id") == "toolu_C"]
            self.assertEqual(len(c_rows), 1)


if __name__ == "__main__":
    unittest.main()
