"""PreToolUse hook: keep PRD lifecycle dirs (backlog/, wip/, done/) under
`dev/local/prds/` only.

Replaces both ~/.claude/hooks/enforce-prd-location.sh (Edit/Write/MultiEdit)
and ~/.claude/hooks/enforce-prd-location-bash.sh (Bash). Branches on
`tool_name` and applies the matching validator.
"""

import os
import shlex
import subprocess
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import allow, block, read_input  # noqa: E402

LIFECYCLE_DIRS = ("backlog", "wip", "done")


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
    resolved = Path(file_path).resolve()
    probe = _existing_ancestor(str(resolved))
    if probe is None:
        return None
    root = _repo_root(probe)
    if root is None:
        return None
    try:
        rel_parts = resolved.relative_to(Path(root).resolve()).parts
    except ValueError:
        return None
    if rel_parts[:3] == ("dev", "local", "prds"):
        return None
    if rel_parts and rel_parts[0] in LIFECYCLE_DIRS:
        return _block_path_msg("/".join(rel_parts))
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
    try:
        tokens = shlex.split(cmd, comments=True)
    except ValueError:
        return
    matches: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        # A whitespace-split token can still hide a path after an = -
        # VAR=backlog/x.md or --log-file=backlog/x.md - splitting on
        # every = reproduces the old regex's (^|\s|=) boundary set
        # (shlex.split already handles the ^/whitespace cases).
        for segment in token.split("="):
            candidate = segment[2:] if segment.startswith("./") else segment
            parts = PurePosixPath(candidate).parts
            if not parts:
                continue
            if parts[:3] == ("dev", "local", "prds"):
                continue
            if parts[0] in LIFECYCLE_DIRS and (len(parts) > 1 or segment.endswith("/")):
                key = f"{parts[0]}/"
                if key not in seen:
                    seen.add(key)
                    matches.append(key)
    if matches:
        block(_block_bash_msg(sorted(matches)))


def main() -> None:
    try:
        data = read_input()
        tool = data.get("tool_name", "")
        if tool in {"Edit", "Write", "MultiEdit"}:
            _validate_file_mode(data)
        elif tool == "Bash":
            _validate_bash_mode(data)
    except Exception as exc:
        # block()/allow() raise SystemExit (BaseException), so a real block
        # still fires; only an UNEXPECTED error lands here. Fail open but LOUD
        # — a policy hook that crashes silently disables the gate with no
        # signal (PRD 00086 R4).
        print(f"policy hook degraded: enforce_prd_location: {exc}", file=sys.stderr)
    allow()


def run(payload):
    """Dispatcher entry point (hooks/dispatch.py). The handler owns its own
    capture: `capture_main` feeds `payload` as stdin, captures stdout/stderr and
    maps main()'s exit, so run() RETURNS the (exit_code, stdout, stderr) triple
    the dispatcher surfaces unchanged. `_common` is imported here, not at module
    scope, so the standalone `__main__` path is unaffected."""
    from _common import capture_main

    return capture_main(main, payload)


if __name__ == "__main__":
    main()
