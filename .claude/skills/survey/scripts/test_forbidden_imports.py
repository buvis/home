import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "survey" / "scripts"))
from run import _detect_forbidden_imports


def test_empty_layers_returns_empty_list():
    assert _detect_forbidden_imports([]) == []


def test_detects_subprocess_import(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("import subprocess\n")
    layer = {"name": "hooks", "path": str(tmp_path), "files": [str(f)]}
    result = _detect_forbidden_imports([layer])
    assert any(r["module"] == "subprocess" for r in result)


def test_clean_file_not_detected(tmp_path):
    f = tmp_path / "clean.py"
    f.write_text("import os\nimport sys\n")
    layer = {"name": "api", "path": str(tmp_path), "files": [str(f)]}
    assert _detect_forbidden_imports([layer]) == []


def test_forbidden_entry_has_module_file_layer_keys(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("import subprocess\n")
    layer = {"name": "hooks", "path": str(tmp_path), "files": [str(f)]}
    result = _detect_forbidden_imports([layer])
    assert result
    assert {"module", "file", "layer"} <= set(result[0].keys())
