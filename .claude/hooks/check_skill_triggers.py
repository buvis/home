"""PostToolUse advisory: name trigger phrases a SKILL.md edit dropped or collides on.

A skill's frontmatter `description` is its only router input, and nothing
checked that its quoted phrases survived an edit. Commit `76feb4475` dropped
"create AGENTS.md" and "improve AGENTS.md" from manage-agents-md in the same
line that added two others; the loss went unnoticed for three weeks.

Git is the baseline - no lock file, no second source of truth. Advisory only,
never blocks: a dropped phrase is sometimes a deliberate rename. Fails open
(exit 0, no output) on any internal error.

Stdlib only. Python 3.10+.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

# `_common` is a sibling, and hooks are run by absolute path rather than
# imported as a package. Both imports of it happen inside the functions below,
# so this stays a plain statement instead of a top-of-file import ordering
# problem.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Installed skills the router can actually fire. skills-library/ is dormant by
# design (never scanned, cannot fire), so a collision there is not yet real.
SKILL_GLOBS = ("skills/*/SKILL.md", "plugins/cache/*/*/*/skills/*/SKILL.md")

# On-disk cache of the phrase->owners index, keyed by the candidates' max
# mtime, so a warm cache spares rereading every installed SKILL.md on each
# edit. Bound at import time next to this script.
_INDEX_CACHE_FILE = Path(__file__).resolve().parent / ".trigger-index-cache.json"

_KEY_RE = re.compile(r"[A-Za-z_][\w-]*\s*:")
_DESC_RE = re.compile(r"description\s*:")


def _fenced_block(text: str) -> str:
    """The YAML block between the leading `---` fence and its closer."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return "\n".join(lines[1:idx])
    return ""


def _description(text: str) -> str:
    """The `description` value, folded to one line (YAML wraps them freely)."""
    collected: list[str] = []
    for line in _fenced_block(text).splitlines():
        if collected:
            if _KEY_RE.match(line):
                break
            collected.append(line)
        elif _DESC_RE.match(line):
            collected.append(line.split(":", 1)[1])
    return " ".join(part.strip() for part in collected)


def extract_triggers(text: str) -> list[str]:
    """Double-quoted phrases in a SKILL.md description, in order.

    De-duplicated case-insensitively, keeping the first spelling. A description
    with no quoted phrase yields [] and is never an error - some skills trigger
    on prose alone.
    """
    found: dict[str, str] = {}
    for phrase in re.findall(r'"([^"]*)"', _description(text)):
        found.setdefault(phrase.casefold(), phrase)
    return list(found.values())


def _git_show(args: list[str], rel: str) -> str | None:
    """`git <args> show HEAD:<rel>`, or None on any failure."""
    try:
        proc = subprocess.run(
            args + ["show", f"HEAD:{rel}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _toplevel(directory: Path) -> str | None:
    """The git work-tree root enclosing `directory`, or None."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def committed_text(path: str) -> str | None:
    """The file's content at HEAD, or None if it is untracked or repo-less.

    An enclosing repo wins (plugin caches are their own clones); otherwise a
    path under $HOME falls back to the ~/.buvis bare repo. Both forms address
    the blob as `HEAD:<path-from-repo-root>`, which is cwd-independent - a
    relative pathspec against a bare repo silently resolves to nothing, which
    would report every file clean.
    """
    resolved = Path(path).resolve()
    root = _toplevel(resolved.parent)
    if root:
        try:
            rel = resolved.relative_to(Path(root).resolve())
        except ValueError:
            return None
        return _git_show(["git", "-C", root], str(rel))
    home = Path.home().resolve()
    buvis = home / ".buvis"
    if buvis.is_dir() and resolved.is_relative_to(home):
        return _git_show(
            ["git", f"--git-dir={buvis}", f"--work-tree={home}"],
            str(resolved.relative_to(home)),
        )
    return None


def dropped_since_head(path: str) -> list[str]:
    """Trigger phrases present at HEAD and absent from the file on disk."""
    old = committed_text(path)
    if old is None:
        return []
    try:
        new = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    current = {phrase.casefold() for phrase in extract_triggers(new)}
    return [p for p in extract_triggers(old) if p.casefold() not in current]


def _glob_paths() -> list[Path]:
    """Every installed skill's SKILL.md (own + plugin cache), resolved."""
    home = Path.home() / ".claude"
    return [p.resolve() for pattern in SKILL_GLOBS for p in home.glob(pattern)]


def _max_mtime(paths: list[Path]) -> float:
    """Highest mtime among `paths`; 0.0 if empty. Skips a raced delete."""
    mtimes: list[float] = []
    for p in paths:
        try:
            mtimes.append(p.stat().st_mtime)
        except OSError:
            continue
    return max(mtimes, default=0.0)


def _index_over(paths: list[Path]) -> dict[str, list[str]]:
    """{casefolded phrase: sorted [owner paths]} scanned fresh over `paths`."""
    index: dict[str, list[str]] = {}
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for phrase in extract_triggers(text):
            index.setdefault(phrase.casefold(), []).append(str(p))
    for owners in index.values():
        owners.sort()
    return index


def _write_cache(cache: dict) -> None:
    """Atomic write of the trigger-index cache (see `observe_tool.py`'s
    `_write_cwd_cache` for the convention this copies). An advisory cache
    that cannot be written is not a reason to fail the advisory, so any
    OSError (missing directory, permissions, ...) is swallowed.
    """
    try:
        tmp = NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(_INDEX_CACHE_FILE.parent), delete=False
        )
        try:
            json.dump(cache, tmp)
            tmp_path = Path(tmp.name)
        finally:
            tmp.close()
        tmp_path.replace(_INDEX_CACHE_FILE)
    except OSError:
        pass


def _cached_index(paths: list[Path], exclude: Path) -> dict[str, list[str]]:
    """The phrase index over `paths` minus `exclude`, reused from disk when the
    candidate set hasn't changed. `exclude`'s own mtime never enters the key,
    so repeated saves of the file being edited can't invalidate it. The key
    covers both the candidates' identities and their max mtime: two distinct
    candidate sets can share a max mtime, and mtime alone would wrongly reuse
    one set's index for the other.
    """
    excl = exclude.resolve()
    candidates = [p for p in paths if p.resolve() != excl]
    key = {"paths": sorted(str(p) for p in candidates), "mtime": _max_mtime(candidates)}
    try:
        cached = json.loads(_INDEX_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cached = None
    if isinstance(cached, dict) and cached.get("key") == key:
        return cached.get("index", {})
    index = _index_over(candidates)
    _write_cache({"key": key, "index": index})
    return index


def collisions(path: str, phrases: list[str]) -> dict[str, list[str]]:
    """{phrase: [other SKILL.md paths]} for phrases another skill also claims.

    Only the edited skill's own phrases are checked, so a pre-existing
    collision between two unrelated skills stays silent - it is not this
    edit's problem.
    """
    if not phrases:
        return {}
    wanted = {phrase.casefold(): phrase for phrase in phrases}
    mine = Path(path).resolve()
    index = _cached_index(_glob_paths(), exclude=mine)
    hits: dict[str, list[str]] = {}
    for key, owner_phrase in wanted.items():
        owners = index.get(key)
        if owners:
            hits[owner_phrase] = owners
    return hits


def findings(path: str) -> list[str]:
    """Advisory lines for one edited SKILL.md; empty when it is clean."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    lines: list[str] = []
    dropped = dropped_since_head(path)
    if dropped:
        lost = ", ".join(f'"{p}"' for p in dropped)
        lines.append(f"{path} no longer claims {lost} (present at HEAD).")
    for phrase, others in collisions(path, extract_triggers(text)).items():
        lines.append(f'"{phrase}" is also claimed by: ' + ", ".join(sorted(others)))
    return lines


def main() -> int:
    from _common import read_input

    try:
        data = read_input()
        path = (data.get("tool_input") or {}).get("file_path") or ""
        # One string compare guards the whole hook: a non-SKILL.md edit costs
        # nothing on an event that already carries four other handlers.
        if os.path.basename(path) != "SKILL.md":
            return 0
        lines = findings(path)
        if not lines:
            return 0
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": (
                            "Skill trigger check (advisory, ~/.claude/hooks/"
                            "check_skill_triggers.py):\n" + "\n".join(lines)
                        ),
                    },
                }
            )
        )
    except Exception:
        return 0  # advisory: never let a router check disturb an edit
    return 0


def run(payload):
    """Dispatcher entry point (hooks/dispatch.py)."""
    from _common import capture_main

    return capture_main(main, payload)


if __name__ == "__main__":
    sys.exit(main())
