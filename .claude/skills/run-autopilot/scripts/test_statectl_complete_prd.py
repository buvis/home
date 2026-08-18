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
import tempfile
import unittest
from pathlib import Path

STATECTL = Path(__file__).parent / "statectl.py"


class StatectlCompletePrdTest(unittest.TestCase):
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

    # Test case 1: happy path ---------------------------------------------------

    def test_complete_prd_appends_documented_object_and_resets_parks_consecutive(
        self,
    ) -> None:
        # batch has no completed_prds key yet - the verb must create it, not
        # assume a caller already seeded the list. deferred_decisions mixes
        # "resolved" (counts), "pending" and "deferred" (both excluded) so the
        # count can't pass by only ever excluding one of the two statuses.
        self.write_state(
            {
                "phase": "review",
                "prd": "0000X-example.md",
                "cycle": 2,
                "tasks_completed": 5,
                "tasks_total": 7,
                "autonomous_decisions": [{"id": 1}, {"id": 2}, {"id": 3}],
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


if __name__ == "__main__":
    unittest.main()
