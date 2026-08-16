"""Tests for statectl.py's compound task verbs.

Split out of test_statectl.py (path-verb tests: get/set/append/del) to keep
both files under the 800-line limit. Same stdlib-only unittest, subprocess
pattern: binds the public contract of the four pre-existing compound verbs -
task-start, task-done, append-attempt, set-contract-card - by running the CLI
as a subprocess and asserting on exit codes and file bytes, never on
internals.

The five verbs PRD 00120 added (task-add, task-set-body, task-set-meta,
task-set-status, tasks-clear) live in test_statectl_new_task_verbs.py.
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

STATECTL = Path(__file__).parent / "statectl.py"


class StatectlTaskVerbsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "state.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_state(self, obj: object) -> None:
        self.state.write_text(json.dumps(obj))

    def load_state(self) -> object:
        return json.loads(self.state.read_text())

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["python3", str(STATECTL), str(self.state), *args],
            capture_output=True,
            text=True,
        )

    # 1. compound task verbs -----------------------------------------------

    def three_tasks(self) -> None:
        self.write_state(
            {
                "phase": "build",
                "tasks_completed": 1,
                "tasks": [
                    {"id": "1", "status": "completed", "attempts": [{"n": 0}]},
                    {"id": "2", "status": "pending"},
                    {"id": "3", "status": "pending"},
                ],
            },
        )

    def write_json(self, name: str, obj: object) -> str:
        path = Path(self.tmp.name) / name
        path.write_text(json.dumps(obj), encoding="utf-8")
        return str(path)

    def test_task_start_marks_only_that_task_in_progress(self) -> None:
        self.three_tasks()
        result = self.run_cli("task-start", "2")
        self.assertEqual(result.returncode, 0)
        state = self.load_state()
        self.assertEqual(state["tasks"][1]["status"], "in_progress")
        self.assertEqual(state["tasks"][0]["status"], "completed")
        self.assertEqual(state["tasks"][2]["status"], "pending")
        self.assertEqual(state["phase"], "build")

    def test_task_done_sets_status_appends_attempt_and_recounts(self) -> None:
        self.three_tasks()
        attempt = self.write_json("a.json", {"attempt": 1, "implementor": "claude"})
        result = self.run_cli("task-done", "2", attempt)
        self.assertEqual(result.returncode, 0)
        state = self.load_state()
        self.assertEqual(state["tasks"][1]["status"], "completed")
        self.assertEqual(
            state["tasks"][1]["attempts"],
            [{"attempt": 1, "implementor": "claude"}],
        )
        # Derived from the array, not from the stale 1 the file carried.
        self.assertEqual(state["tasks_completed"], 2)

    def test_task_done_appends_beside_existing_attempts(self) -> None:
        self.three_tasks()
        attempt = self.write_json("a.json", {"attempt": 2})
        self.assertEqual(self.run_cli("task-done", "1", attempt).returncode, 0)
        self.assertEqual(
            self.load_state()["tasks"][0]["attempts"],
            [{"n": 0}, {"attempt": 2}],
        )

    def test_append_attempt_records_the_entry_without_completing_the_task(
        self,
    ) -> None:
        # The abort/escalate-away paths record an attempt while the task stays open.
        self.three_tasks()
        attempt = self.write_json("a.json", {"attempt": 1, "outcome": "aborted"})
        result = self.run_cli("append-attempt", "2", attempt)
        self.assertEqual(result.returncode, 0)
        state = self.load_state()
        self.assertEqual(
            state["tasks"][1]["attempts"],
            [{"attempt": 1, "outcome": "aborted"}],
        )
        self.assertEqual(state["tasks"][1]["status"], "pending")
        self.assertEqual(state["tasks_completed"], 1)

    def test_append_attempt_appends_beside_existing_attempts(self) -> None:
        self.three_tasks()
        attempt = self.write_json("a.json", {"attempt": 2, "outcome": "escalated"})
        self.assertEqual(self.run_cli("append-attempt", "1", attempt).returncode, 0)
        self.assertEqual(
            self.load_state()["tasks"][0]["attempts"],
            [{"n": 0}, {"attempt": 2, "outcome": "escalated"}],
        )

    def test_append_attempt_resolves_by_id_not_array_position(self) -> None:
        # Same hazard task-done avoids: rework's [D{cycle}] follow-ups leave tasks[]
        # order not matching id order.
        self.write_state(
            {
                "tasks_completed": 0,
                "tasks": [
                    {"id": "17", "status": "pending"},
                    {"id": "3", "status": "pending"},
                ],
            },
        )
        attempt = self.write_json("a.json", {"attempt": 1})
        self.assertEqual(self.run_cli("append-attempt", "3", attempt).returncode, 0)
        state = self.load_state()
        self.assertEqual(state["tasks"][1]["attempts"], [{"attempt": 1}])
        self.assertNotIn("attempts", state["tasks"][0])

    def test_append_attempt_unknown_id_exits_1_leaving_state_untouched(self) -> None:
        self.three_tasks()
        before = self.state.read_bytes()
        attempt = self.write_json("a.json", {"attempt": 1})
        result = self.run_cli("append-attempt", "99", attempt)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.state.read_bytes(), before)

    def test_append_attempt_missing_file_exits_1(self) -> None:
        self.three_tasks()
        missing = str(Path(self.tmp.name) / "nope.json")
        self.assertEqual(self.run_cli("append-attempt", "2", missing).returncode, 1)

    def test_task_verbs_resolve_by_id_not_array_position(self) -> None:
        # Rework's [D{cycle}] follow-ups leave tasks[N] targeting the wrong task.
        self.write_state(
            {
                "tasks_completed": 0,
                "tasks": [
                    {"id": "17", "status": "pending"},
                    {"id": "3", "status": "pending"},
                ],
            },
        )
        self.assertEqual(self.run_cli("task-start", "3").returncode, 0)
        state = self.load_state()
        self.assertEqual(state["tasks"][1]["status"], "in_progress")
        self.assertEqual(state["tasks"][0]["status"], "pending")

    def test_task_verbs_unknown_id_exits_1_and_leaves_state_untouched(self) -> None:
        self.three_tasks()
        before = self.state.read_bytes()
        result = self.run_cli("task-start", "99")
        self.assertEqual(result.returncode, 1)
        self.assertIn("99", result.stderr)
        self.assertEqual(self.state.read_bytes(), before)

    def test_task_done_malformed_attempt_exits_1_and_leaves_state_untouched(
        self,
    ) -> None:
        self.three_tasks()
        before = self.state.read_bytes()
        bad = Path(self.tmp.name) / "bad.json"
        bad.write_text('{"attempt": 1,,,}', encoding="utf-8")
        result = self.run_cli("task-done", "2", str(bad))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.state.read_bytes(), before)

    def test_task_done_missing_attempt_file_exits_1(self) -> None:
        self.three_tasks()
        before = self.state.read_bytes()
        result = self.run_cli("task-done", "2", str(Path(self.tmp.name) / "nope.json"))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.state.read_bytes(), before)

    # 2. contract card from a file -------------------------------------------

    def test_set_contract_card_survives_shell_hostile_content(self) -> None:
        # The inline form failed three times in a row on quoting, real build session.
        self.write_state({"phase": "build"})
        card = Path(self.tmp.name) / "card.md"
        body = "step: 'review' \"gate\"\nnext: $(rm -rf /) | 100% `done`\n"
        card.write_text(body, encoding="utf-8")
        result = self.run_cli("set-contract-card", str(card))
        self.assertEqual(result.returncode, 0)
        state = self.load_state()
        self.assertEqual(state["contract_card"], body.rstrip("\n"))
        self.assertEqual(state["phase"], "build")

    def test_set_contract_card_missing_file_exits_1(self) -> None:
        self.write_state({"phase": "build"})
        before = self.state.read_bytes()
        result = self.run_cli("set-contract-card", str(Path(self.tmp.name) / "no.md"))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.state.read_bytes(), before)

    def test_task_done_is_atomic_across_its_field_effects(self) -> None:
        # A crash between status, attempts and count is what this compound verb
        # removes: .bak holds pre-transition bytes, the live file all three or none.
        self.three_tasks()
        original = self.state.read_bytes()
        attempt = self.write_json("a.json", {"attempt": 1})
        self.assertEqual(self.run_cli("task-done", "3", attempt).returncode, 0)
        self.assertEqual(Path(str(self.state) + ".bak").read_bytes(), original)
        state = self.load_state()
        self.assertEqual(state["tasks"][2]["status"], "completed")
        self.assertEqual(state["tasks"][2]["attempts"], [{"attempt": 1}])
        self.assertEqual(state["tasks_completed"], 2)


if __name__ == "__main__":
    unittest.main()
