"""Tests for update-pidash-tasks.py — the TaskUpdate PostToolUse sync hook.

Binds the single-writer contract: the hook is the sole maintainer of
`tasks_total`/`tasks_completed` in dev/local/autopilot/state.json. It must
match the real TaskUpdate tool_input field (`taskId`), update the task's
status, recompute both counts, and preserve per-task metadata (model,
attempts).
"""

import importlib.util
import io
import json
from pathlib import Path
from unittest import mock

HOOK_PATH = Path(__file__).resolve().parents[1] / "update-pidash-tasks.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("update_pidash_tasks", HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_state(tmp_path: Path, tasks: list) -> Path:
    d = tmp_path / "dev" / "local" / "autopilot"
    d.mkdir(parents=True)
    (d / "state.json").write_text(
        json.dumps({"tasks": tasks, "tasks_total": 0, "tasks_completed": 0})
    )
    return d / "state.json"


def _run(hook, payload: dict, tmp_path: Path, monkeypatch) -> dict:
    state_file = tmp_path / "dev" / "local" / "autopilot" / "state.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO(json.dumps(payload)))
    with mock.patch.object(hook, "mirror_to_session_dir", lambda *a, **k: None):
        hook.main()
    return json.loads(state_file.read_text())


def test_taskupdate_taskid_syncs_status_and_counts(tmp_path, monkeypatch):
    """The hook must match the real TaskUpdate field `taskId` and recompute counts."""
    hook = _load_hook()
    _write_state(
        tmp_path,
        [
            {"id": "1", "name": "A", "status": "completed"},
            {"id": "2", "name": "B", "status": "pending"},
        ],
    )
    out = _run(hook, {"tool_input": {"taskId": "2", "status": "completed"}}, tmp_path, monkeypatch)
    t2 = next(t for t in out["tasks"] if t["id"] == "2")
    assert t2["status"] == "completed"
    assert out["tasks_completed"] == 2
    assert out["tasks_total"] == 2


def test_taskupdate_preserves_task_metadata(tmp_path, monkeypatch):
    """Recomputing counts must not strip model/attempts from a task."""
    hook = _load_hook()
    _write_state(
        tmp_path,
        [
            {
                "id": "1",
                "name": "A",
                "status": "pending",
                "model": "sonnet",
                "attempts": [{"outcome": "completed", "implementor": "claude"}],
            },
        ],
    )
    out = _run(hook, {"tool_input": {"taskId": "1", "status": "completed"}}, tmp_path, monkeypatch)
    t1 = out["tasks"][0]
    assert t1["status"] == "completed"
    assert t1["model"] == "sonnet"
    assert t1["attempts"] == [{"outcome": "completed", "implementor": "claude"}]


def test_legacy_id_field_still_matches(tmp_path, monkeypatch):
    """Backward-compat: a tool_input carrying `id` (not `taskId`) still syncs."""
    hook = _load_hook()
    _write_state(tmp_path, [{"id": "1", "name": "A", "status": "pending"}])
    out = _run(hook, {"tool_input": {"id": "1", "status": "completed"}}, tmp_path, monkeypatch)
    assert out["tasks"][0]["status"] == "completed"
    assert out["tasks_completed"] == 1
    assert out["tasks_total"] == 1
