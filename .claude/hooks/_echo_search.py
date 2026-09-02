"""ripgrep candidate search for the Echo duplicate-detection gate.

Extracted from `cartographer-echo.py` (`# --- ripgrep candidate search ---`,
PRD 00158): one rg over an alternation of the symbols a write is about to
define, grouped per symbol and ranked definition-first, plus the stopword
filter that decides which symbols are worth searching for at all and the
project-root resolution the search runs under. The test-file predicate lives
here because the stopword filter is its only consumer outside the entry hook,
which imports it back.

Stdlib only. Python 3.10+.
"""

from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
from pathlib import Path

import _lib_cartographer as lib
from _echo_symbols import _defined_name

# Low-signal names dropped before match scoring. The duplicate-prone verbs
# (`format`/`parse`/`validate`/`normalize`/`serialize`/`transform`) are
# deliberately ABSENT from this list (PRD success metric).
_STOPWORDS: frozenset[str] = frozenset(
    {
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
        # Generic names defined across many files; collisions are not duplicates.
        # Added 2026-05-31 from audit-echo (top recurring deny symbols).
        "create",
        "setUp",
        "Result",
    },
)
_MIN_SYMBOL_LEN: int = 4  # drop length <= 3

# Test-file path patterns. Matched as substrings (segments) or filename
# suffixes; tests in the project's `tests/` or `test/` dirs, `*_test.go`
# (Go convention), and `*.test.{ts,tsx,js,jsx}` (JS/TS convention).
_TEST_DIR_SEGMENTS: tuple[str, ...] = ("/tests/", "/test/")
_TEST_FILE_SUFFIXES: tuple[str, ...] = (
    "_test.go",
    "_test.py",
    ".test.ts",
    ".test.tsx",
    ".test.js",
    ".test.jsx",
)

_RG_TIMEOUT_SEC: float = 1.0
_RG_MAX_HITS_PER_SYMBOL: int = 5  # hits handed to scoring
_RG_SCAN_LIMIT: int = 50  # hits collected per symbol before definition-first ranking
_RG_BATCH_SCAN_LIMIT: int = (
    500  # total rg output lines parsed per batch (bounds attribution)
)
_RG_EXCLUDE_GLOBS: tuple[str, ...] = (
    "!.git",
    "!node_modules",
    "!vendor",
    "!dist",
    "!build",
    "!__pycache__",
    "!target",
    "!.venv",
)


def is_test_file_path(file_path: str) -> bool:
    if not file_path:
        return False
    norm = file_path.replace("\\", "/")
    if any(seg in norm for seg in _TEST_DIR_SEGMENTS):
        return True
    if any(norm.endswith(suffix) for suffix in _TEST_FILE_SUFFIXES):
        return True
    # pytest prefix convention: test_*.py
    base = norm.rsplit("/", 1)[-1]
    return base.startswith("test_") and base.endswith(".py")


@functools.lru_cache(maxsize=1)
def _resolve_rg() -> str | None:
    """Path to an executable that behaves like ripgrep, or None.

    `rg` is not always a binary on PATH. On a Claude Code install it can be a
    shell function that re-execs the host binary with `argv[0]` set to "rg"
    (`exec -a rg "$CLAUDE_CODE_EXECPATH"`), which `subprocess.run(["rg", ...])`
    never sees: PATH has no `rg`, the spawn raises FileNotFoundError, and echo
    silently reports zero candidates on every edit. Measured 2026-08-26: 621
    `ripgrep_missing` events in a single day, the duplicate-detection gate dead.

    So resolve it the way the shell function does - a real `rg` first, then the
    host binary run under an `argv[0]` of "rg" (callers pass this as
    `executable=`). Cached: this sits on the PreToolUse hot path and the answer
    cannot change within a process. Tests reset it via `_resolve_rg.cache_clear()`.
    """
    found = shutil.which("rg")
    if found is not None:
        return found
    for candidate in (
        os.environ.get("CLAUDE_CODE_EXECPATH"),
        str(Path.home() / ".local" / "bin" / "claude"),
    ):
        if candidate and os.access(candidate, os.X_OK):
            return candidate
    return None


def _parse_rg_line(line: str) -> tuple[str, int, str] | None:
    """Split an `rg -n` line `<file>:<lineno>:<snippet>` -> (file, lineno, snippet)."""
    first = line.find(":")
    if first <= 0:
        return None
    second = line.find(":", first + 1)
    if second <= 0:
        return None
    try:
        lineno = int(line[first + 1 : second])
    except ValueError:
        return None
    return line[:first], lineno, line[second + 1 :].strip()


def _spawn_rg(uniq: list[str], root: Path) -> str | None:
    """One rg over the alternation of `uniq` under `root`: stdout, or None
    after an audited failure (missing binary, timeout, non-match exit)."""
    rg_bin = _resolve_rg()
    if rg_bin is None:
        lib.append_audit({"event": "ripgrep_missing"})
        return None
    pattern = "|".join(re.escape(s) for s in uniq)
    # argv[0] stays "rg": the host binary dispatches on it (see _resolve_rg).
    args = ["rg", "-n", "--max-count", str(_RG_MAX_HITS_PER_SYMBOL * len(uniq))]
    for g in _RG_EXCLUDE_GLOBS:
        args.extend(["--glob", g])
    args.extend(["-e", pattern, "--", str(root)])
    try:
        proc = subprocess.run(
            args,
            executable=rg_bin,
            capture_output=True,
            text=True,
            timeout=_RG_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        lib.append_audit({"event": "ripgrep_timeout", "symbols": len(uniq)})
        return None
    except (FileNotFoundError, PermissionError):
        # Resolved path vanished or lost +x between resolve and spawn.
        _resolve_rg.cache_clear()
        lib.append_audit({"event": "ripgrep_missing"})
        return None
    if proc.returncode not in (0, 1):
        lib.append_audit(
            {
                "event": "ripgrep_error",
                "code": proc.returncode,
                "stderr": proc.stderr[:200],
            },
        )
        return None
    return proc.stdout


def search_candidates_batch(
    symbols: list[str],
    root: Path,
    target_file: Path,
) -> dict[str, list[dict]]:
    """One rg over an alternation of ALL symbols -> `{sym: hits}` (PRD 00088 R3).

    Replaces one rg spawn per symbol (which blew the 5s hook budget on
    symbol-dense files) with a single subprocess. Each group holds up to 5 hits
    `{"file", "line", "snippet"}`, excluding `target_file` and build dirs.
    Attribution is by literal substring, mirroring the per-symbol regex's
    unanchored substring match for identifiers: a line carrying two searched
    symbols lands in both groups, exactly as two separate rg runs would find it.
    On timeout, missing binary, or non-zero rg exit other than 1 (no match):
    returns empty groups and appends a `ripgrep_*` audit-warn event.
    """
    uniq = [s for s in dict.fromkeys(symbols) if s]
    empty: dict[str, list[dict]] = {s: [] for s in uniq}
    if not uniq or not root.exists():
        return empty
    stdout = _spawn_rg(uniq, root)
    if stdout is None:
        return empty
    groups = _group_hits(stdout, uniq, target_file)
    # Only definition lines can block, so rank them ahead of usage sites before
    # truncating: a stable sort keeps rg's order within each group, so the hit
    # cap never drops the duplicate definition behind unrelated call sites.
    for s in uniq:
        groups[s].sort(key=lambda c: _defined_name(c["snippet"]) is None)
        groups[s] = groups[s][:_RG_MAX_HITS_PER_SYMBOL]
    return groups


def _group_hits(
    stdout: str,
    uniq: list[str],
    target_file: Path,
) -> dict[str, list[dict]]:
    """Attribute rg output lines to every searched symbol they mention,
    skipping `target_file` and stopping at the batch scan cap."""
    groups: dict[str, list[dict]] = {s: [] for s in uniq}
    try:
        target_abs = str(target_file.resolve())
    except OSError:
        target_abs = str(target_file)

    scanned = 0
    for line in stdout.splitlines():
        if scanned >= _RG_BATCH_SCAN_LIMIT:
            break
        parsed = _parse_rg_line(line)
        if parsed is None:
            continue
        file_part, lineno, snippet = parsed
        try:
            cand_abs = str(Path(file_part).resolve())
        except OSError:
            cand_abs = file_part
        if cand_abs == target_abs:
            continue
        scanned += 1
        hit = {"file": file_part, "line": lineno, "snippet": snippet}
        for s in uniq:
            if s in snippet and len(groups[s]) < _RG_SCAN_LIMIT:
                groups[s].append(hit)
    return groups


def search_candidates(symbol: str, root: Path, target_file: Path) -> list[dict]:
    """ripgrep for a single `symbol` — the one-symbol case of
    `search_candidates_batch` (kept for its focused tests and any single-symbol
    caller). Returns up to 5 hits, or [] on rg failure."""
    return search_candidates_batch([symbol], root, target_file).get(symbol, [])


def filter_stopwords(symbols: list[str], file_path: str) -> list[str]:
    """Drop low-signal symbols. Returns [] when `file_path` is a test file.

    Test-file detection: any path containing `/tests/` or `/test/`, or
    ending with `_test.go`, `_test.py`, `.test.{ts,tsx,js,jsx}`. Echo
    intentionally never gates writes to test files (those write paths are
    where duplicate-detection produces the most false positives).
    """
    if is_test_file_path(file_path):
        return []
    out: list[str] = []
    for name in symbols:
        if not isinstance(name, str) or not name:
            continue
        if len(name) < _MIN_SYMBOL_LEN:
            continue
        if name in _STOPWORDS:
            continue
        out.append(name)
    return out


def _resolve_project_root(file_path: str) -> Path:
    """Find the git toplevel containing `file_path`, falling back to its parent.

    Echo searches across the project, so the root MUST be a real directory.
    `_lib_cartographer.project_hash` returns identity tuples (hash, name,
    remote), not a path, so we don't reuse it here. Routes through
    `_common.resolve_toplevel` (PRD 00133 finding 42) so this and
    enforce_prd_location.py's `_check_file_path`, both invoked with the same
    payload in the same dispatcher process, share the memoized `git
    rev-parse --show-toplevel` spawn instead of each shelling out on their
    own.
    """
    from _common import resolve_toplevel

    start = file_path or str(Path.cwd())
    root = resolve_toplevel(start)
    if root:
        return Path(root)
    parent = Path(file_path).parent if file_path else Path.cwd()
    return parent if parent.exists() else Path.cwd()
