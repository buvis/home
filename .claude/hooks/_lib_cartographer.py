"""Shared library for Cartographer hooks/skills.

Stdlib-only (except optional `tree_sitter_language_pack`, accessed lazily via
`try_import_tree_sitter`). Python 3.10+. Safe to import from any PreToolUse,
PostToolUse, Notification, or Stop hook.

Public API (added incrementally across PRD 00009 Phase 0 tasks):

    project_hash(path=None) -> tuple[str, str, str]
    atlas_dir(project_hash) -> Path
    append_audit(event) -> None
    resolve_session_key(data) -> str
    load_session_state(session_key, namespace) -> dict
    save_session_state(session_key, namespace, state) -> None
    is_checked(session_key, namespace, key) -> bool
    mark_checked(session_key, namespace, key) -> None
    try_import_tree_sitter() -> ModuleType | None

Conventions
-----------
- Project hash: `sha256(<git-remote-or-toplevel-path>)[:12]`. Decoupled copy
  of `analyze-instincts.py:detect_project` (behavioral parity verified by
  `test_project_hash_matches_analyze_instincts_detect_project`).
- Persistent per-repo state lives under `~/.claude/cartographer/projects/<hash>/`.
- Audit log appends to `~/.claude/cartographer/audit.jsonl` (one JSON event per line).
- Session-state cache at `~/.claude/cache/cartographer/<namespace>/state-<session_key>.json`.

This file is referenced by Phase 1+ Cartographer hooks; keep it under 400 lines.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType


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


def project_hash(path: str | None = None) -> tuple[str, str, str]:
    """Determine project identity from git remote or toplevel path.

    Behavioral copy of `analyze-instincts.py:detect_project` (decoupled per PRD
    00009 open question; this helper adds a `path` parameter the original lacks).
    Parity on shared inputs is enforced by
    `test_project_hash_matches_analyze_instincts_detect_project`.
    Returns `(hash, name, remote_url)`.

    - If a git remote `origin` is configured, hash its URL (with embedded
      credentials stripped) and return its stem as `name`.
    - Otherwise hash the toplevel path returned by `git rev-parse`.
    - On full failure (not a git repo, git not installed) return
      `("global", "global", "")`.

    `path` overrides the working directory of the underlying git invocations
    (defaults to cwd, matching analyze-instincts).
    """
    cwd = path  # subprocess.run accepts None to mean "inherit cwd"
    try:
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=cwd,
            capture_output=True, text=True, timeout=5,
        )
        if remote.returncode == 0 and remote.stdout.strip():
            url = remote.stdout.strip()
            clean = re.sub(r"://[^@]+@", "://", url)
            h = hashlib.sha256(clean.encode()).hexdigest()[:12]
            name = Path(url.rstrip("/")).stem
            return h, name, clean
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    try:
        toplevel = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True, text=True, timeout=5,
        )
        if toplevel.returncode == 0 and toplevel.stdout.strip():
            top = toplevel.stdout.strip()
            h = hashlib.sha256(top.encode()).hexdigest()[:12]
            return h, Path(top).name, ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return "global", "global", ""


def atlas_dir(project_hash: str) -> Path:
    """Resolve the persistent state directory for a project hash.

    Pure path computation; does NOT create the directory.
    """
    return _cartographer_root() / "projects" / project_hash


# --- filesystem init + audit log ---


def _ensure_dirs() -> None:
    """Idempotently create the cartographer on-disk layout.

    Phase 1+ hooks may invoke this lazily; tests may invoke it directly.
    OSError is swallowed because hooks must never crash the host tool.
    """
    try:
        root = _cartographer_root()
        root.mkdir(parents=True, exist_ok=True)
        (root / "projects").mkdir(parents=True, exist_ok=True)
        (root / "scripts").mkdir(parents=True, exist_ok=True)
        _cache_root().mkdir(parents=True, exist_ok=True)
        log = _audit_log()
        if not log.exists():
            log.touch()
    except OSError as exc:
        print(f"[cartographer] _ensure_dirs failed: {exc}", file=sys.stderr)


def _atomic_append(path: Path, line: str) -> None:
    """Append a single line to `path` in `mode='a'` (sets O_APPEND on POSIX).

    With O_APPEND the kernel atomically advances the file offset and writes
    the buffer under the inode lock, so concurrent appends from any process
    holding an O_APPEND fd to this file do not interleave for writes that
    fit in one syscall. Audit lines (one JSON event each) stay well under
    any practical syscall limit.

    PIPE_BUF does not apply here. PIPE_BUF only governs atomicity of pipe /
    FIFO writes; regular-file append atomicity comes from O_APPEND.
    """
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def append_audit(event: dict) -> None:
    """Append one event to ~/.claude/cartographer/audit.jsonl.

    Stamps `ts` (ISO-8601 UTC) if absent. Never raises: I/O or
    serialization failures emit a one-line stderr warning and return.
    """
    try:
        if "ts" not in event:
            event = {"ts": datetime.now(timezone.utc).isoformat(), **event}
        line = json.dumps(event, ensure_ascii=False) + "\n"
        _ensure_dirs()
        _atomic_append(_audit_log(), line)
    except (OSError, TypeError, ValueError) as exc:
        # Hooks cannot crash the host tool. Surface the failure to stderr
        # and return so the calling Edit/Write proceeds.
        print(f"[cartographer] append_audit failed: {exc}", file=sys.stderr)


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
    """Reject anything that could escape the cache root via path tricks.

    Session keys produced by `_sanitize_session_key` already conform to
    `[a-zA-Z0-9_-]`. This boundary check guards `load_session_state` /
    `save_session_state` against callers that bypass `resolve_session_key`
    (or that ever pass an unsanitized namespace).
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
    except (OSError, json.JSONDecodeError):
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


# --- checked-marker primitives ---


def is_checked(session_key: str, namespace: str, key: str) -> bool:
    """Return True iff `key` has been marked in this session+namespace."""
    state = load_session_state(session_key, namespace)
    checked = state.get("checked")
    return isinstance(checked, dict) and key in checked


def mark_checked(session_key: str, namespace: str, key: str) -> None:
    """Record `key` as checked, stamping the current ISO-8601 UTC time."""
    state = load_session_state(session_key, namespace)
    checked = state.get("checked")
    if not isinstance(checked, dict):
        checked = {}
        state["checked"] = checked
    checked[key] = datetime.now(timezone.utc).isoformat()
    save_session_state(session_key, namespace, state)


# --- tree-sitter graceful-import wrapper ---


_TREE_SITTER_LOADED: bool = False
_TREE_SITTER_MODULE: ModuleType | None = None
_TREE_SITTER_WARNED: bool = False


def try_import_tree_sitter() -> ModuleType | None:
    """Import `tree_sitter_language_pack` once per process; return None if missing.

    The first failed import emits one `tree_sitter_missing` audit entry.
    Subsequent calls return the cached result and never re-warn.
    """
    global _TREE_SITTER_LOADED, _TREE_SITTER_MODULE, _TREE_SITTER_WARNED

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
    """Test-only helper: reset the process-lifetime import cache.

    Production code never calls this. The `_for_tests` suffix and underscore
    prefix mark it as private + test-only; test cases use it to simulate
    first-call state for `try_import_tree_sitter`.
    """
    global _TREE_SITTER_LOADED, _TREE_SITTER_MODULE, _TREE_SITTER_WARNED
    _TREE_SITTER_LOADED = False
    _TREE_SITTER_MODULE = None
    _TREE_SITTER_WARNED = False
