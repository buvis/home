import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "survey" / "scripts"))

from run import _write_atlas_md

_BUDGET = 5120

_BASE_ATLAS = {
    "project_hash": "abc123",
    "generated_at": "2024-01-01T00:00:00+00:00",
    "layers": [],
    "naming_conventions": {},
    "error_handling": {},
    "forbidden_imports": [],
    "dependency_edges": [],
}


def _large_atlas() -> dict:
    symbols = [
        {"file": f"/path/to/file_{i}.py", "kind": "function", "name": f"function_{i}_with_long_name", "layer": "api"}
        for i in range(500)
    ]
    # Each import ~40 bytes; 200 imports = ~8KB for that section alone, pushing total well over 5KB
    forbidden = [f"some.deeply.nested.module.path.forbidden_import_{i}" for i in range(200)]
    return {**_BASE_ATLAS, "symbols": symbols, "forbidden_imports": forbidden}


def test_output_within_budget_for_large_atlas(tmp_path):
    md_path = tmp_path / "atlas.md"
    _write_atlas_md(md_path, _large_atlas())
    assert len(md_path.read_bytes()) <= _BUDGET


def test_truncation_comment_added_when_over_budget(tmp_path):
    md_path = tmp_path / "atlas.md"
    _write_atlas_md(md_path, _large_atlas())
    assert "<!-- truncated to 5KB budget -->" in md_path.read_text()


def test_small_atlas_not_truncated(tmp_path):
    md_path = tmp_path / "atlas.md"
    atlas = {**_BASE_ATLAS, "symbols": [
        {"file": f"mod_{i}.py", "kind": "function", "name": f"func_{i}", "layer": "api"}
        for i in range(3)
    ]}
    _write_atlas_md(md_path, atlas)
    assert "truncated" not in md_path.read_text()
