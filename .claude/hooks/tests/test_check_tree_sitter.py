"""Tests for ~/.claude/cartographer/scripts/check-tree-sitter.py."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path.home() / ".claude" / "cartographer" / "scripts" / "check-tree-sitter.py"


def test_script_exists_and_is_executable() -> None:
    # The script is committed with mode 100755 (verified in the buvis bare
    # repo). There is no install-time chmod path; if this assertion ever
    # fails on a fresh clone or after a re-add, restore the +x bit on
    # `~/.claude/cartographer/scripts/check-tree-sitter.py` and commit.
    assert SCRIPT.is_file(), f"missing: {SCRIPT}"
    assert os.access(SCRIPT, os.X_OK), f"not executable: {SCRIPT}"


def test_hit_path_exits_zero_when_package_importable() -> None:
    """If tree_sitter_language_pack is installed, the script must exit 0."""
    pytest.importorskip("tree_sitter_language_pack")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True, text=True, timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout.lower()


def test_miss_path_exits_one_with_remediation(tmp_path: Path) -> None:
    """Force the package to be missing by injecting a shim that raises ImportError."""
    shim = tmp_path / "tree_sitter_language_pack.py"
    shim.write_text('raise ImportError("forced for test")\n', encoding="utf-8")

    env = dict(os.environ)
    # Prepend the shim dir so the subprocess imports our broken module first.
    env["PYTHONPATH"] = str(tmp_path) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True, text=True, timeout=10, env=env,
    )
    assert proc.returncode == 1
    combined = proc.stderr + proc.stdout
    assert "pip install tree-sitter-language-pack" in combined
    assert "pyenv" in combined.lower()


@pytest.mark.parametrize(
    "shim_body",
    [
        'raise SyntaxError("forced broken wheel")\n',
        'raise OSError("forced dylib failure")\n',
        'raise RuntimeError("forced post-install failure")\n',
    ],
)
def test_miss_path_handles_non_import_errors(tmp_path: Path, shim_body: str) -> None:
    """Cycle 3 fix: any import-time failure (not just ImportError) must exit 1 with remediation.

    A broken wheel can raise SyntaxError (corrupt .py), OSError (missing dylib
    on macOS), or other non-ImportError errors at import time. The script must
    print the pip remediation in all of these cases, never a raw traceback.
    """
    shim = tmp_path / "tree_sitter_language_pack.py"
    shim.write_text(shim_body, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True, text=True, timeout=10, env=env,
    )
    assert proc.returncode == 1, f"expected exit 1, got {proc.returncode}: {proc.stderr}"
    combined = proc.stderr + proc.stdout
    assert "pip install tree-sitter-language-pack" in combined
    # Must not be a raw uncaught traceback.
    assert "Traceback (most recent call last)" not in proc.stderr
