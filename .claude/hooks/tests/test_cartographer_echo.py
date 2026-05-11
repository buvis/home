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
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "cartographer-echo.py"


def _import_hook_module():
    """Import the hook by file path (hyphenated filename can't use `import`)."""
    spec = importlib.util.spec_from_file_location("cartographer_echo_mod", HOOK)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def run_hook(
    payload: dict, home: Path, cwd: Path | None = None, env_extra: dict | None = None
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
    log = home / ".claude" / "cartographer" / "audit.jsonl"
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
    skip = [e for e in events if e.get("decision") == "skip" and e.get("reason") == "settings"]
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
    skip = [e for e in events if e.get("decision") == "skip" and e.get("reason") == "large-file"]
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
        "sys.meta_path.insert(0, _Blocker())\n"
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
    skip = [e for e in events if e.get("decision") == "skip" and e.get("reason") == "no-tree-sitter"]
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
    skip = [e for e in events if e.get("decision") == "skip" and e.get("reason") == "test-file"]
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
    assert len(skip) == 1, f"expected skip:unsupported-ext for ext={ext!r}, got {events}"


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


# --- Symbol extraction (unit tests) ---


@pytest.mark.parametrize(
    "ext, content, expected_subset",
    [
        (
            ".py",
            "def format_price():\n    pass\n\nclass Pricing:\n    def parse(self):\n        pass\n",
            {"format_price", "Pricing", "parse"},
        ),
        (
            ".ts",
            "export function formatPrice(): number { return 1; }\n"
            "export class Widget { parseAmount() {} normalize() {} }\n",
            {"formatPrice", "Widget", "parseAmount", "normalize"},
        ),
        (
            ".tsx",
            "function App() { return null; }\n"
            "class Card { format() {} }\n",
            {"App", "Card", "format"},
        ),
        (
            ".js",
            "function transform(x) { return x; }\n"
            "class Box { serialize() {} }\n",
            {"transform", "Box", "serialize"},
        ),
        (
            ".jsx",
            "function Hello() { return null; }\n",
            {"Hello"},
        ),
        (
            ".rs",
            "fn validate() {}\n"
            "struct Order { id: u32 }\n"
            "impl Order { fn parse(&self) {} }\n"
            "enum Status { Open, Closed }\n",
            {"validate", "parse", "Status"},
        ),
        (
            ".go",
            "package main\nfunc Format() {}\ntype Order struct{ ID int }\n",
            {"Format", "Order"},
        ),
    ],
)
def test_extract_symbols_per_language(ext: str, content: str, expected_subset: set[str]) -> None:
    mod = _import_hook_module()
    syms = set(mod.extract_symbols(content, ext))
    missing = expected_subset - syms
    assert not missing, f"missing expected symbols for {ext}: {missing} (got {syms})"


def test_extract_symbols_unsupported_extension_returns_empty() -> None:
    mod = _import_hook_module()
    assert mod.extract_symbols("anything at all", ".md") == []
    assert mod.extract_symbols("anything", ".unknown") == []


def test_extract_symbols_empty_content_returns_empty() -> None:
    mod = _import_hook_module()
    assert mod.extract_symbols("", ".py") == []


def test_extract_symbols_dedupes_preserving_order() -> None:
    mod = _import_hook_module()
    content = "def foo():\n    pass\n\ndef foo():\n    pass\n\ndef bar():\n    pass\n"
    out = mod.extract_symbols(content, ".py")
    assert out.count("foo") == 1
    assert out.index("foo") < out.index("bar")


def test_extract_symbols_anonymous_arrow_not_included() -> None:
    mod = _import_hook_module()
    content = "const x = () => 1;\nfunction named() {}\n"
    syms = mod.extract_symbols(content, ".js")
    assert "named" in syms
    # Anonymous functions (no identifier) must not contribute symbols.
    assert all(s and isinstance(s, str) for s in syms)


# --- End-to-end: extracted symbols flow through to audit on supported files ---


def test_extracted_symbols_recorded_in_audit(tmp_path: Path) -> None:
    """When a supported file passes all skip rules, the audit event lists symbols."""
    payload = {
        "session_id": "sess-extract",
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(tmp_path / "src" / "price.py"),
            "content": "def format_price():\n    pass\n\nclass Pricing:\n    pass\n",
        },
    }
    proc = run_hook(payload, home=tmp_path)
    assert proc.returncode == 0
    events = read_audit(tmp_path)
    allow_events = [e for e in events if e.get("decision") == "allow"]
    assert allow_events, f"expected at least one allow event, got {events}"
    last = allow_events[-1]
    assert "format_price" in last["symbols"]
    assert "Pricing" in last["symbols"]
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
