"""End-to-end tests for hooks/cartographer-echo.py — PreToolUse duplicate-detection gate.

Subprocess-driven: every test runs the hook as `python3 cartographer-echo.py`
with HOME redirected to tmp_path (`echo_test_helpers.run_hook`) so the audit
log and session-state I/O never touch the real ~/.claude/. The hook exits 0
on every path (allow vs deny is signaled via the stdout JSON envelope,
mirroring gateguard-fact-force.py). In-process `handle()`/`main()` tests live
in test_echo_handle.py; the deny envelope's tests in test_echo_envelope.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from .echo_test_helpers import HOOK, read_audit, run_hook

_REQUIRED_AUDIT_KEYS = {
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


def _skip_events(home: Path, reason: str) -> list[dict]:
    return [
        e
        for e in read_audit(home)
        if e.get("decision") == "skip" and e.get("reason") == reason
    ]


def _edit_payload(session: str, file_path: Path) -> dict:
    return {
        "session_id": session,
        "tool_name": "Edit",
        "tool_input": {"file_path": str(file_path), "old_string": "x", "new_string": "y"},
    }


# --- Hook file exists ---


def test_hook_file_exists() -> None:
    assert HOOK.is_file(), f"missing: {HOOK}"


# --- Skip: settings.json ---


def test_skip_claude_settings_json(tmp_path: Path) -> None:
    payload = _edit_payload("sess-test-settings", tmp_path / ".claude" / "settings.json")
    proc = run_hook(payload, home=tmp_path)
    assert proc.returncode == 0
    if proc.stdout.strip():
        envelope = json.loads(proc.stdout)
        assert (
            envelope.get("hookSpecificOutput", {}).get("permissionDecision") != "deny"
        )
    skip = _skip_events(tmp_path, "settings")
    assert len(skip) == 1, f"expected 1 skip:settings event, got {read_audit(tmp_path)}"
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
    assert len(_skip_events(tmp_path, "large-file")) == 1


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
    payload = _edit_payload("sess-nts", tmp_path / "src" / "foo.py")
    proc = run_hook(payload, home=tmp_path, env_extra={"PYTHONPATH": str(shim)})
    assert proc.returncode == 0
    skip = _skip_events(tmp_path, "no-tree-sitter")
    assert len(skip) == 1, f"expected skip:no-tree-sitter, got {read_audit(tmp_path)}"


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
    payload = _edit_payload("sess-test-file", tmp_path / rel_path)
    proc = run_hook(payload, home=tmp_path)
    assert proc.returncode == 0
    skip = _skip_events(tmp_path, "test-file")
    assert len(skip) == 1, (
        f"expected skip:test-file for {rel_path}, got {read_audit(tmp_path)}"
    )


# --- Skip: unsupported extensions ---


@pytest.mark.parametrize("ext", [".md", ".yaml", ".json", ".toml", ".sh", ".txt", ""])
def test_skip_unsupported_ext(tmp_path: Path, ext: str) -> None:
    payload = _edit_payload("sess-unsupp", tmp_path / f"src/file{ext}")
    proc = run_hook(payload, home=tmp_path)
    assert proc.returncode == 0
    skip = _skip_events(tmp_path, "unsupported-ext")
    assert len(skip) == 1, (
        f"expected skip:unsupported-ext for ext={ext!r}, got {read_audit(tmp_path)}"
    )


# --- Malformed / empty stdin: no crash ---


@pytest.mark.parametrize("stdin_text", ["this is not json {", ""])
def test_malformed_or_empty_stdin_no_crash(tmp_path: Path, stdin_text: str) -> None:
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin_text,
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
    payload = _edit_payload("sess-schema", tmp_path / "src" / "x.md")
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


def _audit_probe_payloads(tmp_path: Path) -> list[dict]:
    """One payload per decision class: skip (ext), skip (settings), allow (bash), allow (write)."""
    return [
        _edit_payload("s1", tmp_path / "a.md"),
        _edit_payload("s1", tmp_path / ".claude" / "settings.json"),
        {"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "ls -la"}},
        {
            "session_id": "s1",
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_path / "iso" / "fresh.py"),
                "content": "def somethingTotallyUniqueZZZ(): pass\n",
            },
        },
    ]


def test_audit_every_event_has_required_keys(tmp_path: Path) -> None:
    """Run a sequence of payloads covering allow/deny/skip; every event has required keys."""
    (tmp_path / "iso").mkdir()
    for p in _audit_probe_payloads(tmp_path):
        run_hook(p, home=tmp_path, cwd=tmp_path)
    events = read_audit(tmp_path)
    assert events, "no events written"
    for e in events:
        # tree_sitter_missing warnings have only `ts` + `event` keys; skip those.
        if "decision" not in e:
            continue
        missing = _REQUIRED_AUDIT_KEYS - set(e.keys())
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


# --- two-attempt deny gate (end-to-end via subprocess) ---


def _make_test_repo(tmp_path: Path) -> Path:
    """Make a minimal directory layout with one duplicate-target file."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "util.py").write_text("def formatPrice(p):\n    return p\n")
    return root


def _write_payload(session: str, file_path: Path, content: str) -> dict:
    return {
        "session_id": session,
        "tool_name": "Write",
        "tool_input": {"file_path": str(file_path), "content": content},
    }


def test_two_attempt_first_call_denies(tmp_path: Path) -> None:
    root = _make_test_repo(tmp_path)
    payload = _write_payload(
        "sess-gate-1", root / "price.py", "def formatPrice(p):\n    return f'${p}'\n"
    )
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
    payload = _write_payload(
        "sess-gate-2", root / "price.py", "def formatPrice(p):\n    return f'${p}'\n"
    )
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
    content = "def formatPrice(p):\n    return p\n"
    payload1 = _write_payload("sess-gate-3", root / "price.py", content)
    # different file = different key
    payload2 = _write_payload("sess-gate-3", root / "other.py", content)
    p1 = run_hook(payload1, home=tmp_path, cwd=root)
    p2 = run_hook(payload2, home=tmp_path, cwd=root)
    env1 = json.loads(p1.stdout)
    env2 = json.loads(p2.stdout)
    assert env1["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert env2["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_no_matches_no_deny(tmp_path: Path) -> None:
    """When extracted symbols have no project hits, pass through without denying."""
    root = _make_test_repo(tmp_path)
    payload = _write_payload(
        "sess-no-match",
        root / "fresh.py",
        "def completelyUniqueWidgetName(p):\n    return p\n",
    )
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
    payload = _write_payload(
        "sess-extract",
        root / "price.py",
        "def formatPriceUnique(p):\n    return p\n\nclass UniquePricingThing:\n    pass\n",
    )
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
    payload = _write_payload(
        "sess-no-syms", tmp_path / "src" / "empty.py", "# only a comment\n"
    )
    proc = run_hook(payload, home=tmp_path)
    assert proc.returncode == 0
    events = read_audit(tmp_path)
    allow = [e for e in events if e.get("decision") == "allow"]
    assert allow, f"expected allow event, got {events}"
    assert allow[-1]["reason"] == "no-symbols"
    assert allow[-1]["symbols"] == []


# --- Skip path never emits deny envelope ---


def test_skip_does_not_emit_deny_envelope(tmp_path: Path) -> None:
    payload = _edit_payload("sess-allow", tmp_path / "src" / "doc.md")
    proc = run_hook(payload, home=tmp_path)
    assert proc.returncode == 0
    if proc.stdout.strip():
        envelope = json.loads(proc.stdout)
        assert (
            envelope.get("hookSpecificOutput", {}).get("permissionDecision") != "deny"
        ), "skip path must not deny"
