"""Tests for await_reviewer_outputs.py — the headless review Watcher helper.

Regression guard for the 2026-07-12 loop death: headless `claude -p` killed
the codex reviewer (background Bash) at turn end because no live subagent
held the session open. The Watcher subagent re-runs this script while it
prints WAITING; these tests bind the DONE/WAITING contract.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = Path(__file__).with_name("await_reviewer_outputs.py")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def _backdate(path: Path, secs: float) -> None:
    past = time.time() - secs
    os.utime(path, (past, past))


def test_all_complete_prints_done(tmp_path: Path) -> None:
    f = tmp_path / "bob-output.txt"
    f.write_text("R1: pass\n")
    _backdate(f, 60)
    result = _run("--budget", "1", "--stable", "30", str(f))
    assert result.returncode == 0
    assert result.stdout.strip().splitlines()[-1] == "DONE"
    assert f"done\t{f}" in result.stdout


def test_missing_file_prints_waiting(tmp_path: Path) -> None:
    missing = tmp_path / "never-written.txt"
    result = _run("--budget", "1", "--poll", "1", str(missing))
    assert result.returncode == 0
    assert result.stdout.strip().splitlines()[-1] == "WAITING"
    assert f"pending\t{missing}" in result.stdout


def test_fresh_mtime_counts_as_pending(tmp_path: Path) -> None:
    # A file still being written (mtime inside the quiet period) is not done.
    f = tmp_path / "carl-output.txt"
    f.write_text("partial")
    result = _run("--budget", "1", "--poll", "1", "--stable", "30", str(f))
    assert result.stdout.strip().splitlines()[-1] == "WAITING"


def test_empty_file_counts_as_pending(tmp_path: Path) -> None:
    f = tmp_path / "quinn-output.txt"
    f.touch()
    _backdate(f, 60)
    result = _run("--budget", "1", "--poll", "1", str(f))
    assert result.stdout.strip().splitlines()[-1] == "WAITING"


def test_mixed_files_reports_each_and_waits(tmp_path: Path) -> None:
    done = tmp_path / "carl-output.txt"
    done.write_text("clean\n")
    _backdate(done, 60)
    pending = tmp_path / "bob-output.txt"
    result = _run("--budget", "1", "--poll", "1", str(done), str(pending))
    assert f"done\t{done}" in result.stdout
    assert f"pending\t{pending}" in result.stdout
    assert result.stdout.strip().splitlines()[-1] == "WAITING"


def test_completes_within_budget_once_file_lands(tmp_path: Path) -> None:
    # File already stable at start; a generous budget must not block: the
    # script returns as soon as everything is complete, not at the deadline.
    f = tmp_path / "bob-output.txt"
    f.write_text("R1: pass\n")
    _backdate(f, 60)
    start = time.time()
    result = _run("--budget", "30", "--stable", "30", str(f))
    assert result.stdout.strip().splitlines()[-1] == "DONE"
    assert time.time() - start < 10


def test_no_files_is_usage_error() -> None:
    result = _run("--budget", "1")
    assert result.returncode == 2
