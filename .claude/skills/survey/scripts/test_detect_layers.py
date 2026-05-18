import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "survey" / "scripts"))

from run import _detect_layers


def test_returns_nonempty_list_for_dir_with_subdirs(tmp_path):
    (tmp_path / "api").mkdir()
    result = _detect_layers(tmp_path)
    assert len(result) >= 1


def test_entry_has_exactly_name_path_files_keys(tmp_path):
    (tmp_path / "api").mkdir()
    result = _detect_layers(tmp_path)
    for entry in result:
        assert set(entry.keys()) == {"name", "path", "files"}


def test_classifies_hooks_dir(tmp_path):
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    result = _detect_layers(tmp_path)
    names = [e["name"] for e in result]
    assert "hooks" in names


def test_classifies_lib_dir(tmp_path):
    (tmp_path / "lib").mkdir()
    result = _detect_layers(tmp_path)
    names = [e["name"] for e in result]
    assert "lib" in names


def test_classifies_libs_dir_as_lib(tmp_path):
    (tmp_path / "libs").mkdir()
    result = _detect_layers(tmp_path)
    names = [e["name"] for e in result]
    assert "lib" in names


def test_unknown_dir_name_maps_to_other(tmp_path):
    (tmp_path / "foobar").mkdir()
    result = _detect_layers(tmp_path)
    names = [e["name"] for e in result]
    assert "other" in names


def test_caps_files_at_50(tmp_path):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    for i in range(60):
        (scripts_dir / f"file_{i}.py").write_text("")
    result = _detect_layers(tmp_path)
    entry = next(e for e in result if e["name"] == "scripts")
    assert len(entry["files"]) == 50


def test_excludes_pycache_paths(tmp_path):
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "real.py").write_text("")
    cache_dir = hooks_dir / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "foo.pyc").write_text("")
    result = _detect_layers(tmp_path)
    entry = next(e for e in result if e["name"] == "hooks")
    assert all("__pycache__" not in f for f in entry["files"])


def test_root_entry_when_no_subdirs(tmp_path):
    (tmp_path / "file.py").write_text("")
    result = _detect_layers(tmp_path)
    assert len(result) == 1
    assert result[0]["name"] == "root"
    assert result[0]["path"] == str(tmp_path)
    assert any("file.py" in f for f in result[0]["files"])
