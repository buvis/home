#!/usr/bin/env python3
"""One-shot atlas sweep: run survey --refresh across the active repos.

Each survey runs as a subprocess with cwd set to the target repo (run.py
surveys Path.cwd()), inheriting this interpreter so the tree-sitter pack
provided by `uv run --with tree-sitter-language-pack` is available and the
atlases are not written in degraded regex mode.
"""

import subprocess
import sys

RUN_PY = "/Users/bob/.claude/skills/survey/scripts/run.py"

REPOS = [
    "/Users/bob/git/src/github.com/doogat/ddb",
    "/Users/bob/git/src/github.com/tbouska/figure-skating-guide",
    "/Users/bob/git/src/github.com/buvis/gems",
    "/Users/bob/git/src/github.com/buvis/engram",
    "/Users/bob/git/src/github.com/buvis/claude-aegis",
    "/Users/bob/.claude",
]


def main() -> int:
    failures = 0
    for repo in REPOS:
        proc = subprocess.run(
            [sys.executable, RUN_PY, "--refresh"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=300,
        )
        status = "ok" if proc.returncode == 0 else f"FAILED rc={proc.returncode}"
        tail = (proc.stdout.strip().splitlines() or [""])[-1]
        err_tail = (proc.stderr.strip().splitlines() or [""])[-1]
        print(f"{repo}: {status} | {tail}" + (f" | stderr: {err_tail}" if err_tail else ""))
        if proc.returncode != 0:
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
