#!/usr/bin/env python3
"""Claim the next free PRD number in a repo, atomically.

    allocate_prd_number.py <repo> <slug>

Scans every `dev/local/prds/` subdirectory plus `dev/local/discovery/` for
`NNNNN-` prefixes, then creates an EMPTY file at the next free number and prints
its path. The caller writes the body into that file.

The create-prd convention is scan, write, then re-scan and renumber if someone
claimed your number in between. This claims with `O_CREAT | O_EXCL` instead, so
the file either did not exist and is now yours, or it existed and we move to the
next number. There is no window to lose, and no re-scan to forget.

Numbers are never reused: a parked or completed PRD keeps its number, which is
why the scan covers every lifecycle directory rather than just `backlog/`.
"""

from __future__ import annotations

import errno
import os
import re
import sys
from pathlib import Path

PREFIX_RE = re.compile(r"^(\d{5})-")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# A runaway loop would otherwise spin through five digits of nothing.
MAX_ATTEMPTS = 200


def claimed_numbers(repo: Path) -> set[int]:
    """Every sequence number already spoken for anywhere in the repo."""
    roots = [repo / "dev" / "local" / "prds", repo / "dev" / "local" / "discovery"]
    numbers: set[int] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            match = PREFIX_RE.match(path.name)
            if match:
                numbers.add(int(match.group(1)))
    return numbers


def claim(repo: Path, slug: str) -> Path:
    """Create an empty PRD file at the next free number and return its path."""
    if not SLUG_RE.match(slug):
        raise SystemExit(f"slug must be kebab-case, got {slug!r}")

    backlog = repo / "dev" / "local" / "prds" / "backlog"
    backlog.mkdir(parents=True, exist_ok=True)

    number = max(claimed_numbers(repo), default=0) + 1
    for _ in range(MAX_ATTEMPTS):
        target = backlog / f"{number:05d}-{slug}-v1.md"
        try:
            # The whole point: exclusive create, so a concurrent writer that
            # scanned the same maximum loses the race here instead of silently
            # sharing our number.
            os.close(os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644))
            return target
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise
            number += 1
    raise SystemExit(f"no free PRD number after {MAX_ATTEMPTS} attempts from {number}")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: allocate_prd_number.py <repo> <slug>", file=sys.stderr)
        return 2
    print(claim(Path(argv[1]).resolve(), argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
