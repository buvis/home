"""Tests for cli/runner.py (PRD 00106).

A stub runner binary stands in for `claude -p`; every test asserts an
observable the wrapper's pipeline guaranteed: the exact launch argv, the
command-scoped env, devnull stdin, stderr folded into the tee'd log,
per-session truncation, presenter feed, and the cap TERM path.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

from cli.runner import LAUNCH_ENV, build_argv, make_presenter, spawn


class _Collector:
    def __init__(self) -> None:
        self.lines: list[bytes] = []
        self.closed = False

    def write(self, line: bytes) -> None:
        self.lines.append(line)

    def close(self) -> None:
        self.closed = True


def _stub_runner(tmp_path: Path, body: str) -> str:
    """An executable python stub whose argv shape matches claude's."""
    path = tmp_path / "stub-runner"
    path.write_text(f"#!{sys.executable}\nimport os, sys\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def _ap_dir(tmp_path: Path) -> Path:
    ap = tmp_path / "dev/local/autopilot"
    ap.mkdir(parents=True, exist_ok=True)
    return ap


def test_build_argv_matches_the_wrapper_launch_line():
    argv = build_argv("m1", "xhigh", "fb1")
    assert argv == [
        "claude",
        "-p",
        "--permission-mode",
        "auto",
        "--model",
        "m1",
        "--effort",
        "xhigh",
        "--fallback-model",
        "fb1",
        "--output-format",
        "stream-json",
        "--verbose",
        "/run-autopilot",
    ]


def test_build_argv_skips_fallback_equal_to_launch_model():
    argv = build_argv("m1", "xhigh", "m1")
    assert "--fallback-model" not in argv


def test_build_argv_injects_an_alternate_runner_without_driver_change():
    assert build_argv("m", "low", None, runner_bin="codex-run")[0] == "codex-run"


def test_spawn_tees_raw_output_and_feeds_the_presenter(tmp_path):
    stub = _stub_runner(
        tmp_path,
        'print(\'{"type":"result","total_cost_usd":0.01}\')\nprint("second line")',
    )
    collector = _Collector()
    ap = _ap_dir(tmp_path)
    result = spawn(
        "m",
        "low",
        cap_secs=30,
        autopilot_dir=ap,
        env={},
        runner_bin=stub,
        presenter=collector,
    )
    assert result.returncode == 0
    assert result.cap_fired is False
    raw = result.log_path.read_bytes()
    assert b'{"type":"result","total_cost_usd":0.01}\n' in raw
    assert b"second line\n" in raw
    assert b"".join(collector.lines) == raw
    assert collector.closed is True


def test_spawn_sets_the_command_scoped_unattended_env(tmp_path):
    stub = _stub_runner(
        tmp_path,
        "import json\n"
        "print(json.dumps({k: os.environ.get(k) for k in "
        "('WARDEN_UNATTENDED', 'CLAUDE_UNATTENDED', "
        "'CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS')}))",
    )
    ap = _ap_dir(tmp_path)
    result = spawn(
        "m",
        "low",
        cap_secs=30,
        autopilot_dir=ap,
        env={"PATH": os.environ["PATH"]},
        runner_bin=stub,
        presenter=_Collector(),
    )
    seen = json.loads(result.log_path.read_text())
    assert seen == {key: value for key, value in LAUNCH_ENV.items()}


def test_spawn_gives_the_child_devnull_stdin(tmp_path):
    stub = _stub_runner(tmp_path, "print(repr(sys.stdin.read()))")
    ap = _ap_dir(tmp_path)
    result = spawn(
        "m",
        "low",
        cap_secs=30,
        autopilot_dir=ap,
        env={},
        runner_bin=stub,
        presenter=_Collector(),
    )
    assert result.log_path.read_text().strip() == "''"


def test_spawn_folds_stderr_into_the_log(tmp_path):
    stub = _stub_runner(
        tmp_path,
        'print("to stdout")\nprint("to stderr", file=sys.stderr)',
    )
    ap = _ap_dir(tmp_path)
    result = spawn(
        "m",
        "low",
        cap_secs=30,
        autopilot_dir=ap,
        env={},
        runner_bin=stub,
        presenter=_Collector(),
    )
    text = result.log_path.read_text()
    assert "to stdout" in text
    assert "to stderr" in text


def test_spawn_truncates_the_previous_sessions_log(tmp_path):
    stub = _stub_runner(tmp_path, 'print("fresh")')
    ap = _ap_dir(tmp_path)
    (ap / "last-session.log").write_text("stale content from last session\n")
    result = spawn(
        "m",
        "low",
        cap_secs=30,
        autopilot_dir=ap,
        env={},
        runner_bin=stub,
        presenter=_Collector(),
    )
    assert result.log_path.read_text() == "fresh\n"


def test_spawn_caps_a_hung_session(tmp_path, capsys):
    stub = _stub_runner(
        tmp_path,
        'import time\nprint("started", flush=True)\ntime.sleep(300)',
    )
    ap = _ap_dir(tmp_path)
    # The cap must comfortably outlast interpreter startup, or the stub is
    # TERM'd before its "started" line ever reaches the pipe (measured
    # flaky at 0.3s under parallel suite load).
    result = spawn(
        "m",
        "low",
        cap_secs=2,
        autopilot_dir=ap,
        env={},
        runner_bin=stub,
        grace_secs=5,
        presenter=_Collector(),
    )
    assert result.cap_fired is True
    assert result.returncode != 0
    assert "started" in result.log_path.read_text()
    assert "wall-clock cap" in capsys.readouterr().err


def test_make_presenter_discards_in_tracon_child_mode(capsys):
    presenter = make_presenter({"_AUTOPILOT_TRACON_CHILD": "1"})
    presenter.write(b"never shown\n")
    presenter.close()
    assert capsys.readouterr().out == ""
