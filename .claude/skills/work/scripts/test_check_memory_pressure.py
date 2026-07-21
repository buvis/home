"""Tests for check_memory_pressure.py — macOS memory pressure notification level check."""

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


# --- timeout / nonzero-exit / bad-argv paths ----------------------------------


def _patch_sysctl_nonzero_exit(monkeypatch: pytest.MonkeyPatch, stderr: str) -> None:
    def _fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr)

    monkeypatch.setattr(check_memory_pressure.subprocess, "run", _fake_run)


def test_exits_unknown_when_sysctl_times_out(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A wedged sysctl must not hang the caller: the probe runs precisely when
    # the host is short on RAM, so the subprocess call must be bounded by a
    # timeout, and the timeout firing must be legible as the cause on stdout.
    _patch_sysctl_raises(monkeypatch, subprocess.TimeoutExpired(cmd=SYSCTL_KEY, timeout=5))

    exit_code = check_memory_pressure.main([])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert captured.out.startswith("unknown:")
    reason = captured.out.lower()
    assert "timeout" in reason or "timed out" in reason
    assert len(captured.out.splitlines()) == 1


def test_sysctl_call_is_bounded_by_a_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # R-A, call-site half: the subprocess.run call itself must carry a
    # timeout kwarg. A wedged sysctl can't be simulated behaviourally in a
    # unit test without hanging the suite, so this binds the call's kwargs
    # directly. Deliberately not pinning a specific value: a legitimate
    # tuning change (e.g. 5s -> 10s) must not fail this test, only the
    # absence of a positive bound should.
    recorded_kwargs: dict[str, object] = {}

    def _fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        recorded_kwargs.update(kwargs)
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="1\n", stderr="")

    monkeypatch.setattr(check_memory_pressure.subprocess, "run", _fake_run)

    exit_code = check_memory_pressure.main([])

    assert exit_code == 0
    assert "timeout" in recorded_kwargs
    timeout_value = recorded_kwargs["timeout"]
    assert isinstance(timeout_value, (int, float))
    assert timeout_value > 0


def test_exits_unknown_with_key_and_stderr_when_sysctl_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A non-zero sysctl exit must not surface as an int-parse complaint: the
    # reason line must name the sysctl key and carry sysctl's own stderr, so a
    # renamed key or a non-macOS host is diagnosable from the attempt log
    # alone.
    stderr_text = "sysctl: unknown oid 'kern.memorystatus_vm_pressure_level'"
    _patch_sysctl_nonzero_exit(monkeypatch, stderr_text)

    exit_code = check_memory_pressure.main([])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert captured.out.startswith("unknown:")
    assert SYSCTL_KEY in captured.out
    assert stderr_text in captured.out
    assert len(captured.out.splitlines()) == 1


def test_exits_unknown_on_unparseable_max_level_argument(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # An unparseable --max-level must still honour the one-line stdout
    # contract, not exit with argparse's own status and stderr-only output
    # (which the caller cannot record as a reason).
    exit_code = check_memory_pressure.main(["--max-level", "abc"])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert captured.out.startswith("unknown:")
    assert len(captured.out.splitlines()) == 1


# --- embedded-newline and bad-argv stdout contract ----------------------------


def test_stdout_stays_one_line_when_sysctl_stderr_has_embedded_newlines(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A multi-line sysctl stderr (a real wrapped error message) must not
    # multiply the caller's one-line stdout contract: the routing step reads
    # exactly one line as the reason.
    stderr_text = "sysctl: unknown oid\nkern.memorystatus_vm_pressure_level\nnot found"
    _patch_sysctl_nonzero_exit(monkeypatch, stderr_text)

    exit_code = check_memory_pressure.main([])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    assert captured.out.startswith("unknown:")
    assert SYSCTL_KEY in captured.out


def test_stdout_stays_one_line_when_sysctl_exception_message_has_embedded_newlines(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Same one-line contract when the failure surfaces as a raised exception
    # (not a nonzero exit) whose own message spans multiple lines.
    _patch_sysctl_raises(monkeypatch, OSError("permission denied\nretry failed\ngiving up"))

    exit_code = check_memory_pressure.main([])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    assert captured.out.startswith("unknown:")
    assert SYSCTL_KEY in captured.out


@pytest.mark.parametrize("argv", [["--max-level", "abc"], ["--not-a-real-flag"]])
def test_unknown_reason_is_non_empty_after_prefix_for_bad_argv(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    # A bare "unknown:" with nothing after it tells the caller nothing: both
    # an unparseable --max-level and an unrecognised flag must still leave a
    # non-empty reason after the prefix, on a single line.
    exit_code = check_memory_pressure.main(argv)

    assert exit_code == 2
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    assert captured.out.startswith("unknown:")
    reason = captured.out[len("unknown:") :].strip()
    assert reason != ""


# --- --help path ---------------------------------------------------


def test_help_flag_exits_successfully(capsys: pytest.CaptureFixture[str]) -> None:
    # --help is success, not an argument error: it must exit 0 and print
    # argparse's usage text, never fall into the unknown: exit-2 path that
    # every other bad-argv case takes.
    with pytest.raises(SystemExit) as exc_info:
        check_memory_pressure.main(["--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "usage" in captured.out.lower()
    assert "--max-level" in captured.out
    assert not captured.out.startswith("unknown:")


# --- review gap coverage: newline-safety and the SystemExit branch -----------


def test_stdout_stays_one_line_when_bad_argv_contains_embedded_newline(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # An unrecognised argument containing a newline must not multiply the
    # caller's one-line stdout contract: argument-parsing errors can echo the
    # offending text verbatim, so a newline embedded in argv must not survive
    # into stdout.
    exit_code = check_memory_pressure.main(["--bad-flag\nSECOND-LINE"])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    assert captured.out.startswith("unknown:")
    reason = captured.out[len("unknown:") :].strip()
    assert reason != ""


def test_exits_unknown_when_argument_parsing_raises_system_exit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # On Python versions where argument parsing terminates via SystemExit
    # rather than raising directly, that branch must still honour the
    # one-line exit-2 contract, not let SystemExit propagate past main().
    def _raise_system_exit(argv: list[str] | None) -> int:
        raise SystemExit(2)

    monkeypatch.setattr(check_memory_pressure, "parse_args", _raise_system_exit)

    exit_code = check_memory_pressure.main([])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    assert captured.out.startswith("unknown:")
    reason = captured.out[len("unknown:") :].strip()
    assert reason != ""
