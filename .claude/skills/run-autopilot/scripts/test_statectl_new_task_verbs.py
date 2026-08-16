"""Tests for statectl.py's PRD 00120 task verbs.

Split out of test_statectl_task_verbs.py to keep both files under the
800-line limit. Same stdlib-only unittest, subprocess pattern: binds the
public contract of the five verbs PRD 00120 added - task-add,
task-set-body, task-set-meta, task-set-status and tasks-clear - by running
the CLI as a subprocess and asserting on exit codes and file bytes, never
on internals.

task-start, task-done, append-attempt and set-contract-card stay in
test_statectl_task_verbs.py.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# reset_prd_fields is imported directly (never via the CLI) so one test can
# bind its fixture to the real per-PRD reset producer, not a hand-built shape.
sys.path.insert(0, str(Path(__file__).parent.parent))
from cli.records import reset_prd_fields

STATECTL = Path(__file__).parent / "statectl.py"


class StatectlNewTaskVerbsTest(unittest.TestCase):
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

    # 3. task-add --------------------------------------------------------------

    def write_text_file(self, name: str, text: str) -> str:
        path = Path(self.tmp.name) / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_task_add_assigns_highest_existing_id_plus_one(self) -> None:
        # Highest existing id + 1, not len(tasks) + 1 and not last-entry + 1: rework
        # follow-ups leave tasks[] out of id order, so those shortcuts duplicate ids.
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

    def test_task_add_keeps_climbing_on_repeated_adds_to_the_same_file(self) -> None:
        # Two adds in a row rule out a fixed guess: the id must move off the first.
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
        first = self.run_cli(
            "task-add",
            self.write_json("t.json", {"name": "Wire the verb"}),
        )
        self.assertEqual(first.returncode, 0)
        self.assertEqual(first.stdout.strip(), "6")
        again = self.run_cli("task-add", self.write_json("t2.json", {"name": "Next"}))
        self.assertEqual(again.returncode, 0)
        self.assertEqual(again.stdout.strip(), "7")
        state = self.load_state()
        self.assertEqual([t["id"] for t in state["tasks"]], ["5", "2", "6", "7"])
        self.assertEqual(state["tasks"][-1]["name"], "Next")
        self.assertEqual(state["tasks_total"], 4)

    def test_task_add_id_is_not_a_function_of_task_count(self) -> None:
        # Same task count as another fixture (two), different ids: the answer
        # moves from "6" to "10", so id is not a function of tasks-array length.
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
        # /work renders its dispatch from these fields, so a dropped or mangled one
        # is invisible until the implementor gets a placeholder-shaped prompt.
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
            # Not a documented field: the contract is "every field present passes
            # through whole", not a list of known field names.
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
        # Absent must stay absent: a JSON null renders as "None" in the dispatch.
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
        # `name` is the dispatch subject: a nameless task must surface here, not
        # as a blank prompt an implementor reads later.
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
        # A JSON array has no fields to merge: a clean naming-the-file error, not a
        # raw traceback.
        self.write_state({"tasks": [], "tasks_total": 0, "tasks_completed": 0})
        before = self.state.read_bytes()
        payload = self.write_json("t.json", [{"name": "Wrapped in an array"}])
        result = self.run_cli("task-add", payload)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn(payload, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.state.read_bytes(), before)

    # 4. task-set-body -----------------------------------------------------

    def test_task_set_body_replaces_description_verbatim(self) -> None:
        # Raw file content, never JSON-decoded, and the trailing newline survives
        # (unlike set-contract-card). Target sits at array index 1, off from id.
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

        # A second body: content comes from the passed file, so a different file
        # must produce a different description.
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

    # 5. task-set-meta -------------------------------------------------------

    def test_task_set_meta_merges_overwrites_and_deletes_nulls(self) -> None:
        # One write covers overwrite, add, and delete-on-null; whole-entry equality
        # binds the flattening. Target sits at array index 1, off from id.
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
        # Never changes status: the stale completed-count of 2 stays 2.
        self.assertEqual(state["tasks_completed"], 2)

    def test_task_set_meta_second_merge_moves_the_entry_again(self) -> None:
        # A second merge, different keys deleted: the payload file decides.
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
        first = self.write_json(
            "m.json",
            {"model": "opus", "est_context_peak": 120000, "qwen_eligible": None},
        )
        self.assertEqual(self.run_cli("task-set-meta", "3", first).returncode, 0)
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
        # `id` and `status` are verb-owned: merging either would corrupt lookups
        # or skip the enum/recount, so both are rejected, not silently stripped.
        self.three_tasks()
        # Control first: a legal payload must succeed, proving the guard, not a
        # broken verb, rejects the cases below.
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

    # 6. task-set-status ------------------------------------------------------

    def test_task_set_status_walks_the_enum_and_recounts_completed(self) -> None:
        # Ids are out of array order; the first target sits at index 1, not 2.
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
        # Whole-entry equality: no attempt record came with it (that's task-done's job).
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
        # Control first: a legal value must succeed, proving the enum check below.
        self.assertEqual(self.run_cli("task-set-status", "2", "pending").returncode, 0)
        before = self.state.read_bytes()
        # An allowlist of three strings, not a blocklist of the usual typos.
        for bad in ("done", "Completed", "in progress", "banana", ""):
            result = self.run_cli("task-set-status", "2", bad)
            self.assertEqual(result.returncode, 1, f"{bad!r} should exit 1")
            self.assertEqual(self.state.read_bytes(), before, f"{bad!r} wrote state")

    # 7. tasks-clear -----------------------------------------------------------

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

    # 8. unknown ids on the new task verbs --------------------------------------

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

    # 9. task-add / task-set-meta robustness on missing-tasks and bad payloads --

    def test_task_add_creates_tasks_array_when_absent(self) -> None:
        # No "tasks" key at all - the shape `autopilot init` writes, and the
        # shape every sibling verb already tolerates via _find_task's
        # data.get("tasks"). task-add is the one verb that must work when no
        # tasks exist yet, so it cannot be the one intolerant verb.
        self.write_state({"phase": "build"})
        payload = self.write_json("t.json", {"name": "First"})
        result = self.run_cli("task-add", payload)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "1")
        state = self.load_state()
        self.assertEqual([t["id"] for t in state["tasks"]], ["1"])
        self.assertEqual(state["tasks_total"], 1)

    def test_task_add_succeeds_against_a_reset_prd_fields_state(self) -> None:
        # records.reset_prd_fields runs on every PRD-to-PRD transition in a
        # multi-PRD batch and removes "tasks" entirely rather than resetting
        # it to []. Bound to the real producer, not a hand-built fixture, so
        # a future edit to PER_PRD_RESET_FIELDS that keeps dropping "tasks"
        # is caught here rather than only in a shape nobody re-derives.
        populated = {
            "phase": "review",
            "tasks_total": 1,
            "tasks_completed": 1,
            "tasks": [{"id": "1", "status": "completed"}],
        }
        reset_state = reset_prd_fields(populated)
        self.assertNotIn("tasks", reset_state)
        self.write_state(reset_state)
        payload = self.write_json("t.json", {"name": "Next PRD's first task"})
        result = self.run_cli("task-add", payload)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "1")
        state = self.load_state()
        self.assertEqual([t["id"] for t in state["tasks"]], ["1"])
        self.assertEqual(state["tasks_total"], 1)

    def test_task_set_meta_rejects_a_json_array_payload(self) -> None:
        # A JSON array parses fine but has no .items() to merge: like
        # task-add's non-object-payload guard three lines above it in
        # _build_apply, the failure must be a clean exit, not an uncaught
        # AttributeError from do_task_set_meta calling meta.items().
        self.three_tasks()
        before = self.state.read_bytes()
        payload = self.write_json("m.json", ["not", "an", "object"])
        result = self.run_cli("task-set-meta", "2", payload)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.state.read_bytes(), before)

    def test_task_set_meta_rejects_a_json_scalar_payload(self) -> None:
        self.three_tasks()
        before = self.state.read_bytes()
        payload = self.write_json("m.json", 42)
        result = self.run_cli("task-set-meta", "2", payload)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.state.read_bytes(), before)

    # 10. placeholder round-trip (PRD 00120 Phase 0 exit criterion) ------------

    def test_task_add_round_trip_derives_dispatch_placeholders_from_persisted_body(
        self,
    ) -> None:
        # PRD 00120 Phase 0 Exit Criteria: "Fixture round-trip test green". A
        # full task body written by task-add must survive a session boundary
        # (re-read from the FILE, not the in-memory payload) and still derive
        # the three /work dispatch placeholders documented in work/SKILL.md.
        description = (
            "Wire the new verb into statectl.\n"
            "\n"
            "Acceptance criteria:\n"
            "- statectl task-add prints the assigned id\n"
            "- the entry round-trips every payload field\n"
            "- tasks_total is derived from the array, not incremented\n"
        )
        payload = {
            "name": "Wire task-add",
            "description": description,
            "model": "sonnet",
            "estimated_tokens": 42000,
            "qwen_eligible": True,
        }
        self.write_state({"tasks": [], "tasks_total": 0, "tasks_completed": 0})
        result = self.run_cli("task-add", self.write_json("t.json", payload))
        self.assertEqual(result.returncode, 0)

        # Re-read the state file - not the payload dict - so the assertion
        # binds to what actually persisted, not to what was sent.
        task = self.load_state()["tasks"][0]
        subject, task_description, criteria = _derive_dispatch_placeholders(task)
        self.assertEqual(subject, "Wire task-add")
        self.assertEqual(task_description, description)
        self.assertIn("- statectl task-add prints the assigned id", criteria)
        self.assertIn("- the entry round-trips every payload field", criteria)
        self.assertIn(
            "- tasks_total is derived from the array, not incremented",
            criteria,
        )

    def test_task_add_round_trip_falls_back_for_a_task_with_no_description(
        self,
    ) -> None:
        # PRD 00120's own "Edge case" row: old writers, new readers. A task
        # written before `description` existed must still derive a usable
        # dispatch body, not a KeyError or an empty placeholder.
        self.write_state({"tasks": [], "tasks_total": 0, "tasks_completed": 0})
        result = self.run_cli(
            "task-add",
            self.write_json("t.json", {"name": "Legacy task"}),
        )
        self.assertEqual(result.returncode, 0)

        task = self.load_state()["tasks"][0]
        subject, task_description, criteria = _derive_dispatch_placeholders(task)
        self.assertEqual(subject, "Legacy task")
        self.assertEqual(task_description, "Legacy task")
        self.assertEqual(criteria, "(none recorded)")

    def test_task_add_round_trip_treats_an_empty_description_as_present_not_absent(
        self,
    ) -> None:
        # An empty string is a present description, not an absent one: the
        # name-only fallback in work/SKILL.md is documented for `description`
        # being absent, not merely empty. No "Acceptance criteria:" section
        # exists in an empty body either way.
        self.write_state({"tasks": [], "tasks_total": 0, "tasks_completed": 0})
        result = self.run_cli(
            "task-add",
            self.write_json("t.json", {"name": "Empty body task", "description": ""}),
        )
        self.assertEqual(result.returncode, 0)

        task = self.load_state()["tasks"][0]
        subject, task_description, criteria = _derive_dispatch_placeholders(task)
        self.assertEqual(subject, "Empty body task")
        self.assertEqual(task_description, "")
        self.assertEqual(criteria, "(none recorded)")


def _derive_dispatch_placeholders(task: dict) -> tuple:
    """Local pin of the /work dispatch placeholder derivation documented in
    work/SKILL.md and work/references/self-deslop-prompt.md:

    - task_subject            <- task["name"]
    - task_description        <- task["description"] (full text), or a
      name-only body when `description` is absent (the key missing, not
      merely an empty string).
    - task_acceptance_criteria <- text-extracted out of the "Acceptance
      criteria:" section of that same description; "(none recorded)" when
      there is no "Acceptance criteria:" section to extract from.
    """
    subject = task["name"]
    description = task.get("description")
    if description is None:
        return subject, subject, "(none recorded)"
    marker = "Acceptance criteria:"
    idx = description.find(marker)
    if idx == -1:
        criteria = "(none recorded)"
    else:
        criteria = description[idx + len(marker) :].strip()
    return subject, description, criteria


if __name__ == "__main__":
    unittest.main()
