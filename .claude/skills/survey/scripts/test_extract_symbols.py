import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "survey" / "scripts"))

from run import _extract_symbols


def _layer(tmp_path: Path, name: str, files: list[Path]) -> dict:
    return {"name": name, "path": str(tmp_path / name), "files": [str(f) for f in files]}


def test_extracts_class_from_py_file(tmp_path: Path) -> None:
    src = tmp_path / "api" / "models.py"
    src.parent.mkdir(parents=True)
    src.write_text("class Foo:\n    pass\n")
    layers = [_layer(tmp_path, "api", [src])]
    result = _extract_symbols(layers)
    assert any(
        e["kind"] == "class" and e["name"] == "Foo" and e["layer"] == "api"
        for e in result
    )


def test_extracts_function_from_py_file(tmp_path: Path) -> None:
    src = tmp_path / "lib" / "utils.py"
    src.parent.mkdir(parents=True)
    src.write_text("def my_func():\n    pass\n")
    layers = [_layer(tmp_path, "lib", [src])]
    result = _extract_symbols(layers)
    assert any(
        e["kind"] == "function" and e["name"] == "my_func" and e["layer"] == "lib"
        for e in result
    )


def test_skips_non_py_files(tmp_path: Path) -> None:
    js_file = tmp_path / "api" / "app.js"
    js_file.parent.mkdir(parents=True)
    js_file.write_text("function hello() { return 1; }\n")
    layers = [_layer(tmp_path, "api", [js_file])]
    result = _extract_symbols(layers)
    assert all(e["file"] != str(js_file) for e in result)
    assert result == []


def test_caps_at_500_symbols(tmp_path: Path) -> None:
    layer_dir = tmp_path / "lib"
    layer_dir.mkdir()
    # Each file has 10 functions; 60 files = 600 symbols
    files = []
    for i in range(60):
        f = layer_dir / f"mod_{i}.py"
        f.write_text("\n".join(f"def func_{i}_{j}(): pass" for j in range(10)))
        files.append(f)
    layers = [_layer(tmp_path, "lib", files)]
    result = _extract_symbols(layers)
    assert len(result) == 500


def test_skips_unparseable_py(tmp_path: Path) -> None:
    bad = tmp_path / "api" / "broken.py"
    bad.parent.mkdir(parents=True)
    bad.write_text("def f(: pass\n")
    layers = [_layer(tmp_path, "api", [bad])]
    # Must not raise; must return empty list for that file
    result = _extract_symbols(layers)
    assert all(e["file"] != str(bad) for e in result)


def test_result_entry_has_required_keys(tmp_path: Path) -> None:
    src = tmp_path / "cli" / "main.py"
    src.parent.mkdir(parents=True)
    src.write_text("class Bar: pass\ndef run(): pass\n")
    layers = [_layer(tmp_path, "cli", [src])]
    result = _extract_symbols(layers)
    assert len(result) == 2
    for entry in result:
        assert set(entry.keys()) == {"file", "kind", "name", "layer"}
