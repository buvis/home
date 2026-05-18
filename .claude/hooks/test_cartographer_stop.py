"""Tests for cartographer-stop.py PostToolUse hook."""
import importlib.util
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))

_HOOK_PATH = Path.home() / ".claude" / "hooks" / "cartographer-stop.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("cartographer_stop", _HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_writes_staleness_flag_on_write_tool(tmp_path, monkeypatch):
    atlas_path = tmp_path / "atlas"
    mod = _load_hook()
    monkeypatch.setattr(mod, "atlas_dir", lambda h: atlas_path)
    monkeypatch.setattr(mod, "project_hash", lambda path: ("testhash", "repo", ""))
    payload = {"tool_name": "Write", "tool_input": {"file_path": "/tmp/test.py"}, "tool_result": {}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    mod.main()
    assert (atlas_path / "staleness.flag").exists()


def test_exits_silently_on_error(tmp_path, monkeypatch):
    mod = _load_hook()

    def _raise(path):
        raise RuntimeError("boom")

    monkeypatch.setattr(mod, "project_hash", _raise)
    payload = {"tool_name": "Write", "tool_input": {"file_path": "/tmp/test.py"}, "tool_result": {}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    mod.main()  # must not raise


def test_skips_bash_tool(tmp_path, monkeypatch):
    atlas_path = tmp_path / "atlas"
    mod = _load_hook()
    monkeypatch.setattr(mod, "atlas_dir", lambda h: atlas_path)
    monkeypatch.setattr(mod, "project_hash", lambda path: ("testhash", "repo", ""))
    payload = {"tool_name": "Bash", "tool_input": {"command": "ls"}, "tool_result": {}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    mod.main()
    assert not (atlas_path / "staleness.flag").exists()
