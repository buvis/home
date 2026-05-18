import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "survey" / "scripts"))

import run


def _make_args(if_missing: bool) -> argparse.Namespace:
    return argparse.Namespace(if_missing=if_missing, refresh=False)


def test_if_missing_skips_when_atlas_exists(monkeypatch, tmp_path):
    h = "testhash123"
    atlas_path = tmp_path / ".claude" / "cartographer" / "projects" / h / "atlas.json"
    atlas_path.parent.mkdir(parents=True)
    atlas_path.write_text("{}")
    mtime_before = atlas_path.stat().st_mtime

    monkeypatch.setattr(run, "project_hash", lambda _: (h, None, None))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    calls = []
    monkeypatch.setattr(run, "_detect_layers", lambda p: calls.append(p) or [])

    run.main(_args=_make_args(if_missing=True), _home=tmp_path)

    assert calls == [], "_detect_layers must not be called when atlas exists and --if-missing is set"
    assert atlas_path.stat().st_mtime == mtime_before


def test_if_missing_runs_when_atlas_absent(monkeypatch, tmp_path):
    h = "testhash456"
    monkeypatch.setattr(run, "project_hash", lambda _: (h, None, None))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    calls = []
    monkeypatch.setattr(run, "_detect_layers", lambda p: calls.append(p) or [])
    monkeypatch.setattr(run, "_extract_symbols", lambda layers: [])
    monkeypatch.setattr(run, "_compute_naming_conventions", lambda symbols: {})
    monkeypatch.setattr(run, "_detect_error_handling", lambda layers: {})
    monkeypatch.setattr(run, "_detect_forbidden_imports", lambda layers: [])
    monkeypatch.setattr(run, "_detect_dependency_edges", lambda layers, p: [])
    monkeypatch.setattr(run, "_write_atlas_json", lambda *a, **kw: None)
    monkeypatch.setattr(run, "_write_atlas_md", lambda *a, **kw: None)

    run.main(_args=_make_args(if_missing=True), _home=tmp_path)

    assert calls != [], "_detect_layers must be called when atlas is absent"


def test_no_if_missing_always_runs(monkeypatch, tmp_path):
    h = "testhash789"
    atlas_path = tmp_path / ".claude" / "cartographer" / "projects" / h / "atlas.json"
    atlas_path.parent.mkdir(parents=True)
    atlas_path.write_text("{}")

    monkeypatch.setattr(run, "project_hash", lambda _: (h, None, None))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    calls = []
    monkeypatch.setattr(run, "_detect_layers", lambda p: calls.append(p) or [])
    monkeypatch.setattr(run, "_extract_symbols", lambda layers: [])
    monkeypatch.setattr(run, "_compute_naming_conventions", lambda symbols: {})
    monkeypatch.setattr(run, "_detect_error_handling", lambda layers: {})
    monkeypatch.setattr(run, "_detect_forbidden_imports", lambda layers: [])
    monkeypatch.setattr(run, "_detect_dependency_edges", lambda layers, p: [])
    monkeypatch.setattr(run, "_write_atlas_json", lambda *a, **kw: None)
    monkeypatch.setattr(run, "_write_atlas_md", lambda *a, **kw: None)

    run.main(_args=_make_args(if_missing=False), _home=tmp_path)

    assert calls != [], "_detect_layers must be called when --if-missing is False even if atlas exists"
