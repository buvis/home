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

# `_common` is a sibling, and hooks are run by absolute path rather than
# imported as a package. Both imports of it happen inside the functions below,
# so this stays a plain statement instead of a top-of-file import ordering
# problem.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Installed skills the router can actually fire. skills-library/ is dormant by
# design (never scanned, cannot fire), so a collision there is not yet real.
SKILL_GLOBS = ("skills/*/SKILL.md", "plugins/cache/*/*/*/skills/*/SKILL.md")

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
    hits: dict[str, list[str]] = {}
    for pattern in SKILL_GLOBS:
        for other in (Path.home() / ".claude").glob(pattern):
            if other.resolve() == mine:
                continue
            try:
                text = other.read_text(encoding="utf-8")
            except OSError:
                continue
            for phrase in extract_triggers(text):
                owner = wanted.get(phrase.casefold())
                if owner is not None:
                    hits.setdefault(owner, []).append(str(other))
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
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    "Skill trigger check (advisory, ~/.claude/hooks/"
                    "check_skill_triggers.py):\n" + "\n".join(lines)
                ),
            }
        }))
    except Exception:
        return 0  # advisory: never let a router check disturb an edit
    return 0


def run(payload):
    """Dispatcher entry point (hooks/dispatch.py)."""
    from _common import capture_main

    return capture_main(main, payload)


if __name__ == "__main__":
    sys.exit(main())
