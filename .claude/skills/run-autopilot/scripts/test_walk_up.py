"""Tests for _walk_up.py — the shared autopilot-dir walk-up helper."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).with_name("_walk_up.py")


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _make_autopilot_dir(root: Path) -> Path:
    autopilot = root / "dev" / "local" / "autopilot"
    autopilot.mkdir(parents=True)
    return autopilot


def test_bash_prints_resolved_dir(tmp_path: Path) -> None:
    autopilot = _make_autopilot_dir(tmp_path)
    result = _run(["--bash"], cwd=autopilot)
    assert result.returncode == 0
    assert Path(result.stdout.strip()) == autopilot.resolve()


def test_bash_exits_nonzero_when_no_autopilot_dir(tmp_path: Path) -> None:
    result = _run(["--bash"], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout.strip() == ""


def test_clear_cap_removes_marker(tmp_path: Path) -> None:
    autopilot = _make_autopilot_dir(tmp_path)
    marker = autopilot / ".cap-fired"
    marker.write_text("task-7")
    sub = autopilot / "nested"
    sub.mkdir()

    result = _run(["--clear-cap"], cwd=sub)

    assert result.returncode == 0
    assert not marker.exists()


def test_clear_cap_noop_when_marker_absent(tmp_path: Path) -> None:
    autopilot = _make_autopilot_dir(tmp_path)
    result = _run(["--clear-cap"], cwd=autopilot)
    assert result.returncode == 0
    assert not (autopilot / ".cap-fired").exists()


def test_clear_cap_noop_when_no_autopilot_dir(tmp_path: Path) -> None:
    result = _run(["--clear-cap"], cwd=tmp_path)
    assert result.returncode == 0


def test_clear_cap_leaves_other_files_untouched(tmp_path: Path) -> None:
    autopilot = _make_autopilot_dir(tmp_path)
    (autopilot / ".cap-fired").write_text("task-1")
    (autopilot / "signal").write_text("next")
    (autopilot / "state.json").write_text("{}")

    _run(["--clear-cap"], cwd=autopilot)

    assert not (autopilot / ".cap-fired").exists()
    assert (autopilot / "signal").exists()
    assert (autopilot / "state.json").exists()


def test_unknown_arg_exits_2(tmp_path: Path) -> None:
    result = _run(["--bogus"], cwd=tmp_path)
    assert result.returncode == 2
    assert "usage:" in result.stderr
