import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "survey" / "scripts"))
from run import _write_atlas_json


LAYERS = [{"name": "api", "path": "src/api"}]
SYMBOLS = [{"name": "MyClass", "kind": "class"}]
NAMING = {"functions": "snake_case", "classes": "PascalCase"}
ERROR_HANDLING = {"style": "explicit", "pattern": "raise"}
FORBIDDEN_IMPORTS = ["os.system", "subprocess"]
DEPENDENCY_EDGES = [{"from": "api", "to": "db"}]

REQUIRED_KEYS = {
    "generated_at",
    "project_hash",
    "layers",
    "symbols",
    "naming_conventions",
    "error_handling",
    "forbidden_imports",
    "dependency_edges",
}


def make_atlas_path(tmp_path: Path) -> Path:
    return tmp_path / "projects" / "testhash" / "atlas.json"


def write_and_load(tmp_path: Path) -> dict:
    atlas_path = make_atlas_path(tmp_path)
    _write_atlas_json(
        atlas_path,
        layers=LAYERS,
        symbols=SYMBOLS,
        naming=NAMING,
        error_handling=ERROR_HANDLING,
        forbidden_imports=FORBIDDEN_IMPORTS,
        dependency_edges=DEPENDENCY_EDGES,
    )
    return json.loads(atlas_path.read_text())


def test_written_file_is_valid_json(tmp_path):
    atlas_path = make_atlas_path(tmp_path)
    _write_atlas_json(
        atlas_path,
        layers=LAYERS,
        symbols=SYMBOLS,
        naming=NAMING,
        error_handling=ERROR_HANDLING,
        forbidden_imports=FORBIDDEN_IMPORTS,
        dependency_edges=DEPENDENCY_EDGES,
    )
    assert atlas_path.exists()
    data = json.loads(atlas_path.read_text())
    assert isinstance(data, dict)


def test_has_exactly_required_top_level_keys(tmp_path):
    data = write_and_load(tmp_path)
    assert set(data.keys()) == REQUIRED_KEYS


def test_generated_at_is_valid_iso8601(tmp_path):
    data = write_and_load(tmp_path)
    dt = datetime.fromisoformat(data["generated_at"])
    assert dt is not None


def test_layers_passthrough(tmp_path):
    data = write_and_load(tmp_path)
    assert data["layers"] == LAYERS


def test_naming_conventions_uses_naming_arg(tmp_path):
    data = write_and_load(tmp_path)
    assert data["naming_conventions"] == NAMING


def test_parent_dirs_created_when_missing(tmp_path):
    atlas_path = make_atlas_path(tmp_path)
    assert not atlas_path.parent.exists()
    _write_atlas_json(
        atlas_path,
        layers=LAYERS,
        symbols=SYMBOLS,
        naming=NAMING,
        error_handling=ERROR_HANDLING,
        forbidden_imports=FORBIDDEN_IMPORTS,
        dependency_edges=DEPENDENCY_EDGES,
    )
    assert atlas_path.exists()


def test_project_hash_is_non_empty_string(tmp_path):
    data = write_and_load(tmp_path)
    assert isinstance(data["project_hash"], str)
    assert len(data["project_hash"]) > 0
