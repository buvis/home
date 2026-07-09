#!/usr/bin/env python3
"""Minimal review-file shape check (PRD 00016).

Replaces the 774-line review_coverage.py engine. Validates exactly three
things about a consolidated review file:

1. every launched reviewer has a non-empty section,
2. a parseable verdict line (`Verdict: converged` / `Verdict: N findings`),
3. a test-summary line (`Tests: N passed ...` / `Tests: none (docs-only)`).

No git, no subprocesses, no PRD parsing. A missing element exits 1 with a
one-line gap description on stderr. An unreadable file system exits 0 with a
loud stderr note — an infrastructure error must not masquerade as a coverage
gap (the old gate's DIFF_ERROR philosophy).

CLI: check_review_file.py --review-file <path> [--reviewers alice,bob,...]
When --reviewers is omitted, the file's frontmatter `reviewers:` line (a
comma-separated list written by consolidation) is used; if neither names any
reviewer, only the verdict and tests lines are checked.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

VERDICT_RE = re.compile(r"^Verdict: (converged|\d+ findings?)\s*$", re.MULTILINE)
TESTS_RE = re.compile(
    r"^Tests: (\d+ passed.*|none \(docs-only\))\s*$", re.MULTILINE
)
FRONTMATTER_REVIEWERS_RE = re.compile(r"^reviewers:\s*(.+)$", re.MULTILINE)


def reviewer_section_nonempty(lines: list[str], name: str) -> bool:
    """True when a heading names the reviewer and its body has content."""
    needle = name.strip().lower()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#") and needle in line.lower():
            for follow in lines[i + 1 :]:
                if follow.lstrip().startswith("#"):
                    return False
                if follow.strip():
                    return True
            return False
    return False


def check(text: str, reviewers: list[str]) -> str | None:
    """Return a one-line gap description, or None when the shape holds."""
    lines = text.splitlines()
    for reviewer in reviewers:
        if not reviewer_section_nonempty(lines, reviewer):
            return f"reviewer section missing or empty: {reviewer}"
    if not VERDICT_RE.search(text):
        return "no verdict line (expected 'Verdict: converged' or 'Verdict: N findings')"
    if not TESTS_RE.search(text):
        return "no tests line (expected 'Tests: N passed ...' or 'Tests: none (docs-only)')"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-file", type=Path, required=True)
    parser.add_argument("--reviewers", default=None)
    args = parser.parse_args()

    if not args.review_file.exists():
        sys.stderr.write(f"missing review file {args.review_file}\n")
        return 1
    try:
        text = args.review_file.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        # Fail open: infra error, not a coverage gap. Loud, never silent.
        sys.stderr.write(
            f"check_review_file: cannot read {args.review_file} ({exc}); "
            "allowing hand-off (infrastructure error, not a coverage gap)\n"
        )
        return 0

    if args.reviewers is not None:
        reviewers = [r for r in args.reviewers.split(",") if r.strip()]
    else:
        match = FRONTMATTER_REVIEWERS_RE.search(text)
        reviewers = (
            [r for r in match.group(1).split(",") if r.strip()] if match else []
        )

    gap = check(text, reviewers)
    if gap is not None:
        sys.stderr.write(gap + "\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
