"""Project-identity resolution for Cartographer.

Split out of `_lib_cartographer.py` to keep that file under its PRD-00009
400-line cap when the ~/.claude work-tree fallback landed (PRD 00088 R1).
`_lib_cartographer` re-exports `project_hash`, so `lib.project_hash` is
unchanged for every caller and test.

`project_hash` is a behavioral copy of `analyze-instincts.py:detect_project` on
the git-resolution branches (a parity test guards drift), plus a ~/.claude
meta-repo work-tree fallback the original deliberately lacks. Uses `Path.home()`
directly (tests patch it globally) — no `_home` indirection, so this module
stays free of any `_lib_cartographer` import and the two cannot cycle.

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path


def _meta_worktree_root(path: str | None) -> str | None:
    """The ~/.claude meta-repo root when `path` is at or under it, else None.

    ~/.claude is a bare-repo WORK-TREE (tracked by ~/.buvis, work-tree $HOME)
    with no `.git` of its own, so `project_hash`'s git branches resolve nothing
    and it would collapse to `'global'` — a repo that can never have an atlas
    (PRD 00088 R1). Give it a STABLE path-keyed identity anchored at ~/.claude,
    NOT the raw cwd: a hook firing from a ~/.claude subdir must resolve the same
    hash as `/survey ~/.claude`, or the atlas write and the recon read would key
    different dirs. Scoped to the meta-repo — a non-git scratch dir elsewhere
    stays `'global'`.
    """
    root = (Path.home() / ".claude").resolve()
    try:
        here = Path(path).resolve() if path else Path.cwd()
    except (OSError, ValueError):
        return None
    if here == root or root in here.parents:
        return str(root)
    return None


def project_hash(path: str | None = None) -> tuple[str, str, str]:
    """Determine project identity from git remote or toplevel path.

    Behavioral copy of `analyze-instincts.py:detect_project` on the git
    branches (parity test guards drift); adds a `path` parameter the original
    lacks. Returns `(hash, name, remote_url)`. Prefers the `origin` remote (with
    embedded credentials stripped), then the toplevel path. Where detect_project
    returns `("global", "global", "")`, this additionally resolves the ~/.claude
    meta-repo work-tree to a stable path-keyed identity (PRD 00088 R1,
    cartographer-only — the one intentional divergence); any other non-git path
    still falls back to `global`.
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
    except (subprocess.TimeoutExpired, FileNotFoundError, NotADirectoryError):
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
    except (subprocess.TimeoutExpired, FileNotFoundError, NotADirectoryError):
        pass

    meta = _meta_worktree_root(path)
    if meta is not None:
        h = hashlib.sha256(meta.encode()).hexdigest()[:12]
        # ".claude" -> "claude": a clean display name (addressing is by hash).
        return h, Path(meta).name.lstrip("."), ""

    return "global", "global", ""
