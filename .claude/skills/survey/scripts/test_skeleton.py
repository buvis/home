"""Tests for run.py argparse interface and stub functions.

run.py does NOT exist yet — these tests are expected to fail until it is created.
"""
import importlib
import subprocess
import sys
from pathlib import Path

RUN_PY = Path.home() / ".claude" / "skills" / "survey" / "scripts" / "run.py"

STUB_FUNCTIONS = [
    "_detect_layers",
    "_write_atlas_json",
    "_extract_symbols",
    "_compute_naming_conventions",
    "_detect_error_handling",
    "_write_atlas_md",
    "_detect_forbidden_imports",
    "_detect_dependency_edges",
]


def test_accepts_no_flags():
    result = subprocess.run([sys.executable, str(RUN_PY)], capture_output=True)
    assert result.returncode == 0


def test_accepts_refresh_flag():
    result = subprocess.run([sys.executable, str(RUN_PY), "--refresh"], capture_output=True)
    assert result.returncode == 0


def test_accepts_if_missing_flag():
    result = subprocess.run([sys.executable, str(RUN_PY), "--if-missing"], capture_output=True)
    assert result.returncode == 0


def test_rejects_unknown_flag():
    result = subprocess.run(
        [sys.executable, str(RUN_PY), "--unknown-flag"], capture_output=True
    )
    assert result.returncode != 0


def test_exposes_stub_functions():
    sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
    sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "survey" / "scripts"))
    module = importlib.import_module("run")
    for name in STUB_FUNCTIONS:
        fn = getattr(module, name, None)
        assert callable(fn), f"{name} is not callable"
