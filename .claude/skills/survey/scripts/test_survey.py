import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "survey" / "scripts"))
from run import main


def _run_survey(tmp_path: Path, monkeypatch, refresh: bool = False) -> Path:
    monkeypatch.chdir(tmp_path)
    main(argparse.Namespace(refresh=refresh, if_missing=False), _home=tmp_path)
    atlas_paths = list(tmp_path.glob(".claude/cartographer/projects/*/atlas.json"))
    assert atlas_paths, "main() did not create atlas.json"
    return atlas_paths[0]


def test_main_creates_atlas_json(tmp_path, monkeypatch):
    atlas_path = _run_survey(tmp_path, monkeypatch)
    assert atlas_path.exists()


def test_atlas_json_has_required_keys(tmp_path, monkeypatch):
    atlas_path = _run_survey(tmp_path, monkeypatch)
    data = json.loads(atlas_path.read_text())
    required = {"generated_at", "project_hash", "layers", "symbols",
                "naming_conventions", "error_handling", "forbidden_imports", "dependency_edges"}
    assert required <= set(data.keys())


def test_atlas_md_created_alongside_json(tmp_path, monkeypatch):
    atlas_path = _run_survey(tmp_path, monkeypatch)
    md_path = atlas_path.parent / "atlas.md"
    assert md_path.exists()


def test_atlas_md_within_5kb_budget(tmp_path, monkeypatch):
    atlas_path = _run_survey(tmp_path, monkeypatch)
    md_path = atlas_path.parent / "atlas.md"
    assert len(md_path.read_bytes()) <= 5120


def test_refresh_clears_staleness_flag_end_to_end(tmp_path, monkeypatch):
    atlas_path = _run_survey(tmp_path, monkeypatch)
    flag = atlas_path.parent / "staleness.flag"
    flag.write_text("stale")
    main(argparse.Namespace(refresh=True, if_missing=False), _home=tmp_path)
    assert not flag.exists()
