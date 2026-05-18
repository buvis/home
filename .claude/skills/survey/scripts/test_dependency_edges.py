import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "survey" / "scripts"))
from run import _detect_dependency_edges


def _make_layer(tmp_path: Path, name: str, source: str) -> dict:
    d = tmp_path / name
    d.mkdir()
    f = d / "mod.py"
    f.write_text(source)
    return {"name": name, "path": str(d), "files": [str(f)]}


def test_empty_layers_returns_empty_list(tmp_path):
    assert _detect_dependency_edges([], tmp_path) == []


def test_cross_layer_import_produces_edge(tmp_path):
    api_layer = _make_layer(tmp_path, "api", "")
    cli_layer = _make_layer(tmp_path, "cli", "from api import something\n")
    result = _detect_dependency_edges([api_layer, cli_layer], tmp_path)
    assert any(e["from_layer"] == "cli" and e["to_layer"] == "api" for e in result)


def test_same_layer_import_not_an_edge(tmp_path):
    cli_layer = _make_layer(tmp_path, "cli", "from cli import helper\n")
    result = _detect_dependency_edges([cli_layer], tmp_path)
    assert result == []


def test_edge_entry_has_required_keys(tmp_path):
    api_layer = _make_layer(tmp_path, "api", "")
    cli_layer = _make_layer(tmp_path, "cli", "from api import x\n")
    result = _detect_dependency_edges([api_layer, cli_layer], tmp_path)
    assert result
    assert {"from_layer", "to_layer", "count"} <= set(result[0].keys())
