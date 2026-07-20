"""Tests for hooks/track_skills.py (PRD 00086 R2 compliance counter)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import track_skills

HOOK = Path(__file__).resolve().parents[1] / "track_skills.py"


def skill_use(tool_id: str, skill: str) -> dict:
    return {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "invoking"},
                {"type": "tool_use", "id": tool_id, "name": "Skill",
                 "input": {"skill": skill}},
            ]
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
        input=json.dumps(payload), capture_output=True, text=True,
        timeout=10, env=env,
    )


def read_rows(home: Path) -> list[dict]:
    f = home / ".claude" / "metrics" / "skills.jsonl"
    if not f.is_file():
        return []
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]


class ParseTests(unittest.TestCase):
    def test_extracts_skill_names_and_ids(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = Path(td) / "t.jsonl"
            write_transcript(t, [
                skill_use("toolu_1", "review-work-completion"),
                {"type": "user", "message": {"content": "hi"}},
                skill_use("toolu_2", "plan-tasks"),
            ])
            got = track_skills.skill_invocations(t)
            self.assertEqual(got, [("toolu_1", "review-work-completion"),
                                   ("toolu_2", "plan-tasks")])

    def test_dedups_repeated_tool_use_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = Path(td) / "t.jsonl"
            write_transcript(t, [skill_use("toolu_1", "brush"),
                                 skill_use("toolu_1", "brush")])
            self.assertEqual(track_skills.skill_invocations(t),
                             [("toolu_1", "brush")])

    def test_ignores_non_skill_tool_use(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = Path(td) / "t.jsonl"
            write_transcript(t, [{
                "type": "assistant",
                "message": {"content": [
                    {"type": "tool_use", "id": "b1", "name": "Bash",
                     "input": {"command": "ls"}}]},
            }])
            self.assertEqual(track_skills.skill_invocations(t), [])

    def test_unreadable_transcript_returns_empty(self) -> None:
        self.assertEqual(track_skills.skill_invocations(Path("/nope/x.jsonl")), [])


class EndToEndTests(unittest.TestCase):
    def test_writes_rows_with_source_and_session(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            t = home / "t.jsonl"
            write_transcript(t, [skill_use("toolu_1", "survey")])
            r = run_hook({"transcript_path": str(t), "session_id": "sess-A"}, home,
                         extra_env={"_AUTOPILOT_LOOP": "test-loop"})
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


if __name__ == "__main__":
    unittest.main()
