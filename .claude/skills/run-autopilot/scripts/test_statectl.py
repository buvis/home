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

    # 12. task-add --------------------------------------------------------------

    def write_text_file(self, name: str, text: str) -> str:
        path = Path(self.tmp.name) / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_task_add_assigns_next_sequential_id_and_prints_it(self) -> None:
        # Highest existing id + 1 - not len(tasks) + 1 and not last-entry + 1:
        # rework follow-ups leave tasks[] out of id order, so those two shortcuts
        # would hand out a duplicate id. Two adds in a row on one state file also
        # rule out a fixed guess: the second id has to move off the first.
        self.write_state(
            {
                "phase": "build",
                "tasks_total": 5,
                "tasks_completed": 0,
                "tasks": [
                    {"id": "5", "status": "pending"},
                    {"id": "2", "status": "pending"},
                ],
            },
        )
        payload = self.write_json("t.json", {"name": "Wire the verb"})
        result = self.run_cli("task-add", payload)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "6")
        state = self.load_state()
        self.assertEqual(len(state["tasks"]), 3)
        self.assertEqual(state["tasks"][-1]["id"], "6")
        self.assertEqual(state["tasks"][-1]["name"], "Wire the verb")
        self.assertEqual(state["tasks"][-1]["status"], "pending")
        self.assertEqual(state["tasks"][0], {"id": "5", "status": "pending"})
        # Derived from the array, not incremented off the stale 5 in the file.
        self.assertEqual(state["tasks_total"], 3)
        self.assertEqual(state["phase"], "build")

        # Second add on the same file: the id must come off the array as it now
        # stands, so it keeps climbing.
        again = self.run_cli("task-add", self.write_json("t2.json", {"name": "Next"}))
        self.assertEqual(again.returncode, 0)
        self.assertEqual(again.stdout.strip(), "7")
        state = self.load_state()
        self.assertEqual([t["id"] for t in state["tasks"]], ["5", "2", "6", "7"])
        self.assertEqual(state["tasks"][-1]["name"], "Next")
        self.assertEqual(state["tasks_total"], 4)

        # Same task count as the fixture this test opened with (two), different
        # ids: the answer moves from "6" to "10", so the id cannot be a function
        # of how many tasks are in the array.
        self.write_state(
            {
                "tasks_total": 2,
                "tasks_completed": 0,
                "tasks": [
                    {"id": "9", "status": "pending"},
                    {"id": "1", "status": "pending"},
                ],
            },
        )
        wider = self.run_cli("task-add", self.write_json("t3.json", {"name": "Wide"}))
        self.assertEqual(wider.returncode, 0)
        self.assertEqual(wider.stdout.strip(), "10")
        state = self.load_state()
        self.assertEqual([t["id"] for t in state["tasks"]], ["9", "1", "10"])
        self.assertEqual(state["tasks_total"], 3)

    def test_task_add_on_empty_task_list_assigns_id_1(self) -> None:
        self.write_state({"tasks": [], "tasks_total": 0, "tasks_completed": 0})
        payload = self.write_json("t.json", {"name": "First"})
        result = self.run_cli("task-add", payload)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "1")
        state = self.load_state()
        self.assertEqual([t["id"] for t in state["tasks"]], ["1"])
        self.assertEqual(state["tasks_total"], 1)

    def test_task_add_roundtrips_every_payload_field(self) -> None:
        # /work renders its dispatch from these: task_subject from name,
        # task_description from description, so a dropped or mangled field is
        # invisible until the implementor gets a placeholder-shaped prompt.
        self.write_state({"tasks": [], "tasks_total": 0, "tasks_completed": 0})
        payload = {
            "name": "Add task-add",
            "description": "Multi-line\nbody with 'quotes' and \"doubles\"",
            "blocked_by": [1],
            "model": "sonnet",
            "estimated_tokens": 42000,
            "est_context_peak": 118000,
            "qwen_eligible": False,
            "qwen_excluded_reason": "multi-file",
            # Not one of the documented optional fields: the contract is "every
            # payload field that was present", so the payload passes through
            # whole rather than through a list of known field names.
            "acceptance_criteria": "the CLI prints the assigned id",
        }
        result = self.run_cli("task-add", self.write_json("t.json", payload))
        self.assertEqual(result.returncode, 0)
        entry = self.load_state()["tasks"][0]
        for key, value in payload.items():
            self.assertEqual(entry[key], value, f"{key} did not round-trip")
        self.assertEqual(entry["status"], "pending")
        # The printed id is the id that landed in the file, not a second guess.
        self.assertEqual(entry["id"], result.stdout.strip())

    def test_task_add_omits_absent_optional_fields(self) -> None:
        # Absent must stay absent: a JSON null placeholder renders as "None" in
        # the dispatch and reads as a real value to every consumer.
        self.write_state({"tasks": [], "tasks_total": 0, "tasks_completed": 0})
        result = self.run_cli("task-add", self.write_json("t.json", {"name": "Bare"}))
        self.assertEqual(result.returncode, 0)
        entry = self.load_state()["tasks"][0]
        self.assertEqual(entry["id"], "1")
        self.assertEqual(entry["name"], "Bare")
        self.assertEqual(entry["status"], "pending")
        for absent in (
            "description",
            "blocked_by",
            "model",
            "estimated_tokens",
            "est_context_peak",
            "qwen_eligible",
            "qwen_excluded_reason",
        ):
            self.assertNotIn(absent, entry)

    def test_task_add_rejects_a_payload_without_a_name(self) -> None:
        # `name` is the dispatch subject: a nameless task is a caller mistake
        # that must surface here, not a blank prompt an implementor reads later.
        self.write_state({"tasks": [], "tasks_total": 0, "tasks_completed": 0})
        before = self.state.read_bytes()
        for label, payload in (
            ("empty", {}),
            ("no name key", {"description": "body only"}),
            ("empty name", {"name": ""}),
            ("non-string name", {"name": 7}),
        ):
            result = self.run_cli("task-add", self.write_json("t.json", payload))
            self.assertEqual(result.returncode, 1, f"{label} should exit 1")
            self.assertEqual(result.stdout, "", f"{label} should print no id")
            self.assertEqual(
                self.state.read_bytes(),
                before,
                f"{label} must leave the state file byte-identical",
            )

    def test_task_add_rejects_a_non_object_payload(self) -> None:
        # A JSON array parses fine but has no fields to merge: the failure is a
        # clean bad-argument error naming the file, not a raw traceback.
        self.write_state({"tasks": [], "tasks_total": 0, "tasks_completed": 0})
        before = self.state.read_bytes()
        payload = self.write_json("t.json", [{"name": "Wrapped in an array"}])
        result = self.run_cli("task-add", payload)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn(payload, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.state.read_bytes(), before)

    # 13. task-set-body ----------------------------------------------------------

    def test_task_set_body_replaces_description_verbatim(self) -> None:
        # Raw file content, never JSON-decoded, and - unlike set-contract-card -
        # the trailing newline survives. Ids are out of array order and the
        # target sits at index 1, so tasks[0], tasks[-1] and int(id) - 1 each
        # land on a different entry than the id does.
        self.write_state(
            {
                "tasks_total": 3,
                "tasks_completed": 0,
                "tasks": [
                    {"id": "17", "status": "completed"},
                    {"id": "3", "status": "pending", "description": "old body"},
                    {"id": "8", "status": "pending"},
                ],
            },
        )
        body = "step: 'one' \"two\"\n\nrun: $(rm -rf /) | 100% `done`\n"
        result = self.run_cli("task-set-body", "3", self.write_text_file("b.md", body))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        state = self.load_state()
        self.assertEqual(state["tasks"][1]["description"], body)
        self.assertEqual(state["tasks"][1]["status"], "pending")
        self.assertEqual(state["tasks"][0], {"id": "17", "status": "completed"})
        self.assertEqual(state["tasks"][2], {"id": "8", "status": "pending"})
        # Not a status verb: the stale count in the file is left alone.
        self.assertEqual(state["tasks_completed"], 0)

        # A second body on the same task: the content comes from the file that
        # was passed, so a different file has to produce a different description.
        second = "rewritten\n\tindented `tail`\n"
        again = self.run_cli(
            "task-set-body",
            "3",
            self.write_text_file("b2.md", second),
        )
        self.assertEqual(again.returncode, 0)
        state = self.load_state()
        self.assertEqual(state["tasks"][1]["description"], second)
        self.assertEqual(state["tasks"][0], {"id": "17", "status": "completed"})
        self.assertEqual(state["tasks"][2], {"id": "8", "status": "pending"})

    # 14. task-set-meta ----------------------------------------------------------

    def test_task_set_meta_merges_deletes_nulls_and_leaves_omitted_keys(self) -> None:
        # One write covers all three effects: overwrite, add, delete-on-null.
        # Equality on the whole entry also binds the flattening - a "metadata"
        # sub-object would fail here. Ids are out of array order and the target
        # sits at index 1, so tasks[0], tasks[-1] and int(id) - 1 each land on a
        # different entry than the id does.
        self.write_state(
            {
                "tasks_total": 3,
                "tasks_completed": 2,
                "tasks": [
                    {"id": "17", "status": "pending"},
                    {
                        "id": "3",
                        "status": "completed",
                        "model": "sonnet",
                        "estimated_tokens": 100,
                        "qwen_eligible": True,
                    },
                    {"id": "8", "status": "pending"},
                ],
            },
        )
        meta = self.write_json(
            "m.json",
            {"model": "opus", "est_context_peak": 120000, "qwen_eligible": None},
        )
        result = self.run_cli("task-set-meta", "3", meta)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        state = self.load_state()
        self.assertEqual(
            state["tasks"][1],
            {
                "id": "3",
                "status": "completed",
                "model": "opus",
                "estimated_tokens": 100,
                "est_context_peak": 120000,
            },
        )
        self.assertEqual(state["tasks"][0], {"id": "17", "status": "pending"})
        self.assertEqual(state["tasks"][2], {"id": "8", "status": "pending"})
        # This verb never changes status, so it never recounts: the stale 2 the
        # file carried stays 2 even though only one task is completed.
        self.assertEqual(state["tasks_completed"], 2)

        # A second merge on the same task, with different keys and a different
        # key deleted: the payload file decides, so the entry has to move again.
        second = self.write_json(
            "m2.json",
            {
                "qwen_eligible": True,
                "est_context_peak": 90000,
                "estimated_tokens": None,
            },
        )
        again = self.run_cli("task-set-meta", "3", second)
        self.assertEqual(again.returncode, 0)
        state = self.load_state()
        self.assertEqual(
            state["tasks"][1],
            {
                "id": "3",
                "status": "completed",
                "model": "opus",
                "est_context_peak": 90000,
                "qwen_eligible": True,
            },
        )
        self.assertEqual(state["tasks"][0], {"id": "17", "status": "pending"})
        self.assertEqual(state["tasks"][2], {"id": "8", "status": "pending"})

    def test_task_set_meta_rejects_reserved_keys(self) -> None:
        # `id` and `status` are verb-owned. Merging `id` would put two entries
        # under one id, hiding the first from every id lookup; merging `status`
        # would walk past both the enum check and the tasks_completed recount.
        # Rejected, never silently stripped - the caller made a mistake.
        self.three_tasks()
        # Control first: a legal payload must succeed, so the rejections below
        # prove the reserved-key guard and not a broken verb.
        legal = self.write_json("ok.json", {"model": "opus"})
        self.assertEqual(self.run_cli("task-set-meta", "2", legal).returncode, 0)
        before = self.state.read_bytes()
        for label, meta in (
            ("id", {"id": "3"}),
            ("status", {"status": "completed"}),
            ("bad status", {"status": "banana"}),
            ("beside a legal key", {"model": "sonnet", "status": "completed"}),
        ):
            result = self.run_cli("task-set-meta", "2", self.write_json("m.json", meta))
            self.assertEqual(result.returncode, 1, f"{label} should exit 1")
            self.assertEqual(
                self.state.read_bytes(),
                before,
                f"{label} must leave the state file byte-identical",
            )

    # 15. task-set-status --------------------------------------------------------

    def test_task_set_status_walks_the_enum_and_recounts_completed(self) -> None:
        # Ids are out of array order and the first target sits at index 1, so
        # tasks[0], tasks[-1] and int(id) - 1 (index 2 here) each land on a
        # different entry than the id does.
        self.write_state(
            {
                "tasks_total": 3,
                # Stale on purpose: the count must be derived from the array.
                "tasks_completed": 0,
                "tasks": [
                    {"id": "17", "status": "completed"},
                    {"id": "3", "status": "pending"},
                    {"id": "8", "status": "pending"},
                ],
            },
        )
        into = self.run_cli("task-set-status", "3", "completed")
        self.assertEqual(into.returncode, 0)
        self.assertEqual(into.stdout, "")
        state = self.load_state()
        # Whole-entry equality: the status moved and no attempt record came with
        # it, because appending one is task-done's job, not this verb's.
        self.assertEqual(state["tasks"][1], {"id": "3", "status": "completed"})
        self.assertEqual(state["tasks"][0], {"id": "17", "status": "completed"})
        self.assertEqual(state["tasks"][2], {"id": "8", "status": "pending"})
        self.assertEqual(state["tasks_completed"], 2)

        back = self.run_cli("task-set-status", "3", "in_progress")
        self.assertEqual(back.returncode, 0)
        state = self.load_state()
        self.assertEqual(state["tasks"][1]["status"], "in_progress")
        self.assertEqual(state["tasks"][0]["status"], "completed")
        self.assertEqual(state["tasks_completed"], 1)

        out = self.run_cli("task-set-status", "17", "pending")
        self.assertEqual(out.returncode, 0)
        state = self.load_state()
        self.assertEqual(state["tasks"][0]["status"], "pending")
        self.assertEqual(state["tasks"][1]["status"], "in_progress")
        self.assertEqual(state["tasks"][2]["status"], "pending")
        self.assertEqual(state["tasks_completed"], 0)

    def test_task_set_status_rejects_an_invalid_status(self) -> None:
        self.three_tasks()
        # Control first: a legal value must succeed, so the rejections below
        # prove the enum check and not just an unrecognised verb.
        self.assertEqual(self.run_cli("task-set-status", "2", "pending").returncode, 0)
        before = self.state.read_bytes()
        # Near-misses of the enum and values nowhere near it: this is an
        # allowlist of three strings, not a blocklist of the usual typos.
        for bad in ("done", "Completed", "in progress", "banana", ""):
            result = self.run_cli("task-set-status", "2", bad)
            self.assertEqual(result.returncode, 1, f"{bad!r} should exit 1")
            self.assertEqual(self.state.read_bytes(), before, f"{bad!r} wrote state")

    # 16. tasks-clear ------------------------------------------------------------

    def test_tasks_clear_empties_tasks_and_zeroes_counts(self) -> None:
        self.write_state(
            {
                "phase": "build",
                "batch": {"id": "b1"},
                "contract_card": "step: review",
                "rework_task_ids": ["3"],
                "cycle": 2,
                "prd": "00120-migrate-task-tracking-to-statectl.md",
                "next_phase": "build",
                "work_start_sha": "abc123",
                "tasks_total": 3,
                "tasks_completed": 1,
                "tasks": [
                    {"id": "1", "status": "completed", "attempts": [{"n": 0}]},
                    {"id": "2", "status": "pending"},
                    {"id": "3", "status": "pending"},
                ],
            },
        )
        original = self.state.read_bytes()
        result = self.run_cli("tasks-clear")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        state = self.load_state()
        self.assertEqual(state["tasks"], [])
        self.assertEqual(state["tasks_total"], 0)
        self.assertEqual(state["tasks_completed"], 0)
        # Scope is exactly those three keys; every other field survives as-is,
        # named or not. schema_version joins them because every write through
        # the sanctioned writer stamps it - it is not this verb's doing.
        cleared = ("tasks", "tasks_total", "tasks_completed", "schema_version")
        self.assertEqual(
            {k: v for k, v in state.items() if k not in cleared},
            {
                "phase": "build",
                "batch": {"id": "b1"},
                "contract_card": "step: review",
                "rework_task_ids": ["3"],
                "cycle": 2,
                "prd": "00120-migrate-task-tracking-to-statectl.md",
                "next_phase": "build",
                "work_start_sha": "abc123",
            },
        )
        # One write, not three: the rotating backup holds the pre-clear bytes.
        self.assertEqual(Path(str(self.state) + ".bak").read_bytes(), original)

    # 17. unknown ids on the new task verbs --------------------------------------

    def test_new_task_verbs_unknown_id_exit_1_and_leave_state_untouched(self) -> None:
        self.three_tasks()
        before = self.state.read_bytes()
        body = self.write_text_file("b.md", "new body\n")
        meta = self.write_json("m.json", {"model": "opus"})
        for args in (
            ("task-set-body", "99", body),
            ("task-set-meta", "99", meta),
            ("task-set-status", "99", "completed"),
        ):
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 1, f"{args[0]} should exit 1")
            self.assertIn("99", result.stderr, f"{args[0]} should name the id")
            self.assertEqual(
                self.state.read_bytes(),
                before,
                f"{args[0]} must leave the state file byte-identical",
            )


if __name__ == "__main__":
    unittest.main()
