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


# --- Stopword filter ---


def test_stopword_filter_preserves_duplicate_prone_verbs() -> None:
    mod = _import_hook_module()
    syms = ["format", "parse", "validate", "normalize", "serialize", "transform"]
    out = mod.filter_stopwords(syms, "/abs/src/x.py")
    assert set(out) == set(syms), f"in-scope verbs must survive, got {out}"


@pytest.mark.parametrize(
    "stopword",
    [
        "__init__", "__main__", "main", "init", "setup", "run", "start", "stop",
        "new", "default", "clone", "eq", "hash", "to_string", "from_string",
    ],
)
def test_stopword_filter_drops_stopwords(stopword: str) -> None:
    mod = _import_hook_module()
    out = mod.filter_stopwords([stopword, "format_price"], "/abs/src/x.py")
    assert stopword not in out
    assert "format_price" in out


def test_stopword_filter_drops_short_names() -> None:
    mod = _import_hook_module()
    out = mod.filter_stopwords(["a", "ab", "abc", "abcd", "abcde"], "/abs/src/x.py")
    # Length <= 3 dropped; 4 and 5 retained.
    assert "abcd" in out
    assert "abcde" in out
    assert "abc" not in out
    assert "ab" not in out
    assert "a" not in out


@pytest.mark.parametrize(
    "rel_path",
    [
        "/abs/tests/x.py",
        "/abs/test/x.py",
        "/abs/src/foo_test.go",
        "/abs/src/widget.test.ts",
        "/abs/src/widget.test.tsx",
        "/abs/src/widget.test.js",
        "/abs/src/widget.test.jsx",
    ],
)
def test_stopword_filter_test_path_returns_empty(rel_path: str) -> None:
    mod = _import_hook_module()
    out = mod.filter_stopwords(["formatPrice", "parse", "validate"], rel_path)
    assert out == [], f"test-file path must return [], got {out} for {rel_path}"


# --- ripgrep candidate search ---


def test_search_candidates_finds_definition_elsewhere(tmp_path: Path) -> None:
    """A symbol defined in one file is found when searching from another."""
    mod = _import_hook_module()
    root = tmp_path / "proj"
    root.mkdir()
    (root / "util.py").write_text("def formatPrice(p):\n    return f'${p}'\n")
    target = root / "price.py"
    target.write_text("# target file\n")
    candidates = mod.search_candidates("formatPrice", root, target)
    assert candidates, f"expected at least one candidate, got {candidates}"
    assert candidates[0]["file"].endswith("util.py")
    assert "formatPrice" in candidates[0]["snippet"]
    assert candidates[0]["line"] == 1


def test_search_candidates_excludes_target_file(tmp_path: Path) -> None:
    mod = _import_hook_module()
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "price.py"
    target.write_text("def formatPrice(p):\n    return p\n")
    # Only target file mentions the symbol — must be excluded.
    candidates = mod.search_candidates("formatPrice", root, target)
    assert candidates == []


def test_search_candidates_skips_build_dirs(tmp_path: Path) -> None:
    mod = _import_hook_module()
    root = tmp_path / "proj"
    (root / "node_modules" / "x").mkdir(parents=True)
    (root / "node_modules" / "x" / "pkg.js").write_text("function formatPrice(){}\n")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("formatPrice\n")
    target = root / "main.js"
    target.write_text("// target\n")
    candidates = mod.search_candidates("formatPrice", root, target)
    assert candidates == [], f"build dirs must be skipped, got {candidates}"


def test_search_candidates_returns_empty_when_rg_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """If `rg` is unavailable, returns [] without crashing."""
    mod = _import_hook_module()
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "x.py"
    target.write_text("# target\n")
    # Force subprocess.run to raise FileNotFoundError as if rg were missing.
    import subprocess as _sp
    monkeypatch.setattr(_sp, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    out = mod.search_candidates("formatPrice", root, target)
    assert out == []


def test_search_candidates_timeout_returns_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _import_hook_module()
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "x.py"
    target.write_text("# target\n")
    import subprocess as _sp
    def fake_run(*args, **kwargs):
        raise _sp.TimeoutExpired(cmd=args[0], timeout=1.0)
    monkeypatch.setattr(_sp, "run", fake_run)
    out = mod.search_candidates("formatPrice", root, target)
    assert out == []


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


# --- match scoring ---


def test_score_match_strong_exact_token() -> None:
    mod = _import_hook_module()
    cand = {"file": "u.py", "line": 1, "snippet": "def formatPrice(p):"}
    assert mod.score_match("formatPrice", cand) == "strong"


def test_score_match_strong_distinguishes_substring() -> None:
    """Substring-only matches must NOT be classified as strong."""
    mod = _import_hook_module()
    cand = {"file": "u.py", "line": 1, "snippet": "def formatPriceTag(p):"}
    assert mod.score_match("formatPrice", cand) != "strong"


def test_score_match_medium_levenshtein_within_2() -> None:
    mod = _import_hook_module()
    cand = {"file": "u.py", "line": 1, "snippet": "def formatPric(p):"}  # distance 1
    assert mod.score_match("formatPrice", cand) == "medium"


def test_score_match_weak_long_substring_overlap() -> None:
    mod = _import_hook_module()
    cand = {"file": "u.py", "line": 1, "snippet": "def priceFormatter(p):"}  # shares "Format" (6+ via case-insensitive? we'll require literal)
    # The snippet contains the literal "Format" - 6 chars shared with "formatPrice".
    # Test the case-insensitive contiguous overlap directly:
    cand2 = {"file": "u.py", "line": 1, "snippet": "def priceformatter(p):"}
    assert mod.score_match("formatPrice", cand2) == "weak"


def test_score_match_none_when_no_overlap() -> None:
    mod = _import_hook_module()
    cand = {"file": "u.py", "line": 1, "snippet": "def xyz(): return 1"}
    assert mod.score_match("formatPrice", cand) is None


def test_decide_blocks_on_strong() -> None:
    mod = _import_hook_module()
    groups = {
        "formatPrice": [{"file": "u.py", "line": 1, "snippet": "def formatPrice(p):"}],
    }
    decision, matches = mod.decide(["formatPrice"], groups)
    assert decision == "deny"
    assert matches and matches[0]["score"] == "strong"
    assert matches[0]["symbol"] == "formatPrice"


def test_decide_blocks_on_medium() -> None:
    mod = _import_hook_module()
    groups = {
        "formatPrice": [{"file": "u.py", "line": 1, "snippet": "def formatPric(p):"}],
    }
    decision, matches = mod.decide(["formatPrice"], groups)
    assert decision == "deny"
    assert matches[0]["score"] == "medium"


def test_decide_allows_on_weak_only() -> None:
    mod = _import_hook_module()
    groups = {
        "formatPrice": [{"file": "u.py", "line": 1, "snippet": "def priceformatter(p):"}],
    }
    decision, matches = mod.decide(["formatPrice"], groups)
    assert decision == "allow"
    # Weak matches are NOT included in deny matches list (which is for the envelope).
    assert matches == []


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
