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
- Project hash: `sha256(<git-remote-or-toplevel-path>)[:12]`. Decoupled
  byte-for-byte copy of `analyze-instincts.py:detect_project` per PRD 00009.
- Persistent per-repo state lives under `~/.claude/cartographer/projects/<hash>/`.
- Audit log appends to `~/.claude/cartographer/audit.jsonl` (one JSON event per line).
- Session-state cache at `~/.claude/cache/cartographer/<namespace>/state-<session_key>.json`.

This file is referenced by Phase 1+ Cartographer hooks; keep it under 400 lines.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


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

    Mirrors `analyze-instincts.py:detect_project` byte-for-byte (decoupled copy
    per PRD 00009 open question). Returns `(hash, name, remote_url)`.

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
    """Append a single line to `path` in `mode='a'`.

    A single `write()` call keeps the line atomic on POSIX for sizes under
    PIPE_BUF (4096 on Linux, 512 on macOS). Audit lines stay well under that.
    """
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def append_audit(event: dict) -> None:
    """Append one event to ~/.claude/cartographer/audit.jsonl.

    Stamps `ts` (ISO-8601 UTC) if absent. Never raises — I/O or
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
