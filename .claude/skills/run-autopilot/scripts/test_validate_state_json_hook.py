"""Tests for validate_state_json_hook.py.

Stdlib-only unittest, subprocess.run pattern (matches ~/.claude/hooks/tests/).

Regression under test: a headless session wrote state.json ending with a
literal `</content>` line (harness-tag bleed, ddb 2026-07-16); the autoclaude
wrapper then halted the loop as 'died (state.json unreadable)' instead of
reporting the session's real PAUSE. The hook must exit 2 on any write that
leaves state.json unparseable, and stay silent for everything else.
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).parent / "validate_state_json_hook.py"


def run_hook(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["python3", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )


class ValidateStateJsonHookTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.autopilot_dir = Path(self.tmp.name) / "dev" / "local" / "autopilot"
        self.autopilot_dir.mkdir(parents=True)
        self.state = self.autopilot_dir / "state.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def payload(self, path: Path) -> dict:
        return {"tool_name": "Write", "tool_input": {"file_path": str(path)}}

    def test_rejects_trailing_content_tag(self) -> None:
        """The 2026-07-16 corruption shape: valid JSON + stray wrapper tag."""
        self.state.write_text('{"phase": "paused"}\n</content>\n')
        result = run_hook(self.payload(self.state))
        self.assertEqual(result.returncode, 2)
        self.assertIn("not valid JSON", result.stderr)

    def test_accepts_valid_state_json(self) -> None:
        self.state.write_text('{"phase": "build", "tasks": []}\n')
        result = run_hook(self.payload(self.state))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")

    def test_ignores_other_files(self) -> None:
        other = self.autopilot_dir / "notes.md"
        other.write_text("not json at all")
        result = run_hook(self.payload(other))
        self.assertEqual(result.returncode, 0)

    def test_ignores_missing_file(self) -> None:
        result = run_hook(self.payload(self.state))
        self.assertEqual(result.returncode, 0)

    def test_survives_garbage_stdin(self) -> None:
        result = subprocess.run(
            ["python3", str(HOOK)],
            input="not json",
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)

    # PRD 00051 task 9: cli.schema.validate on top of parse-only ------------

    def test_rejects_schema_invalid_valid_json(self) -> None:
        """A hand-edit that leaves valid JSON but violates cli.schema (a
        known field with the wrong type) must exit 2 and name the field."""
        self.state.write_text(json.dumps({
            "prd": "x.md",
            "phase": "build",
            "next_phase": "build",
            "cycle": "three",
            "batch": {"id": "b", "completed_prds": [], "parks_consecutive": 0},
        }))
        result = run_hook(self.payload(self.state))
        self.assertEqual(result.returncode, 2)
        self.assertIn("cycle", result.stderr)

    def test_accepts_schema_valid_minimal_state(self) -> None:
        self.state.write_text(json.dumps({
            "prd": "x.md",
            "phase": "build",
            "next_phase": "build",
            "cycle": 1,
            "batch": {"id": "b", "completed_prds": [], "parks_consecutive": 0},
        }))
        result = run_hook(self.payload(self.state))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
