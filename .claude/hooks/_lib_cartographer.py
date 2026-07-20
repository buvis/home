"""Shared library for Cartographer hooks/skills.

Stdlib-only (except optional `tree_sitter_language_pack`, accessed lazily via
`try_import_tree_sitter`). Python 3.10+. Safe to import from any PreToolUse,
PostToolUse, Notification, or Stop hook. Public API + conventions:

    project_hash, atlas_dir, append_audit, resolve_session_key,
    load_session_state, save_session_state, is_checked, mark_checked,
    try_import_tree_sitter.

- Project hash: `sha256(<git-remote-or-toplevel-path>)[:12]`. Decoupled copy
  of `analyze-instincts.py:detect_project`; parity test guards drift.
- Per-repo state: `~/.claude/cartographer/projects/<hash>/`.
- Audit log: `~/.claude/cartographer/audit.jsonl` (one JSON event per line).
- Session-state: `~/.claude/cache/cartographer/<namespace>/state-<key>.json`.

Keep under 400 lines (PRD 00009); split into a package if exceeded.
"""

from __future__ import annotations

import fcntl
import hashlib
import importlib
import json
import os
import re
import sys
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Iterator

# project_hash split into a sibling module for the PRD-00009 400-line cap when
# the ~/.claude work-tree fallback landed (PRD 00088); re-exported so
# `lib.project_hash` is unchanged for every caller and test.
from _cartographer_identity import project_hash as project_hash


def _home() -> Path:
    """Indirection so tests can monkeypatch `Path.home`."""
    return Path.home()


def _cartographer_root() -> Path:
    return _home() / ".claude" / "cartographer"


def _cache_root() -> Path:
    return _home() / ".claude" / "cache" / "cartographer"


def _audit_log() -> Path:
    return _cartographer_root() / "audit.jsonl"


# --- per-repo addressing ---
# `project_hash` is re-exported from `_cartographer_identity` (imported above).


def atlas_dir(project_hash: str) -> Path:
    """Resolve the projects-root subdir for a project hash (no mkdir).

    The argument is validated against `[a-zA-Z0-9_-]+` (defense-in-depth,
    matching `_state_path`) so a caller passing user-derived input cannot
    escape via `..` or `/`. The parameter name matches the PRD signature
    and intentionally shadows the module-level `project_hash` function.
    """
    _validate_path_segment(project_hash, "project_hash")
    return _cartographer_root() / "projects" / project_hash


# --- filesystem init + audit log ---


def _ensure_dirs() -> None:
    """Idempotently create the cartographer on-disk layout (no `scripts/`).

    `scripts/` ships via the buvis bare repo, so runtime mkdir would be pure
    hot-path overhead. OSError is swallowed: hooks must not crash the host tool.
    """
    try:
        root = _cartographer_root()
        root.mkdir(parents=True, exist_ok=True)
        (root / "projects").mkdir(parents=True, exist_ok=True)
        _cache_root().mkdir(parents=True, exist_ok=True)
        log = _audit_log()
        if not log.exists():
            log.touch()
    except OSError as exc:
        print(f"[cartographer] _ensure_dirs failed: {exc}", file=sys.stderr)


def _atomic_append(path: Path, line: str) -> None:
    """Append a single line via `mode='a'` (POSIX O_APPEND).

    Python TextIOWrapper buffers `fh.write` and emits one `write(2)` at
    `__exit__` for ~80B audit lines (well under the 8KiB default buffer).
    The kernel applies O_APPEND atomicity per syscall (offset advance under
    the inode lock), so concurrent appenders do not interleave within that
    single small write; larger writes that split across syscalls would lose
    this guarantee. `test_append_audit_concurrent_threads` verifies behavior
    empirically. PIPE_BUF governs pipes/FIFOs, not regular files.
    """
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


_DIRS_ENSURED: bool = False


def append_audit(event: dict) -> None:
    """Append one event to ~/.claude/cartographer/audit.jsonl.

    Stamps `ts` (ISO-8601 UTC) if absent. Never raises: I/O or
    serialization failures emit a one-line stderr warning and return.
    `_ensure_dirs` is invoked once per process (sentinel-cached) so the
    audit hot path skips repeated mkdir/exists syscalls after the first
    successful init.
    """
    global _DIRS_ENSURED
    try:
        if "ts" not in event:
            event = {"ts": datetime.now(timezone.utc).isoformat(), **event}
        line = json.dumps(event, ensure_ascii=False) + "\n"
        if not _DIRS_ENSURED:
            _ensure_dirs()
            _DIRS_ENSURED = True
        _atomic_append(_audit_log(), line)
    except (OSError, TypeError, ValueError) as exc:
        # Hooks cannot crash the host tool. Surface the failure to stderr
        # and return so the calling Edit/Write proceeds.
        print(f"[cartographer] append_audit failed: {exc}", file=sys.stderr)


def _reset_ensure_dirs_for_tests() -> None:
    """Test-only: clear the `_DIRS_ENSURED` sentinel. Production never calls this."""
    global _DIRS_ENSURED
    _DIRS_ENSURED = False


# --- session-key resolution (verbatim copy of gateguard-fact-force.py:104-135) ---


def _hash_key(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"


def _sanitize_session_key(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", raw)
    if sanitized and len(sanitized) <= 64:
        return sanitized
    return _hash_key("sid", raw)


def resolve_session_key(data: dict) -> str:
    """Derive a stable session key from PreToolUse hook input.

    Decoupled copy of `gateguard-fact-force.py:resolve_session_key`; behavioral
    parity verified by `test_resolve_session_key_parity_with_gateguard`.
    Prefers explicit `session_id`, then a `transcript_path` hash, then a cwd hash.
    """
    candidates = [
        data.get("session_id"),
        data.get("sessionId"),
        (data.get("session") or {}).get("id") if isinstance(data.get("session"), dict) else None,
        os.environ.get("CLAUDE_SESSION_ID"),
    ]
    for c in candidates:
        sanitized = _sanitize_session_key(c if isinstance(c, str) else None)
        if sanitized:
            return sanitized

    transcript = (
        data.get("transcript_path")
        or data.get("transcriptPath")
        or os.environ.get("CLAUDE_TRANSCRIPT_PATH")
    )
    if isinstance(transcript, str) and transcript.strip():
        return _hash_key("tx", str(Path(transcript.strip()).resolve()))

    project = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return _hash_key("proj", str(Path(project).resolve()))


# --- namespaced session-state I/O ---


_VALID_PATH_SEGMENT = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_path_segment(value: str, kind: str) -> None:
    """Reject path-traversal vectors at the lib boundary (`[a-zA-Z0-9_-]+`).

    Sanitized session keys already conform; this guards callers that bypass
    `resolve_session_key` or pass an unsanitized namespace.
    """
    if not isinstance(value, str) or not _VALID_PATH_SEGMENT.fullmatch(value):
        raise ValueError(
            f"_lib_cartographer: invalid {kind} {value!r}; "
            "must match [a-zA-Z0-9_-]+ (no slashes, dots, spaces, newlines, or null bytes)"
        )


def _state_path(session_key: str, namespace: str) -> Path:
    _validate_path_segment(session_key, "session_key")
    _validate_path_segment(namespace, "namespace")
    return _cache_root() / namespace / f"state-{session_key}.json"


def load_session_state(session_key: str, namespace: str) -> dict:
    """Read a per-session, per-namespace state dict.

    Missing files and corrupted JSON return `{}` so callers can treat the
    cache as best-effort.
    """
    path = _state_path(session_key, namespace)
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        # UnicodeDecodeError covers a state file containing non-UTF-8 bytes
        # (partial-write corruption from a non-cartographer writer); the
        # contract is missing/corrupted -> {}, so swallow.
        return {}
    return loaded if isinstance(loaded, dict) else {}


def save_session_state(session_key: str, namespace: str, state: dict) -> None:
    """Atomically write per-session, per-namespace state.

    Uses tempfile + os.replace so a crash mid-write leaves the prior file
    intact. I/O failures (OSError, serialization) are logged to stderr and
    swallowed. `ValueError` from `_state_path` input validation (invalid
    `session_key` or `namespace`) propagates to the caller; that is a
    programming-error class and must fail loudly.
    """
    path = _state_path(session_key, namespace)
    tmp_path: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".tmp.")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
        tmp_path = None
    except (OSError, TypeError, ValueError) as exc:
        print(f"[cartographer] save_session_state failed: {exc}", file=sys.stderr)
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# --- file-level mutex (cross-process + cross-thread) ---


_PROC_LOCKS: dict[str, threading.Lock] = {}
_PROC_LOCKS_GUARD = threading.Lock()


@contextmanager
def _file_mutex(lock_path: Path) -> Iterator[None]:
    """Serialize critical sections across processes and threads.

    Combines `fcntl.flock` (cross-process, per-fd) with a per-path
    `threading.Lock` (cross-thread within a single process). Both must be
    held; release order is reversed via context-manager unwind.
    """
    key = str(lock_path)
    with _PROC_LOCKS_GUARD:
        tlock = _PROC_LOCKS.setdefault(key, threading.Lock())
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with tlock, open(lock_path, "w", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


# --- checked-marker primitives ---


def is_checked(session_key: str, namespace: str, key: str) -> bool:
    """Return True iff `key` has been marked in this session+namespace."""
    state = load_session_state(session_key, namespace)
    checked = state.get("checked")
    return isinstance(checked, dict) and key in checked


def mark_checked(session_key: str, namespace: str, key: str) -> None:
    """Record `key` as checked, stamping the current ISO-8601 UTC time.

    The load-modify-save is serialized via `_file_mutex` on a sentinel
    `.lock` sidecar so concurrent threads or processes that mark distinct
    keys against the same session+namespace cannot lose updates. The
    atomic temp+rename in `save_session_state` alone only prevents partial
    reads, not lost writes.
    """
    state_path = _state_path(session_key, namespace)
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    with _file_mutex(lock_path):
        state = load_session_state(session_key, namespace)
        checked = state.get("checked")
        if not isinstance(checked, dict):
            checked = {}
            state["checked"] = checked
        checked[key] = datetime.now(timezone.utc).isoformat()
        save_session_state(session_key, namespace, state)


# --- tree-sitter graceful-import wrapper ---


_TREE_SITTER_LOCK = threading.Lock()
_TREE_SITTER_LOADED: bool = False
_TREE_SITTER_MODULE: ModuleType | None = None
_TREE_SITTER_WARNED: bool = False


def try_import_tree_sitter() -> ModuleType | None:
    """Import `tree_sitter_language_pack` once per process; return None if missing.

    The first failed import emits one `tree_sitter_missing` audit entry.
    Subsequent calls return the cached result and never re-warn. Uses
    double-checked locking so concurrent first-callers do not each emit an
    audit entry (PRD contract: deduped per process).
    """
    global _TREE_SITTER_LOADED, _TREE_SITTER_MODULE, _TREE_SITTER_WARNED

    if _TREE_SITTER_LOADED:
        return _TREE_SITTER_MODULE

    with _TREE_SITTER_LOCK:
        if _TREE_SITTER_LOADED:
            return _TREE_SITTER_MODULE
        try:
            _TREE_SITTER_MODULE = importlib.import_module("tree_sitter_language_pack")
        except ImportError:
            _TREE_SITTER_MODULE = None
            if not _TREE_SITTER_WARNED:
                append_audit({"event": "tree_sitter_missing"})
                _TREE_SITTER_WARNED = True
        _TREE_SITTER_LOADED = True
        return _TREE_SITTER_MODULE


def _reset_tree_sitter_cache_for_tests() -> None:
    """Test-only: reset the process-lifetime import cache. Never used in production."""
    global _TREE_SITTER_LOADED, _TREE_SITTER_MODULE, _TREE_SITTER_WARNED
    _TREE_SITTER_LOADED = False
    _TREE_SITTER_MODULE = None
    _TREE_SITTER_WARNED = False
