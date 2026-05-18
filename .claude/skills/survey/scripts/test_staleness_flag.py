import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "survey" / "scripts"))
from run import main


def _atlas_dir(tmp_path: Path) -> Path:
    dirs = list(tmp_path.glob(".claude/cartographer/projects/*/"))
    assert dirs, "main() did not create atlas dir"
    return dirs[0]


def _run_once(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.chdir(tmp_path)
    main(argparse.Namespace(refresh=False, if_missing=False), _home=tmp_path)
    return _atlas_dir(tmp_path)


def test_refresh_clears_staleness_flag(tmp_path, monkeypatch):
    atlas_dir = _run_once(tmp_path, monkeypatch)
    flag = atlas_dir / "staleness.flag"
    flag.write_text("stale")
    main(argparse.Namespace(refresh=True, if_missing=False), _home=tmp_path)
    assert not flag.exists()


def test_no_refresh_preserves_staleness_flag(tmp_path, monkeypatch):
    atlas_dir = _run_once(tmp_path, monkeypatch)
    flag = atlas_dir / "staleness.flag"
    flag.write_text("stale")
    main(argparse.Namespace(refresh=False, if_missing=False), _home=tmp_path)
    assert flag.exists()


def test_refresh_without_flag_does_not_raise(tmp_path, monkeypatch):
    _run_once(tmp_path, monkeypatch)
    main(argparse.Namespace(refresh=True, if_missing=False), _home=tmp_path)
