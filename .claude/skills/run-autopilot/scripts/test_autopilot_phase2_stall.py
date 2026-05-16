"""Integration tests for the Phase 2 oversized_task stall path.

Covers SKILL.md Phase 2 "Handle plan-tasks stall (oversized task)" steps:
  - PRD moved from wip/ to stalled/
  - stall_reason cleared from state
  - PRD-specific fields reset (phases_completed, cycle, tasks, etc.)
  - batch field preserved
  - stalled/ directory created if absent
  - sequence prefix preserved on moved PRD
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path


def _setup_pre_stall_fixture(root: Path, prd_name: str) -> tuple[Path, Path]:
    """Create the pre-stall directory layout and state.json.

    Returns (autopilot_dir, wip_dir).
    """
    autopilot_dir = root / "dev" / "local" / "autopilot"
    autopilot_dir.mkdir(parents=True)
    wip_dir = root / "dev" / "local" / "prds" / "wip"
    wip_dir.mkdir(parents=True)
    (wip_dir / prd_name).write_text("# PRD content")

    state = {
        "phase": "planning",
        "next_phase": "planning",
        "phases_completed": ["catchup"],
        "cycle": 1,
        "prd": prd_name,
        "tasks_total": 2,
        "tasks_completed": 0,
        "replan_count": 0,
        "tasks": [
            {"id": "1", "name": "Task one", "status": "pending"},
            {"id": "2", "name": "Task two", "status": "pending"},
        ],
        "task_aborts": [],
        "autonomous_decisions": [],
        "deferred_decisions": [],
        "review_cycles": [],
        "doubts": [],
        "rework_task_ids": [],
        "stall_reason": {
            "stalled": "oversized_task",
            "task": "1",
            "estimated_tokens": 200000,
        },
        "batch": {
            "id": "202601010000",
            "mode": "autopilot",
            "completed_prds": [],
            "catchup_completed_at": "2026-01-01T00:00:00Z",
            "catchup_head_sha": "abc1234",
        },
    }
    (autopilot_dir / "state.json").write_text(json.dumps(state, indent=2))
    return autopilot_dir, wip_dir


def apply_stall_procedure(
    root: Path, autopilot_dir: Path, wip_dir: Path, prd_name: str
) -> None:
    """Apply the Phase 2 oversized_task stall procedure from SKILL.md.

    Steps:
    1. Read current state.
    2. Delete tasks from TaskList (simulated: clear state.tasks).
    3. mkdir -p stalled/.
    4. mv PRD from wip/ to stalled/.
    5. Clear stall_reason; reset PRD-specific fields; preserve batch.
    6. Write state back atomically.
    """
    state_path = autopilot_dir / "state.json"
    state = json.loads(state_path.read_text())

    stalled_dir = root / "dev" / "local" / "prds" / "stalled"
    stalled_dir.mkdir(parents=True, exist_ok=True)

    src = wip_dir / prd_name
    dst = stalled_dir / prd_name
    shutil.move(str(src), str(dst))

    batch = state.get("batch")
    state.update(
        {
            "phases_completed": [],
            "cycle": 1,
            "tasks_total": 0,
            "tasks_completed": 0,
            "replan_count": 0,
            "tasks": [],
            "task_aborts": [],
            "autonomous_decisions": [],
            "deferred_decisions": [],
            "review_cycles": [],
            "doubts": [],
            "rework_task_ids": [],
            "next_phase": "catchup",
        }
    )
    del state["stall_reason"]
    state["batch"] = batch

    tmp = state_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(state_path)


class Phase2StallPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.root = Path(self._tmpdir)
        self.prd_name = "00042-big-feature.md"
        self.autopilot_dir, self.wip_dir = _setup_pre_stall_fixture(
            self.root, self.prd_name
        )
        apply_stall_procedure(
            self.root, self.autopilot_dir, self.wip_dir, self.prd_name
        )

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _state(self) -> dict:
        return json.loads((self.autopilot_dir / "state.json").read_text())

    def test_prd_moved_from_wip_to_stalled(self) -> None:
        self.assertFalse((self.wip_dir / self.prd_name).exists())
        stalled_path = self.root / "dev" / "local" / "prds" / "stalled" / self.prd_name
        self.assertTrue(stalled_path.exists())

    def test_stall_reason_cleared(self) -> None:
        self.assertNotIn("stall_reason", self._state())

    def test_prd_specific_fields_reset(self) -> None:
        s = self._state()
        self.assertEqual(s["phases_completed"], [])
        self.assertEqual(s["cycle"], 1)
        self.assertEqual(s["tasks_total"], 0)
        self.assertEqual(s["tasks_completed"], 0)
        self.assertEqual(s["replan_count"], 0)
        self.assertEqual(s["tasks"], [])
        self.assertEqual(s["rework_task_ids"], [])
        self.assertEqual(s["next_phase"], "catchup")

    def test_batch_field_preserved(self) -> None:
        batch = self._state()["batch"]
        self.assertEqual(batch["id"], "202601010000")
        self.assertEqual(batch["catchup_head_sha"], "abc1234")

    def test_stalled_dir_created_if_missing(self) -> None:
        root2 = Path(tempfile.mkdtemp())
        try:
            prd = "00001-new.md"
            ap_dir, wip = _setup_pre_stall_fixture(root2, prd)
            stalled = root2 / "dev" / "local" / "prds" / "stalled"
            self.assertFalse(stalled.exists())
            apply_stall_procedure(root2, ap_dir, wip, prd)
            self.assertTrue(stalled.exists())
        finally:
            shutil.rmtree(str(root2), ignore_errors=True)

    def test_stalled_prd_keeps_sequence_prefix(self) -> None:
        stalled_path = self.root / "dev" / "local" / "prds" / "stalled" / self.prd_name
        self.assertTrue(stalled_path.name.startswith("00042-"))


if __name__ == "__main__":
    unittest.main()
