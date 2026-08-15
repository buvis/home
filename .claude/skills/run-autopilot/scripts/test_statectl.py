"""Tests for statectl.py.

Stdlib-only unittest, subprocess pattern (matches test_validate_state_json_hook.py).
Runs under both `python3 test_statectl.py` and `python3 -m pytest test_statectl.py`.

statectl.py is a small JSON-state mutator invoked as:

    python3 statectl.py <state-path> <verb> <json-path> [value]

verbs: get | set | append | del. These tests bind the public contract only,
by running the CLI as a subprocess and asserting on exit codes and file bytes,
never on internals.
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

STATECTL = Path(__file__).parent / "statectl.py"


class StatectlTest(unittest.TestCase):
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

    # 1. Happy-path round-trips ------------------------------------------------

    def test_get_returns_value(self) -> None:
        self.write_state({"phase": "build"})
        result = self.run_cli("get", "phase")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), "build")

    def test_set_then_get_roundtrips(self) -> None:
        self.write_state({"phase": "build"})
        setr = self.run_cli("set", "phase", json.dumps("review"))
        self.assertEqual(setr.returncode, 0)
        self.assertEqual(setr.stdout, "")
        getr = self.run_cli("get", "phase")
        self.assertEqual(getr.returncode, 0)
        self.assertEqual(json.loads(getr.stdout), "review")

    def test_append_then_get_returns_array(self) -> None:
        self.write_state({"events": ["start"]})
        appr = self.run_cli("append", "events", json.dumps("stop"))
        self.assertEqual(appr.returncode, 0)
        self.assertEqual(appr.stdout, "")
        getr = self.run_cli("get", "events")
        self.assertEqual(getr.returncode, 0)
        self.assertEqual(json.loads(getr.stdout), ["start", "stop"])

    def test_del_removes_field(self) -> None:
        self.write_state({"phase": "build", "keep": 1})
        delr = self.run_cli("del", "phase")
        self.assertEqual(delr.returncode, 0)
        state = self.load_state()
        self.assertNotIn("phase", state)
        self.assertEqual(state["keep"], 1)

    # 2. set preserves siblings ------------------------------------------------

    def test_set_preserves_siblings(self) -> None:
        self.write_state({"phase": "build", "batch": {"id": "b1"}, "tasks": []})
        result = self.run_cli("set", "phase", json.dumps("review"))
        self.assertEqual(result.returncode, 0)
        state = self.load_state()
        self.assertEqual(state["phase"], "review")
        self.assertEqual(state["batch"], {"id": "b1"})
        self.assertEqual(state["tasks"], [])

    # 2b. nested-path navigation (dots + [index]) ------------------------------

    def test_get_nested_path(self) -> None:
        # Every other get/set test uses a top-level key; a get broken for nested
        # paths would slip past them. Bind dotted-key and indexed descent here.
        self.write_state(
            {"batch": {"id": "b1"}, "tasks": [{"attempts": [{"n": 1}]}]},
        )
        idr = self.run_cli("get", "batch.id")
        self.assertEqual(idr.returncode, 0)
        self.assertEqual(json.loads(idr.stdout), "b1")
        attr = self.run_cli("get", "tasks[0].attempts")
        self.assertEqual(attr.returncode, 0)
        self.assertEqual(json.loads(attr.stdout), [{"n": 1}])

    def test_set_nested_path_preserves_siblings(self) -> None:
        # Setting a nested key must not clobber its siblings inside the parent.
        self.write_state({"batch": {"id": "b1", "mode": "x"}})
        setr = self.run_cli("set", "batch.id", json.dumps("b2"))
        self.assertEqual(setr.returncode, 0)
        idr = self.run_cli("get", "batch.id")
        self.assertEqual(idr.returncode, 0)
        self.assertEqual(json.loads(idr.stdout), "b2")
        moder = self.run_cli("get", "batch.mode")
        self.assertEqual(moder.returncode, 0)
        self.assertEqual(json.loads(moder.stdout), "x")

    # 3. append creates a missing array ----------------------------------------

    def test_append_creates_missing_array(self) -> None:
        self.write_state({"phase": "build"})
        result = self.run_cli("append", "events", json.dumps("first"))
        self.assertEqual(result.returncode, 0)
        state = self.load_state()
        self.assertEqual(state["events"], ["first"])
        self.assertEqual(state["phase"], "build")

    # 4. concurrent appends both land (the key test) ---------------------------

    def test_two_concurrent_appends_both_land(self) -> None:
        # A single race is a FLAKY guard: a lock-free impl false-passes ~22% of
        # the time because spawn overhead usually serializes the two writers by
        # luck. Repeat on a FRESH file each round so a missing lock loses a write
        # within a few iterations; a correctly-locked impl survives all of them.
        entries = [json.dumps({"who": "a"}), json.dumps({"who": "b"})]
        for i in range(25):
            state = Path(self.tmp.name) / f"race_{i}.json"
            state.write_text(json.dumps({"tasks": [{"attempts": []}]}))
            # Start BOTH processes before waiting on either, so they genuinely race.
            procs = [
                subprocess.Popen(
                    [
                        "python3",
                        str(STATECTL),
                        str(state),
                        "append",
                        "tasks[0].attempts",
                        entry,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                for entry in entries
            ]
            for proc in procs:
                proc.wait()
            for proc in procs:
                self.assertEqual(proc.returncode, 0, f"iteration {i}: nonzero exit")
            # Must still parse: json.loads raises (failing the test) if not.
            attempts = json.loads(state.read_text())["tasks"][0]["attempts"]
            self.assertIn({"who": "a"}, attempts, f"iteration {i}: lost writer a")
            self.assertIn({"who": "b"}, attempts, f"iteration {i}: lost writer b")
            self.assertEqual(len(attempts), 2, f"iteration {i}: lost a write")

    # 5. missing file exits 2 --------------------------------------------------

    def test_missing_file_exits_2(self) -> None:
        # self.state was never written.
        result = self.run_cli("get", "phase")
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.strip())

    # 6. corrupt file is never overwritten -------------------------------------

    def test_corrupt_file_not_overwritten(self) -> None:
        self.state.write_bytes(b'{"phase": "build",,,}')
        before = self.state.read_bytes()
        result = self.run_cli("set", "phase", json.dumps("review"))
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.strip())
        after = self.state.read_bytes()
        self.assertEqual(before, after)

    # 7. backup written before the first mutation ------------------------------

    def test_backup_written_before_first_mutation(self) -> None:
        self.write_state({"phase": "build"})
        original = self.state.read_bytes()
        result = self.run_cli("set", "phase", json.dumps("review"))
        self.assertEqual(result.returncode, 0)
        bak = Path(str(self.state) + ".bak")
        self.assertTrue(bak.exists())
        self.assertEqual(bak.read_bytes(), original)

    def test_backup_rotates_across_invocations(self) -> None:
        # One rotating backup, not append-only and not frozen at the original:
        # after the 2nd mutation, .bak must hold the 1st mutation's result (the
        # bytes present just before the 2nd write), byte-for-byte.
        self.write_state({"phase": "build"})
        first = self.run_cli("set", "phase", json.dumps("review"))
        self.assertEqual(first.returncode, 0)
        after_first = self.state.read_bytes()
        second = self.run_cli("set", "phase", json.dumps("done"))
        self.assertEqual(second.returncode, 0)
        bak = Path(str(self.state) + ".bak")
        self.assertTrue(bak.exists())
        self.assertEqual(bak.read_bytes(), after_first)

    # 8. unsupported path grammar exits 1 --------------------------------------

    def test_unsupported_path_grammar_exits_1(self) -> None:
        self.write_state({"tasks": []})
        # Non-numeric index is outside the "dots + [index]" grammar.
        result = self.run_cli("get", "tasks[x]")
        self.assertEqual(result.returncode, 1)

    # 9. negative indices target from the end (Python-style) -------------------

    def test_negative_index_targets_last_element(self) -> None:
        # The skill prose targets state.tasks[i].attempts[-1] directly (the most
        # recent attempt); statectl must resolve [-1] to the last list element
        # for get and set, or the sole-writer mandate is impossible on that path.
        self.write_state({"tasks": [{"attempts": [{"n": 1}, {"n": 2}]}]})
        getr = self.run_cli("get", "tasks[0].attempts[-1]")
        self.assertEqual(getr.returncode, 0)
        self.assertEqual(json.loads(getr.stdout), {"n": 2})
        setr = self.run_cli("set", "tasks[0].attempts[-1].done", json.dumps(True))
        self.assertEqual(setr.returncode, 0)
        state = self.load_state()
        self.assertEqual(state["tasks"][0]["attempts"][-1], {"n": 2, "done": True})
        self.assertEqual(state["tasks"][0]["attempts"][0], {"n": 1})

    def test_malformed_negative_index_exits_1(self) -> None:
        # A lone '-' or a double '--1' is outside the integer grammar.
        self.write_state({"tasks": [{"attempts": []}]})
        for bad in ("tasks[0].attempts[-]", "tasks[0].attempts[--1]"):
            result = self.run_cli("get", bad)
            self.assertEqual(result.returncode, 1, f"{bad!r} should exit 1")

    # 10. compound task verbs --------------------------------------------------

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
        # The abort and escalate-away paths record an attempt while the task
        # stays open, so neither status nor the derived count may move.
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
        # Same hazard task-done exists to avoid: once rework appends
        # [D{cycle}] follow-ups, tasks[] order stops matching id order.
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
        # The whole point of the verbs: rework appends [D{cycle}] follow-ups, so
        # tasks[] order stops matching id order and a tasks[N] path targets the
        # wrong task.
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

    # 11. contract card from a file --------------------------------------------

    def test_set_contract_card_survives_shell_hostile_content(self) -> None:
        # The reason this verb exists: the inline form failed three times in a row
        # on quoting during a real build session.
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
        # A crash between status, attempts and the count is what the compound verb
        # removes: the .bak must hold the pre-transition bytes, and the live file
        # must carry all three effects or none.
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
