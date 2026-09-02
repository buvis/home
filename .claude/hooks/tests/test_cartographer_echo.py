"""Tests for hooks/cartographer-echo.py — PreToolUse duplicate-detection gate.

Subprocess-driven end-to-end tests. HOME is redirected to tmp_path so the
audit log and session-state I/O never touch the real ~/.claude/. The hook
exits 0 on every path (allow vs deny is signaled via the stdout JSON
envelope, mirroring gateguard-fact-force.py).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import _echo_catalog

HOOK = Path(__file__).resolve().parents[1] / "cartographer-echo.py"


def _import_hook_module():
    """Import the hook by file path (hyphenated filename can't use `import`)."""
    spec = importlib.util.spec_from_file_location("cartographer_echo_mod", HOOK)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def run_hook(
    payload: dict,
    home: Path,
    cwd: Path | None = None,
    env_extra: dict | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "HOME": str(home)}
    # Force a fresh session-key resolution per test run.
    env.pop("CLAUDE_SESSION_ID", None)
    env.pop("CLAUDE_TRANSCRIPT_PATH", None)
    env.pop("CLAUDE_PROJECT_DIR", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd) if cwd else None,
        timeout=15,
    )


def read_audit(home: Path) -> list[dict]:
    log = home / ".local" / "share" / "agents" / "cartographer" / "audit.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


# --- Hook file exists ---


def test_hook_file_exists() -> None:
    assert HOOK.is_file(), f"missing: {HOOK}"


# --- Skip: settings.json ---


def test_skip_claude_settings_json(tmp_path: Path) -> None:
    payload = {
        "session_id": "sess-test-settings",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(tmp_path / ".claude" / "settings.json"),
            "old_string": "x",
            "new_string": "y",
        },
    }
    proc = run_hook(payload, home=tmp_path)
    assert proc.returncode == 0
    if proc.stdout.strip():
        envelope = json.loads(proc.stdout)
        assert (
            envelope.get("hookSpecificOutput", {}).get("permissionDecision") != "deny"
        )
    events = read_audit(tmp_path)
    skip = [
        e
        for e in events
        if e.get("decision") == "skip" and e.get("reason") == "settings"
    ]
    assert len(skip) == 1, f"expected 1 skip:settings event, got {events}"
    assert skip[0]["phase"] == "echo"


# --- Skip: large content ---


def test_skip_large_content(tmp_path: Path) -> None:
    big = "x" * (500_001)
    payload = {
        "session_id": "sess-large",
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(tmp_path / "src" / "big.py"),
            "content": big,
        },
    }
    proc = run_hook(payload, home=tmp_path)
    assert proc.returncode == 0
    events = read_audit(tmp_path)
    skip = [
        e
        for e in events
        if e.get("decision") == "skip" and e.get("reason") == "large-file"
    ]
    assert len(skip) == 1


# --- Skip: no tree-sitter ---


def test_skip_no_tree_sitter(tmp_path: Path) -> None:
    """When tree_sitter_language_pack import fails, hook emits skip:no-tree-sitter and allows."""
    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "sitecustomize.py").write_text(
        "import sys\n"
        "class _Blocker:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'tree_sitter_language_pack' or name.startswith('tree_sitter_language_pack.'):\n"
        "            raise ImportError('blocked-for-test')\n"
        "        return None\n"
        "sys.meta_path.insert(0, _Blocker())\n",
    )
    payload = {
        "session_id": "sess-nts",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(tmp_path / "src" / "foo.py"),
            "old_string": "x",
            "new_string": "y",
        },
    }
    proc = run_hook(payload, home=tmp_path, env_extra={"PYTHONPATH": str(shim)})
    assert proc.returncode == 0
    events = read_audit(tmp_path)
    skip = [
        e
        for e in events
        if e.get("decision") == "skip" and e.get("reason") == "no-tree-sitter"
    ]
    assert len(skip) == 1, f"expected skip:no-tree-sitter, got {events}"


# --- Skip: test files ---


@pytest.mark.parametrize(
    "rel_path",
    [
        "tests/test_foo.py",
        "test/test_bar.py",
        "src/foo_test.go",
        "src/widget.test.ts",
        "src/widget.test.tsx",
        "src/widget.test.js",
        "src/widget.test.jsx",
    ],
)
def test_skip_test_file(tmp_path: Path, rel_path: str) -> None:
    payload = {
        "session_id": "sess-test-file",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(tmp_path / rel_path),
            "old_string": "x",
            "new_string": "y",
        },
    }
    proc = run_hook(payload, home=tmp_path)
    assert proc.returncode == 0
    events = read_audit(tmp_path)
    skip = [
        e
        for e in events
        if e.get("decision") == "skip" and e.get("reason") == "test-file"
    ]
    assert len(skip) == 1, f"expected skip:test-file for {rel_path}, got {events}"


# --- Skip: unsupported extensions ---


@pytest.mark.parametrize("ext", [".md", ".yaml", ".json", ".toml", ".sh", ".txt", ""])
def test_skip_unsupported_ext(tmp_path: Path, ext: str) -> None:
    payload = {
        "session_id": "sess-unsupp",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(tmp_path / f"src/file{ext}"),
            "old_string": "x",
            "new_string": "y",
        },
    }
    proc = run_hook(payload, home=tmp_path)
    assert proc.returncode == 0
    events = read_audit(tmp_path)
    skip = [
        e
        for e in events
        if e.get("decision") == "skip" and e.get("reason") == "unsupported-ext"
    ]
    assert len(skip) == 1, (
        f"expected skip:unsupported-ext for ext={ext!r}, got {events}"
    )


# --- Malformed / empty stdin: no crash ---


def test_malformed_json_no_crash(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input="this is not json {",
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(tmp_path)},
        timeout=10,
    )
    assert proc.returncode == 0
    assert "Traceback" not in proc.stderr


def test_empty_stdin_no_crash(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input="",
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(tmp_path)},
        timeout=10,
    )
    assert proc.returncode == 0
    assert "Traceback" not in proc.stderr


# --- Non-targeted tools pass through ---


def test_unknown_tool_passes_through(tmp_path: Path) -> None:
    payload = {
        "session_id": "sess-other",
        "tool_name": "Read",
        "tool_input": {"file_path": "/tmp/x"},
    }
    proc = run_hook(payload, home=tmp_path)
    assert proc.returncode == 0
    events = read_audit(tmp_path)
    assert all(e.get("tool") != "Read" for e in events)


# --- Audit event schema ---


def test_audit_event_required_keys(tmp_path: Path) -> None:
    payload = {
        "session_id": "sess-schema",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(tmp_path / "src" / "x.md"),
            "old_string": "x",
            "new_string": "y",
        },
    }
    proc = run_hook(payload, home=tmp_path)
    assert proc.returncode == 0
    events = read_audit(tmp_path)
    assert events, "no audit events written"
    e = events[-1]
    for key in ("ts", "session", "tool", "file", "decision", "reason", "phase"):
        assert key in e, f"missing key {key} in event {e}"
    assert e["phase"] == "echo"
    assert e["tool"] == "Edit"
    assert e["decision"] == "skip"


# --- Direct-call coverage (handle / main bypass subprocess for line coverage) ---


def _isolate_hook_for_direct_call(
    monkeypatch: pytest.MonkeyPatch,
    home: Path,
) -> object:
    """Import the hook with HOME pointed at a tmp dir and lib cache cleared."""
    monkeypatch.setenv("HOME", str(home))
    # Force fresh import of lib + hook
    for name in ("_lib_cartographer", "cartographer_echo_mod"):
        if name in sys.modules:
            del sys.modules[name]
    return _import_hook_module()


def test_handle_direct_call_unknown_tool_no_audit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mod = _isolate_hook_for_direct_call(monkeypatch, tmp_path)
    mod.handle(
        {"tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}, "session_id": "s"},
    )
    events = read_audit(tmp_path)
    assert all(e.get("tool") != "Read" for e in events)


def test_handle_direct_call_edit_skip_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mod = _isolate_hook_for_direct_call(monkeypatch, tmp_path)
    mod.handle(
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(tmp_path / ".claude" / "settings.json"),
                "old_string": "x",
                "new_string": "y",
            },
            "session_id": "s",
        },
    )
    events = read_audit(tmp_path)
    assert any(e.get("reason") == "settings" for e in events)


def test_handle_direct_call_bash_clean(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mod = _isolate_hook_for_direct_call(monkeypatch, tmp_path)
    mod.handle(
        {"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "session_id": "s"},
    )
    events = read_audit(tmp_path)
    assert any(e.get("reason") == "bash-clean" for e in events)


def test_handle_direct_call_write_no_symbols(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mod = _isolate_hook_for_direct_call(monkeypatch, tmp_path)
    iso = tmp_path / "iso"
    iso.mkdir()
    mod.handle(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(iso / "x.py"),
                "content": "# comment only\n",
            },
            "session_id": "s",
        },
    )
    events = read_audit(tmp_path)
    assert any(e.get("reason") == "no-symbols" for e in events)


def test_deny_key_deterministic() -> None:
    mod = _import_hook_module()
    a = mod.deny_key("/a.py", ["foo", "bar"])
    b = mod.deny_key("/a.py", ["bar", "foo"])  # sorted order
    assert a == b
    assert len(a) == 24


def test_handle_direct_call_bash_bypass_deny_and_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
) -> None:
    mod = _isolate_hook_for_direct_call(monkeypatch, tmp_path)
    (tmp_path / "src").mkdir()
    monkeypatch.chdir(tmp_path)
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "cat > src/util.py <<EOF\ndef foo(): pass\nEOF"},
        "session_id": "s-bash-direct",
    }
    mod.handle(payload)
    out = capsys.readouterr().out
    assert out.strip(), "expected deny envelope"
    env = json.loads(out)
    assert env["hookSpecificOutput"]["permissionDecision"] == "deny"
    # Second call → allow.
    mod.handle(payload)
    out2 = capsys.readouterr().out
    if out2.strip():
        env2 = json.loads(out2)
        assert env2["hookSpecificOutput"]["permissionDecision"] != "deny"


def test_handle_direct_call_edit_deny_and_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
) -> None:
    mod = _isolate_hook_for_direct_call(monkeypatch, tmp_path)
    root = tmp_path / "proj"
    root.mkdir()
    (root / "lib.py").write_text("def formatPrice(p):\n    return p\n")
    monkeypatch.chdir(root)
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(root / "price.py"),
            "content": "def formatPrice(p):\n    return f'${p}'\n",
        },
        "session_id": "s-edit-direct",
    }
    mod.handle(payload)
    out = capsys.readouterr().out
    env = json.loads(out)
    assert env["hookSpecificOutput"]["permissionDecision"] == "deny"
    # Retry → allow.
    mod.handle(payload)
    out2 = capsys.readouterr().out
    if out2.strip():
        env2 = json.loads(out2)
        assert env2["hookSpecificOutput"]["permissionDecision"] != "deny"


def test_main_function_parses_stdin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Cover main()'s json parse + handle() dispatch + exception path."""
    mod = _isolate_hook_for_direct_call(monkeypatch, tmp_path)
    import io

    payload = {"tool_name": "Bash", "tool_input": {"command": "ls"}, "session_id": "s"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    rc = mod.main()
    assert rc == 0


def test_main_empty_stdin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _isolate_hook_for_direct_call(monkeypatch, tmp_path)
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    rc = mod.main()
    assert rc == 0


def test_main_malformed_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _isolate_hook_for_direct_call(monkeypatch, tmp_path)
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO("{ not json"))
    rc = mod.main()
    assert rc == 0


def test_main_non_dict_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _isolate_hook_for_direct_call(monkeypatch, tmp_path)
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO("[1, 2, 3]"))
    rc = mod.main()
    assert rc == 0


# --- Audit schema completeness ---


def test_audit_every_event_has_required_keys(tmp_path: Path) -> None:
    """Run a sequence of payloads covering allow/deny/skip; every event has required keys."""
    payloads = [
        # Skip: unsupported ext
        {
            "session_id": "s1",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(tmp_path / "a.md"),
                "old_string": "x",
                "new_string": "y",
            },
        },
        # Skip: settings.json
        {
            "session_id": "s1",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(tmp_path / ".claude" / "settings.json"),
                "old_string": "x",
                "new_string": "y",
            },
        },
        # Bash clean
        {"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "ls -la"}},
        # Write supported ext with no project hits
        {
            "session_id": "s1",
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_path / "iso" / "fresh.py"),
                "content": "def somethingTotallyUniqueZZZ(): pass\n",
            },
        },
    ]
    (tmp_path / "iso").mkdir()
    required = {
        "ts",
        "session",
        "tool",
        "file",
        "decision",
        "reason",
        "symbols",
        "matches",
        "phase",
    }
    for p in payloads:
        run_hook(p, home=tmp_path, cwd=tmp_path)
    events = read_audit(tmp_path)
    assert events, "no events written"
    for e in events:
        # tree_sitter_missing warnings have only `ts` + `event` keys; skip those.
        if "decision" not in e:
            continue
        missing = required - set(e.keys())
        assert not missing, f"event missing {missing}: {e}"
        assert e["phase"] == "echo"


def test_mcp_serena_tool_emits_skip_audit(tmp_path: Path) -> None:
    payload = {
        "session_id": "sess-mcp",
        "tool_name": "mcp__serena__write_file",
        "tool_input": {"file_path": str(tmp_path / "x.py"), "content": "x = 1"},
    }
    proc = run_hook(payload, home=tmp_path)
    assert proc.returncode == 0
    events = read_audit(tmp_path)
    mcp = [e for e in events if e.get("tool", "").startswith("mcp__serena__")]
    assert mcp, f"expected mcp__serena__ audit event, got {events}"
    assert mcp[0]["decision"] == "skip"
    assert mcp[0]["reason"] == "mcp-unsupported"


# --- Bash bypass deny (end-to-end) ---


def test_bash_bypass_denies_first_attempt(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    payload = {
        "session_id": "sess-bash-1",
        "tool_name": "Bash",
        "tool_input": {"command": "cat > src/util.py <<EOF\nprint('hi')\nEOF"},
    }
    proc = run_hook(payload, home=tmp_path, cwd=tmp_path)
    assert proc.returncode == 0
    assert proc.stdout.strip()
    env = json.loads(proc.stdout)
    assert env["hookSpecificOutput"]["permissionDecision"] == "deny"
    reason = env["hookSpecificOutput"]["permissionDecisionReason"]
    assert "Write tool" in reason
    events = read_audit(tmp_path)
    deny = [
        e
        for e in events
        if e.get("decision") == "deny" and e.get("reason") == "bash-bypass"
    ]
    assert deny, f"expected bash-bypass deny audit, got {events}"


def test_bash_bypass_second_attempt_allows(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    payload = {
        "session_id": "sess-bash-2",
        "tool_name": "Bash",
        "tool_input": {"command": "cat > src/util.py <<EOF\nprint('hi')\nEOF"},
    }
    p1 = run_hook(payload, home=tmp_path, cwd=tmp_path)
    env1 = json.loads(p1.stdout)
    assert env1["hookSpecificOutput"]["permissionDecision"] == "deny"
    p2 = run_hook(payload, home=tmp_path, cwd=tmp_path)
    assert p2.returncode == 0
    if p2.stdout.strip():
        env2 = json.loads(p2.stdout)
        assert env2["hookSpecificOutput"]["permissionDecision"] != "deny"


def test_clean_bash_passes_through(tmp_path: Path) -> None:
    payload = {
        "session_id": "sess-bash-clean",
        "tool_name": "Bash",
        "tool_input": {"command": "ls -la"},
    }
    proc = run_hook(payload, home=tmp_path)
    assert proc.returncode == 0
    if proc.stdout.strip():
        env = json.loads(proc.stdout)
        assert env["hookSpecificOutput"]["permissionDecision"] != "deny"


# --- deny envelope with rationalization excerpt ---


def test_build_deny_envelope_shape() -> None:
    mod = _import_hook_module()
    matches = [
        {"symbol": "formatPrice", "file": "src/util.py", "line": 42, "score": "strong"},
    ]
    env = mod.build_deny_envelope(matches)
    assert env["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert env["hookSpecificOutput"]["permissionDecision"] == "deny"
    reason = env["hookSpecificOutput"]["permissionDecisionReason"]
    assert "formatPrice" in reason
    assert "src/util.py:42" in reason or "`src/util.py:42`" in reason
    assert "retry" in reason.lower()


def test_build_deny_envelope_contains_rationalization_quote() -> None:
    mod = _import_hook_module()
    matches = [
        {"symbol": "formatPrice", "file": "src/util.py", "line": 42, "score": "strong"},
    ]
    env = mod.build_deny_envelope(matches)
    reason = env["hookSpecificOutput"]["permissionDecisionReason"]
    # Block quote line(s) indicate the rationalization excerpt.
    assert any(line.startswith(">") for line in reason.splitlines()), reason


def test_build_deny_envelope_reason_length_capped() -> None:
    mod = _import_hook_module()
    matches = [
        {"symbol": "formatPrice", "file": "src/util.py", "line": 42, "score": "strong"},
    ]
    env = mod.build_deny_envelope(matches)
    reason = env["hookSpecificOutput"]["permissionDecisionReason"]
    assert len(reason) <= 1500


def test_build_deny_envelope_picks_strong_over_medium() -> None:
    mod = _import_hook_module()
    matches = [
        {"symbol": "formatPrice", "file": "src/a.py", "line": 1, "score": "medium"},
        {"symbol": "formatPrice", "file": "src/b.py", "line": 2, "score": "strong"},
    ]
    env = mod.build_deny_envelope(matches)
    reason = env["hookSpecificOutput"]["permissionDecisionReason"]
    assert "src/b.py:2" in reason


def test_build_deny_envelope_verbs_cite_couldnt_find_helper() -> None:
    """Symbols that contain `format`/`parse`/`validate`/etc cite the 'couldn't find existing helper' rationalization."""
    mod = _import_hook_module()
    matches = [
        {"symbol": "formatPrice", "file": "src/util.py", "line": 42, "score": "strong"},
    ]
    env = mod.build_deny_envelope(matches)
    reason = env["hookSpecificOutput"]["permissionDecisionReason"]
    assert "couldn't find" in reason.lower() or "didn't grep" in reason.lower()


def test_build_deny_envelope_empty_matches_returns_basic_reason() -> None:
    mod = _import_hook_module()
    env = mod.build_deny_envelope([])
    assert env["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert env["hookSpecificOutput"]["permissionDecisionReason"]


# --- two-attempt deny gate (end-to-end via subprocess) ---


def _make_test_repo(tmp_path: Path) -> Path:
    """Make a minimal directory layout with one duplicate-target file."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "util.py").write_text("def formatPrice(p):\n    return p\n")
    return root


def test_two_attempt_first_call_denies(tmp_path: Path) -> None:
    root = _make_test_repo(tmp_path)
    payload = {
        "session_id": "sess-gate-1",
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(root / "price.py"),
            "content": "def formatPrice(p):\n    return f'${p}'\n",
        },
    }
    proc = run_hook(payload, home=tmp_path, cwd=root)
    assert proc.returncode == 0
    assert proc.stdout.strip(), "expected deny envelope on stdout"
    env = json.loads(proc.stdout)
    assert env["hookSpecificOutput"]["permissionDecision"] == "deny"
    events = read_audit(tmp_path)
    deny = [e for e in events if e.get("decision") == "deny"]
    assert deny, f"expected deny audit, got {events}"


def test_two_attempt_second_call_allows(tmp_path: Path) -> None:
    root = _make_test_repo(tmp_path)
    payload = {
        "session_id": "sess-gate-2",
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(root / "price.py"),
            "content": "def formatPrice(p):\n    return f'${p}'\n",
        },
    }
    # First call: deny + mark.
    proc1 = run_hook(payload, home=tmp_path, cwd=root)
    env1 = json.loads(proc1.stdout)
    assert env1["hookSpecificOutput"]["permissionDecision"] == "deny"
    # Second call with same payload: allow.
    proc2 = run_hook(payload, home=tmp_path, cwd=root)
    assert proc2.returncode == 0
    if proc2.stdout.strip():
        env2 = json.loads(proc2.stdout)
        assert env2["hookSpecificOutput"]["permissionDecision"] != "deny"
    events = read_audit(tmp_path)
    second = [e for e in events if e.get("reason") == "second-attempt"]
    assert second, f"expected second-attempt allow audit, got {events}"


def test_two_attempt_different_file_still_denies(tmp_path: Path) -> None:
    root = _make_test_repo(tmp_path)
    payload1 = {
        "session_id": "sess-gate-3",
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(root / "price.py"),
            "content": "def formatPrice(p):\n    return p\n",
        },
    }
    payload2 = {
        "session_id": "sess-gate-3",
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(root / "other.py"),  # different file = different key
            "content": "def formatPrice(p):\n    return p\n",
        },
    }
    p1 = run_hook(payload1, home=tmp_path, cwd=root)
    p2 = run_hook(payload2, home=tmp_path, cwd=root)
    env1 = json.loads(p1.stdout)
    env2 = json.loads(p2.stdout)
    assert env1["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert env2["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_no_matches_no_deny(tmp_path: Path) -> None:
    """When extracted symbols have no project hits, pass through without denying."""
    root = _make_test_repo(tmp_path)
    payload = {
        "session_id": "sess-no-match",
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(root / "fresh.py"),
            "content": "def completelyUniqueWidgetName(p):\n    return p\n",
        },
    }
    proc = run_hook(payload, home=tmp_path, cwd=root)
    assert proc.returncode == 0
    if proc.stdout.strip():
        env = json.loads(proc.stdout)
        assert env["hookSpecificOutput"]["permissionDecision"] != "deny"


# --- End-to-end: extracted symbols flow through to audit on supported files ---


def test_extracted_symbols_recorded_in_audit(tmp_path: Path) -> None:
    """Extracted symbols appear in the audit event regardless of allow/deny outcome."""
    root = tmp_path / "isolated"
    root.mkdir()
    payload = {
        "session_id": "sess-extract",
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(root / "price.py"),
            "content": "def formatPriceUnique(p):\n    return p\n\nclass UniquePricingThing:\n    pass\n",
        },
    }
    proc = run_hook(payload, home=tmp_path, cwd=root)
    assert proc.returncode == 0
    events = read_audit(tmp_path)
    symbol_events = [e for e in events if e.get("symbols")]
    assert symbol_events, f"expected event carrying symbols, got {events}"
    last = symbol_events[-1]
    assert "formatPriceUnique" in last["symbols"]
    assert "UniquePricingThing" in last["symbols"]
    assert last["phase"] == "echo"


def test_no_symbols_extracted_audits_no_symbols_reason(tmp_path: Path) -> None:
    payload = {
        "session_id": "sess-no-syms",
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(tmp_path / "src" / "empty.py"),
            "content": "# only a comment\n",
        },
    }
    proc = run_hook(payload, home=tmp_path)
    assert proc.returncode == 0
    events = read_audit(tmp_path)
    allow = [e for e in events if e.get("decision") == "allow"]
    assert allow, f"expected allow event, got {events}"
    assert allow[-1]["reason"] == "no-symbols"
    assert allow[-1]["symbols"] == []


# --- Skip path never emits deny envelope ---


def test_skip_does_not_emit_deny_envelope(tmp_path: Path) -> None:
    payload = {
        "session_id": "sess-allow",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(tmp_path / "src" / "doc.md"),
            "old_string": "x",
            "new_string": "y",
        },
    }
    proc = run_hook(payload, home=tmp_path)
    assert proc.returncode == 0
    if proc.stdout.strip():
        envelope = json.loads(proc.stdout)
        assert (
            envelope.get("hookSpecificOutput", {}).get("permissionDecision") != "deny"
        ), "skip path must not deny"


# --- Deny payload attribution: pinned to rules-library/ after the catalog move ---


def test_build_deny_envelope_attribution_cites_new_catalog_path() -> None:
    mod = _import_hook_module()
    matches = [
        {"symbol": "formatPrice", "file": "src/util.py", "line": 42, "score": "strong"},
    ]
    env = mod.build_deny_envelope(matches)
    reason = env["hookSpecificOutput"]["permissionDecisionReason"]
    assert "Rationalization (`rules-library/rationalizations.md`):" in reason
    assert "rules/rationalizations.md" not in reason, (
        f"attribution still cites the old rules/ path: {reason!r}"
    )


def test_build_deny_envelope_excerpt_line_format_pinned() -> None:
    """The quoted excerpt line directly under the attribution keeps its exact
    shape: `> "<excuse>". Why it's wrong: <why> Counter-action: <counter>`."""
    import re

    mod = _import_hook_module()
    matches = [
        {"symbol": "formatPrice", "file": "src/util.py", "line": 42, "score": "strong"},
    ]
    env = mod.build_deny_envelope(matches)
    reason = env["hookSpecificOutput"]["permissionDecisionReason"]
    lines = reason.splitlines()
    attribution_idx = next(
        (
            i
            for i, line in enumerate(lines)
            if line.strip() == "Rationalization (`rules-library/rationalizations.md`):"
        ),
        None,
    )
    assert attribution_idx is not None, f"attribution line not found in: {reason!r}"
    excerpt_line = lines[attribution_idx + 1].strip()
    pattern = r'^> ".+"\. Why it\'s wrong: .+ Counter-action: .+$'
    assert re.match(pattern, excerpt_line), (
        f"excerpt line format changed: {excerpt_line!r}"
    )


# --- Real dispatch regression: one PreToolUse Edit costs one git spawn ---


def _git_toplevel_call_counter(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Patch subprocess.run to count resolve_toplevel-shaped
    (`-C <dir> rev-parse --show-toplevel`) spawns into a mutable counter."""
    calls = [0]
    original_run = subprocess.run

    def counting_run(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args")
        if cmd and "-C" in cmd and "rev-parse" in cmd and "--show-toplevel" in cmd:
            calls[0] += 1
        return original_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", counting_run)
    return calls


def _prepare_edit_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Prepare one PreToolUse Edit dispatch and return its JSON payload.

    Side effects beyond building the payload: points HOME at tmp_path,
    inserts the hooks dir onto sys.path so handler modules can import their
    siblings, git-inits a fresh temp repo, and clears the shared
    `_common._TOPLEVEL_CACHE` so the dispatch under test starts cold.
    """
    hooks_dir = HOOK.parent
    monkeypatch.setenv("HOME", str(tmp_path))
    if str(hooks_dir) not in sys.path:
        sys.path.insert(0, str(hooks_dir))

    import _common

    _common._TOPLEVEL_CACHE.clear()

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo)],
        check=True,
        capture_output=True,
    )
    target = repo / "src" / "widget.py"  # parent dir does not exist yet
    payload = {
        "session_id": "sess-shared-toplevel",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(target),
            "old_string": "pass",
            "new_string": "def widgetFactory():\n    pass\n",
        },
    }
    return json.dumps(payload)


def _invoked_route_names(monkeypatch: pytest.MonkeyPatch, dispatch) -> list[str]:
    """Patch dispatch._invoke to record each route name it actually runs, so
    the test can positively confirm both target handlers were dispatched."""
    names: list[str] = []
    original_invoke = dispatch._invoke

    def recording_invoke(route, payload):
        names.append(route.name)
        return original_invoke(route, payload)

    monkeypatch.setattr(dispatch, "_invoke", recording_invoke)
    return names


def test_single_edit_dispatch_spawns_git_rev_parse_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    """One PreToolUse Edit dispatched through dispatch.main("pre") -- which
    runs every ROUTES handler matching Edit|Write|MultiEdit, each isolated by
    dispatch's own per-handler `_invoke` -- must spawn `_common.
    resolve_toplevel`'s `git -C <dir> rev-parse --show-toplevel` at most once
    total (PRD 00133 finding 42). Also asserts cartographer-echo was actually
    dispatched and did not fault -- a crash is caught and swallowed by
    `_invoke` per handler, so a naive spawn-count check alone would stay green
    even if cartographer-echo crashed before resolving.

    NARROWED, and honestly so: this used to prove the spawn was shared ACROSS
    two in-process handlers, enforce_prd_location and cartographer-echo, via
    `_common._TOPLEVEL_CACHE`. enforce_prd_location is now a separate hook
    process registered by the autopilot plugin, so it cannot share that cache
    at all and spawns its own `git rev-parse` per tool call. cartographer-echo
    is the only `resolve_toplevel` consumer left on this route, so what remains
    here is the weaker single-handler claim: it resolves once, not per file.
    The cross-handler guarantee finding 42 secured is gone, not merely untested.

    Scoped to `-C`-shaped calls: cartographer-echo's handler also spawns a
    separate, out-of-scope `git rev-parse --show-toplevel` (no `-C`,
    cwd-relative) via `_cartographer_identity.project_hash()`.
    """
    import io

    import dispatch

    stdin_json = _prepare_edit_dispatch(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_json))
    calls = _git_toplevel_call_counter(monkeypatch)
    invoked = _invoked_route_names(monkeypatch, dispatch)

    with pytest.raises(SystemExit):
        dispatch.main("pre")

    assert calls[0] == 1, (
        f"expected exactly one _common.resolve_toplevel git spawn across "
        f"all dispatched handlers, got {calls[0]}"
    )
    assert "cartographer-echo" in invoked, (
        f"expected cartographer-echo to actually be dispatched, got {invoked}"
    )
    assert "enforce_prd_location" not in invoked, (
        f"enforce_prd_location is the autopilot plugin's hook now; routing it "
        f"here as well would fire it twice per tool call, got {invoked}"
    )
    out, err = capsys.readouterr()
    combined = out + err
    assert "Traceback" not in combined, combined
    assert "[dispatch] cartographer-echo:" not in combined, combined


def test_build_deny_envelope_surrounding_lines_unchanged_by_catalog_move() -> None:
    """The catalog move only rewords the attribution's path; the leading Echo
    line, the 'Existing implementation' line, and the trailing retry line must
    stay exactly as before."""
    mod = _import_hook_module()
    matches = [
        {"symbol": "formatPrice", "file": "src/util.py", "line": 42, "score": "strong"},
    ]
    env = mod.build_deny_envelope(matches)
    reason = env["hookSpecificOutput"]["permissionDecisionReason"]
    lines = [line.strip() for line in reason.splitlines() if line.strip()]
    assert lines[0] == "Echo: `formatPrice` likely duplicates `src/util.py:42`."
    assert (
        "Existing implementation is at `src/util.py:42` — import it instead of writing a parallel one."
        in lines
    )
    assert (
        lines[-1] == "If this is genuinely new, retry — the second attempt will pass."
    )


# --- rationalization reachability through the deny message (PRD 00157) ---


def _use_synthetic_catalog(
    monkeypatch: pytest.MonkeyPatch,
    path: Path,
    body: str,
) -> None:
    """Point the catalog module at a one-test synthetic catalog (auto-restored)."""
    path.write_text(body, encoding="utf-8")
    monkeypatch.setattr(_echo_catalog, "_RATIONALIZATIONS_PATH", path)
    monkeypatch.setattr(_echo_catalog, "_RATIONALIZATIONS_CACHE", None)


def test_appended_catalog_entry_is_cited_by_deny_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An entry appended to the bottom of the catalog must be reachable through
    its own trigger terms, without being moved to the top and with no code
    change. Fails while the selector falls back to the first entry in file
    order."""
    mod = _import_hook_module()
    _use_synthetic_catalog(
        monkeypatch,
        tmp_path / "rationalizations.md",
        '### "First entry"\n\n'
        "- **Why it's wrong**: first why.\n"
        "- **Counter-action**: first counter.\n\n"
        '### "Appended entry"\n\n'
        "- **Why it's wrong**: appended why.\n"
        "- **Counter-action**: appended counter.\n"
        "- **Triggers**: frobnicate\n",
    )
    matches = [
        {
            "symbol": "frobnicate_widget",
            "file": "src/w.py",
            "line": 7,
            "score": "strong",
        },
    ]
    env = mod.build_deny_envelope(matches)
    reason = env["hookSpecificOutput"]["permissionDecisionReason"]
    assert "Appended entry" in reason, reason
    assert "appended why" in reason, reason


def test_no_trigger_match_renders_deny_without_rationalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no entry's triggers match, the deny must render with no
    rationalization block at all — an irrelevant excuse is worse than none."""
    mod = _import_hook_module()
    _use_synthetic_catalog(
        monkeypatch,
        tmp_path / "rationalizations.md",
        '### "Only entry"\n\n'
        "- **Why it's wrong**: only why.\n"
        "- **Counter-action**: only counter.\n"
        "- **Triggers**: frobnicate\n",
    )
    matches = [
        {"symbol": "load_config", "file": "src/c.py", "line": 3, "score": "strong"},
    ]
    env = mod.build_deny_envelope(matches)
    reason = env["hookSpecificOutput"]["permissionDecisionReason"]
    assert env["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "Rationalization" not in reason, reason
    assert not any(line.startswith(">") for line in reason.splitlines()), reason
    assert "load_config" in reason
    assert reason.splitlines()[-1] == (
        "If this is genuinely new, retry — the second attempt will pass."
    )
