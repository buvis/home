"""Autopilot write-scope fence (PreToolUse).

Incident-bound: in batch 202608180438 (2026-08-18) an unattended subagent
edited a file in the user's zettelkasten vault, which a sync daemon
auto-committed and pushed. Armed only when CLAUDE_UNATTENDED=1, this hook
denies Write/Edit/MultiEdit/NotebookEdit targets outside the session's repo,
its dev/local and the temp roots; without the marker it allows every write.

Stdlib only. Python 3.10+.
"""

import os
import sys
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import allow, block, read_input

MARKER = "CLAUDE_UNATTENDED"
KILL_SWITCH = "_AUTOPILOT_WRITE_SCOPE"  # "off" disarms the fence
PATH_KEYS = ("file_path", "notebook_path")
EXTRA_ROOTS_VAR = "_AUTOPILOT_WRITE_SCOPE_EXTRA"  # ':'-joined extra roots
TMP_ROOTS = ("/tmp",)  # static temp roots; also the suite's test seam


def _repo_root(cwd: Path) -> Path:
    """Nearest ancestor of `cwd` holding `dev/local/autopilot`; `cwd` if none.

    The predicate is the launcher's own (`cli/loop.py` walks up for
    `dev/local/autopilot`), and the walk stops at $HOME exclusive so a stray
    `$HOME/dev/local/autopilot` cannot pull every repo's scope up to $HOME.
    Walks UNRESOLVED: the `~/.claude` repo's `dev/local` is a symlink, and
    resolving would hand back the target's ancestors instead of the repo's.
    """
    home = Path.home()
    for candidate in (cwd, *cwd.parents):
        if home.is_relative_to(candidate):
            break
        if (candidate / "dev" / "local" / "autopilot").is_dir():
            return candidate
    return cwd


def _allowed_roots(cwd: str, env: Mapping[str, str]) -> list[Path]:
    """Realpath'd roots an autopilot session may write under.

    `env` is injected so tests can supply a synthetic TMPDIR. `TMP_ROOTS` is
    read as a module global here, never as a default argument, so the suite's
    seam keeps working.
    """
    repo = _repo_root(Path(cwd))
    candidates = [repo, repo / "dev" / "local"]
    if env.get("TMPDIR"):
        candidates.append(Path(env["TMPDIR"]))
    candidates.extend(Path(root) for root in TMP_ROOTS)
    candidates.extend(
        Path(extra) for extra in env.get(EXTRA_ROOTS_VAR, "").split(":") if extra
    )
    home = Path(os.path.realpath(Path.home()))
    roots: list[Path] = []
    for candidate in candidates:
        root = Path(os.path.realpath(candidate))
        # Root floor: $HOME itself and everything above it grant no scope.
        if home.is_relative_to(root) or root in roots:
            continue
        roots.append(root)
    return roots


def _targets(tool_input: dict) -> list[str]:
    """Every path a Write/Edit/MultiEdit/NotebookEdit payload writes to."""
    targets = [tool_input[key] for key in PATH_KEYS if tool_input.get(key)]
    targets.extend(
        edit["file_path"]
        for edit in tool_input.get("edits") or []
        if edit.get("file_path")
    )
    return targets


def _resolve(target: str, cwd: str) -> str:
    """expanduser -> anchor a relative path at `cwd` -> os.path.realpath."""
    path = os.path.expanduser(target)
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    return os.path.realpath(path)


def _breach(target: str, roots: list[Path], cwd: str) -> str | None:
    """Return a one-line block reason if `target` escapes `roots`, else None."""
    resolved = _resolve(target, cwd)
    if any(Path(resolved).is_relative_to(root) for root in roots):
        return None
    return (
        f"BLOCKED: autopilot write-scope fence: {resolved!r} is outside the "
        f"allowed scope ({', '.join(repr(str(r)) for r in roots)}). "
        "Write inside the session's repo, its dev/local, or a temp dir; "
        "add a root via _AUTOPILOT_WRITE_SCOPE_EXTRA, or set "
        "_AUTOPILOT_WRITE_SCOPE=off to disarm."
    )


def main() -> None:
    try:
        payload = read_input()
        if os.environ.get(MARKER) != "1":
            allow()
        if os.environ.get(KILL_SWITCH) == "off":
            print(
                "enforce_write_scope: disarmed by _AUTOPILOT_WRITE_SCOPE=off",
                file=sys.stderr,
            )
            allow()
        targets = _targets(payload.get("tool_input") or {})
        if not targets:
            allow()
        cwd = payload.get("cwd") or os.getcwd()
        roots = _allowed_roots(cwd, os.environ)
        if not roots:
            block(
                "enforce_write_scope: no usable write scope (every candidate "
                "root was $HOME or above); refusing all writes"
            )
        for target in targets:
            reason = _breach(target, roots, cwd)
            if reason:
                block(reason)
        allow()
    except Exception as exc:
        print(f"policy hook degraded: enforce_write_scope: {exc}", file=sys.stderr)
        allow()


def run(payload) -> tuple[int, str, str]:
    """Dispatcher entry point; delegates to _common.capture_main(main, payload)."""
    from _common import capture_main

    return capture_main(main, payload)


if __name__ == "__main__":
    main()
