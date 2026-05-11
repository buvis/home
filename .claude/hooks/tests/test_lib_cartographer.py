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


# --- resolve_session_key ---


def _load_gateguard():
    spec = importlib.util.spec_from_file_location(
        "gateguard_fact_force", HOOKS_DIR / "gateguard-fact-force.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_resolve_session_key_uses_session_id(lib) -> None:
    assert lib.resolve_session_key({"session_id": "abc-123"}) == "abc-123"


def test_resolve_session_key_falls_back_to_transcript(lib, tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.touch()
    key = lib.resolve_session_key({"transcript_path": str(transcript)})
    assert key.startswith("tx-")


def test_resolve_session_key_falls_back_to_cwd(lib, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    monkeypatch.delenv("CLAUDE_TRANSCRIPT_PATH", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    key = lib.resolve_session_key({})
    assert key.startswith("proj-")


def test_resolve_session_key_parity_with_gateguard(
    lib, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Strip env vars both modules consult so the empty-dict sample exercises the
    # `proj-` cwd-fallback branch (otherwise CI environments with these set
    # silently skip that branch).
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    monkeypatch.delenv("CLAUDE_TRANSCRIPT_PATH", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)

    gg = _load_gateguard()
    samples: list[dict] = [
        {"session_id": "explicit-session"},
        {"transcript_path": str(tmp_path / "abc.jsonl")},
        {},
    ]
    (tmp_path / "abc.jsonl").touch()
    for sample in samples:
        assert lib.resolve_session_key(sample) == gg.resolve_session_key(sample)


# --- session-state I/O ---


def test_save_load_round_trip(lib, fake_home: Path) -> None:
    lib.save_session_state("sid1", "echo", {"a": 1, "b": [2, 3]})
    assert lib.load_session_state("sid1", "echo") == {"a": 1, "b": [2, 3]}


def test_load_missing_returns_empty(lib, fake_home: Path) -> None:
    assert lib.load_session_state("never-saved", "echo") == {}


def test_namespace_isolation(lib, fake_home: Path) -> None:
    lib.save_session_state("sid", "echo", {"x": 1})
    assert lib.load_session_state("sid", "recon") == {}
    assert lib.load_session_state("sid", "echo") == {"x": 1}


def test_corrupted_json_returns_empty(lib, fake_home: Path) -> None:
    target = fake_home / ".claude" / "cache" / "cartographer" / "echo" / "state-sid.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("not json {", encoding="utf-8")
    assert lib.load_session_state("sid", "echo") == {}


def test_save_atomic_failure_preserves_prior(
    lib, fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lib.save_session_state("sid", "echo", {"old": 1})

    def boom(src: object, dst: object) -> None:
        raise OSError("forced replace failure")

    monkeypatch.setattr(os, "replace", boom)
    lib.save_session_state("sid", "echo", {"new": 2})  # must not raise

    assert lib.load_session_state("sid", "echo") == {"old": 1}
    # No tmp leftovers
    ns_dir = fake_home / ".claude" / "cache" / "cartographer" / "echo"
    leftovers = [p for p in ns_dir.iterdir() if ".tmp." in p.name]
    assert leftovers == []


# --- is_checked / mark_checked ---


def test_is_checked_initially_false(lib, fake_home: Path) -> None:
    assert lib.is_checked("sid", "echo", "foo") is False


def test_mark_then_is_checked_true(lib, fake_home: Path) -> None:
    lib.mark_checked("sid", "echo", "foo")
    assert lib.is_checked("sid", "echo", "foo") is True


def test_checked_namespace_isolation(lib, fake_home: Path) -> None:
    lib.mark_checked("sid", "echo", "foo")
    assert lib.is_checked("sid", "recon", "foo") is False


def test_checked_session_isolation(lib, fake_home: Path) -> None:
    lib.mark_checked("sid1", "echo", "foo")
    assert lib.is_checked("sid2", "echo", "foo") is False


def test_marked_state_persists_iso_timestamp(lib, fake_home: Path) -> None:
    lib.mark_checked("sid", "echo", "foo")
    raw = (fake_home / ".claude" / "cache" / "cartographer" / "echo" / "state-sid.json").read_text()
    state = json.loads(raw)
    assert isinstance(state["checked"], dict)
    ts = state["checked"]["foo"]
    assert isinstance(ts, str)
    assert "+00:00" in ts or ts.endswith("Z")


def test_corrupted_state_recovers_via_mark(lib, fake_home: Path) -> None:
    target = fake_home / ".claude" / "cache" / "cartographer" / "echo" / "state-sid.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("junk", encoding="utf-8")
    assert lib.is_checked("sid", "echo", "foo") is False
    lib.mark_checked("sid", "echo", "foo")  # must not raise on corrupted prior
    assert lib.is_checked("sid", "echo", "foo") is True


# --- try_import_tree_sitter ---


def test_try_import_tree_sitter_hit(
    lib, fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inject a fake tree_sitter_language_pack and confirm cached return."""
    import types as _types

    fake_module = _types.ModuleType("tree_sitter_language_pack")
    fake_module.__version__ = "fake-0.0.1"
    monkeypatch.setitem(sys.modules, "tree_sitter_language_pack", fake_module)
    lib._reset_tree_sitter_cache_for_tests()

    first = lib.try_import_tree_sitter()
    assert first is fake_module

    # Even if we strip sys.modules now, the cached value should still return.
    monkeypatch.delitem(sys.modules, "tree_sitter_language_pack", raising=False)
    second = lib.try_import_tree_sitter()
    assert second is fake_module


def test_try_import_tree_sitter_miss(
    lib, fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Force ImportError, confirm None + a single audit warn line."""
    monkeypatch.delitem(sys.modules, "tree_sitter_language_pack", raising=False)
    real_import_module = importlib.import_module

    def fake_import(name: str, package: str | None = None):
        if name == "tree_sitter_language_pack":
            raise ImportError("forced")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    lib._reset_tree_sitter_cache_for_tests()

    assert lib.try_import_tree_sitter() is None
    audit_lines = _audit_path(fake_home).read_text(encoding="utf-8").splitlines()
    miss_lines = [line for line in audit_lines if json.loads(line).get("event") == "tree_sitter_missing"]
    assert len(miss_lines) == 1


def test_try_import_tree_sitter_miss_then_call_again_no_extra_audit(
    lib, fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delitem(sys.modules, "tree_sitter_language_pack", raising=False)
    real_import_module = importlib.import_module

    def fake_import(name: str, package: str | None = None):
        if name == "tree_sitter_language_pack":
            raise ImportError("forced")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    lib._reset_tree_sitter_cache_for_tests()

    lib.try_import_tree_sitter()
    lib.try_import_tree_sitter()  # second miss-call must not log a second time
    lib.try_import_tree_sitter()

    audit_lines = _audit_path(fake_home).read_text(encoding="utf-8").splitlines()
    miss_lines = [line for line in audit_lines if json.loads(line).get("event") == "tree_sitter_missing"]
    assert len(miss_lines) == 1


# --- _state_path input validation (defense-in-depth at lib boundary) ---


_INVALID_SEGMENTS = [
    "",                # empty
    "../escape",       # parent traversal
    "..",              # bare dotdot
    "a/b",             # forward slash
    "a\\b",            # backslash
    ".hidden",         # leading dot
    "/absolute",       # absolute path
    "with\x00null",    # null byte
    "name with space", # whitespace
    "name.dot",        # interior dot (consistent with sanitized session keys)
    "trailing\n",      # trailing newline (re.match $ accepts; fullmatch rejects)
    "lead\ning",       # interior newline
]


@pytest.mark.parametrize("bad", _INVALID_SEGMENTS)
def test_state_path_rejects_invalid_namespace(lib, fake_home: Path, bad: str) -> None:
    with pytest.raises(ValueError):
        lib._state_path("valid-session", bad)


@pytest.mark.parametrize("bad", _INVALID_SEGMENTS)
def test_state_path_rejects_invalid_session_key(lib, fake_home: Path, bad: str) -> None:
    with pytest.raises(ValueError):
        lib._state_path(bad, "echo")


def test_load_session_state_rejects_invalid_namespace(lib, fake_home: Path) -> None:
    with pytest.raises(ValueError):
        lib.load_session_state("sid", "../escape")


def test_save_session_state_rejects_invalid_namespace(lib, fake_home: Path) -> None:
    """save_session_state catches OSError/TypeError/ValueError inside its try block,
    but _state_path is called BEFORE the try, so traversal attempts must propagate."""
    with pytest.raises(ValueError):
        lib.save_session_state("sid", "../escape", {"x": 1})


def test_is_checked_rejects_invalid_namespace(lib, fake_home: Path) -> None:
    with pytest.raises(ValueError):
        lib.is_checked("sid", "../escape", "key")


def test_mark_checked_rejects_invalid_namespace(lib, fake_home: Path) -> None:
    with pytest.raises(ValueError):
        lib.mark_checked("sid", "../escape", "key")


def test_state_path_accepts_valid_segments(lib, fake_home: Path) -> None:
    """Sanity: the validator must not over-reject. Keys produced by
    _sanitize_session_key (alphanumeric + _ + -) must continue to work."""
    # Round-trip a save/load with the kinds of values resolve_session_key produces.
    lib.save_session_state("explicit-session", "echo", {"ok": True})
    lib.save_session_state("tx-deadbeef1234", "recon-gate", {"ok": True})
    lib.save_session_state("proj-abc123", "architect_nudge", {"ok": True})
    assert lib.load_session_state("explicit-session", "echo") == {"ok": True}
    assert lib.load_session_state("tx-deadbeef1234", "recon-gate") == {"ok": True}
    assert lib.load_session_state("proj-abc123", "architect_nudge") == {"ok": True}
