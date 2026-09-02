"""Tests for hooks/_echo_search.py — ripgrep candidate search, the stopword
filter, the test-file predicate and project-root resolution for the Echo gate.

`hooks/` is on sys.path via the tests package (`tests/__init__.py`), so the
module imports by bare name. Every patch lands on a SHARED object (`shutil`,
`pathlib.Path`, `subprocess`, the cartographer lib), so all of them go through
monkeypatch; a bare assignment would leak into every later test.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import _common
import _echo_search as search
import pytest


@pytest.fixture(autouse=True)
def _fresh_rg_resolution():
    """`_resolve_rg` is an LRU cache on a module imported once per session; a
    test that resolves "no rg anywhere" would otherwise poison every later
    search. Production is unaffected: each hook call is a fresh process."""
    search._resolve_rg.cache_clear()
    yield
    search._resolve_rg.cache_clear()


# --- Test-file predicate ---


@pytest.mark.parametrize(
    "path",
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
def test_is_test_file_path_conventions(path: str) -> None:
    assert search.is_test_file_path(path) is True


def test_is_test_file_pytest_prefix() -> None:
    assert search.is_test_file_path("/p/test_consolidate.py") is True
    assert search.is_test_file_path("/p/widget_test.py") is True
    assert search.is_test_file_path("/p/consolidate.py") is False
    # Prefix rule is Python-only; a non-.py "test_" file is not matched here.
    assert search.is_test_file_path("/p/test_thing.rs") is False
    assert search.is_test_file_path("") is False


# --- Stopword filter ---


def test_stopword_filter_preserves_duplicate_prone_verbs() -> None:
    syms = ["format", "parse", "validate", "normalize", "serialize", "transform"]
    out = search.filter_stopwords(syms, "/abs/src/x.py")
    assert set(out) == set(syms), f"in-scope verbs must survive, got {out}"


@pytest.mark.parametrize(
    "stopword",
    [
        "__init__",
        "__main__",
        "main",
        "init",
        "setup",
        "run",
        "start",
        "stop",
        "new",
        "default",
        "clone",
        "eq",
        "hash",
        "to_string",
        "from_string",
    ],
)
def test_stopword_filter_drops_stopwords(stopword: str) -> None:
    out = search.filter_stopwords([stopword, "format_price"], "/abs/src/x.py")
    assert stopword not in out
    assert "format_price" in out


def test_stopword_filter_drops_short_names() -> None:
    out = search.filter_stopwords(["a", "ab", "abc", "abcd", "abcde"], "/abs/src/x.py")
    # Length <= 3 dropped; 4 and 5 retained.
    assert "abcd" in out
    assert "abcde" in out
    assert "abc" not in out
    assert "ab" not in out
    assert "a" not in out


def test_stopword_filter_test_path_returns_empty() -> None:
    out = search.filter_stopwords(
        ["formatPrice", "parse", "validate"], "/abs/tests/x.py"
    )
    assert out == [], f"test-file path must return [], got {out}"


def test_stopword_filters_generic_names() -> None:
    kept = search.filter_stopwords(
        ["create", "setUp", "Result", "extractRecurrenceId"],
        "a.py",
    )
    assert kept == ["extractRecurrenceId"]


# --- ripgrep resolution ---


def test_search_candidates_works_when_rg_is_not_on_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Candidate search must survive `rg` being a shell function, not a binary.

    Regression: a Claude Code install can expose `rg` only as a shell function
    that re-execs the host binary with argv[0]="rg". `subprocess.run(["rg",...])`
    then raises FileNotFoundError, every search returns zero candidates, and the
    duplicate-detection gate is dead while still reporting allow. Measured
    2026-08-26: 621 `ripgrep_missing` events in one day. `shutil.which` returning
    None is exactly that condition.
    """
    monkeypatch.setattr(search.shutil, "which", lambda _name: None)

    root = tmp_path / "proj"
    root.mkdir()
    (root / "util.py").write_text("def formatPrice(p):\n    return f'${p}'\n")
    target = root / "price.py"
    target.write_text("# target file\n")

    candidates = search.search_candidates("formatPrice", root, target)
    assert candidates, (
        "candidate search must fall back to the host binary when no rg is on "
        f"PATH; got {candidates} (resolved: {search._resolve_rg()!r})"
    )
    assert candidates[0]["file"].endswith("util.py")


def test_no_resolvable_ripgrep_degrades_quietly_and_audits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no rg AND no host binary, search returns [] and records why.

    The gate must fail open (never block an edit it cannot reason about) but
    must leave the `ripgrep_missing` breadcrumb that made this bug findable.
    """
    monkeypatch.setattr(search.shutil, "which", lambda _name: None)
    monkeypatch.setenv("CLAUDE_CODE_EXECPATH", str(tmp_path / "absent"))
    monkeypatch.setattr(search.Path, "home", staticmethod(lambda: tmp_path / "nohome"))
    assert search._resolve_rg() is None, "precondition: nothing resolvable"

    audit: list[dict] = []
    monkeypatch.setattr(search.lib, "append_audit", audit.append)

    root = tmp_path / "proj"
    root.mkdir()
    (root / "util.py").write_text("def formatPrice(p):\n    return 1\n")
    target = root / "price.py"
    target.write_text("# target\n")

    assert search.search_candidates("formatPrice", root, target) == []
    assert any(e.get("event") == "ripgrep_missing" for e in audit), (
        f"an unresolvable ripgrep must audit 'ripgrep_missing'; got {audit}"
    )


# --- ripgrep candidate search ---


def test_search_candidates_finds_definition_elsewhere(tmp_path: Path) -> None:
    """A symbol defined in one file is found when searching from another."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "util.py").write_text("def formatPrice(p):\n    return f'${p}'\n")
    target = root / "price.py"
    target.write_text("# target file\n")
    candidates = search.search_candidates("formatPrice", root, target)
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
    root = tmp_path / "proj"
    root.mkdir()
    usage_lines = "\n".join(f"    total{i} = aggregate_query(pool)" for i in range(8))
    (root / "callers.py").write_text(usage_lines + "\n")
    (root / "queries.py").write_text("def aggregate_query(pool):\n    return pool\n")
    target = root / "new.py"
    target.write_text("# target\n")
    candidates = search.search_candidates("aggregate_query", root, target)
    assert candidates, "expected candidates"
    assert search._defined_name(candidates[0]["snippet"]) == "aggregate_query"


def test_search_candidates_excludes_target_file(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "price.py"
    target.write_text("def formatPrice(p):\n    return p\n")
    # Only target file mentions the symbol — must be excluded.
    candidates = search.search_candidates("formatPrice", root, target)
    assert candidates == []


def test_search_candidates_skips_build_dirs(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "node_modules" / "x").mkdir(parents=True)
    (root / "node_modules" / "x" / "pkg.js").write_text("function formatPrice(){}\n")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("formatPrice\n")
    target = root / "main.js"
    target.write_text("// target\n")
    candidates = search.search_candidates("formatPrice", root, target)
    assert candidates == [], f"build dirs must be skipped, got {candidates}"


def test_search_candidates_returns_empty_when_rg_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """If `rg` is unavailable, returns [] without crashing."""
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "x.py"
    target.write_text("# target\n")
    # Force subprocess.run to raise FileNotFoundError as if rg were missing.
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()),
    )
    out = search.search_candidates("formatPrice", root, target)
    assert out == []


def test_search_candidates_timeout_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "x.py"
    target.write_text("# target\n")

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=1.0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = search.search_candidates("formatPrice", root, target)
    assert out == []


def test_search_candidates_rg_error_exit_audits_and_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An rg exit other than 0 or 1 is an error, audited as `ripgrep_error`."""
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "x.py"
    target.write_text("# target\n")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 2, stdout="", stderr="boom"),
    )
    audit: list[dict] = []
    monkeypatch.setattr(search.lib, "append_audit", audit.append)
    assert search.search_candidates("formatPrice", root, target) == []
    assert audit and audit[0]["event"] == "ripgrep_error" and audit[0]["code"] == 2


def test_search_candidates_batch_groups_by_symbol(tmp_path: Path) -> None:
    """One rg over an alternation attributes each hit to the right symbol group,
    and the single-symbol group matches the search_candidates wrapper (PRD 00088 R3)."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("def format_price(p):\n    return p\n")
    (root / "b.py").write_text("class Widget:\n    def parse(self):\n        pass\n")
    target = root / "new.py"
    target.write_text("# target\n")

    groups = search.search_candidates_batch(
        ["format_price", "Widget", "parse", "absent_sym"],
        root,
        target,
    )

    assert any(h["file"].endswith("a.py") for h in groups["format_price"])
    assert any(h["file"].endswith("b.py") for h in groups["Widget"])
    assert any(h["file"].endswith("b.py") for h in groups["parse"])
    assert groups["absent_sym"] == []
    # one rg over the batch matches what a per-symbol search would find
    assert groups["format_price"] == search.search_candidates(
        "format_price", root, target
    )


@pytest.mark.integration
def test_search_candidates_batch_p95_under_hook_budget(tmp_path: Path) -> None:
    """30 symbols resolve in ONE rg spawn well under the 5s hook budget — the
    per-symbol version spawned 30 subprocesses and could blow it (PRD 00088 R3)."""
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
        groups = search.search_candidates_batch(symbols, root, target)
        durations.append(time.perf_counter() - start)

    assert all(groups[s] for s in symbols), "every symbol must have at least one hit"
    durations.sort()
    p95 = durations[int(len(durations) * 0.95) - 1]  # 19th of 20 runs
    assert p95 < 2.0, f"p95 {p95:.3f}s exceeded the budget (the hook cap is 5s)"


# --- _resolve_project_root(""): must ask git, not just return cwd ---


def test_resolve_project_root_empty_path_asks_git_for_repo_toplevel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_resolve_project_root("")` must resolve to the git repo TOPLEVEL by
    asking `_common.resolve_toplevel`, not just return `Path.cwd()` unasked
    (PRD 00133 finding 42's `start`-path contract: file_path or
    str(Path.cwd()) is the resolution START, not the answer). The cwd is a
    SUBDIRECTORY of the repo so "returned the toplevel" and "returned the
    cwd" are distinguishable answers."""
    repo = tmp_path / "repo"
    subdir = repo / "src"
    subdir.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo)],
        check=True,
        capture_output=True,
    )
    monkeypatch.chdir(subdir)

    _common._TOPLEVEL_CACHE.clear()
    try:
        result = search._resolve_project_root("")
    finally:
        _common._TOPLEVEL_CACHE.clear()

    assert os.path.realpath(str(result)) == os.path.realpath(str(repo))
    assert os.path.realpath(str(result)) != os.path.realpath(str(subdir))
