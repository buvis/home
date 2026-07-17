"""Tests for strunk-ruling-inject.py PreToolUse hook.

Conventions (mirrors test_cartographer_recon_brief.py):
- pytest function-style; bare `def test_*`.
- All filesystem state is redirected to `tmp_path` via `monkeypatch.setattr(Path, "home", ...)`,
  which sandboxes both the plugin cache and the throttle store. The module computes
  `_CACHE_ROOT` / `_STORE_PATH` / `_AUDIT_PATH` at import time, so the `hook` fixture
  loads it fresh (importlib, module_from_spec) *after* the home is patched.
- Fixtures build a FAKE strunk cache tree; the real `~/.claude/plugins/cache` is only
  touched by the single real-cache set-completeness test at the bottom of this file.
- Only external boundaries are mocked: `Path.home` (sandbox) and `os.replace` (spied,
  still delegating to the real call). All store/cache/audit I/O is real.
"""

from __future__ import annotations

import builtins
import importlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOKS_DIR))

_HOOK_PATH = HOOKS_DIR / "strunk-ruling-inject.py"

_SKIP_AS_ROOT = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root bypasses the chmod permission bits this test depends on",
)


def _load_hook():
    spec = importlib.util.spec_from_file_location("strunk_ruling_inject", _HOOK_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Constants (copied verbatim from the contract - never read from the module)
# ---------------------------------------------------------------------------

_ATTRIBUTION_LITERAL = "Guidance for this file type, from the strunk `{skill}` skill:"

_WEB = ("web-patterns", "apply-design-system", "web-security", "web-performance")

_SKILLS_BY_EXT_LITERAL = {
    ".py": ("python-patterns",),
    ".pyi": ("python-patterns",),
    ".rs": ("rust-patterns",),
    ".css": _WEB,
    ".html": _WEB,
    ".vue": _WEB,
    ".ts": _WEB,
    ".tsx": _WEB,
    ".jsx": _WEB,
    ".svelte": _WEB + ("frontend-patterns",),
}

_TEST_SKILLS_BY_EXT_LITERAL = {
    ".py": ("python-testing",),
    ".pyi": ("python-testing",),
    ".rs": ("rust-testing",),
    ".css": ("e2e-testing",),
    ".html": ("e2e-testing",),
    ".vue": ("e2e-testing",),
    ".ts": ("e2e-testing",),
    ".tsx": ("e2e-testing",),
    ".jsx": ("e2e-testing",),
    ".svelte": ("e2e-testing",),
}

_TEST_DIR_SEGMENTS_LITERAL = ("/tests/", "/test/")

_TEST_FILE_SUFFIXES_LITERAL = (
    "_test.py", "_test.rs", ".test.ts", ".test.tsx", ".test.js", ".test.jsx",
    ".spec.ts", ".spec.tsx", ".spec.js",
)

# Extensions a real repo is full of that the contract deliberately leaves unmapped
# (note `.js`: the table maps .jsx/.ts/.tsx but not plain .js).
_UNMAPPED_EXTS = (".md", ".go", ".json", ".sh", ".js", ".txt", ".toml", ".yaml", ".lock", "")

_ALL_SKILLS = (
    "python-patterns",
    "python-testing",
    "rust-patterns",
    "rust-testing",
    "web-patterns",
    "apply-design-system",
    "web-security",
    "web-performance",
    "frontend-patterns",
    "e2e-testing",
)

_TODAY = datetime.now(timezone.utc).date().isoformat()
_YESTERDAY = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect Path.home() to a tmp dir so the hook never touches the real ~/.claude."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def hook(fake_home: Path):
    """Load a fresh strunk-ruling-inject module bound to this test's sandboxed home."""
    return _load_hook()


@pytest.fixture
def io_watch(monkeypatch: pytest.MonkeyPatch, fake_home: Path) -> list[str]:
    """Record every filesystem access, by canonical path, at BOTH layers.

    Spying on the I/O boundary rather than on module attribute names is deliberate: an
    implementation can route around a monkeypatched public name by calling its own
    private helper.

    `os.open` / `os.read` / `os.stat` are spied because they sit BELOW pathlib and
    `builtins.open`: a hook that reads through `os.open` + `os.read`, or probes with
    `Path.is_dir()` (which lands on `os.stat`), is completely invisible to the
    higher-level names. Recorded targets are canonicalised with realpath, because a
    raw-string prefix test is defeated by an equivalent spelling of the same directory
    (`.../buvis-plugins/./strunk`).

    Returns the list of accessed paths; call `.clear()` after fixture setup to ignore
    the test's own writes.
    """
    seen: list[str] = []
    fd_paths: dict[int, str] = {}

    def _canonical(target):
        raw = os.fspath(target)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        return os.path.realpath(raw)

    def _record(target) -> None:
        try:
            seen.append(_canonical(target))
        except TypeError:
            seen.append(repr(target))

    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes
    real_path_open = Path.open
    real_iterdir = Path.iterdir
    real_glob = Path.glob
    real_open = builtins.open
    real_scandir = os.scandir
    real_listdir = os.listdir
    real_os_open = os.open
    real_os_read = os.read
    real_os_stat = os.stat

    def _read_text(self, *a, **k):
        _record(self)
        return real_read_text(self, *a, **k)

    def _read_bytes(self, *a, **k):
        _record(self)
        return real_read_bytes(self, *a, **k)

    def _path_open(self, *a, **k):
        _record(self)
        return real_path_open(self, *a, **k)

    def _iterdir(self, *a, **k):
        _record(self)
        return real_iterdir(self, *a, **k)

    def _glob(self, *a, **k):
        _record(self)
        return real_glob(self, *a, **k)

    def _open(file, *a, **k):
        _record(file)
        return real_open(file, *a, **k)

    def _scandir(path=".", *a, **k):
        _record(path)
        return real_scandir(path, *a, **k)

    def _listdir(path=".", *a, **k):
        _record(path)
        return real_listdir(path, *a, **k)

    def _os_open(path, *a, **k):
        fd = real_os_open(path, *a, **k)
        _record(path)
        try:
            fd_paths[fd] = _canonical(path)
        except TypeError:
            pass
        return fd

    def _os_read(fd, *a, **k):
        known = fd_paths.get(fd)
        if known is not None:
            seen.append(known)
        return real_os_read(fd, *a, **k)

    def _os_stat(path, *a, **k):
        _record(path)
        return real_os_stat(path, *a, **k)

    monkeypatch.setattr(Path, "read_text", _read_text)
    monkeypatch.setattr(Path, "read_bytes", _read_bytes)
    monkeypatch.setattr(Path, "open", _path_open)
    monkeypatch.setattr(Path, "iterdir", _iterdir)
    monkeypatch.setattr(Path, "glob", _glob)
    monkeypatch.setattr(builtins, "open", _open)
    monkeypatch.setattr(os, "scandir", _scandir)
    monkeypatch.setattr(os, "listdir", _listdir)
    monkeypatch.setattr(os, "open", _os_open)
    monkeypatch.setattr(os, "read", _os_read)
    monkeypatch.setattr(os, "stat", _os_stat)
    return seen


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _attribution(skill: str) -> str:
    return _ATTRIBUTION_LITERAL.format(skill=skill)


def _body_for(skill: str) -> str:
    return f"# {skill}\n\nBody text for {skill}.\n"


def _frontmatter(skill: str) -> str:
    return f"---\nname: {skill}\ndescription: fixture skill\n---\n"


def _expected_payload(skills: tuple[str, ...]) -> str:
    return "\n\n".join(_attribution(s) + "\n\n" + _body_for(s) for s in skills)


def _cache_root(home: Path) -> Path:
    return home / ".claude" / "plugins" / "cache" / "buvis-plugins" / "strunk"


def _write_cache(home: Path, version: str = "0.2.0", skills: tuple[str, ...] = _ALL_SKILLS) -> Path:
    """Build a fake `<cache>/<version>/skills/<skill>/SKILL.md` tree."""
    skills_dir = _cache_root(home) / version / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    for skill in skills:
        d = skills_dir / skill
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(_frontmatter(skill) + _body_for(skill), encoding="utf-8")
    return skills_dir


def _skill_md(home: Path, skill: str, version: str = "0.2.0") -> Path:
    return _cache_root(home) / version / "skills" / skill / "SKILL.md"


def _store_path(home: Path) -> Path:
    return home / ".claude" / "cache" / "strunk-inject" / "injected.json"


def _lock_path(home: Path) -> Path:
    return _store_path(home).with_suffix(".lock")


def _audit_path(home: Path) -> Path:
    return home / ".claude" / "cache" / "strunk-inject" / "audit.jsonl"


def _read_store(home: Path) -> dict:
    p = _store_path(home)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _seed_store_file(home: Path, store: dict) -> Path:
    p = _store_path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store), encoding="utf-8")
    return p


def _read_audit_events(home: Path) -> list[dict]:
    p = _audit_path(home)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _payload(file_path: str = "/repo/app.py", session_id: str = "sess-1", tool_name: str = "Read") -> dict:
    return {"session_id": session_id, "tool_name": tool_name, "tool_input": {"file_path": file_path}}


def _novel_dir() -> str:
    """A directory no implementation can carry as a literal.

    uuid4().hex is drawn from [0-9a-f], so a generated segment can never accidentally
    spell "test" or "spec" ("t" and "s" are not hex digits) and can never be lifted
    from this file into a lookup table.
    """
    return f"/{uuid4().hex}/{uuid4().hex}"


def _novel_stem() -> str:
    return uuid4().hex


def _accesses_under(seen: list[str], root: Path) -> list[str]:
    """Accesses landing on `root` or below it, compared on canonical paths.

    Both sides go through realpath: comparing raw strings lets an equivalent spelling
    of the same directory (`.../buvis-plugins/./strunk`) read as "not under root".
    """
    prefix = os.path.realpath(str(root))
    return [p for p in seen if p == prefix or p.startswith(prefix + os.sep)]


def _assert_fresh_utc_timestamp(value: str) -> None:
    """An audit line is forensic evidence: a hardcoded epoch stamp is worse than none."""
    assert isinstance(value, str) and value, f"audit ts is missing: {value!r}"
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(text)
    assert parsed.tzinfo is not None, f"audit ts is not timezone-aware: {value}"
    assert parsed.utcoffset() == timedelta(0), f"audit ts is not UTC: {value}"
    age = datetime.now(timezone.utc) - parsed
    assert -timedelta(seconds=5) <= age <= timedelta(minutes=5), f"audit ts is not recent: {value}"


def _forbid_call(name: str, calls: list[str]):
    """A spy that both records and raises, so a call shows up even if main swallows it."""
    def _spy(*a, **k):
        calls.append(name)
        raise AssertionError(f"{name} must not run on the suppressed path")
    return _spy


def _run(hook_mod, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], payload: dict) -> str:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    hook_mod.main()
    return capsys.readouterr().out


def _run_subprocess(home: Path, stdin_text: str) -> subprocess.CompletedProcess[str]:
    """Run the hook as a real process against `home` (Path.home() follows $HOME on POSIX)."""
    return subprocess.run(
        [sys.executable, str(_HOOK_PATH)],
        input=stdin_text,
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(home)},
        timeout=60,
        check=False,
    )


# ---------------------------------------------------------------------------
# Mapping tables: pinned against the contract as literals
# ---------------------------------------------------------------------------
#
# These tests pin WHAT the tables say. The suite below them pins that
# skills_for_path is DRIVEN BY those tables, using paths generated at run time.
# Together they leave no room for a lookup table of memorised example paths: the
# behaviour tests build their paths from the table keys, and the table keys are
# themselves pinned here against the contract.

def test_web_skills_tuple_matches_the_agreed_contract(hook) -> None:
    assert hook._WEB_SKILLS == ("web-patterns", "apply-design-system", "web-security", "web-performance")


def test_skills_by_ext_table_matches_the_agreed_contract(hook) -> None:
    assert hook._SKILLS_BY_EXT == _SKILLS_BY_EXT_LITERAL


def test_test_skills_by_ext_table_matches_the_agreed_contract(hook) -> None:
    assert hook._TEST_SKILLS_BY_EXT == _TEST_SKILLS_BY_EXT_LITERAL


def test_test_dir_segments_match_the_agreed_contract(hook) -> None:
    assert hook._TEST_DIR_SEGMENTS == _TEST_DIR_SEGMENTS_LITERAL


def test_test_file_suffixes_match_the_agreed_contract(hook) -> None:
    assert hook._TEST_FILE_SUFFIXES == _TEST_FILE_SUFFIXES_LITERAL


# ---------------------------------------------------------------------------
# Mapping behaviour: skills_for_path is driven by the tables, not by examples
# ---------------------------------------------------------------------------

def test_every_mapped_extension_selects_its_declared_skills_on_an_arbitrary_path(hook) -> None:
    """Every path here is generated, so the only way to answer is to read the
    extension and consult the table. A hook that recognises example paths returns ()
    for real files and fails this test."""
    for ext, expected in hook._SKILLS_BY_EXT.items():
        for _ in range(3):
            path = f"{_novel_dir()}/{_novel_stem()}{ext}"
            assert hook.skills_for_path(path) == expected, path


def test_a_mapped_extension_is_recognised_wherever_the_file_lives(hook) -> None:
    """The mapping keys on the extension alone: directory depth, absolute vs relative,
    and stem must not change the answer."""
    stem = _novel_stem()
    for path in (
        f"/{stem}.py",
        f"/{uuid4().hex}/{stem}.py",
        f"/{uuid4().hex}/{uuid4().hex}/{uuid4().hex}/{uuid4().hex}/{stem}.py",
        f"{stem}.py",
        f"./{uuid4().hex}/{stem}.py",
        f"/{uuid4().hex}/{stem}.PY",
    ):
        assert hook.skills_for_path(path) == ("python-patterns",), path


def test_every_mapped_extension_gains_its_testing_skills_on_a_generated_test_path(hook) -> None:
    for ext, base in hook._SKILLS_BY_EXT.items():
        overlay = hook._TEST_SKILLS_BY_EXT[ext]
        for segment in hook._TEST_DIR_SEGMENTS:
            path = f"/{uuid4().hex}{segment}{_novel_stem()}{ext}"
            assert hook.skills_for_path(path) == base + overlay, path


def test_every_declared_test_suffix_adds_the_overlay_for_its_extension(hook) -> None:
    for suffix in hook._TEST_FILE_SUFFIXES:
        ext = "." + suffix.rsplit(".", 1)[1]
        if ext not in hook._SKILLS_BY_EXT:
            continue  # e.g. ".test.js": a test suffix on an unmapped extension
        path = f"{_novel_dir()}/{_novel_stem()}{suffix}"
        expected = hook._SKILLS_BY_EXT[ext] + hook._TEST_SKILLS_BY_EXT[ext]
        assert hook.skills_for_path(path) == expected, path


def test_a_test_prefixed_python_file_gains_the_python_testing_overlay(hook) -> None:
    path = f"{_novel_dir()}/test_{_novel_stem()}.py"

    assert hook.skills_for_path(path) == ("python-patterns", "python-testing")


def test_extensions_outside_the_table_select_no_skills(hook) -> None:
    for ext in _UNMAPPED_EXTS:
        assert ext not in hook._SKILLS_BY_EXT, f"{ext} is unexpectedly mapped"
        path = f"{_novel_dir()}/{_novel_stem()}{ext}"
        assert hook.skills_for_path(path) == (), path


def test_extensions_outside_the_table_select_no_skills_even_on_a_test_path(hook) -> None:
    """The test overlay is additive to a mapped base, never a mapping of its own."""
    for ext in _UNMAPPED_EXTS:
        path = f"/{uuid4().hex}/tests/{_novel_stem()}{ext}"
        assert hook.skills_for_path(path) == (), path


# ---------------------------------------------------------------------------
# file_extension
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("file_path", "expected"),
    [
        ("/repo/app.py", ".py"),
        ("/repo/Card.svelte", ".svelte"),
        ("/repo/APP.PY", ".py"),
        ("/repo/Card.TSX", ".tsx"),
        ("/repo/Makefile", ""),
        ("/repo/archive.tar.gz", ".gz"),
        ("", ""),
    ],
    ids=["py", "svelte", "uppercase-py", "uppercase-tsx", "no-extension", "double-extension", "empty"],
)
def test_file_extension_is_dotted_and_lowercased(hook, file_path: str, expected: str) -> None:
    assert hook.file_extension(file_path) == expected


def test_every_table_extension_is_read_back_off_an_arbitrary_path(hook) -> None:
    """Generated paths, so the extension must actually be parsed rather than matched
    against known example filenames."""
    for ext in hook._SKILLS_BY_EXT:
        assert hook.file_extension(f"{_novel_dir()}/{_novel_stem()}{ext}") == ext
        assert hook.file_extension(f"{_novel_dir()}/{_novel_stem()}{ext.upper()}") == ext


# ---------------------------------------------------------------------------
# is_test_file_path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "file_path",
    [
        "/repo/tests/app.py",
        "/repo/test/app.py",
        "/repo/src/test_app.py",
        "test_app.py",
        "/repo/src/app_test.py",
        "/repo/src/lib_test.rs",
        "/repo/e2e/login.spec.ts",
        "/repo/e2e/login.spec.tsx",
        "/repo/e2e/login.spec.js",
        "/repo/e2e/Card.test.ts",
        "/repo/e2e/Card.test.tsx",
        "/repo/e2e/card.test.js",
        "/repo/e2e/Card.test.jsx",
    ],
    ids=[
        "tests-dir", "test-dir", "test-prefix-py", "bare-test-prefix-py", "test-suffix-py",
        "test-suffix-rs", "spec-ts", "spec-tsx", "spec-js", "test-ts", "test-tsx", "test-js", "test-jsx",
    ],
)
def test_recognises_test_paths(hook, file_path: str) -> None:
    assert hook.is_test_file_path(file_path) is True


def test_every_declared_test_dir_segment_marks_an_arbitrary_path_as_a_test_path(hook) -> None:
    for segment in hook._TEST_DIR_SEGMENTS:
        path = f"/{uuid4().hex}{segment}{_novel_stem()}.py"
        assert hook.is_test_file_path(path) is True, path


def test_every_declared_test_suffix_marks_an_arbitrary_path_as_a_test_path(hook) -> None:
    for suffix in hook._TEST_FILE_SUFFIXES:
        path = f"{_novel_dir()}/{_novel_stem()}{suffix}"
        assert hook.is_test_file_path(path) is True, path


def test_a_test_prefixed_python_file_is_a_test_path_whatever_it_is_called(hook) -> None:
    path = f"{_novel_dir()}/test_{_novel_stem()}.py"

    assert hook.is_test_file_path(path) is True


@pytest.mark.parametrize(
    "file_path",
    ["/repo/src/latest.py", "/repo/src/app.py", "/repo/src/protest.rs", "/repo/src/testing_utils.py"],
    ids=["latest-py", "plain-source", "protest-rs", "testing-prefix-without-underscore"],
)
def test_source_files_whose_names_merely_contain_test_are_not_test_paths(hook, file_path: str) -> None:
    """`latest.py` contains "test" but is production code; matching it would inject
    python-testing guidance into every such file."""
    assert hook.is_test_file_path(file_path) is False


def test_an_arbitrary_source_path_is_not_a_test_path(hook) -> None:
    """Generated segments are hex, so they can never spell "test" or "spec": anything
    that answers True here is matching too broadly."""
    for _ in range(5):
        path = f"{_novel_dir()}/{_novel_stem()}.py"
        assert hook.is_test_file_path(path) is False, path


@pytest.mark.parametrize(
    "name",
    ["latest.py", "protest.rs", "contest.ts", "greatest.py", "attest.jsx"],
    ids=["latest", "protest", "contest", "greatest", "attest"],
)
def test_a_test_substring_inside_a_stem_never_makes_a_test_path(hook, name: str) -> None:
    path = f"{_novel_dir()}/{name}"

    assert hook.is_test_file_path(path) is False


# ---------------------------------------------------------------------------
# target_file_path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tool_name", ["Read", "Edit", "Write", "MultiEdit"])
def test_file_tools_expose_their_target_path(hook, tool_name: str) -> None:
    assert hook.target_file_path(tool_name, {"file_path": "/repo/app.py"}) == "/repo/app.py"


@pytest.mark.parametrize(
    ("tool_name", "tool_input"),
    [
        ("Bash", {"command": "ls /repo/app.py"}),
        ("Grep", {"file_path": "/repo/app.py"}),
        ("Task", {"file_path": "/repo/app.py"}),
        ("Read", {}),
        ("Edit", {"old_string": "a"}),
    ],
    ids=["bash", "grep", "task", "read-without-file_path", "edit-without-file_path"],
)
def test_non_file_tools_and_pathless_inputs_expose_no_target_path(hook, tool_name: str, tool_input: dict) -> None:
    assert hook.target_file_path(tool_name, tool_input) == ""


# ---------------------------------------------------------------------------
# _version_key / resolve_strunk_skills_dir
# ---------------------------------------------------------------------------

def test_version_key_parses_dotted_numeric_segments(hook) -> None:
    assert hook._version_key("0.2.0") == (0, 2, 0)
    assert hook._version_key("1.10.3") == (1, 10, 3)


def test_version_key_orders_numerically_not_lexically(hook) -> None:
    """Lexical ordering would rank "0.2.0" above "0.10.0"."""
    assert hook._version_key("0.10.0") > hook._version_key("0.2.0")


def test_version_key_sorts_non_numeric_segments_below_every_real_version(hook) -> None:
    assert hook._version_key("nightly") == (-1,)
    assert hook._version_key("1.x.3") == (1, -1, 3)
    assert hook._version_key("nightly") < hook._version_key("0.0.1")


def test_resolves_the_only_installed_version(hook, fake_home) -> None:
    _write_cache(fake_home, version="0.2.0")

    resolved = hook.resolve_strunk_skills_dir()

    assert resolved == (_cache_root(fake_home) / "0.2.0" / "skills", "0.2.0")


def test_resolves_the_numerically_highest_version_not_the_lexically_highest(hook, fake_home) -> None:
    _write_cache(fake_home, version="0.2.0")
    _write_cache(fake_home, version="0.10.0")

    skills_dir, version = hook.resolve_strunk_skills_dir()

    assert version == "0.10.0"
    assert skills_dir == _cache_root(fake_home) / "0.10.0" / "skills"


def test_malformed_version_dir_loses_to_a_real_version_instead_of_raising(hook, fake_home) -> None:
    _write_cache(fake_home, version="0.2.0")
    _write_cache(fake_home, version="nightly")

    skills_dir, version = hook.resolve_strunk_skills_dir()

    assert version == "0.2.0"
    assert skills_dir == _cache_root(fake_home) / "0.2.0" / "skills"


def test_malformed_version_dir_alone_resolves_without_raising(hook, fake_home) -> None:
    _write_cache(fake_home, version="nightly")

    resolved = hook.resolve_strunk_skills_dir()

    assert resolved == (_cache_root(fake_home) / "nightly" / "skills", "nightly")


def test_absent_cache_root_resolves_to_none(hook, fake_home) -> None:
    assert not _cache_root(fake_home).exists()
    assert hook.resolve_strunk_skills_dir() is None


def test_cache_root_without_any_version_dir_resolves_to_none(hook, fake_home) -> None:
    _cache_root(fake_home).mkdir(parents=True)

    assert hook.resolve_strunk_skills_dir() is None


def test_version_dir_without_a_skills_subdir_resolves_to_none(hook, fake_home) -> None:
    (_cache_root(fake_home) / "0.3.0").mkdir(parents=True)

    assert hook.resolve_strunk_skills_dir() is None


def test_winning_version_without_a_skills_subdir_resolves_to_none_without_falling_back(hook, fake_home) -> None:
    """The winner is chosen first, then checked for `skills/`; a broken newest install
    is reported as unresolvable rather than silently serving stale guidance."""
    _write_cache(fake_home, version="0.2.0")
    (_cache_root(fake_home) / "0.10.0").mkdir(parents=True)

    assert hook.resolve_strunk_skills_dir() is None


# ---------------------------------------------------------------------------
# strip_frontmatter
# ---------------------------------------------------------------------------

def test_strip_frontmatter_drops_a_leading_yaml_block(hook) -> None:
    text = "---\nname: python-patterns\ndescription: x\n---\n# Body\n\nprose\n"

    assert hook.strip_frontmatter(text) == "# Body\n\nprose\n"


def test_strip_frontmatter_returns_text_without_frontmatter_unchanged(hook) -> None:
    text = "# Body\n\nprose\n"

    assert hook.strip_frontmatter(text) == text


def test_strip_frontmatter_keeps_a_horizontal_rule_that_is_not_leading_frontmatter(hook) -> None:
    text = "# Body\n\n---\n\nmore prose\n"

    assert hook.strip_frontmatter(text) == text


def test_strip_frontmatter_only_drops_the_first_block(hook) -> None:
    text = "---\nname: x\n---\nbody\n---\nnot frontmatter\n---\ntail\n"

    assert hook.strip_frontmatter(text) == "body\n---\nnot frontmatter\n---\ntail\n"


def test_strip_frontmatter_leaves_empty_text_unchanged(hook) -> None:
    assert hook.strip_frontmatter("") == ""


# ---------------------------------------------------------------------------
# build_payload
# ---------------------------------------------------------------------------

def test_payload_is_the_attribution_header_followed_by_the_verbatim_skill_body(hook, fake_home) -> None:
    """The header is pinned as a literal: adding a version, an authority clause, or
    any other embellishment to it must fail this test."""
    skills_dir = _write_cache(fake_home)

    payload, delivered = hook.build_payload(skills_dir, ("python-patterns",))

    assert payload == (
        "Guidance for this file type, from the strunk `python-patterns` skill:"
        "\n\n"
        "# python-patterns\n\nBody text for python-patterns.\n"
    )
    assert delivered == ("python-patterns",)


def test_attribution_template_is_the_agreed_literal(hook) -> None:
    assert hook._ATTRIBUTION == "Guidance for this file type, from the strunk `{skill}` skill:"


def test_payload_body_is_byte_identical_to_the_source_skill_md(hook, fake_home) -> None:
    """No reflow, no trimming, no transcoding: the shipped body must be the file's
    own bytes with only the frontmatter removed."""
    skills_dir = _write_cache(fake_home)
    body = "# Rules\n\n- Use `pathlib`\t(tab)   \n\n\nTrailing blank lines and unicode: café - ✓\n\n"
    _skill_md(fake_home, "python-patterns").write_text(
        _frontmatter("python-patterns") + body, encoding="utf-8"
    )

    payload, delivered = hook.build_payload(skills_dir, ("python-patterns",))

    assert payload == _attribution("python-patterns") + "\n\n" + body
    assert payload.endswith(body)
    assert delivered == ("python-patterns",)


def test_multiple_skills_are_joined_in_declaration_order_with_a_blank_line(hook, fake_home) -> None:
    skills_dir = _write_cache(fake_home)
    skills = ("web-patterns", "apply-design-system", "frontend-patterns")

    payload, delivered = hook.build_payload(skills_dir, skills)

    assert payload == (
        _attribution("web-patterns") + "\n\n" + _body_for("web-patterns")
        + "\n\n"
        + _attribution("apply-design-system") + "\n\n" + _body_for("apply-design-system")
        + "\n\n"
        + _attribution("frontend-patterns") + "\n\n" + _body_for("frontend-patterns")
    )
    assert delivered == skills


def test_missing_skill_md_is_skipped_rather_than_fabricated(hook, fake_home) -> None:
    skills_dir = _write_cache(fake_home, skills=("web-patterns", "web-security"))

    payload, delivered = hook.build_payload(skills_dir, ("web-patterns", "apply-design-system", "web-security"))

    assert delivered == ("web-patterns", "web-security")
    assert payload == _expected_payload(("web-patterns", "web-security"))
    assert "apply-design-system" not in payload


@_SKIP_AS_ROOT
def test_unreadable_skill_md_is_skipped_rather_than_fabricated(hook, fake_home) -> None:
    skills_dir = _write_cache(fake_home)
    unreadable = _skill_md(fake_home, "apply-design-system")
    unreadable.chmod(0o000)
    try:
        payload, delivered = hook.build_payload(skills_dir, ("web-patterns", "apply-design-system"))
    finally:
        unreadable.chmod(0o600)

    assert delivered == ("web-patterns",)
    assert payload == _attribution("web-patterns") + "\n\n" + _body_for("web-patterns")


def test_all_skills_missing_yields_an_empty_payload_and_no_delivered_skills(hook, fake_home) -> None:
    skills_dir = _write_cache(fake_home, skills=())

    payload, delivered = hook.build_payload(skills_dir, ("python-patterns", "python-testing"))

    assert payload == ""
    assert delivered == ()


# ---------------------------------------------------------------------------
# Store: load / prune / save
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_content",
    ["{not valid json", "[]", "", "null", '"a string"'],
    ids=["invalid-json-bytes", "valid-json-not-a-dict", "empty-file", "json-null", "json-string"],
)
def test_unusable_store_content_loads_as_an_empty_store(hook, fake_home, bad_content: str) -> None:
    p = _store_path(fake_home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(bad_content, encoding="utf-8")

    assert hook._load_store(p) == {}


def test_absent_store_loads_as_an_empty_store(hook, fake_home) -> None:
    assert hook._load_store(_store_path(fake_home)) == {}


def test_store_round_trips_through_save_and_load(hook, fake_home) -> None:
    p = _store_path(fake_home)
    p.parent.mkdir(parents=True, exist_ok=True)
    store = {"sess-1": {"day": _TODAY, "skills": ["python-patterns", "python-testing"]}}

    hook._save_store(p, store)

    assert hook._load_store(p) == store


def test_prune_drops_sessions_from_other_days_and_keeps_todays(hook) -> None:
    store = {
        "stale": {"day": _YESTERDAY, "skills": ["python-patterns"]},
        "fresh": {"day": _TODAY, "skills": ["rust-patterns"]},
    }

    assert hook._prune_store(store, _TODAY) == {"fresh": {"day": _TODAY, "skills": ["rust-patterns"]}}


def test_prune_of_an_empty_store_is_an_empty_store(hook) -> None:
    assert hook._prune_store({}, _TODAY) == {}


def test_store_is_replaced_atomically_from_a_temp_file_in_the_same_directory(hook, fake_home, monkeypatch) -> None:
    """A partially written store must never be observable: the new content lands on a
    temp file first and is swapped in with a single os.replace."""
    store_path = _store_path(fake_home)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps({"old": {"day": _YESTERDAY, "skills": []}}), encoding="utf-8")

    seen: list[tuple[str, str]] = []
    real_replace = os.replace

    def _spy_replace(src, dst):
        seen.append((str(src), str(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(hook.os, "replace", _spy_replace)
    new_store = {"sess-1": {"day": _TODAY, "skills": ["python-patterns"]}}

    hook._save_store(store_path, new_store)

    assert len(seen) == 1
    src, dst = seen[0]
    assert dst == str(store_path)
    assert src != str(store_path)
    assert Path(src).parent == store_path.parent
    assert json.loads(store_path.read_text(encoding="utf-8")) == new_store
    assert [p.name for p in store_path.parent.iterdir()] == [store_path.name]


@_SKIP_AS_ROOT
def test_save_store_swallows_an_unwritable_directory(hook, fake_home, capsys) -> None:
    d = _store_path(fake_home).parent
    d.mkdir(parents=True, exist_ok=True)
    d.chmod(0o500)
    try:
        hook._save_store(_store_path(fake_home), {"sess-1": {"day": _TODAY, "skills": []}})  # must not raise
    finally:
        d.chmod(0o700)

    assert capsys.readouterr().out == ""
    assert not _store_path(fake_home).exists()


# ---------------------------------------------------------------------------
# Inject: envelope, payload, store record, audit
# ---------------------------------------------------------------------------

def test_first_touch_of_a_mapped_file_injects_and_records_the_skill(hook, monkeypatch, capsys, fake_home) -> None:
    _write_cache(fake_home)

    out = _run(hook, monkeypatch, capsys, _payload(file_path="/repo/app.py"))
    envelope = json.loads(out)

    assert envelope == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": _expected_payload(("python-patterns",)),
        }
    }
    assert "permissionDecision" not in envelope["hookSpecificOutput"]
    assert "decision" not in envelope
    assert _read_store(fake_home) == {"sess-1": {"day": _TODAY, "skills": ["python-patterns"]}}


@pytest.mark.parametrize(
    ("ext", "expected"),
    [
        (".py", ("python-patterns",)),
        (".rs", ("rust-patterns",)),
        (".ts", _WEB),
        (".svelte", _WEB + ("frontend-patterns",)),
    ],
    ids=["py", "rs", "ts", "svelte"],
)
def test_an_arbitrary_real_world_path_injects_end_to_end(
    hook, monkeypatch, capsys, fake_home, ext: str, expected: tuple[str, ...]
) -> None:
    """Binds main() itself to the mapping, not just skills_for_path: the path is
    generated at run time, so no implementation can carry it as a literal. A hook that
    only recognises this suite's example paths ships nothing here."""
    _write_cache(fake_home)
    file_path = f"{_novel_dir()}/{_novel_stem()}{ext}"

    out = _run(hook, monkeypatch, capsys, _payload(file_path=file_path))

    assert json.loads(out)["hookSpecificOutput"]["additionalContext"] == _expected_payload(expected)
    assert _read_audit_events(fake_home)[0]["file"] == file_path


def test_an_arbitrary_real_world_test_path_injects_the_testing_overlay_end_to_end(
    hook, monkeypatch, capsys, fake_home
) -> None:
    _write_cache(fake_home)
    file_path = f"/{uuid4().hex}/tests/test_{_novel_stem()}.py"

    out = _run(hook, monkeypatch, capsys, _payload(file_path=file_path))

    assert json.loads(out)["hookSpecificOutput"]["additionalContext"] == _expected_payload(
        ("python-patterns", "python-testing")
    )


def test_svelte_touch_injects_every_web_skill_plus_frontend_patterns_in_order(
    hook, monkeypatch, capsys, fake_home
) -> None:
    _write_cache(fake_home)

    out = _run(hook, monkeypatch, capsys, _payload(file_path="/repo/src/Card.svelte"))
    context = json.loads(out)["hookSpecificOutput"]["additionalContext"]

    assert context == _expected_payload(_WEB + ("frontend-patterns",))


def test_touching_a_test_file_injects_the_testing_skill_alongside_the_base_skill(
    hook, monkeypatch, capsys, fake_home
) -> None:
    _write_cache(fake_home)

    out = _run(hook, monkeypatch, capsys, _payload(file_path="/repo/tests/test_app.py"))
    context = json.loads(out)["hookSpecificOutput"]["additionalContext"]

    assert context == _expected_payload(("python-patterns", "python-testing"))
    assert set(_read_store(fake_home)["sess-1"]["skills"]) == {"python-patterns", "python-testing"}


@pytest.mark.parametrize("tool_name", ["Read", "Edit", "Write", "MultiEdit"])
def test_every_file_tool_triggers_injection(hook, monkeypatch, capsys, fake_home, tool_name: str) -> None:
    _write_cache(fake_home)

    out = _run(hook, monkeypatch, capsys, _payload(file_path="/repo/app.py", tool_name=tool_name))

    assert json.loads(out)["hookSpecificOutput"]["additionalContext"] == _expected_payload(("python-patterns",))


def test_inject_is_audited_with_the_session_delivered_skills_and_version(
    hook, monkeypatch, capsys, fake_home
) -> None:
    _write_cache(fake_home, version="0.10.0")

    _run(hook, monkeypatch, capsys, _payload(file_path="/repo/tests/test_app.py", session_id="sess-audit"))

    events = _read_audit_events(fake_home)
    assert len(events) == 1
    event = events[0]
    assert event["decision"] == "inject"
    assert event["session"] == "sess-audit"
    assert event["file"] == "/repo/tests/test_app.py"
    assert event["skills"] == ["python-patterns", "python-testing"]
    assert event["version"] == "0.10.0"
    _assert_fresh_utc_timestamp(event["ts"])


def test_lock_file_is_a_sidecar_and_never_the_store_file(hook, monkeypatch, capsys, fake_home) -> None:
    """Locking the store file itself would risk truncating it; the mutex takes a
    separate `injected.lock` next to it."""
    _write_cache(fake_home)

    _run(hook, monkeypatch, capsys, _payload(file_path="/repo/app.py"))

    assert _lock_path(fake_home).name == "injected.lock"
    assert _lock_path(fake_home).exists()
    assert _read_store(fake_home) == {"sess-1": {"day": _TODAY, "skills": ["python-patterns"]}}


# ---------------------------------------------------------------------------
# Throttle: (session x skill)
# ---------------------------------------------------------------------------

def test_second_touch_of_the_same_skill_in_the_same_session_injects_nothing(
    hook, monkeypatch, capsys, fake_home
) -> None:
    _write_cache(fake_home)
    first = _run(hook, monkeypatch, capsys, _payload(file_path="/repo/app.py"))
    assert first != ""
    store_after_first = _read_store(fake_home)

    second = _run(hook, monkeypatch, capsys, _payload(file_path="/repo/other.py"))

    assert second == ""
    assert _read_store(fake_home) == store_after_first


def test_a_different_session_receives_the_same_skill_again(hook, monkeypatch, capsys, fake_home) -> None:
    _write_cache(fake_home)
    _run(hook, monkeypatch, capsys, _payload(file_path="/repo/app.py", session_id="sess-a"))

    out = _run(hook, monkeypatch, capsys, _payload(file_path="/repo/app.py", session_id="sess-b"))

    assert json.loads(out)["hookSpecificOutput"]["additionalContext"] == _expected_payload(("python-patterns",))
    store = _read_store(fake_home)
    assert store["sess-a"]["skills"] == ["python-patterns"]
    assert store["sess-b"]["skills"] == ["python-patterns"]


def test_a_partially_throttled_set_injects_only_the_skills_not_yet_seen(
    hook, monkeypatch, capsys, fake_home
) -> None:
    _write_cache(fake_home)
    _run(hook, monkeypatch, capsys, _payload(file_path="/repo/app.py", session_id="sess-2"))

    out = _run(hook, monkeypatch, capsys, _payload(file_path="/repo/tests/test_app.py", session_id="sess-2"))
    context = json.loads(out)["hookSpecificOutput"]["additionalContext"]

    assert context == _expected_payload(("python-testing",))
    assert "python-patterns" not in context
    assert set(_read_store(fake_home)["sess-2"]["skills"]) == {"python-patterns", "python-testing"}


def test_a_different_skill_family_in_the_same_session_still_injects(hook, monkeypatch, capsys, fake_home) -> None:
    _write_cache(fake_home)
    _run(hook, monkeypatch, capsys, _payload(file_path="/repo/app.py", session_id="sess-mix"))

    out = _run(hook, monkeypatch, capsys, _payload(file_path="/repo/lib.rs", session_id="sess-mix"))

    assert json.loads(out)["hookSpecificOutput"]["additionalContext"] == _expected_payload(("rust-patterns",))
    assert set(_read_store(fake_home)["sess-mix"]["skills"]) == {"python-patterns", "rust-patterns"}


def test_a_throttled_no_op_is_not_audited(hook, monkeypatch, capsys, fake_home) -> None:
    _write_cache(fake_home)
    _run(hook, monkeypatch, capsys, _payload(file_path="/repo/app.py"))
    assert len(_read_audit_events(fake_home)) == 1

    _run(hook, monkeypatch, capsys, _payload(file_path="/repo/app.py"))

    assert len(_read_audit_events(fake_home)) == 1


def test_main_prunes_sessions_from_earlier_days_out_of_the_store(
    hook, monkeypatch, capsys, fake_home
) -> None:
    """`day` exists only so the store stays bounded. Nothing else in this suite proves
    main ever prunes: an implementation that writes `day` and never reads it keeps every
    session that ever ran, forever, and every other test stays green."""
    _write_cache(fake_home)
    _seed_store_file(fake_home, {
        "yesterday-session": {"day": _YESTERDAY, "skills": ["python-patterns"]},
        "ancient-session": {"day": "2020-01-01", "skills": ["rust-patterns"]},
        "today-session": {"day": _TODAY, "skills": ["rust-patterns"]},
    })

    out = _run(hook, monkeypatch, capsys, _payload(file_path="/repo/app.py", session_id="fresh-session"))

    assert out != ""
    store = _read_store(fake_home)
    assert "yesterday-session" not in store, f"stale session survived: {store}"
    assert "ancient-session" not in store, f"stale session survived: {store}"
    assert store["today-session"] == {"day": _TODAY, "skills": ["rust-patterns"]}
    assert store["fresh-session"] == {"day": _TODAY, "skills": ["python-patterns"]}


@pytest.mark.parametrize(
    "bad_content",
    ["{not valid json", "[]"],
    ids=["invalid-json-bytes", "valid-json-not-a-dict"],
)
def test_a_malformed_store_is_rebuilt_and_the_injection_still_ships(
    hook, monkeypatch, capsys, fake_home, bad_content: str
) -> None:
    _write_cache(fake_home)
    store_path = _store_path(fake_home)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(bad_content, encoding="utf-8")

    out = _run(hook, monkeypatch, capsys, _payload(file_path="/repo/app.py"))
    envelope = json.loads(out)  # must not crash

    assert envelope["hookSpecificOutput"]["additionalContext"] == _expected_payload(("python-patterns",))
    assert _read_store(fake_home) == {"sess-1": {"day": _TODAY, "skills": ["python-patterns"]}}


# ---------------------------------------------------------------------------
# Concurrency: the lost-write regression (real processes, real flock)
# ---------------------------------------------------------------------------

# Loads the hook in a child process and stretches the store's read-modify-write
# window by sleeping once, immediately AFTER the store's bytes have been read.
#
# The delay is injected at the I/O boundary, not at `mod._load_store`: an
# implementation that reads the store through a private helper would dodge a
# module-attribute patch and quietly reduce these tests to a scheduling coin-flip.
# The injection points cover BOTH layers - Path.read_text / Path.read_bytes /
# Path.open / builtins.open, and os.open + os.read underneath them - because a
# store read done with os.open is invisible to every pathlib-level name.
#
# Sleeping after the read (never after the open) is what makes the failure
# deterministic: both processes must have their stale copy of the store in hand
# before either writes. With `_file_mutex` the second process blocks on the lock
# and its read observes the first process's entry; without it both read the same
# store and the last save silently drops the other's entry.
#
# _stretch() announces itself on stderr so each test can PROVE its race window
# actually opened. A concurrency test whose delay silently never fired is not
# testing concurrency - it is a coin flip that reports green.
_RACER = '''\
import builtins
import importlib.util
import io
import os
import sys
import time
from pathlib import Path

hook_path, delay, store_path, payload = sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4]
store_path = os.path.realpath(store_path)

_fired = []


def _stretch():
    if _fired:
        return
    _fired.append(True)
    sys.stderr.write("RACE-WINDOW-OPENED\\n")
    sys.stderr.flush()
    time.sleep(delay)


def _is_store(target):
    try:
        return os.path.realpath(os.fspath(target)) == store_path
    except TypeError:
        return False


class _StretchingFile:
    """Delegates to the real handle, sleeping once after the store's first read."""

    def __init__(self, fh):
        self._fh = fh

    def read(self, *a, **k):
        data = self._fh.read(*a, **k)
        _stretch()
        return data

    def readlines(self, *a, **k):
        data = self._fh.readlines(*a, **k)
        _stretch()
        return data

    def __iter__(self):
        return iter(self._fh)

    def __enter__(self):
        self._fh.__enter__()
        return self

    def __exit__(self, *exc):
        return self._fh.__exit__(*exc)

    def __getattr__(self, name):
        return getattr(self._fh, name)


_real_read_text = Path.read_text
_real_read_bytes = Path.read_bytes
_real_path_open = Path.open
_real_open = builtins.open
_real_os_open = os.open
_real_os_read = os.read

_store_fds = set()


def _read_text(self, *a, **k):
    out = _real_read_text(self, *a, **k)
    if _is_store(self):
        _stretch()
    return out


def _read_bytes(self, *a, **k):
    out = _real_read_bytes(self, *a, **k)
    if _is_store(self):
        _stretch()
    return out


def _path_open(self, *a, **k):
    fh = _real_path_open(self, *a, **k)
    if _is_store(self):
        return _StretchingFile(fh)
    return fh


def _open(file, *a, **k):
    fh = _real_open(file, *a, **k)
    if _is_store(file):
        return _StretchingFile(fh)
    return fh


def _os_open(path, *a, **k):
    fd = _real_os_open(path, *a, **k)
    if _is_store(path):
        _store_fds.add(fd)
    return fd


def _os_read(fd, *a, **k):
    data = _real_os_read(fd, *a, **k)
    if fd in _store_fds:
        _stretch()
    return data


Path.read_text = _read_text
Path.read_bytes = _read_bytes
Path.open = _path_open
builtins.open = _open
os.open = _os_open
os.read = _os_read

spec = importlib.util.spec_from_file_location("strunk_ruling_inject", hook_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
sys.stdin = io.StringIO(payload)
mod.main()
'''

_RACE_DELAY = 1.0


@pytest.fixture
def racer_script(tmp_path: Path) -> Path:
    path = tmp_path / "racer.py"
    path.write_text(_RACER, encoding="utf-8")
    return path


def _spawn_racer(home: Path, racer: Path, payload: dict) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable, str(racer), str(_HOOK_PATH), str(_RACE_DELAY),
            str(_store_path(home)), json.dumps(payload),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "HOME": str(home)},
    )


_RACE_MARKER = "RACE-WINDOW-OPENED"


def _assert_race_window_opened(err_a: str, err_b: str, elapsed: float) -> None:
    """Without this the test is a coin flip: a delay that never fired proves nothing."""
    assert _RACE_MARKER in err_a, f"first process never opened its race window: {err_a}"
    assert _RACE_MARKER in err_b, f"second process never opened its race window: {err_b}"
    assert elapsed >= _RACE_DELAY, f"race window never opened (whole race took {elapsed:.2f}s)"


def test_concurrent_sessions_do_not_lose_each_others_store_entries(tmp_path, racer_script) -> None:
    _write_cache(tmp_path)
    _seed_store_file(tmp_path, {})  # the racer stretches the window around a real read

    started = time.perf_counter()
    a = _spawn_racer(tmp_path, racer_script, _payload(file_path="/repo/app.py", session_id="sess-a"))
    b = _spawn_racer(tmp_path, racer_script, _payload(file_path="/repo/app.py", session_id="sess-b"))
    out_a, err_a = a.communicate(timeout=60)
    out_b, err_b = b.communicate(timeout=60)
    elapsed = time.perf_counter() - started

    assert a.returncode == 0, err_a
    assert b.returncode == 0, err_b
    assert out_a != "" and out_b != ""
    _assert_race_window_opened(err_a, err_b, elapsed)

    store = _read_store(tmp_path)
    assert sorted(store) == ["sess-a", "sess-b"], f"lost write: {store}"
    assert store["sess-a"]["skills"] == ["python-patterns"]
    assert store["sess-b"]["skills"] == ["python-patterns"]


def test_concurrent_skills_in_one_session_do_not_lose_each_other(tmp_path, racer_script) -> None:
    _write_cache(tmp_path)
    _seed_store_file(tmp_path, {})

    started = time.perf_counter()
    a = _spawn_racer(tmp_path, racer_script, _payload(file_path="/repo/app.py", session_id="sess-x"))
    b = _spawn_racer(tmp_path, racer_script, _payload(file_path="/repo/lib.rs", session_id="sess-x"))
    out_a, err_a = a.communicate(timeout=60)
    out_b, err_b = b.communicate(timeout=60)
    elapsed = time.perf_counter() - started

    assert a.returncode == 0, err_a
    assert b.returncode == 0, err_b
    assert out_a != "" and out_b != ""
    _assert_race_window_opened(err_a, err_b, elapsed)

    store = _read_store(tmp_path)
    assert sorted(store) == ["sess-x"], f"lost write: {store}"
    assert set(store["sess-x"]["skills"]) == {"python-patterns", "rust-patterns"}, f"lost write: {store}"


def test_an_unusable_lock_path_degrades_to_injecting_without_the_lock(
    hook, monkeypatch, capsys, fake_home
) -> None:
    """Bookkeeping loses to delivery: if the mutex cannot be taken the guidance still
    ships rather than being dropped."""
    _write_cache(fake_home)
    lock = _lock_path(fake_home)
    lock.mkdir(parents=True)  # a directory where the lock file belongs: open() raises

    out = _run(hook, monkeypatch, capsys, _payload(file_path="/repo/app.py"))

    assert json.loads(out)["hookSpecificOutput"]["additionalContext"] == _expected_payload(("python-patterns",))
    assert _read_store(fake_home) == {"sess-1": {"day": _TODAY, "skills": ["python-patterns"]}}


def test_file_mutex_releases_so_a_second_acquisition_does_not_deadlock(hook, fake_home) -> None:
    lock = _lock_path(fake_home)
    lock.parent.mkdir(parents=True, exist_ok=True)

    with hook._file_mutex(lock):
        pass
    with hook._file_mutex(lock):
        pass

    assert lock.exists()


# ---------------------------------------------------------------------------
# Audit: resolve-failed / skill-unreadable / silence on suppressed + throttled
# ---------------------------------------------------------------------------

def test_a_missing_strunk_cache_is_audited_as_resolve_failed(hook, monkeypatch, capsys, fake_home) -> None:
    out = _run(hook, monkeypatch, capsys, _payload(file_path="/repo/app.py", session_id="sess-r"))

    assert out == ""
    events = _read_audit_events(fake_home)
    assert len(events) == 1
    event = events[0]
    assert event["decision"] == "resolve-failed"
    assert event["session"] == "sess-r"
    assert event["file"] == "/repo/app.py"
    assert event["skills"] == []
    assert event["version"] is None
    _assert_fresh_utc_timestamp(event["ts"])


@_SKIP_AS_ROOT
def test_an_unreadable_skill_md_is_audited_and_the_readable_skills_still_ship(
    hook, monkeypatch, capsys, fake_home
) -> None:
    _write_cache(fake_home)
    unreadable = _skill_md(fake_home, "apply-design-system")
    unreadable.chmod(0o000)
    try:
        out = _run(hook, monkeypatch, capsys, _payload(file_path="/repo/Card.svelte", session_id="sess-u"))
    finally:
        unreadable.chmod(0o600)

    context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    delivered = ("web-patterns", "web-security", "web-performance", "frontend-patterns")
    assert context == _expected_payload(delivered)

    events = _read_audit_events(fake_home)
    decisions = [e["decision"] for e in events]
    assert "skill-unreadable" in decisions
    unreadable_event = events[decisions.index("skill-unreadable")]
    assert unreadable_event["session"] == "sess-u"
    assert unreadable_event["file"] == "/repo/Card.svelte"
    # The audit exists to make a silently-dead delivery path greppable, so the event
    # names the skill that FAILED (not the delivered set) and the version it failed in.
    assert unreadable_event["skills"] == ["apply-design-system"]
    assert unreadable_event["version"] == "0.2.0"
    _assert_fresh_utc_timestamp(unreadable_event["ts"])

    inject_event = events[decisions.index("inject")]
    assert inject_event["skills"] == list(delivered)


def test_the_suppressed_path_is_never_audited(hook, monkeypatch, capsys, fake_home) -> None:
    _write_cache(fake_home)

    out = _run(hook, monkeypatch, capsys, _payload(file_path="/repo/README.md"))

    assert out == ""
    assert _read_audit_events(fake_home) == []
    assert not _audit_path(fake_home).exists()


@_SKIP_AS_ROOT
def test_an_unwritable_audit_file_neither_raises_nor_suppresses_the_injection(
    hook, monkeypatch, capsys, fake_home
) -> None:
    _write_cache(fake_home)
    audit = _audit_path(fake_home)
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text("", encoding="utf-8")
    audit.chmod(0o400)
    try:
        out = _run(hook, monkeypatch, capsys, _payload(file_path="/repo/app.py"))

        assert json.loads(out)["hookSpecificOutput"]["additionalContext"] == _expected_payload(("python-patterns",))
        assert _read_store(fake_home) == {"sess-1": {"day": _TODAY, "skills": ["python-patterns"]}}
        assert audit.read_text(encoding="utf-8") == ""
    finally:
        audit.chmod(0o600)


def test_append_audit_swallows_an_unusable_audit_path(hook, fake_home, capsys) -> None:
    _audit_path(fake_home).mkdir(parents=True)  # a directory where the log belongs

    hook._append_audit(  # must not raise
        {"ts": _TODAY, "session": "s", "decision": "inject", "file": "/a.py", "skills": [], "version": "0.2.0"}
    )

    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# Suppressed-path purity (the latency contract, asserted structurally)
# ---------------------------------------------------------------------------

def test_an_unmapped_extension_touches_neither_the_cache_nor_the_store_on_disk(
    hook, monkeypatch, capsys, fake_home, io_watch
) -> None:
    """The common case (.md/.json/.sh) must cost nothing beyond parsing stdin: no
    cache scan, no store read, no SKILL.md read.

    Checked two ways, because each catches what the other misses. The name spy catches
    a plain call to `resolve_strunk_skills_dir` / `_load_store`; it is blind to an
    implementation that calls its own private helpers instead. The I/O spy catches the
    filesystem access whatever internal route reaches it, down to `os.open`/`os.read`;
    it is blind to a call that does no I/O. Recorded rather than timed, so the contract
    is pinned deterministically instead of against a wall clock.
    """
    _write_cache(fake_home)
    _seed_store_file(fake_home, {"sess-1": {"day": _TODAY, "skills": []}})
    calls: list[str] = []
    monkeypatch.setattr(hook, "resolve_strunk_skills_dir", _forbid_call("resolve_strunk_skills_dir", calls))
    monkeypatch.setattr(hook, "_load_store", _forbid_call("_load_store", calls))
    io_watch.clear()  # ignore this test's own setup writes

    for ext in _UNMAPPED_EXTS:
        out = _run(hook, monkeypatch, capsys, _payload(file_path=f"{_novel_dir()}/{_novel_stem()}{ext}"))
        assert out == ""

    assert calls == []
    assert _accesses_under(io_watch, _cache_root(fake_home)) == []
    assert _accesses_under(io_watch, _store_path(fake_home).parent) == []


def test_a_non_file_tool_touches_neither_the_cache_nor_the_store_on_disk(
    hook, monkeypatch, capsys, fake_home, io_watch
) -> None:
    _write_cache(fake_home)
    _seed_store_file(fake_home, {"sess-1": {"day": _TODAY, "skills": []}})
    calls: list[str] = []
    monkeypatch.setattr(hook, "resolve_strunk_skills_dir", _forbid_call("resolve_strunk_skills_dir", calls))
    monkeypatch.setattr(hook, "_load_store", _forbid_call("_load_store", calls))
    io_watch.clear()

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({
        "session_id": "sess-1", "tool_name": "Bash", "tool_input": {"command": "python app.py"},
    })))
    hook.main()

    assert capsys.readouterr().out == ""
    assert calls == []
    assert _accesses_under(io_watch, _cache_root(fake_home)) == []
    assert _accesses_under(io_watch, _store_path(fake_home).parent) == []


def test_a_mapped_extension_does_reach_the_cache_and_the_store_on_disk(
    hook, monkeypatch, capsys, fake_home, io_watch
) -> None:
    """The control for the two purity tests above: proves the io_watch spy actually
    sees the accesses it claims are absent on the suppressed path. Without this, a
    spy that recorded nothing at all would make those tests vacuously green."""
    _write_cache(fake_home)
    _seed_store_file(fake_home, {"sess-1": {"day": _TODAY, "skills": []}})
    io_watch.clear()

    out = _run(hook, monkeypatch, capsys, _payload(file_path=f"{_novel_dir()}/{_novel_stem()}.py"))

    assert out != ""
    assert _accesses_under(io_watch, _cache_root(fake_home)) != []
    assert _accesses_under(io_watch, _store_path(fake_home).parent) != []


# ---------------------------------------------------------------------------
# Exit-0 contract: malformed input never yields an envelope, never fails
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "stdin_text",
    [
        "",
        "   \n",
        "not json at all",
        "[]",
        "42",
        '"a string"',
        "null",
        json.dumps({"session_id": "sess-1", "tool_name": "Read"}),
        json.dumps({"session_id": "sess-1", "tool_name": "Read", "tool_input": {}}),
        json.dumps({"session_id": "sess-1", "tool_input": {"file_path": "/repo/app.py"}}),
        json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/repo/app.py"}}),
    ],
    ids=[
        "empty-stdin", "whitespace-stdin", "non-json", "json-list", "json-int", "json-string",
        "json-null", "absent-tool_input", "absent-file_path", "absent-tool_name",
        "absent-session_id",
    ],
)
def test_malformed_stdin_exits_zero_without_an_envelope(tmp_path, stdin_text: str) -> None:
    """The fake cache is fully populated, so a well-formed payload *would* inject here
    (see the integration test): the input shape alone is what produces silence."""
    _write_cache(tmp_path)

    proc = _run_subprocess(tmp_path, stdin_text)

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""
    assert not _store_path(tmp_path).exists()


@_SKIP_AS_ROOT
def test_every_mapped_skill_unreadable_exits_zero_without_an_envelope(tmp_path) -> None:
    _write_cache(tmp_path)
    unreadable = _skill_md(tmp_path, "python-patterns")
    unreadable.chmod(0o000)
    try:
        proc = _run_subprocess(tmp_path, json.dumps(_payload(file_path="/repo/app.py")))
    finally:
        unreadable.chmod(0o600)

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""


@_SKIP_AS_ROOT
def test_an_unreadable_skill_is_not_recorded_so_the_next_touch_retries_it(
    hook, monkeypatch, capsys, fake_home
) -> None:
    """Burning the throttle slot on a read failure would silence the skill for the whole
    session; only delivered skills are recorded."""
    _write_cache(fake_home)
    skill_md = _skill_md(fake_home, "python-patterns")
    original = skill_md.read_text(encoding="utf-8")
    skill_md.chmod(0o000)
    try:
        first = _run(hook, monkeypatch, capsys, _payload(file_path="/repo/app.py", session_id="sess-retry"))
    finally:
        skill_md.chmod(0o600)

    assert first == ""
    assert _read_store(fake_home).get("sess-retry", {}).get("skills", []) == []

    second = _run(hook, monkeypatch, capsys, _payload(file_path="/repo/app.py", session_id="sess-retry"))

    assert json.loads(second)["hookSpecificOutput"]["additionalContext"] == (
        _attribution("python-patterns") + "\n\n" + hook.strip_frontmatter(original)
    )
    assert _read_store(fake_home)["sess-retry"]["skills"] == ["python-patterns"]


# ---------------------------------------------------------------------------
# Exit-0 contract: storage failures never cost the delivery
# ---------------------------------------------------------------------------

@_SKIP_AS_ROOT
def test_an_unwritable_store_dir_exits_zero_and_still_emits_the_envelope(tmp_path) -> None:
    """Store, lock and audit all live in this dir; none of them may outrank delivery."""
    _write_cache(tmp_path)
    d = _store_path(tmp_path).parent
    d.mkdir(parents=True, exist_ok=True)
    d.chmod(0o500)
    try:
        proc = _run_subprocess(tmp_path, json.dumps(_payload(file_path="/repo/app.py")))
    finally:
        d.chmod(0o700)

    assert proc.returncode == 0, proc.stderr
    envelope = json.loads(proc.stdout)
    assert envelope["hookSpecificOutput"]["additionalContext"] == _expected_payload(("python-patterns",))
    assert not _store_path(tmp_path).exists()


@_SKIP_AS_ROOT
def test_an_unwritable_lock_path_exits_zero_and_still_emits_the_envelope(tmp_path) -> None:
    _write_cache(tmp_path)
    lock = _lock_path(tmp_path)
    lock.mkdir(parents=True)

    proc = _run_subprocess(tmp_path, json.dumps(_payload(file_path="/repo/app.py")))

    assert proc.returncode == 0, proc.stderr
    envelope = json.loads(proc.stdout)
    assert envelope["hookSpecificOutput"]["additionalContext"] == _expected_payload(("python-patterns",))


@_SKIP_AS_ROOT
def test_an_unwritable_audit_file_exits_zero_and_still_emits_the_envelope(tmp_path) -> None:
    _write_cache(tmp_path)
    audit = _audit_path(tmp_path)
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text("", encoding="utf-8")
    audit.chmod(0o400)
    try:
        proc = _run_subprocess(tmp_path, json.dumps(_payload(file_path="/repo/app.py")))
    finally:
        audit.chmod(0o600)

    assert proc.returncode == 0, proc.stderr
    envelope = json.loads(proc.stdout)
    assert envelope["hookSpecificOutput"]["additionalContext"] == _expected_payload(("python-patterns",))
    assert audit.read_text(encoding="utf-8") == ""


# ---------------------------------------------------------------------------
# Integration: real process, real stdin, real cache tree
# ---------------------------------------------------------------------------

def test_a_real_pretooluse_payload_yields_a_parseable_envelope(tmp_path) -> None:
    _write_cache(tmp_path)
    stdin_text = json.dumps({
        "session_id": "int-1",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": "/repo",
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": "/repo/src/app.py", "old_string": "a", "new_string": "b"},
    })

    proc = _run_subprocess(tmp_path, stdin_text)

    assert proc.returncode == 0, proc.stderr
    envelope = json.loads(proc.stdout)
    assert envelope == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": _expected_payload(("python-patterns",)),
        }
    }
    assert _read_store(tmp_path) == {"int-1": {"day": _TODAY, "skills": ["python-patterns"]}}
    assert [e["decision"] for e in _read_audit_events(tmp_path)] == ["inject"]


# ---------------------------------------------------------------------------
# Real installed cache: every mapped skill must actually exist
# ---------------------------------------------------------------------------

def test_every_mapped_skill_resolves_to_a_readable_skill_md_in_the_installed_cache() -> None:
    """Runs against the REAL strunk install (no sandboxed home): a name that drifts out
    of the plugin silently degrades to no guidance, which the fixture tree cannot catch."""
    mod = _load_hook()
    resolved = mod.resolve_strunk_skills_dir()
    if resolved is None:
        pytest.skip("the strunk plugin cache is not installed")
    skills_dir, _version = resolved

    mapped: set[str] = set()
    for table in (mod._SKILLS_BY_EXT, mod._TEST_SKILLS_BY_EXT):
        for skills in table.values():
            mapped.update(skills)

    unreadable = []
    for skill in sorted(mapped):
        path = skills_dir / skill / "SKILL.md"
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            unreadable.append(skill)
            continue
        if not mod.strip_frontmatter(body).strip():
            unreadable.append(skill)

    assert unreadable == [], f"mapped skills missing/empty in {skills_dir}: {unreadable}"
