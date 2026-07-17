#!/usr/bin/env python3
"""strunk-ruling-inject: inject strunk skill rulings once per (session, skill).

PreToolUse hook. Reads one JSON payload from stdin; when the tool's target file
has a mapped extension, injects the matching strunk `SKILL.md` bodies (verbatim,
under an attribution header) as `additionalContext`.

Never blocks a tool call: exit 0 on every path, diagnostics to stderr only.
Shape follows cartographer-recon-brief.py, with the (repo x UTC-day) throttle
key swapped for (session x skill).
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# The hooks/ directory is on sys.path when invoked via settings.json; prepend it
# explicitly so the module also resolves `_common` when loaded from any cwd
# (mirrors cartographer-echo.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common

_CACHE_ROOT = Path.home() / ".claude" / "plugins" / "cache" / "buvis-plugins" / "strunk"
_STORE_PATH = Path.home() / ".claude" / "cache" / "strunk-inject" / "injected.json"
_AUDIT_PATH = Path.home() / ".claude" / "cache" / "strunk-inject" / "audit.jsonl"

_WEB_SKILLS: tuple[str, ...] = (
    "web-patterns", "apply-design-system", "web-security", "web-performance",
)

# ext -> skills injected on ANY touch of that file type
_SKILLS_BY_EXT: dict[str, tuple[str, ...]] = {
    ".py": ("python-patterns",),
    ".pyi": ("python-patterns",),
    ".rs": ("rust-patterns",),
    ".css": _WEB_SKILLS,
    ".html": _WEB_SKILLS,
    ".vue": _WEB_SKILLS,
    ".ts": _WEB_SKILLS,
    ".tsx": _WEB_SKILLS,
    ".jsx": _WEB_SKILLS,
    ".svelte": _WEB_SKILLS + ("frontend-patterns",),
}

# ext -> EXTRA skills injected only when the path is a test file
_TEST_SKILLS_BY_EXT: dict[str, tuple[str, ...]] = {
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

# Mirrors cartographer-echo.py's convention (that module is not importable:
# hyphenated filename). Keep the two in sync by convention, not by import.
_TEST_DIR_SEGMENTS: tuple[str, ...] = ("/tests/", "/test/")
_TEST_FILE_SUFFIXES: tuple[str, ...] = (
    "_test.py", "_test.rs", ".test.ts", ".test.tsx", ".test.js", ".test.jsx",
    ".spec.ts", ".spec.tsx", ".spec.js",
)

# The Phase-0-PROVEN string, verbatim. It is the ONLY attribution value with a
# measured 3/3 obedience result. Do NOT add an authority claim, a version, or any
# other embellishment: the model audits injected imperatives for prompt-injection
# register, and a self-asserted authority claim is exactly that register.
_ATTRIBUTION = "Guidance for this file type, from the strunk `{skill}` skill:"

_TOOLS_WITH_FILE_PATH: tuple[str, ...] = ("Read", "Edit", "Write", "MultiEdit")


# --- path classification (mirrors cartographer-echo.py) ---


def file_extension(file_path: str) -> str:
    """Return the dotted lowercase extension (`.py`) or `""` if none."""
    if not file_path:
        return ""
    name = file_path.replace("\\", "/").rsplit("/", 1)[-1]
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1].lower()


def is_test_file_path(file_path: str) -> bool:
    """True for `/tests/`|`/test/` segments, _TEST_FILE_SUFFIXES, or `test_*.py`."""
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


def target_file_path(tool_name: str, tool_input: dict) -> str:
    """Return `tool_input.file_path` for the file tools, `""` otherwise."""
    if tool_name in _TOOLS_WITH_FILE_PATH:
        fp = tool_input.get("file_path")
        if isinstance(fp, str):
            return fp
    return ""


def skills_for_path(file_path: str) -> tuple[str, ...]:
    """Skills mapped to this path's extension, plus the test overlay on test paths."""
    ext = file_extension(file_path)
    base = _SKILLS_BY_EXT.get(ext)
    if base is None:
        return ()
    if is_test_file_path(file_path):
        return base + _TEST_SKILLS_BY_EXT[ext]
    return base


# --- strunk cache resolution ---


def _version_key(name: str) -> tuple[int, ...]:
    """`"0.2.0"` -> `(0, 2, 0)`. Non-numeric segments sort below every real version."""
    return tuple(int(part) if part.isdigit() else -1 for part in name.split("."))


def resolve_strunk_skills_dir() -> tuple[Path, str] | None:
    """Return the highest installed version's `skills/` dir and its version string."""
    try:
        versions = [d for d in _CACHE_ROOT.iterdir() if d.is_dir()]
    except OSError:
        return None
    if not versions:
        return None
    winner = max(versions, key=lambda d: _version_key(d.name))
    skills_dir = winner / "skills"
    if not skills_dir.is_dir():
        return None
    return skills_dir, winner.name


# --- payload ---


def strip_frontmatter(text: str) -> str:
    """Drop a leading `---\\n...\\n---\\n` block. Frontmatter is router metadata."""
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 3)
    if end == -1:
        return text
    return text[end + len("\n---\n"):]


def build_payload(skills_dir: Path, skills: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    """Attribution header + verbatim SKILL.md body per skill, joined by a blank line.

    A skill whose SKILL.md is missing or unreadable is skipped, never fabricated.
    Returns (payload, delivered_skills).
    """
    sections: list[str] = []
    delivered: list[str] = []
    for skill in skills:
        try:
            body = (skills_dir / skill / "SKILL.md").read_text(encoding="utf-8")
        except OSError:
            continue
        sections.append(_ATTRIBUTION.format(skill=skill) + "\n\n" + strip_frontmatter(body))
        delivered.append(skill)
    return "\n\n".join(sections), tuple(delivered)


# --- audit ---


def _append_audit(event: dict) -> None:
    """Append one JSON line to the audit log. Never raises."""
    try:
        _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_AUDIT_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
    except OSError as exc:
        print(f"[strunk-inject] audit write failed: {exc}", file=sys.stderr)


# --- throttle store ---


def _load_store(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_store(path: Path, store: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(store, fh)
        os.replace(tmp, path)
    except OSError as exc:
        print(f"[strunk-inject] store write failed: {exc}", file=sys.stderr)


def _prune_store(store: dict, today: str) -> dict:
    """Keep only today's entries, so session ids cannot grow the file forever."""
    return {
        key: entry for key, entry in store.items()
        if isinstance(entry, dict) and entry.get("day") == today
    }


# --- file-level mutex (cross-process + cross-thread) ---
#
# Copied from _lib_cartographer.py's `_file_mutex` - the house pattern for exactly
# this hazard. Not imported: that lock lives in cartographer's namespace, which
# this hook does not own.

_PROC_LOCKS: dict[str, threading.Lock] = {}
_PROC_LOCKS_GUARD = threading.Lock()


@contextmanager
def _file_mutex(lock_path: Path) -> Iterator[None]:
    """Serialize the store's read-modify-write across processes and threads.

    Combines `fcntl.flock` (cross-process, per-fd) with a per-path
    `threading.Lock` (cross-thread within a single process). If the lock cannot
    be taken the body still runs, unlocked: a lost write costs one duplicate
    injection, a raised exception would cost the delivery.
    """
    with _PROC_LOCKS_GUARD:
        tlock = _PROC_LOCKS.setdefault(str(lock_path), threading.Lock())
    with tlock:
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            fh = open(lock_path, "w", encoding="utf-8")
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        except OSError as exc:
            print(f"[strunk-inject] lock unavailable: {exc}", file=sys.stderr)
            yield
            return
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            fh.close()


# --- main ---


def main() -> None:
    try:
        data = _common.read_input()
        tool_input = data.get("tool_input") or {}
        file_path = target_file_path(data.get("tool_name") or "", tool_input)
        skills = skills_for_path(file_path)
        if not skills:
            # Suppressed path (the common case): no store read, no cache scan,
            # no stat probe. Latency contract.
            return
        session_id = data.get("session_id") or ""
        if not session_id:
            return

        with _file_mutex(_STORE_PATH.with_suffix(".lock")):
            today = datetime.now(timezone.utc).date().isoformat()
            store = _prune_store(_load_store(_STORE_PATH), today)
            seen = (store.get(session_id) or {}).get("skills") or []
            pending = tuple(skill for skill in skills if skill not in seen)
            if not pending:
                return  # steady state; auditing it would flood the log

            resolved = resolve_strunk_skills_dir()
            if resolved is None:
                _append_audit({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "session": session_id, "decision": "resolve-failed",
                    "file": file_path, "skills": [], "version": None,
                })
                return
            skills_dir, version = resolved

            payload, delivered = build_payload(skills_dir, pending)
            for skill in pending:
                if skill not in delivered:
                    _append_audit({
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "session": session_id, "decision": "skill-unreadable",
                        "file": file_path, "skills": [skill], "version": version,
                    })
            if not payload:
                return

            # Delivery outranks bookkeeping: emit before the store/audit writes.
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": payload,
                }
            }))
            store[session_id] = {"day": today, "skills": list(seen) + list(delivered)}
            _save_store(_STORE_PATH, store)
            _append_audit({
                "ts": datetime.now(timezone.utc).isoformat(),
                "session": session_id, "decision": "inject",
                "file": file_path, "skills": list(delivered), "version": version,
            })
    except Exception as exc:
        # A delivery hook that blocks a tool call is worse than no guidance.
        print(f"[strunk-inject] failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
