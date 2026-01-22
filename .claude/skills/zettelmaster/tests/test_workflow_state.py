import json
import tempfile
from pathlib import Path

import pytest

from zettelmaster.workflow_state import (
    WorkflowPhase,
    WorkflowStatus,
    PhaseResult,
    WorkflowStateManager,
)


@pytest.fixture()
def manager():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir) / ".workflow"
        mgr = WorkflowStateManager(state_dir)
        yield mgr


def create_sample_workflow(mgr: WorkflowStateManager):
    return mgr.create_workflow(["inbox/alpha", "inbox/beta"], metadata={"owner": "tests"})


def test_create_and_load_workflow(manager):
    state = create_sample_workflow(manager)
    workflow_id = state.workflow_id

    reloaded = WorkflowStateManager(manager.state_dir).load_workflow(workflow_id)
    assert reloaded.workflow_id == workflow_id
    assert reloaded.directories == ["inbox/alpha", "inbox/beta"]
    assert reloaded.status == WorkflowStatus.PENDING


def test_start_and_complete_phase(manager):
    create_sample_workflow(manager)
    assert manager.start_phase(WorkflowPhase.EXTRACTION)

    results = {"files": 3, "extracted": 2}
    assert manager.complete_phase(WorkflowPhase.EXTRACTION, results)

    state = manager.current_state
    phase_result = state.phase_results[WorkflowPhase.EXTRACTION.value]
    assert phase_result.status == WorkflowStatus.COMPLETED
    assert phase_result.results == results
    assert state.total_cost >= 0


def test_fail_phase_records_error(manager):
    create_sample_workflow(manager)
    manager.start_phase(WorkflowPhase.PLANNING)
    manager.fail_phase(WorkflowPhase.PLANNING, "LLM timeout")

    state = manager.current_state
    assert state.status == WorkflowStatus.FAILED
    assert state.error_log
    assert any("LLM timeout" in entry["error"] for entry in state.error_log)


def test_pause_and_resume(manager):
    create_sample_workflow(manager)
    manager.start_phase(WorkflowPhase.EXTRACTION)
    assert manager.pause_workflow()
    assert manager.current_state.status == WorkflowStatus.PAUSED
    assert manager.resume_workflow()
    assert manager.current_state.status == WorkflowStatus.IN_PROGRESS


def test_checkpoint_and_restore(manager):
    state = create_sample_workflow(manager)
    manager.start_phase(WorkflowPhase.EXTRACTION)
    checkpoint = manager._create_checkpoint(WorkflowPhase.EXTRACTION, {"files": 1})

    checkpoint_data = json.loads(checkpoint.read_text())
    assert checkpoint_data == {"files": 1}


def test_complete_workflow_writes_summary(manager):
    create_sample_workflow(manager)
    manager.complete_workflow()

    summary_files = list(manager.state_dir.glob("summary_*.txt"))
    assert summary_files, "Expected summary file to be created"


def test_get_latest_workflow(manager):
    first = create_sample_workflow(manager)
    second = manager.create_workflow(["later"], metadata={})

    latest = manager.get_latest_workflow()
    assert latest.workflow_id == second.workflow_id
