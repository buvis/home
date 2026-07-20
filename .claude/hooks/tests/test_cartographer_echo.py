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
import time
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


def test_search_candidates_ranks_definition_first(tmp_path: Path) -> None:
    """With many usage sites and one definition, the definition is not dropped.

    Usage sites outnumber the hit cap; the definition lives in another file.
    Definition-first ranking must surface it at position 0 regardless of rg
    order, so the duplicate is never lost behind unrelated call sites.
    """
    mod = _import_hook_module()
    root = tmp_path / "proj"
    root.mkdir()
    usage_lines = "\n".join(f"    total{i} = aggregate_query(pool)" for i in range(8))
    (root / "callers.py").write_text(usage_lines + "\n")
    (root / "queries.py").write_text("def aggregate_query(pool):\n    return pool\n")
    target = root / "new.py"
    target.write_text("# target\n")
    candidates = mod.search_candidates("aggregate_query", root, target)
    assert candidates, "expected candidates"
    assert mod._defined_name(candidates[0]["snippet"]) == "aggregate_query"


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


def test_search_candidates_batch_groups_by_symbol(tmp_path: Path) -> None:
    """One rg over an alternation attributes each hit to the right symbol group,
    and the single-symbol group matches the search_candidates wrapper (PRD 00088 R3)."""
    mod = _import_hook_module()
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("def format_price(p):\n    return p\n")
    (root / "b.py").write_text("class Widget:\n    def parse(self):\n        pass\n")
    target = root / "new.py"
    target.write_text("# target\n")

    groups = mod.search_candidates_batch(
        ["format_price", "Widget", "parse", "absent_sym"], root, target
    )

    assert any(h["file"].endswith("a.py") for h in groups["format_price"])
    assert any(h["file"].endswith("b.py") for h in groups["Widget"])
    assert any(h["file"].endswith("b.py") for h in groups["parse"])
    assert groups["absent_sym"] == []
    # one rg over the batch matches what a per-symbol search would find
    assert groups["format_price"] == mod.search_candidates("format_price", root, target)


@pytest.mark.integration
def test_search_candidates_batch_p95_under_hook_budget(tmp_path: Path) -> None:
    """30 symbols resolve in ONE rg spawn well under the 5s hook budget — the
    per-symbol version spawned 30 subprocesses and could blow it (PRD 00088 R3)."""
    mod = _import_hook_module()
    root = tmp_path / "proj"
    root.mkdir()
    symbols = [f"sym_{i}" for i in range(30)]
    for f in range(6):
        parts = []
        for i in range(f * 5, f * 5 + 5):
            parts.append(f"def sym_{i}(x):\n    return x\n")
            parts.extend(f"    y = sym_{i}(z)\n" for _ in range(3))  # usage sites
        (root / f"mod_{f}.py").write_text("".join(parts))
    target = root / "new.py"
    target.write_text("# target\n")

    durations: list[float] = []
    groups: dict[str, list[dict]] = {}
    for _ in range(20):
        start = time.perf_counter()
        groups = mod.search_candidates_batch(symbols, root, target)
        durations.append(time.perf_counter() - start)

    assert all(groups[s] for s in symbols), "every symbol must have at least one hit"
    durations.sort()
    p95 = durations[int(len(durations) * 0.95) - 1]  # 19th of 20 runs
    assert p95 < 2.0, f"p95 {p95:.3f}s exceeded the budget (the hook cap is 5s)"


# --- Direct-call coverage (handle / main bypass subprocess for line coverage) ---


def _isolate_hook_for_direct_call(monkeypatch: pytest.MonkeyPatch, home: Path) -> object:
    """Import the hook with HOME pointed at a tmp dir and lib cache cleared."""
    monkeypatch.setenv("HOME", str(home))
    # Force fresh import of lib + hook
    for name in ("_lib_cartographer", "cartographer_echo_mod"):
        if name in sys.modules:
            del sys.modules[name]
    return _import_hook_module()


def test_handle_direct_call_unknown_tool_no_audit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _isolate_hook_for_direct_call(monkeypatch, tmp_path)
    mod.handle({"tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}, "session_id": "s"})
    events = read_audit(tmp_path)
    assert all(e.get("tool") != "Read" for e in events)


def test_handle_direct_call_edit_skip_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _isolate_hook_for_direct_call(monkeypatch, tmp_path)
    mod.handle({
        "tool_name": "Edit",
        "tool_input": {"file_path": str(tmp_path / ".claude" / "settings.json"), "old_string": "x", "new_string": "y"},
        "session_id": "s",
    })
    events = read_audit(tmp_path)
    assert any(e.get("reason") == "settings" for e in events)


def test_handle_direct_call_bash_clean(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _isolate_hook_for_direct_call(monkeypatch, tmp_path)
    mod.handle({"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "session_id": "s"})
    events = read_audit(tmp_path)
    assert any(e.get("reason") == "bash-clean" for e in events)


def test_handle_direct_call_write_no_symbols(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _isolate_hook_for_direct_call(monkeypatch, tmp_path)
    iso = tmp_path / "iso"
    iso.mkdir()
    mod.handle({
        "tool_name": "Write",
        "tool_input": {"file_path": str(iso / "x.py"), "content": "# comment only\n"},
        "session_id": "s",
    })
    events = read_audit(tmp_path)
    assert any(e.get("reason") == "no-symbols" for e in events)


def test_extract_content_multiedit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = _isolate_hook_for_direct_call(monkeypatch, tmp_path)
    out = mod.extract_content(
        "MultiEdit",
        {"edits": [{"new_string": "def foo(): pass"}, {"new_string": "def bar(): pass"}]},
    )
    assert "foo" in out and "bar" in out


def test_extract_content_unknown_tool_empty() -> None:
    mod = _import_hook_module()
    assert mod.extract_content("Unknown", {"content": "x"}) == ""


def test_deny_key_deterministic() -> None:
    mod = _import_hook_module()
    a = mod.deny_key("/a.py", ["foo", "bar"])
    b = mod.deny_key("/a.py", ["bar", "foo"])  # sorted order
    assert a == b
    assert len(a) == 24


def test_handle_direct_call_bash_bypass_deny_and_retry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
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


def test_handle_direct_call_edit_deny_and_retry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
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


def test_main_function_parses_stdin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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


def test_rationalizations_parsed_from_rules_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The rationalizations parser must successfully load real rule file content."""
    mod = _import_hook_module()
    # Clear cache so loader actually runs.
    mod._RATIONALIZATIONS_CACHE = None
    rats = mod._load_rationalizations()
    assert "Quick fix, skip atlas" in rats or "Couldn't find existing helper" in rats


# --- Audit schema completeness ---


def test_audit_every_event_has_required_keys(tmp_path: Path) -> None:
    """Run a sequence of payloads covering allow/deny/skip; every event has required keys."""
    payloads = [
        # Skip: unsupported ext
        {"session_id": "s1", "tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / "a.md"), "old_string": "x", "new_string": "y"}},
        # Skip: settings.json
        {"session_id": "s1", "tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / ".claude" / "settings.json"), "old_string": "x", "new_string": "y"}},
        # Bash clean
        {"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "ls -la"}},
        # Write supported ext with no project hits
        {"session_id": "s1", "tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "iso" / "fresh.py"), "content": "def somethingTotallyUniqueZZZ(): pass\n"}},
    ]
    (tmp_path / "iso").mkdir()
    required = {"ts", "session", "tool", "file", "decision", "reason", "symbols", "matches", "phase"}
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
    deny = [e for e in events if e.get("decision") == "deny" and e.get("reason") == "bash-bypass"]
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


# --- Bash bypass pattern detection ---


@pytest.mark.parametrize(
    "command, expected_pattern",
    [
        ("cat > src/util/format.ts <<EOF\nexport function formatPrice(){}\nEOF\n", "cat-redirect"),
        ("tee src/lib.py", "tee"),
        ("python3 -c \"open('src/x.py', 'w').write('...')\"", "python-open-write"),
        ("sed -i 's/foo/bar/' src/main.rs", "sed-inplace"),
        ("echo hello > out.md", "redirect-source"),
    ],
)
def test_detect_bash_bypass_positive(tmp_path: Path, command: str, expected_pattern: str) -> None:
    mod = _import_hook_module()
    # Create the dirs referenced so resolve() works inside cwd.
    (tmp_path / "src" / "util").mkdir(parents=True, exist_ok=True)
    detected = mod.detect_bash_bypass(command, tmp_path)
    assert detected is not None, f"expected {expected_pattern}, got None for {command!r}"
    assert detected[0] == expected_pattern, detected


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "cat /etc/passwd",
        "grep -r foo .",
        "git status",
        "python3 script.py --flag",
        # Outside cwd
        "cat > /tmp/scratch.py <<EOF\nx\nEOF",
    ],
)
def test_detect_bash_bypass_negative(tmp_path: Path, command: str) -> None:
    mod = _import_hook_module()
    detected = mod.detect_bash_bypass(command, tmp_path)
    assert detected is None, f"false-positive on {command!r}: {detected}"


def test_detect_bash_bypass_settings_json_skipped(tmp_path: Path) -> None:
    """Edits to ~/.claude/settings.json must not be flagged (gateguard owns it)."""
    mod = _import_hook_module()
    # Simulate a redirect to a settings.json path.
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text("{}")
    cmd = f"echo {{}} > {settings}"
    detected = mod.detect_bash_bypass(cmd, tmp_path)
    assert detected is None


# --- deny envelope with rationalization excerpt ---


def test_build_deny_envelope_shape() -> None:
    mod = _import_hook_module()
    matches = [{"symbol": "formatPrice", "file": "src/util.py", "line": 42, "score": "strong"}]
    env = mod.build_deny_envelope(matches)
    assert env["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert env["hookSpecificOutput"]["permissionDecision"] == "deny"
    reason = env["hookSpecificOutput"]["permissionDecisionReason"]
    assert "formatPrice" in reason
    assert "src/util.py:42" in reason or "`src/util.py:42`" in reason
    assert "retry" in reason.lower()


def test_build_deny_envelope_contains_rationalization_quote() -> None:
    mod = _import_hook_module()
    matches = [{"symbol": "formatPrice", "file": "src/util.py", "line": 42, "score": "strong"}]
    env = mod.build_deny_envelope(matches)
    reason = env["hookSpecificOutput"]["permissionDecisionReason"]
    # Block quote line(s) indicate the rationalization excerpt.
    assert any(line.startswith(">") for line in reason.splitlines()), reason


def test_build_deny_envelope_reason_length_capped() -> None:
    mod = _import_hook_module()
    matches = [{"symbol": "formatPrice", "file": "src/util.py", "line": 42, "score": "strong"}]
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
    matches = [{"symbol": "formatPrice", "file": "src/util.py", "line": 42, "score": "strong"}]
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


# --- Definition-aware matching: a usage site must NOT block (audit 2026-05) ---


def test_score_match_usage_site_not_strong() -> None:
    """A call/usage of the exact name is not a duplicate definition -> not blocking."""
    mod = _import_hook_module()
    cand = {"file": "u.py", "line": 1, "snippet": "total = formatPrice(item)"}
    assert mod.score_match("formatPrice", cand) != "strong"
    assert mod.score_match("formatPrice", cand) != "medium"


def test_score_match_type_annotation_not_strong() -> None:
    """Exact name in a type position (e.g. `-> Result`) must not block."""
    mod = _import_hook_module()
    cand = {"file": "u.rs", "line": 1, "snippet": "pub fn run() -> Result<(), Error> {"}
    assert mod.score_match("Result", cand) != "strong"
    assert mod.score_match("Result", cand) != "medium"


def test_score_match_strong_rust_fn() -> None:
    mod = _import_hook_module()
    cand = {"file": "u.rs", "line": 1, "snippet": "pub fn formatPrice(p: i32) -> i32 {"}
    assert mod.score_match("formatPrice", cand) == "strong"


def test_score_match_strong_go_method_receiver() -> None:
    mod = _import_hook_module()
    cand = {"file": "u.go", "line": 1, "snippet": "func (s *Svc) formatPrice(p int) int {"}
    assert mod.score_match("formatPrice", cand) == "strong"


def test_decide_allows_usage_site_only() -> None:
    mod = _import_hook_module()
    groups = {
        "aggregate_query": [
            {"file": "a.rs", "line": 1, "snippet": "let rows = aggregate_query(&pool);"},
        ],
    }
    decision, matches = mod.decide(["aggregate_query"], groups)
    assert decision == "allow"
    assert matches == []


def test_defined_name_extracts_declared_identifier() -> None:
    mod = _import_hook_module()
    assert mod._defined_name("def foo(x):") == "foo"
    assert mod._defined_name("class Bar:") == "Bar"
    assert mod._defined_name("pub fn baz() {") == "baz"
    assert mod._defined_name("func (r *T) Qux() {") == "Qux"
    assert mod._defined_name("    x = foo()") is None
    assert mod._defined_name("return formatPrice(a)") is None


def test_decide_match_records_snippet() -> None:
    """Blocking matches carry the snippet so the audit log holds the evidence."""
    mod = _import_hook_module()
    groups = {
        "formatPrice": [{"file": "u.py", "line": 1, "snippet": "def formatPrice(p):"}],
    }
    _decision, matches = mod.decide(["formatPrice"], groups)
    assert matches[0]["snippet"] == "def formatPrice(p):"


def test_decide_match_snippet_capped() -> None:
    mod = _import_hook_module()
    long_snippet = "def formatPrice(" + "x" * 500 + "):"
    groups = {"formatPrice": [{"file": "u.py", "line": 1, "snippet": long_snippet}]}
    _decision, matches = mod.decide(["formatPrice"], groups)
    assert len(matches[0]["snippet"]) == mod._SNIPPET_AUDIT_CAP


# --- Stopwords: generic names defined in many files are not duplicates ---


def test_stopword_filters_generic_names() -> None:
    mod = _import_hook_module()
    kept = mod.filter_stopwords(["create", "setUp", "Result", "extractRecurrenceId"], "a.py")
    assert kept == ["extractRecurrenceId"]


# --- pytest test_*.py prefix convention is recognized as a test file ---


def test_is_test_file_pytest_prefix() -> None:
    mod = _import_hook_module()
    assert mod.is_test_file_path("/p/test_consolidate.py") is True
    assert mod.is_test_file_path("/p/widget_test.py") is True
    assert mod.is_test_file_path("/p/consolidate.py") is False
    # Prefix rule is Python-only; a non-.py "test_" file is not matched here.
    assert mod.is_test_file_path("/p/test_thing.rs") is False


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
