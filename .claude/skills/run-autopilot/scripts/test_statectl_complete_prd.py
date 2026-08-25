"""Tests for statectl.py's complete-prd verb.

Binds the public contract of complete-prd: appending the documented
batch.completed_prds object (filename, cycles, autonomous_decisions,
escalated_decisions, tasks_completed, tasks_total) computed from the state
being closed, and resetting batch.parks_consecutive to 0 in the same write.
Same stdlib-only unittest, subprocess pattern as test_statectl_new_task_verbs.py:
runs the CLI as a subprocess and asserts on exit codes and file bytes, never
on internals.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

STATECTL = Path(__file__).parent / "statectl.py"
GOLDEN_FIXTURE = (
    Path(__file__).parent.parent
    / "cli"
    / "golden"
    / "state-batch-202608162223-reconstructed.json"
)

# In-process access to the cli package, needed only by the tests below that
# monkeypatch or call cli internals directly (everything else in this module
# drives complete-prd as a subprocess and asserts on file bytes only).
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR.parent))
from cli import render_report, statectl

# Shared by the two autonomous-parity tests below: two ordinary
# autonomous-decision entries ("a", "b") plus one assumed-ambiguity entry
# that deliberately carries cycle, question and reason - all renderable
# cells under the blank-row rule - so only its type value can be what drops
# it from the Autonomous Decisions table. Pins the expected count at 2, not
# 0 or 3.
_AUTONOMOUS_DECISIONS_MIX = [
    {
        "cycle": 1,
        "issue": "a",
        "severity": "low",
        "action": "auto-fix",
        "reason": "r",
    },
    {
        "type": "assumed-ambiguity",
        "cycle": 1,
        "question": "q?",
        "assumption": "assumed x",
        "reason": "loop mode",
    },
    {
        "cycle": 1,
        "issue": "b",
        "severity": "low",
        "action": "auto-fix",
        "reason": "r",
    },
]


class StatectlCompletePrdTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "state.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_state(self, obj: object) -> None:
        self.state.write_text(json.dumps(obj))

    def load_state(self) -> object:
        return json.loads(self.state.read_text(encoding="utf-8"))

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["python3", str(STATECTL), str(self.state), *args],
            capture_output=True,
            text=True,
        )

    # Test case 1: happy path ---------------------------------------------------

    def test_complete_prd_appends_documented_object_and_resets_parks_consecutive(
        self,
    ) -> None:
        # batch has no completed_prds key yet - the verb must create it, not
        # assume a caller already seeded the list. deferred_decisions mixes
        # "resolved" (counts), "pending" and "deferred" (both excluded) so the
        # count can't pass by only ever excluding one of the two statuses.
        # The autonomous_decisions entries each carry a renderable cell on
        # purpose: the count mirrors render_report._autonomous's blank-row
        # rule, so filler like {"id": N} would render no row and count 0.
        self.write_state(
            {
                "phase": "review",
                "prd": "0000X-example.md",
                "cycle": 2,
                "tasks_completed": 5,
                "tasks_total": 7,
                "autonomous_decisions": [
                    {"id": 1, "issue": "a", "action": "auto-fix"},
                    {"id": 2, "issue": "b", "action": "auto-fix"},
                    {"id": 3, "issue": "c", "action": "auto-fix"},
                ],
                "deferred_decisions": [
                    {"status": "resolved"},
                    {"status": "pending"},
                    {"status": "pending"},
                    {"status": "deferred"},
                ],
                "batch": {"parks_consecutive": 2},
            },
        )
        result = self.run_cli("complete-prd", "0000X-example.md")
        self.assertEqual(result.returncode, 0)
        state = self.load_state()
        self.assertEqual(
            state["batch"]["completed_prds"][-1],
            {
                "filename": "0000X-example.md",
                "cycles": 2,
                "autonomous_decisions": 3,
                "escalated_decisions": 1,
                "tasks_completed": 5,
                "tasks_total": 7,
            },
        )
        self.assertEqual(state["batch"]["parks_consecutive"], 0)

    # Regression: escalated_decisions is an EXCLUSION rule (anything other than
    # pending/deferred counts), not an allowlist of the single word "resolved" -
    # mirrors render_report._is_pending's own definition. A status word Alice or
    # Bob might realistically stamp (e.g. "escalated") must count too.
    def test_complete_prd_counts_any_non_pending_non_deferred_status_as_escalated(
        self,
    ) -> None:
        self.write_state(
            {
                "phase": "review",
                "prd": "0000X-example.md",
                "cycle": 1,
                "tasks_completed": 1,
                "tasks_total": 1,
                "deferred_decisions": [
                    {"status": "escalated"},
                    {"status": "pending"},
                ],
                "batch": {"parks_consecutive": 0},
            },
        )
        result = self.run_cli("complete-prd", "0000X-example.md")
        self.assertEqual(result.returncode, 0)
        entry = self.load_state()["batch"]["completed_prds"][-1]
        self.assertEqual(entry["escalated_decisions"], 1)

    # Regression: filename is read off state["prd"], not trusted from the CLI
    # arg - a caller-passed name that diverges from state.prd is a usage
    # mistake, not a value to silently record.
    def test_complete_prd_rejects_a_filename_arg_that_does_not_match_state_prd(
        self,
    ) -> None:
        self.write_state(
            {
                "phase": "review",
                "prd": "0000X-real.md",
                "cycle": 1,
                "tasks_completed": 1,
                "tasks_total": 1,
                "batch": {"parks_consecutive": 0},
            },
        )
        result = self.run_cli("complete-prd", "0000X-wrong.md")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("completed_prds", self.load_state().get("batch", {}))

    # Test case 2: preserves sibling fields --------------------------------------

    def test_complete_prd_preserves_other_sibling_fields(self) -> None:
        self.write_state(
            {
                "phase": "review",
                "prd": "0000X-example.md",
                "cycle": 1,
                "tasks_completed": 1,
                "tasks_total": 1,
                "contract_card": "step: review",
                "batch": {"parks_consecutive": 0},
            },
        )
        result = self.run_cli("complete-prd", "0000X-example.md")
        self.assertEqual(result.returncode, 0)
        state = self.load_state()
        self.assertEqual(state["phase"], "review")
        self.assertEqual(state["contract_card"], "step: review")

    # Test case 3: appends without overwriting prior entries --------------------

    def test_complete_prd_appends_to_an_existing_completed_prds_list(self) -> None:
        self.write_state(
            {
                "phase": "review",
                "prd": "00002-second.md",
                "cycle": 1,
                "tasks_completed": 1,
                "tasks_total": 1,
                "batch": {
                    "parks_consecutive": 0,
                    "completed_prds": [
                        {
                            "filename": "00001-first.md",
                            "cycles": 3,
                            "autonomous_decisions": 0,
                            "escalated_decisions": 0,
                            "tasks_completed": 4,
                            "tasks_total": 4,
                        },
                    ],
                },
            },
        )
        result = self.run_cli("complete-prd", "00002-second.md")
        self.assertEqual(result.returncode, 0)
        entries = self.load_state()["batch"]["completed_prds"]
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["filename"], "00001-first.md")
        self.assertEqual(entries[1]["filename"], "00002-second.md")

    # Test case 4: deferred_decisions absent -------------------------------------

    def test_complete_prd_records_zero_escalated_decisions_when_deferred_decisions_absent(
        self,
    ) -> None:
        self.write_state(
            {
                "phase": "review",
                "prd": "0000X-example.md",
                "cycle": 1,
                "tasks_completed": 1,
                "tasks_total": 1,
                "autonomous_decisions": [{"id": 1}],
                "batch": {"parks_consecutive": 0},
            },
        )
        result = self.run_cli("complete-prd", "0000X-example.md")
        self.assertEqual(result.returncode, 0)
        entry = self.load_state()["batch"]["completed_prds"][-1]
        self.assertEqual(entry["escalated_decisions"], 0)

    # Test case 5: autonomous_decisions absent -----------------------------------

    def test_complete_prd_records_zero_autonomous_decisions_when_key_absent(
        self,
    ) -> None:
        self.write_state(
            {
                "phase": "review",
                "prd": "0000X-example.md",
                "cycle": 1,
                "tasks_completed": 1,
                "tasks_total": 1,
                "deferred_decisions": [{"status": "pending"}],
                "batch": {"parks_consecutive": 0},
            },
        )
        result = self.run_cli("complete-prd", "0000X-example.md")
        self.assertEqual(result.returncode, 0)
        entry = self.load_state()["batch"]["completed_prds"][-1]
        self.assertEqual(entry["autonomous_decisions"], 0)

    # Defect 1: state shapes the codebase itself produces are missing one or
    # more of cycle/tasks_completed/tasks_total. do_complete_prd must not
    # crash on them - the first PRD of a fresh batch reaches this verb with
    # no "cycle" key at all (only the rework and reset paths ever write it).

    def test_missing_cycle_key_records_one_cycle_not_a_crash(self) -> None:
        self.write_state(
            {
                "phase": "review",
                "prd": "0000X-example.md",
                "tasks_completed": 5,
                "tasks_total": 7,
                "batch": {"parks_consecutive": 0},
            },
        )
        result = self.run_cli("complete-prd", "0000X-example.md")
        self.assertEqual(result.returncode, 0)
        entry = self.load_state()["batch"]["completed_prds"][-1]
        self.assertEqual(entry["cycles"], 1)

    def test_missing_task_count_keys_records_zero_for_both_not_a_crash(
        self,
    ) -> None:
        self.write_state(
            {
                "phase": "review",
                "prd": "0000X-example.md",
                "cycle": 3,
                "batch": {"parks_consecutive": 0},
            },
        )
        result = self.run_cli("complete-prd", "0000X-example.md")
        self.assertEqual(result.returncode, 0)
        entry = self.load_state()["batch"]["completed_prds"][-1]
        self.assertEqual(entry["tasks_completed"], 0)
        self.assertEqual(entry["tasks_total"], 0)

    def test_missing_cycle_and_task_count_keys_records_all_defaults_not_a_crash(
        self,
    ) -> None:
        self.write_state(
            {
                "phase": "review",
                "prd": "0000X-example.md",
                "batch": {"parks_consecutive": 0},
            },
        )
        result = self.run_cli("complete-prd", "0000X-example.md")
        self.assertEqual(result.returncode, 0)
        entry = self.load_state()["batch"]["completed_prds"][-1]
        self.assertEqual(entry["cycles"], 1)
        self.assertEqual(entry["tasks_completed"], 0)
        self.assertEqual(entry["tasks_total"], 0)

    # Defect 2: the writer must count only decisions the renderer would draw
    # a row for - one non-empty cell among cycle/issue-or-question/severity/
    # action/reason-or-resolution, where empty means None OR "".

    def test_blank_autonomous_decision_entry_is_not_counted(self) -> None:
        self.write_state(
            {
                "phase": "review",
                "prd": "0000X-example.md",
                "cycle": 1,
                "tasks_completed": 1,
                "tasks_total": 1,
                "autonomous_decisions": [
                    {
                        "cycle": 1,
                        "issue": "a",
                        "severity": "low",
                        "action": "auto-fix",
                        "reason": "x",
                    },
                    {
                        "cycle": 2,
                        "issue": "b",
                        "severity": "medium",
                        "action": "auto-fix",
                        "reason": "y",
                    },
                    {},
                ],
                "batch": {"parks_consecutive": 0},
            },
        )
        result = self.run_cli("complete-prd", "0000X-example.md")
        self.assertEqual(result.returncode, 0)
        entry = self.load_state()["batch"]["completed_prds"][-1]
        self.assertEqual(entry["autonomous_decisions"], 2)

    def test_autonomous_decision_entry_with_all_empty_string_cells_is_not_counted(
        self,
    ) -> None:
        self.write_state(
            {
                "phase": "review",
                "prd": "0000X-example.md",
                "cycle": 1,
                "tasks_completed": 1,
                "tasks_total": 1,
                "autonomous_decisions": [
                    {
                        "cycle": 1,
                        "issue": "a",
                        "severity": "low",
                        "action": "auto-fix",
                        "reason": "x",
                    },
                    {
                        "cycle": "",
                        "issue": "",
                        "severity": "",
                        "action": "",
                        "reason": "",
                    },
                ],
                "batch": {"parks_consecutive": 0},
            },
        )
        result = self.run_cli("complete-prd", "0000X-example.md")
        self.assertEqual(result.returncode, 0)
        entry = self.load_state()["batch"]["completed_prds"][-1]
        self.assertEqual(entry["autonomous_decisions"], 1)

    # Regression: a naive "drop anything without an issue" fix would exclude
    # this entry too, undercounting to 0 instead of 1 - one non-empty cell
    # (cycle alone) is enough for the renderer to draw the row.
    def test_autonomous_decision_entry_with_only_cycle_populated_is_counted(
        self,
    ) -> None:
        self.write_state(
            {
                "phase": "review",
                "prd": "0000X-example.md",
                "cycle": 1,
                "tasks_completed": 1,
                "tasks_total": 1,
                "autonomous_decisions": [
                    {},
                    {"cycle": 5},
                ],
                "batch": {"parks_consecutive": 0},
            },
        )
        result = self.run_cli("complete-prd", "0000X-example.md")
        self.assertEqual(result.returncode, 0)
        entry = self.load_state()["batch"]["completed_prds"][-1]
        self.assertEqual(entry["autonomous_decisions"], 1)

    # Defect 2, the fixture case: a real reconstructed batch state whose
    # autonomous_decisions holds 7 entries, one entirely blank, and whose
    # hand-written completed_prds[0] record (and the renderer) both agree on
    # 6. The fixture's root tasks_completed/tasks_total are already 0 (wiped
    # by tasks-clear in this reconstructed state, unlike the hand-written record's
    # 7/7 from before that wipe), so this test asserts the decision count
    # only and does not compare task fields.
    def test_golden_batch_fixture_records_six_autonomous_decisions_not_seven(
        self,
    ) -> None:
        fixture_state = json.loads(GOLDEN_FIXTURE.read_text(encoding="utf-8"))
        self.write_state(fixture_state)
        result = self.run_cli("complete-prd", fixture_state["prd"])
        self.assertEqual(result.returncode, 0)
        entry = self.load_state()["batch"]["completed_prds"][-1]
        self.assertEqual(entry["autonomous_decisions"], 6)

    # Defect 2, sharpened: the rule is "has a non-empty cell among the five
    # the renderer draws" (cycle/issue-or-question/severity/action/reason-or-
    # resolution), not "has any non-empty value under any key". An entry
    # whose only populated field is outside those five renders no row and
    # must not be counted. Paired with a well-formed decision so the expected
    # count is 1, not 0 - a broken implementation that counts nothing can't
    # pass by accident.
    def test_entry_with_only_non_renderable_keys_is_not_counted(self) -> None:
        self.write_state(
            {
                "phase": "review",
                "prd": "0000X-example.md",
                "cycle": 1,
                "tasks_completed": 1,
                "tasks_total": 1,
                "autonomous_decisions": [
                    {
                        "cycle": 1,
                        "issue": "a",
                        "severity": "low",
                        "action": "auto-fix",
                        "reason": "x",
                    },
                    {"id": 7},
                ],
                "batch": {"parks_consecutive": 0},
            },
        )
        result = self.run_cli("complete-prd", "0000X-example.md")
        self.assertEqual(result.returncode, 0)
        entry = self.load_state()["batch"]["completed_prds"][-1]
        self.assertEqual(entry["autonomous_decisions"], 1)

    # Regression: an entry can carry keys outside the renderer's five cells
    # AND a populated cell among them - it must still count. Guards against
    # an over-correction that rejects any entry with an unrecognized key
    # instead of checking the five cells specifically.
    def test_entry_with_non_renderable_key_and_populated_renderable_cell_is_counted(
        self,
    ) -> None:
        self.write_state(
            {
                "phase": "review",
                "prd": "0000X-example.md",
                "cycle": 1,
                "tasks_completed": 1,
                "tasks_total": 1,
                "autonomous_decisions": [
                    {"id": 7, "severity": "high"},
                ],
                "batch": {"parks_consecutive": 0},
            },
        )
        result = self.run_cli("complete-prd", "0000X-example.md")
        self.assertEqual(result.returncode, 0)
        entry = self.load_state()["batch"]["completed_prds"][-1]
        self.assertEqual(entry["autonomous_decisions"], 1)

    # Sharpest form of the rule: a populated value under a non-renderable key
    # sits alongside renderable cells that are all explicitly emptied. The
    # entry still renders no row, so it must not count - this is the case
    # that most clearly separates "any value on the entry" from "a non-empty
    # renderer cell". Paired with a well-formed decision so the expected
    # count is 1, not 0.
    def test_entry_with_populated_non_renderable_key_but_empty_renderable_cells_is_not_counted(
        self,
    ) -> None:
        self.write_state(
            {
                "phase": "review",
                "prd": "0000X-example.md",
                "cycle": 1,
                "tasks_completed": 1,
                "tasks_total": 1,
                "autonomous_decisions": [
                    {
                        "cycle": 1,
                        "issue": "a",
                        "severity": "low",
                        "action": "auto-fix",
                        "reason": "x",
                    },
                    {"id": 7, "issue": "", "severity": "", "action": ""},
                ],
                "batch": {"parks_consecutive": 0},
            },
        )
        result = self.run_cli("complete-prd", "0000X-example.md")
        self.assertEqual(result.returncode, 0)
        entry = self.load_state()["batch"]["completed_prds"][-1]
        self.assertEqual(entry["autonomous_decisions"], 1)

    # PRD 00122 item 4: the count must match the rows the "Autonomous
    # Decisions" table draws, and that table skips every entry whose type is
    # exactly "assumed-ambiguity" (those land in "Assumptions Made" instead).
    # See _AUTONOMOUS_DECISIONS_MIX for why the count is 2, not 0 or 3.
    def test_assumed_ambiguity_entries_are_excluded_from_the_autonomous_count(
        self,
    ) -> None:
        self.write_state(
            {
                "phase": "review",
                "prd": "0000X-example.md",
                "cycle": 1,
                "tasks_completed": 1,
                "tasks_total": 1,
                "autonomous_decisions": _AUTONOMOUS_DECISIONS_MIX,
                "batch": {"parks_consecutive": 0},
            },
        )
        result = self.run_cli("complete-prd", "0000X-example.md")
        self.assertEqual(result.returncode, 0)
        entry = self.load_state()["batch"]["completed_prds"][-1]
        self.assertEqual(entry["autonomous_decisions"], 2)

    # PRD 00122 item 4, render-side half (Bob's finding): the prior test
    # only checks the persisted count; it never renders the same decision
    # list and confirms the table itself draws the matching number of rows.
    # This is a characterization test - it passes today because
    # render_report.is_autonomous_row already excludes "assumed-ambiguity"
    # entries - and it exists to pin that invariant so a future change to
    # either the writer's count or the renderer's row selection alone breaks
    # this test instead of letting the two sides silently diverge. Asserts
    # on rendered content, not line position: both ordinary decisions' issue
    # cells appear verbatim, the assumed-ambiguity entry's question text
    # never does, and the data-row count - found by locating the "---"
    # separator by its own shape (only "|" and "-" characters) rather than a
    # fixed index, then counting the "| "-prefixed lines after it - is 2.
    def test_persisted_autonomous_count_matches_rendered_autonomous_data_rows(
        self,
    ) -> None:
        self.write_state(
            {
                "phase": "review",
                "prd": "0000X-example.md",
                "cycle": 1,
                "tasks_completed": 1,
                "tasks_total": 1,
                "autonomous_decisions": _AUTONOMOUS_DECISIONS_MIX,
                "batch": {"parks_consecutive": 0},
            },
        )
        result = self.run_cli("complete-prd", "0000X-example.md")
        self.assertEqual(result.returncode, 0)
        entry = self.load_state()["batch"]["completed_prds"][-1]
        self.assertEqual(entry["autonomous_decisions"], 2)

        rendered = render_report._autonomous(_AUTONOMOUS_DECISIONS_MIX)
        rendered_text = "\n".join(rendered)
        self.assertIn("| a |", rendered_text)
        self.assertIn("| b |", rendered_text)
        self.assertNotIn("q?", rendered_text)

        separator_index = next(
            i for i, line in enumerate(rendered) if line and set(line) <= {"|", "-"}
        )
        data_rows = [
            line for line in rendered[separator_index + 1 :] if line.startswith("| ")
        ]
        self.assertEqual(len(data_rows), 2)

    # PRD 00122 item 4, escalated half (Alice/Bob's finding): unlike the
    # autonomous count, the escalated count had no render-side binding -
    # EscalatedRowPredicateTest pins is_escalated_row's own rule and its
    # routing via a mock stub, but nothing renders render_report._escalated()
    # against a real deferred_decisions list and compares row counts.
    # pending and deferred (b, c) are both excluded; resolved (a) is not -
    # pinning the persisted count at 1, not 0 or 3, catches the exclusion
    # vanishing even though that would move both sides together; comparing
    # against the rendered row count catches the two sides diverging from
    # each other.
    def test_persisted_escalated_count_matches_rendered_escalated_data_rows(
        self,
    ) -> None:
        decisions = [
            {"status": "resolved", "issue": "a"},
            {"status": "pending", "issue": "b"},
            {"status": "deferred", "issue": "c"},
        ]
        self.write_state(
            {
                "phase": "review",
                "prd": "0000X-example.md",
                "cycle": 1,
                "tasks_completed": 1,
                "tasks_total": 1,
                "deferred_decisions": decisions,
                "batch": {"parks_consecutive": 0},
            },
        )
        result = self.run_cli("complete-prd", "0000X-example.md")
        self.assertEqual(result.returncode, 0)
        entry = self.load_state()["batch"]["completed_prds"][-1]
        self.assertEqual(entry["escalated_decisions"], 1)

        rendered = render_report._escalated(decisions)
        rendered_text = "\n".join(rendered)
        self.assertIn("| a |", rendered_text)
        self.assertNotIn("| b |", rendered_text)
        self.assertNotIn("| c |", rendered_text)

        separator_index = next(
            i for i, line in enumerate(rendered) if line and set(line) <= {"|", "-"}
        )
        data_rows = [
            line for line in rendered[separator_index + 1 :] if line.startswith("| ")
        ]
        self.assertEqual(len(data_rows), entry["escalated_decisions"])


class EscalatedRowPredicateTest(unittest.TestCase):
    # Carl's finding: statectl._completed_prd_record's escalated count
    # re-implements render_report's pending/deferred rule inline instead of
    # calling a shared predicate, so the two sides can drift apart even
    # though they agree today. Both entries below share the same "pending"
    # status, so the real (unshared) rule would score them identically - 0
    # either way, regardless of which one - while the stub tells them apart
    # by an unrelated "note" field and yields 1. That total, 1, cannot be
    # produced by coincidence from the real rule on this input, so the test
    # only passes once the count is actually routed through
    # render_report.is_escalated_row per entry, not merely equal to it.
    def test_completed_prd_record_escalated_count_follows_is_escalated_row_stub(
        self,
    ) -> None:
        data = {
            "prd": "0000X-example.md",
            "cycle": 1,
            "tasks_completed": 1,
            "tasks_total": 1,
            "deferred_decisions": [
                {"status": "pending", "note": "keep"},
                {"status": "pending", "note": "drop"},
            ],
        }
        with mock.patch.object(
            render_report,
            "is_escalated_row",
            side_effect=lambda entry: entry.get("note") == "keep",
        ):
            record = statectl._completed_prd_record(data)
        self.assertEqual(record["escalated_decisions"], 1)

    def test_is_escalated_row_treats_absent_status_as_pending_not_escalated(
        self,
    ) -> None:
        self.assertFalse(render_report.is_escalated_row({"cycle": 1}))

    def test_is_escalated_row_excludes_pending_and_deferred_statuses(
        self,
    ) -> None:
        self.assertFalse(render_report.is_escalated_row({"status": "pending"}))
        self.assertFalse(render_report.is_escalated_row({"status": "deferred"}))

    def test_is_escalated_row_treats_any_other_status_as_escalated(
        self,
    ) -> None:
        self.assertTrue(render_report.is_escalated_row({"status": "resolved"}))

    def test_is_escalated_row_returns_false_for_non_dict_entry_without_raising(
        self,
    ) -> None:
        self.assertFalse(render_report.is_escalated_row("not-a-dict"))


if __name__ == "__main__":
    unittest.main()
