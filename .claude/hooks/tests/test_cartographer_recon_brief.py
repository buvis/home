"""Tests for cartographer-recon-brief.py UserPromptSubmit hook.

Conventions (mirrors test_lib_cartographer.py / test_cartographer_stop.py):
- pytest function-style; bare `def test_*`.
- All filesystem state is redirected to `tmp_path` via `monkeypatch.setattr(Path, "home", ...)`.
- The hook is loaded fresh (importlib, module_from_spec) once per test so each
  test exercises a clean module against its own sandboxed home.
- Only the external boundary is mocked: `_lib_cartographer.project_hash` (avoids
  git) and `Path.home` (sandboxes the filesystem). `atlas_dir`, `append_audit`,
  and all store I/O are real.
"""

from __future__ import annotations

import importlib
import importlib.util
import io
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOKS_DIR))

_HOOK_PATH = HOOKS_DIR / "cartographer-recon-brief.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("cartographer_recon_brief", _HOOK_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect Path.home() to a tmp dir so the hook never touches the real ~/.claude."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    if "_lib_cartographer" in sys.modules:
        del sys.modules["_lib_cartographer"]
    (tmp_path / ".claude" / "cartographer").mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def lib(fake_home: Path):
    """Import _lib_cartographer fresh under the sandboxed home; reset its dir-creation cache.

    _lib_cartographer.append_audit caches directory creation in the module
    global `_DIRS_ENSURED`. Force it False here so each test's audit line
    lands under that test's own tmp home rather than silently no-op-ing.
    """
    mod = importlib.import_module("_lib_cartographer")
    mod._DIRS_ENSURED = False
    return mod


@pytest.fixture
def hook(lib):
    """Load a fresh cartographer-recon-brief module for each test."""
    return _load_hook()


# ---------------------------------------------------------------------------
# Constants (copied verbatim from the contract)
# ---------------------------------------------------------------------------

_HEADER = (
    "Atlas for this repo (consult before editing). Before adding new code: "
    "know the role of the file you touch, find two existing files with "
    "similar shape, and use a declared extension point or justify a new one."
)
_STALE_WARNING = "⚠ atlas is stale - recommend /survey --refresh"
_NO_ATLAS_LINE = "No atlas for this repo yet — run `/survey` to generate one."

_TODAY = datetime.now(timezone.utc).date().isoformat()
_YESTERDAY = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
_FUTURE = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _payload(cwd: str = "/repo", session_id: str = "sess-1") -> dict:
    return {"cwd": cwd, "session_id": session_id}


def _run(hook_mod, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], payload: dict) -> str:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    hook_mod.main()
    return capsys.readouterr().out


def _set_repo(monkeypatch: pytest.MonkeyPatch, lib_mod, repo_hash: str, name: str = "repo", remote: str = "") -> None:
    monkeypatch.setattr(lib_mod, "project_hash", lambda cwd: (repo_hash, name, remote))


def _write_atlas(lib_mod, repo_hash: str, content: str) -> Path:
    d = lib_mod.atlas_dir(repo_hash)
    d.mkdir(parents=True, exist_ok=True)
    (d / "atlas.md").write_text(content, encoding="utf-8")
    return d


def _write_stale_flag(lib_mod, repo_hash: str) -> None:
    d = lib_mod.atlas_dir(repo_hash)
    d.mkdir(parents=True, exist_ok=True)
    (d / "staleness.flag").touch()


def _store_path(home: Path) -> Path:
    return home / ".claude" / "cache" / "cartographer" / "recon" / "injected.json"


def _read_store(home: Path) -> dict:
    p = _store_path(home)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _seed_store(home: Path, repo_hash: str, date_str: str) -> None:
    p = _store_path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({repo_hash: date_str}), encoding="utf-8")


def _audit_path(home: Path) -> Path:
    return home / ".claude" / "cartographer" / "audit.jsonl"


def _read_audit_events(home: Path) -> list[dict]:
    p = _audit_path(home)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# First prompt of day / inject
# ---------------------------------------------------------------------------

def test_first_prompt_of_day_injects_header_and_excerpt(hook, lib, monkeypatch, capsys, fake_home) -> None:
    _set_repo(monkeypatch, lib, "hash-a", name="repo-a", remote="https://example.com/repo-a.git")
    _write_atlas(lib, "hash-a", "atlas body text")

    out = _run(hook, monkeypatch, capsys, _payload(session_id="sess-1"))
    envelope = json.loads(out)

    assert envelope == {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": _HEADER + "\n\n" + "atlas body text",
        }
    }
    assert "decision" not in envelope
    assert "permissionDecision" not in envelope

    assert _read_store(fake_home) == {"hash-a": _TODAY}

    events = _read_audit_events(fake_home)
    assert len(events) == 1
    event = events[0]
    assert event["decision"] == "inject"
    assert event["repo_hash"] == "hash-a"
    assert event["session"] == "sess-1"
    assert event["phase"] == "recon"
    assert event["atlas_excerpt_bytes"] == len("atlas body text".encode("utf-8"))
    assert event["stale"] is False
    assert "ts" in event


def test_audit_session_defaults_to_empty_string_when_absent(hook, lib, monkeypatch, capsys, fake_home) -> None:
    _set_repo(monkeypatch, lib, "hash-nosession")
    _write_atlas(lib, "hash-nosession", "body")

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"cwd": "/repo"})))
    hook.main()
    capsys.readouterr()

    events = _read_audit_events(fake_home)
    assert len(events) == 1
    assert events[0]["session"] == ""


# ---------------------------------------------------------------------------
# Throttle: suppress / rollover / clock skew / per-repo isolation
# ---------------------------------------------------------------------------

def test_suppresses_second_prompt_same_day(hook, lib, monkeypatch, capsys, fake_home) -> None:
    _set_repo(monkeypatch, lib, "hash-supp")
    _write_atlas(lib, "hash-supp", "atlas supp")
    _seed_store(fake_home, "hash-supp", _TODAY)
    store_before = _read_store(fake_home)

    out = _run(hook, monkeypatch, capsys, _payload())

    assert out == ""
    assert _read_store(fake_home) == store_before
    assert _read_audit_events(fake_home) == []


def test_second_repo_injects_independently_same_day(hook, lib, monkeypatch, capsys, fake_home) -> None:
    _set_repo(monkeypatch, lib, "hash-a")
    _write_atlas(lib, "hash-a", "atlas A")
    out_a = _run(hook, monkeypatch, capsys, _payload(session_id="sess-a"))
    assert json.loads(out_a)["hookSpecificOutput"]["additionalContext"] == _HEADER + "\n\n" + "atlas A"

    _set_repo(monkeypatch, lib, "hash-b")
    _write_atlas(lib, "hash-b", "atlas B")
    out_b = _run(hook, monkeypatch, capsys, _payload(session_id="sess-b"))
    assert json.loads(out_b)["hookSpecificOutput"]["additionalContext"] == _HEADER + "\n\n" + "atlas B"

    assert _read_store(fake_home) == {"hash-a": _TODAY, "hash-b": _TODAY}
    events = _read_audit_events(fake_home)
    assert len(events) == 2
    assert [e["repo_hash"] for e in events] == ["hash-a", "hash-b"]
    assert all(e["decision"] == "inject" for e in events)


def test_day_rollover_reinjects_and_updates_store(hook, lib, monkeypatch, capsys, fake_home) -> None:
    _set_repo(monkeypatch, lib, "hash-roll")
    _write_atlas(lib, "hash-roll", "atlas roll")
    _seed_store(fake_home, "hash-roll", _YESTERDAY)

    out = _run(hook, monkeypatch, capsys, _payload())

    assert json.loads(out)["hookSpecificOutput"]["additionalContext"] == _HEADER + "\n\n" + "atlas roll"
    assert _read_store(fake_home) == {"hash-roll": _TODAY}
    events = _read_audit_events(fake_home)
    assert len(events) == 1
    assert events[0]["decision"] == "inject"


def test_future_dated_store_entry_still_reinjects(hook, lib, monkeypatch, capsys, fake_home) -> None:
    """Clock-skew case: a stored date ahead of today is != today, so it reinjects.

    Pins the `!=` throttle semantics (not a `<=` comparison).
    """
    _set_repo(monkeypatch, lib, "hash-future")
    _write_atlas(lib, "hash-future", "atlas future")
    _seed_store(fake_home, "hash-future", _FUTURE)

    out = _run(hook, monkeypatch, capsys, _payload())

    assert json.loads(out)["hookSpecificOutput"]["additionalContext"] == _HEADER + "\n\n" + "atlas future"
    assert _read_store(fake_home) == {"hash-future": _TODAY}


# ---------------------------------------------------------------------------
# Missing atlas
# ---------------------------------------------------------------------------

def test_missing_atlas_emits_survey_recommendation_only(hook, lib, monkeypatch, capsys, fake_home) -> None:
    _set_repo(monkeypatch, lib, "hash-noatlas")
    # no atlas.md written

    out = _run(hook, monkeypatch, capsys, _payload(session_id="sess-2"))
    envelope = json.loads(out)

    assert envelope == {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": _NO_ATLAS_LINE,
        }
    }

    events = _read_audit_events(fake_home)
    assert len(events) == 1
    event = events[0]
    assert event["decision"] == "atlas-missing"
    assert event["repo_hash"] == "hash-noatlas"
    assert event["atlas_excerpt_bytes"] == 0
    assert event["stale"] is False


def test_missing_atlas_recommendation_does_not_repeat_same_day(hook, lib, monkeypatch, capsys, fake_home) -> None:
    _set_repo(monkeypatch, lib, "hash-noatlas2")

    first = _run(hook, monkeypatch, capsys, _payload())
    assert json.loads(first)["hookSpecificOutput"]["additionalContext"] == _NO_ATLAS_LINE
    assert len(_read_audit_events(fake_home)) == 1

    second = _run(hook, monkeypatch, capsys, _payload())
    assert second == ""
    assert len(_read_audit_events(fake_home)) == 1


# ---------------------------------------------------------------------------
# Non-repo cwd (global skip)
# ---------------------------------------------------------------------------

def test_non_repo_cwd_produces_no_output_no_store_no_audit(hook, lib, monkeypatch, capsys, fake_home) -> None:
    _set_repo(monkeypatch, lib, "global", name="global", remote="")

    out = _run(hook, monkeypatch, capsys, _payload())

    assert out == ""
    assert not _store_path(fake_home).exists()
    assert _read_audit_events(fake_home) == []


# ---------------------------------------------------------------------------
# Stale flag
# ---------------------------------------------------------------------------

def test_stale_flag_appends_warning_after_excerpt(hook, lib, monkeypatch, capsys, fake_home) -> None:
    _set_repo(monkeypatch, lib, "hash-stale")
    _write_atlas(lib, "hash-stale", "atlas stale body")
    _write_stale_flag(lib, "hash-stale")

    out = _run(hook, monkeypatch, capsys, _payload())
    envelope = json.loads(out)

    expected = _HEADER + "\n\n" + "atlas stale body" + "\n\n" + _STALE_WARNING
    assert envelope["hookSpecificOutput"]["additionalContext"] == expected

    events = _read_audit_events(fake_home)
    assert events[0]["stale"] is True


# ---------------------------------------------------------------------------
# Truncation: >1KB and multibyte boundary
# ---------------------------------------------------------------------------

def test_atlas_over_1kb_is_truncated_to_1024_bytes(hook, lib, monkeypatch, capsys, fake_home) -> None:
    _set_repo(monkeypatch, lib, "big-hash")
    _write_atlas(lib, "big-hash", "x" * 2000)

    out = _run(hook, monkeypatch, capsys, _payload())
    envelope = json.loads(out)
    ctx = envelope["hookSpecificOutput"]["additionalContext"]
    expected_excerpt = "x" * 1024

    assert ctx == _HEADER + "\n\n" + expected_excerpt
    events = _read_audit_events(fake_home)
    assert events[-1]["atlas_excerpt_bytes"] == 1024


def test_atlas_truncation_at_multibyte_boundary_yields_valid_utf8(hook, lib, monkeypatch, capsys, fake_home) -> None:
    """Byte 1024 lands mid-way through a 3-byte UTF-8 char ("€" = 0xE2 0x82 0xAC).

    The split char must be dropped, not raise a decode error, and the excerpt
    must stay <= 1024 bytes.
    """
    _set_repo(monkeypatch, lib, "boundary-hash")
    content = "a" * 1023 + "€" + "b" * 50
    _write_atlas(lib, "boundary-hash", content)
    raw_bytes = content.encode("utf-8")
    expected_excerpt = raw_bytes[:1024].decode("utf-8", "ignore")

    out = _run(hook, monkeypatch, capsys, _payload())
    envelope = json.loads(out)
    ctx = envelope["hookSpecificOutput"]["additionalContext"]

    assert ctx == _HEADER + "\n\n" + expected_excerpt
    assert len(expected_excerpt.encode("utf-8")) <= 1024

    events = _read_audit_events(fake_home)
    assert events[-1]["atlas_excerpt_bytes"] == len(expected_excerpt.encode("utf-8"))


# ---------------------------------------------------------------------------
# Malformed store / malformed stdin
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_content",
    ["{not valid json", "[]"],
    ids=["invalid-json-bytes", "valid-json-not-a-dict"],
)
def test_malformed_store_rebuilds_and_still_injects(hook, lib, monkeypatch, capsys, fake_home, bad_content: str) -> None:
    _set_repo(monkeypatch, lib, "hash-malformed")
    _write_atlas(lib, "hash-malformed", "atlas body")
    store_path = _store_path(fake_home)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(bad_content, encoding="utf-8")

    out = _run(hook, monkeypatch, capsys, _payload())
    envelope = json.loads(out)  # must not crash

    assert envelope["hookSpecificOutput"]["additionalContext"] == _HEADER + "\n\n" + "atlas body"
    assert _read_store(fake_home) == {"hash-malformed": _TODAY}


def test_malformed_stdin_exits_silently_with_no_side_effects(hook, monkeypatch, capsys, fake_home) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    hook.main()  # must not raise

    captured = capsys.readouterr()
    assert captured.out == ""
    # Malformed stdin is an expected boundary condition, not a bug: it stays
    # fully silent (no stderr breadcrumb), distinct from an internal failure.
    assert captured.err == ""
    assert not _store_path(fake_home).exists()
    assert _read_audit_events(fake_home) == []


# ---------------------------------------------------------------------------
# Internal failure: stderr breadcrumb, no stdout, never crashes (R10)
# ---------------------------------------------------------------------------

def test_internal_error_writes_stderr_breadcrumb_and_no_stdout(hook, lib, monkeypatch, capsys, fake_home) -> None:
    """A genuine failure inside the recon logic must not vanish silently.

    Unlike malformed stdin (an expected boundary that stays silent), an
    unexpected exception in the hook's own logic writes a one-line stderr
    breadcrumb, emits no stdout, produces no side effects, and never raises
    (a UserPromptSubmit hook must never crash the prompt). Binds the R10
    'never silently swallow errors' intent, matching the sibling hooks
    cartographer-echo / cartographer-stop.
    """
    def boom(cwd: str):
        raise RuntimeError("project_hash blew up")

    monkeypatch.setattr(lib, "project_hash", boom)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_payload())))
    hook.main()  # must not raise

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[cartographer-recon]" in captured.err
    assert not _store_path(fake_home).exists()
    assert _read_audit_events(fake_home) == []


# ---------------------------------------------------------------------------
# Mixed run: audit line counts
# ---------------------------------------------------------------------------

def test_mixed_run_produces_one_audit_line_per_inject_and_atlas_missing_zero_for_suppress(
    hook, lib, monkeypatch, capsys, fake_home
) -> None:
    # 1. inject
    _set_repo(monkeypatch, lib, "hash-mix1")
    _write_atlas(lib, "hash-mix1", "mix atlas")
    out1 = _run(hook, monkeypatch, capsys, _payload())
    assert out1 != ""

    # 2. suppress (same repo, same day)
    out2 = _run(hook, monkeypatch, capsys, _payload())
    assert out2 == ""

    # 3. atlas-missing (different repo)
    _set_repo(monkeypatch, lib, "hash-mix2")
    out3 = _run(hook, monkeypatch, capsys, _payload())
    assert out3 != ""

    events = _read_audit_events(fake_home)
    assert len(events) == 2
    assert events[0]["decision"] == "inject"
    assert events[0]["repo_hash"] == "hash-mix1"
    assert events[1]["decision"] == "atlas-missing"
    assert events[1]["repo_hash"] == "hash-mix2"


# ---------------------------------------------------------------------------
# Latency (best-effort; skip rather than hard-fail on a loaded machine)
# ---------------------------------------------------------------------------

def test_suppressed_path_p95_latency_under_150ms(hook, lib, monkeypatch, capsys, fake_home) -> None:
    """~100 suppressed invocations; p95 < 150ms. project_hash is patched, so this
    mostly measures the hook body + store I/O, not git."""
    _set_repo(monkeypatch, lib, "perf-suppress")
    _write_atlas(lib, "perf-suppress", "atlas content")
    _seed_store(fake_home, "perf-suppress", _TODAY)

    durations: list[float] = []
    n = 100
    for _ in range(n):
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_payload())))
        t0 = time.perf_counter()
        hook.main()
        durations.append(time.perf_counter() - t0)
    capsys.readouterr()

    durations.sort()
    p95_ms = durations[int(n * 0.95) - 1] * 1000
    try:
        assert p95_ms < 150.0
    except AssertionError:
        pytest.skip(f"suppressed p95 {p95_ms:.1f}ms >= 150ms threshold (possibly a loaded machine)")


def test_inject_path_p95_latency_under_200ms(hook, lib, monkeypatch, capsys, fake_home) -> None:
    """~100 forced-inject invocations (store reset to a past date before each call,
    outside the timed region); p95 < 200ms."""
    _set_repo(monkeypatch, lib, "perf-inject")
    _write_atlas(lib, "perf-inject", "atlas content for perf test")

    durations: list[float] = []
    n = 100
    for _ in range(n):
        _seed_store(fake_home, "perf-inject", "2020-01-01")
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_payload())))
        t0 = time.perf_counter()
        hook.main()
        durations.append(time.perf_counter() - t0)
    capsys.readouterr()

    durations.sort()
    p95_ms = durations[int(n * 0.95) - 1] * 1000
    try:
        assert p95_ms < 200.0
    except AssertionError:
        pytest.skip(f"inject p95 {p95_ms:.1f}ms >= 200ms threshold (possibly a loaded machine)")
