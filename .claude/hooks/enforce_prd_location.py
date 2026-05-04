"""PreToolUse hook: keep PRD lifecycle dirs (backlog/, wip/, done/) under
`dev/local/prds/` only.

Replaces both ~/.claude/hooks/enforce-prd-location.sh (Edit/Write/MultiEdit)
and ~/.claude/hooks/enforce-prd-location-bash.sh (Bash). Branches on
`tool_name` and applies the matching validator.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import allow, block, read_input  # noqa: E402

LIFECYCLE_DIRS = ("backlog", "wip", "done")
BASH_LIFECYCLE_RE = re.compile(r"(^|\s|=)(\./)?(backlog|wip|done)/")


def _block_path_msg(rel: str) -> str:
    return f"""\
BLOCKED: `{rel}` looks like a PRD lifecycle path at repo root.

PRDs must live under `dev/local/prds/`:
  - dev/local/prds/backlog/    (planned, not started)
  - dev/local/prds/wip/        (actively implementing)
  - dev/local/prds/done/       (completed)

If this is a PRD, retry with `dev/local/prds/{rel}`.
If this is genuinely something else that must live at repo root, rename the directory to avoid clashing with PRD lifecycle folders."""


def _block_bash_msg(matches: list[str]) -> str:
    formatted = "\n".join(f"  {m}" for m in matches)
    return f"""\
BLOCKED: command references a repo-root `backlog/`, `wip/`, or `done/` directory.

PRDs must live under `dev/local/prds/`:
  - dev/local/prds/backlog/    (planned, not started)
  - dev/local/prds/wip/        (actively implementing)
  - dev/local/prds/done/       (completed)

Offending references in the command:
{formatted}

If this is a PRD move, retry with `dev/local/prds/<lifecycle>/` paths on both sides.
If this is genuinely an unrelated directory, rename it to avoid clashing with PRD lifecycle folders."""


def _existing_ancestor(path: str) -> str | None:
    """Walk up `path` until an existing directory is found."""
    probe = os.path.dirname(path) or "/"
    while probe and probe != "/" and not os.path.isdir(probe):
        probe = os.path.dirname(probe)
    if probe and os.path.isdir(probe):
        return probe
    return None


def _repo_root(probe: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", probe, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    root = result.stdout.strip()
    return root or None


def _check_file_path(file_path: str) -> str | None:
    """Return a block reason if file_path violates the rule, else None."""
    if not file_path:
        return None
    # Normalize relative paths up-front so `_existing_ancestor` always resolves
    # against an existing directory (matching the bash original's `dirname`
    # walk reaching `.` when the path is relative).
    file_path = os.path.abspath(file_path)
    if "/dev/local/prds/" in file_path:
        return None
    probe = _existing_ancestor(file_path)
    if probe is None:
        return None
    root = _repo_root(probe)
    if root is None:
        return None
    # `file_path` is already absolute (normalized at the top of this function),
    # so no further joining is required.
    abs_path = file_path
    # macOS aliases (/tmp -> /private/tmp) make string-prefix comparison against
    # the git-toplevel root unreliable. Canonicalize by replacing the existing
    # probe prefix with its resolved form, then re-appending the unresolved tail.
    canon_probe = str(Path(probe).resolve())
    if abs_path == probe:
        canon_abs = canon_probe
    elif abs_path.startswith(probe + "/"):
        canon_abs = canon_probe + abs_path[len(probe):]
    else:
        return None
    if not canon_abs.startswith(root + "/"):
        return None
    rel = canon_abs[len(root) + 1:]
    head = rel.split("/", 1)[0]
    if head in LIFECYCLE_DIRS:
        return _block_path_msg(rel)
    return None


def _validate_file_mode(data: dict) -> None:
    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}
    if tool == "MultiEdit":
        for edit in tool_input.get("edits") or []:
            if not isinstance(edit, dict):
                continue
            reason = _check_file_path(edit.get("file_path") or "")
            if reason:
                block(reason)
    else:
        reason = _check_file_path(tool_input.get("file_path") or "")
        if reason:
            block(reason)


def _validate_bash_mode(data: dict) -> None:
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not cmd:
        return
    matches: list[str] = []
    seen: set[str] = set()
    for m in BASH_LIFECYCLE_RE.finditer(cmd):
        leading, dot_slash, name = m.group(1), m.group(2) or "", m.group(3)
        # Reconstruct the matched token without the leading boundary char
        token = f"{dot_slash}{name}/"
        if token in seen:
            continue
        seen.add(token)
        matches.append(token)
    if matches:
        block(_block_bash_msg(sorted(matches)))


def main() -> None:
    data = read_input()
    tool = data.get("tool_name", "")
    if tool in {"Edit", "Write", "MultiEdit"}:
        _validate_file_mode(data)
    elif tool == "Bash":
        _validate_bash_mode(data)
    allow()


if __name__ == "__main__":
    main()
