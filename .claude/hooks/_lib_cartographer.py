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
import re
import subprocess
from pathlib import Path

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
    return Path.home() / ".claude" / "cartographer" / "projects" / project_hash
