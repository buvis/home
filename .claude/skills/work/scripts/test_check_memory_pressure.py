"""Tests for check_memory_pressure.py — macOS memory pressure headroom check."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).with_name("check_memory_pressure.py")
_SPEC = importlib.util.spec_from_file_location("check_memory_pressure", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
check_memory_pressure = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_memory_pressure)


SYSCTL_KEY = "kern.memorystatus_vm_pressure_level"


def _patch_sysctl_output(monkeypatch: pytest.MonkeyPatch, stdout: str) -> None:
    def _fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(check_memory_pressure.subprocess, "run", _fake_run)


def _patch_sysctl_raises(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    def _fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise exc

    monkeypatch.setattr(check_memory_pressure.subprocess, "run", _fake_run)


# --- ok / pressure verdicts ---------------------------------------------------


def test_exits_ok_when_level_at_or_below_max(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_sysctl_output(monkeypatch, "1\n")

    exit_code = check_memory_pressure.main([])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.rstrip("\n") == "ok: pressure level 1 <= 1"


@pytest.mark.parametrize("level", [2, 4])
def test_exits_pressure_when_level_above_max(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], level: int
) -> None:
    _patch_sysctl_output(monkeypatch, f"{level}\n")

    exit_code = check_memory_pressure.main([])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.out.rstrip("\n") == f"pressure: level {level} > 1"


def test_boundary_level_equal_to_max_is_ok(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Pins <=, not <: level equal to --max-level must still be OK.
    _patch_sysctl_output(monkeypatch, "2\n")

    exit_code = check_memory_pressure.main(["--max-level", "2"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.rstrip("\n") == "ok: pressure level 2 <= 2"


# --- unknown / exit-2 paths ---------------------------------------------------


def test_exits_unknown_when_sysctl_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_sysctl_raises(monkeypatch, FileNotFoundError("sysctl: not found"))

    exit_code = check_memory_pressure.main([])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert captured.out.startswith("unknown:")
    # The sysctl key must be named so a broken probe is diagnosable from
    # stdout alone.
    assert SYSCTL_KEY in captured.out


@pytest.mark.parametrize("bad_output", ["", "foo"])
def test_exits_unknown_when_sysctl_output_unparseable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bad_output: str
) -> None:
    _patch_sysctl_output(monkeypatch, bad_output)

    exit_code = check_memory_pressure.main([])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert captured.out.startswith("unknown:")


def test_unexpected_exception_exits_unknown(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Collision guard: an unexpected exception type must map to exit 2, never
    # let a traceback fall through to Python's default exit 1 (a caller reads
    # exit 1 as a genuine pressure verdict).
    _patch_sysctl_raises(monkeypatch, RuntimeError("boom"))

    exit_code = check_memory_pressure.main([])

    assert exit_code == 2
    assert exit_code != 1
    captured = capsys.readouterr()
    assert captured.out.startswith("unknown:")


# --- stdout shape ---------------------------------------------------


def test_stdout_is_exactly_one_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_sysctl_output(monkeypatch, "1\n")
    check_memory_pressure.main([])
    ok_out = capsys.readouterr().out
    assert len(ok_out.splitlines()) == 1

    _patch_sysctl_output(monkeypatch, "2\n")
    check_memory_pressure.main([])
    pressure_out = capsys.readouterr().out
    assert len(pressure_out.splitlines()) == 1

    _patch_sysctl_raises(monkeypatch, FileNotFoundError("sysctl: not found"))
    check_memory_pressure.main([])
    unknown_out = capsys.readouterr().out
    assert len(unknown_out.splitlines()) == 1
