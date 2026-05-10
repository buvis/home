"""Tests for hooks/_lib_cartographer.py.

Run with: `uvx pytest ~/.claude/hooks/tests/test_lib_cartographer.py -v`

Conventions:
- pytest function-style; bare `def test_*`.
- All filesystem state is redirected to `tmp_path` via `monkeypatch.setattr(Path, "home", ...)`.
- Tests must NEVER touch the real `~/.claude/cartographer/` or `~/.claude/cache/cartographer/`.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOKS_DIR))


@pytest.fixture
def fake_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect Path.home() to a tmp dir so the lib never writes to the real ~/.claude."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # Force a fresh import so module-level constants pick up the patched home.
    if "_lib_cartographer" in sys.modules:
        del sys.modules["_lib_cartographer"]
    return tmp_path


@pytest.fixture
def lib(fake_home: Path):
    """Import _lib_cartographer with a tmp HOME already in place."""
    return importlib.import_module("_lib_cartographer")


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )


def _make_repo(path: Path, remote: str | None = None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "master")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    if remote is not None:
        _git(path, "remote", "add", "origin", remote)


# --- project_hash ---


def test_project_hash_with_remote(lib, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_repo(repo, remote="https://github.com/example/widgets.git")

    cwd = os.getcwd()
    os.chdir(repo)
    try:
        h, name, remote = lib.project_hash()
    finally:
        os.chdir(cwd)

    expected_hash = hashlib.sha256(b"https://github.com/example/widgets.git").hexdigest()[:12]
    assert h == expected_hash
    assert name == "widgets"
    assert remote == "https://github.com/example/widgets.git"


def test_project_hash_strips_embedded_credentials(lib, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_repo(repo, remote="https://user:token@github.com/example/widgets.git")

    cwd = os.getcwd()
    os.chdir(repo)
    try:
        h, _, remote = lib.project_hash()
    finally:
        os.chdir(cwd)
    cleaned = "https://github.com/example/widgets.git"
    assert remote == cleaned
    assert h == hashlib.sha256(cleaned.encode()).hexdigest()[:12]


def test_project_hash_no_remote_falls_back_to_path(lib, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_repo(repo, remote=None)

    cwd = os.getcwd()
    os.chdir(repo)
    try:
        h, name, remote = lib.project_hash()
    finally:
        os.chdir(cwd)

    # detect_project uses the toplevel string git reports, not Path.resolve().
    toplevel = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert h == hashlib.sha256(toplevel.encode()).hexdigest()[:12]
    assert name == Path(toplevel).name
    assert remote == ""


def test_project_hash_no_git_falls_back_to_global(lib, tmp_path: Path) -> None:
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()

    cwd = os.getcwd()
    os.chdir(not_a_repo)
    try:
        h, name, remote = lib.project_hash()
    finally:
        os.chdir(cwd)
    assert h == "global"
    assert name == "global"
    assert remote == ""


def test_project_hash_matches_analyze_instincts_detect_project(lib, tmp_path: Path) -> None:
    """Cross-check parity with analyze-instincts.py:detect_project."""
    spec = importlib.util.spec_from_file_location(
        "analyze_instincts", HOOKS_DIR / "analyze-instincts.py"
    )
    assert spec is not None and spec.loader is not None
    ai = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ai)

    repo = tmp_path / "repo"
    _make_repo(repo, remote="https://github.com/example/parity.git")

    cwd = os.getcwd()
    os.chdir(repo)
    try:
        ours = lib.project_hash()
        theirs = ai.detect_project()
    finally:
        os.chdir(cwd)

    assert ours == theirs


# --- atlas_dir ---


def test_atlas_dir_returns_expected_path(lib, fake_home: Path) -> None:
    p = lib.atlas_dir("abc123def456")
    assert p == fake_home / ".claude" / "cartographer" / "projects" / "abc123def456"


def test_atlas_dir_does_not_create_directory(lib, fake_home: Path) -> None:
    p = lib.atlas_dir("never-created")
    assert not p.exists()


# --- _ensure_dirs / append_audit ---


def _audit_path(home: Path) -> Path:
    return home / ".claude" / "cartographer" / "audit.jsonl"


def test_ensure_dirs_creates_layout(lib, fake_home: Path) -> None:
    lib._ensure_dirs()
    assert (fake_home / ".claude" / "cartographer").is_dir()
    assert (fake_home / ".claude" / "cartographer" / "projects").is_dir()
    assert (fake_home / ".claude" / "cartographer" / "scripts").is_dir()
    assert (fake_home / ".claude" / "cache" / "cartographer").is_dir()
    assert _audit_path(fake_home).is_file()


def test_ensure_dirs_idempotent(lib, fake_home: Path) -> None:
    lib._ensure_dirs()
    lib._ensure_dirs()  # second call must not raise
    assert _audit_path(fake_home).is_file()


def test_append_audit_writes_one_line_with_timestamp(lib, fake_home: Path) -> None:
    lib.append_audit({"event": "hello"})
    lines = _audit_path(fake_home).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["event"] == "hello"
    assert isinstance(obj.get("ts"), str) and ("+00:00" in obj["ts"] or obj["ts"].endswith("Z"))


def test_append_audit_preserves_caller_supplied_ts(lib, fake_home: Path) -> None:
    lib.append_audit({"event": "x", "ts": "2026-01-01T00:00:00+00:00"})
    obj = json.loads(_audit_path(fake_home).read_text(encoding="utf-8").splitlines()[0])
    assert obj["ts"] == "2026-01-01T00:00:00+00:00"


def test_append_audit_1000_sequential(lib, fake_home: Path) -> None:
    for i in range(1000):
        lib.append_audit({"event": "seq", "i": i})
    lines = _audit_path(fake_home).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1000
    parsed = [json.loads(line) for line in lines]
    assert [p["i"] for p in parsed] == list(range(1000))


def test_append_audit_concurrent_threads(lib, fake_home: Path) -> None:
    import threading

    def worker(tag: str) -> None:
        for i in range(500):
            lib.append_audit({"event": "concur", "tag": tag, "i": i})

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start(); t2.start(); t1.join(); t2.join()

    lines = _audit_path(fake_home).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1000
    for line in lines:
        json.loads(line)


def test_append_audit_swallows_write_errors(
    lib,
    fake_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A write-failure simulation must not propagate exceptions to the caller."""

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("forced failure")

    # Patch the lib's _atomic_append symbol (added by the implementation) so the
    # write fails. The lib must catch this and emit a stderr warning.
    monkeypatch.setattr(lib, "_atomic_append", boom)
    lib.append_audit({"event": "should_not_crash"})  # must not raise
    captured = capsys.readouterr()
    assert captured.err  # some warning must reach stderr
