import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "survey" / "scripts"))

from run import _detect_error_handling


def _make_layer(tmp_path: Path, name: str, filename: str, source: str) -> tuple[dict, Path]:
    layer_dir = tmp_path / name
    layer_dir.mkdir()
    f = layer_dir / filename
    f.write_text(source)
    return {"name": name, "path": str(layer_dir), "files": [str(f)]}, f


def test_counts_try_except(tmp_path: Path) -> None:
    layer, _ = _make_layer(tmp_path, "hooks", "example.py", "try:\n    pass\nexcept Exception:\n    pass\n")
    result = _detect_error_handling([layer])
    assert result["hooks"]["try_except"] == 1


def test_counts_raises(tmp_path: Path) -> None:
    layer, _ = _make_layer(tmp_path, "hooks", "example.py", "raise ValueError('oops')\n")
    result = _detect_error_handling([layer])
    assert result["hooks"]["raises"] == 1


def test_dominant_exceptions_when_raises_gt_zero(tmp_path: Path) -> None:
    layer, _ = _make_layer(tmp_path, "hooks", "example.py", "raise ValueError('oops')\n")
    result = _detect_error_handling([layer])
    assert result["hooks"]["dominant_style"] == "exceptions"


def test_dominant_unknown_when_no_signals(tmp_path: Path) -> None:
    layer, _ = _make_layer(tmp_path, "hooks", "example.py", "x = 1\n")
    result = _detect_error_handling([layer])
    assert result["hooks"]["dominant_style"] == "unknown"


def test_skips_unparseable_files(tmp_path: Path) -> None:
    layer, _ = _make_layer(tmp_path, "hooks", "example.py", "def (broken syntax:\n")
    try:
        result = _detect_error_handling([layer])
    except Exception as exc:
        raise AssertionError(f"_detect_error_handling raised unexpectedly: {exc}") from exc
