import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "survey" / "scripts"))

from run import _write_atlas_md

_MINIMAL_ATLAS = {
    "project_hash": "abc123",
    "generated_at": "2024-01-01T00:00:00+00:00",
    "layers": [],
    "symbols": [],
    "naming_conventions": {},
    "error_handling": {},
    "forbidden_imports": [],
    "dependency_edges": [],
}


def test_file_is_created(tmp_path):
    md_path = tmp_path / "atlas.md"
    _write_atlas_md(md_path, dict(_MINIMAL_ATLAS))
    assert md_path.exists()


def test_contains_title(tmp_path):
    md_path = tmp_path / "atlas.md"
    _write_atlas_md(md_path, dict(_MINIMAL_ATLAS))
    content = md_path.read_text()
    assert "# Atlas:" in content


def test_layers_table_present(tmp_path):
    md_path = tmp_path / "atlas.md"
    atlas = dict(_MINIMAL_ATLAS)
    atlas["layers"] = [{"name": "api", "files": ["api/views.py", "api/models.py"]}]
    atlas["naming_conventions"] = {"api": {"dominant": "snake_case"}}
    _write_atlas_md(md_path, atlas)
    content = md_path.read_text()
    assert "## Layers" in content
    assert "| Layer |" in content


def test_symbols_section_capped_at_20(tmp_path):
    md_path = tmp_path / "atlas.md"
    atlas = dict(_MINIMAL_ATLAS)
    atlas["symbols"] = [
        {"file": f"mod_{i}.py", "kind": "function", "name": f"func_{i}"}
        for i in range(25)
    ]
    _write_atlas_md(md_path, atlas)
    content = md_path.read_text()
    lines = content.splitlines()
    in_symbols = False
    row_count = 0
    for line in lines:
        if line.startswith("## Symbols"):
            in_symbols = True
            continue
        if in_symbols and line.startswith("## "):
            break
        if in_symbols and line.startswith("|") and "---" not in line and "File" not in line:
            row_count += 1
    assert row_count <= 20


def test_skips_forbidden_imports_when_empty(tmp_path):
    md_path = tmp_path / "atlas.md"
    _write_atlas_md(md_path, dict(_MINIMAL_ATLAS))
    content = md_path.read_text()
    assert "## Forbidden Imports" not in content


def test_parent_dirs_created(tmp_path):
    md_path = tmp_path / "deep" / "nested" / "dir" / "atlas.md"
    _write_atlas_md(md_path, dict(_MINIMAL_ATLAS))
    assert md_path.exists()
