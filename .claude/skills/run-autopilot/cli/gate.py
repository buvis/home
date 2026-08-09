#!/usr/bin/env python3
"""cli/gate.py - the review-file shape gate (PRD 00016, absorbed by PRD 00107).

Moved here from review-work-completion/scripts/check_review_file.py so the
deterministic review gate lives in the tested CLI codebase; that path remains
as a re-export shim because four skills and several suites name it. Wired as
`autopilot gate` in cli/__main__.py; also runnable directly
(`python3 cli/gate.py <flags>`) with the identical contract.

Validates exactly four things about a consolidated review file:

1. every launched reviewer has a non-empty section,
2. a parseable verdict line (`Verdict: converged` / `Verdict: N findings`),
3. a test-summary line (`Tests: N passed ...` / `Tests: none (docs-only)`),
4. a codex_rung_guard line — `codex_rung_guard: not fired`, plain
   `fired (N codex-implemented task(s))`, or that fired form suffixed
   `; eve unavailable, doubt lens fell back to claude` or
   `; constraint UNMET` — checked ONLY when --require-codex-guard is
   passed, and checked for CONSISTENCY as well as grammar: a well-formed
   line can still lie. `fired (0 ...)` is self-contradictory (the guard
   fires only when at least one task was codex-implemented), and plain
   `fired (N)` asserts a non-codex doubt reviewer covered the lens, which
   requires a non-empty eve section to back it. The two suffixed forms are
   exempt from that second rule: each already records why Eve did not run.

This gate checks several different kinds of review file (consolidated
reviews, blind reviews, shadow-run renders), and only the consolidated
review carries a codex_rung_guard line — so that check is opt-in, not
imposed on every caller.

No git, no subprocesses, no PRD parsing. A missing element exits 1 with a
one-line gap description on stderr. An unreadable file system exits 0 with a
loud stderr note — an infrastructure error must not masquerade as a coverage
gap (the old gate's DIFF_ERROR philosophy).

--assert-constraint-met is an opt-in semantic check on top of the shape
check above: when the codex_rung_guard line records `; constraint UNMET`
(the doubt lens ran on codex alone), exit 2 instead of the usual 0 — a
failure class distinct from a shape gap, so a caller can tell "malformed
file" (exit 1) apart from "constraint not certified" (exit 2). A shape gap
still wins when both are present: a file that fails the shape check cannot
be trusted for a constraint reading, so it exits 1, not 2. Without this
flag, `; constraint UNMET` remains a validly-shaped, exit-0 recorded form.

CLI: autopilot gate --review-file <path> [--reviewers alice,bob,...]
[--require-codex-guard] [--assert-constraint-met]
When --reviewers is omitted, the file's frontmatter `reviewers:` line (a
comma-separated list written by consolidation) is used; if neither names any
reviewer, only the verdict and tests lines are checked.

Exit codes (gate-scoped, unchanged from check_review_file.py):
    0  shape holds (or unreadable file — fail open, loud)
    1  shape gap (or missing review file)
    2  --assert-constraint-met and the guard line records `; constraint UNMET`
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

VERDICT_RE = re.compile(r"^Verdict: (converged|\d+ findings?)\s*$", re.MULTILINE)
TESTS_RE = re.compile(
    r"^Tests: (\d+ passed.*|none \(docs-only\))\s*$",
    re.MULTILINE,
)
CODEX_RUNG_GUARD_RE = re.compile(
    r"^codex_rung_guard: ("
    r"fired \(\d+ codex-implemented task\(s\)\)"
    r"(; eve unavailable, doubt lens fell back to claude|; constraint UNMET)?"
    r"|not fired)\s*$",
    re.MULTILINE,
)
CONSTRAINT_UNMET_RE = re.compile(
    r"^codex_rung_guard: fired \(\d+ codex-implemented task\(s\)\); constraint UNMET\s*$",
    re.MULTILINE,
)
# Same fired branch as CODEX_RUNG_GUARD_RE, but capturing the count and the
# suffix so the consistency check below can read them. Only ever consulted
# AFTER the shape check has passed, so the line is already known well-formed.
FIRED_GUARD_RE = re.compile(
    r"^codex_rung_guard: fired \((\d+) codex-implemented task\(s\)\)"
    r"(; eve unavailable, doubt lens fell back to claude|; constraint UNMET)?\s*$",
    re.MULTILINE,
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


def check(
    text: str,
    reviewers: list[str],
    require_codex_guard: bool = False,
) -> str | None:
    """Return a one-line gap description, or None when the shape holds."""
    lines = text.splitlines()
    for reviewer in reviewers:
        if not reviewer_section_nonempty(lines, reviewer):
            return f"reviewer section missing or empty: {reviewer}"
    if not VERDICT_RE.search(text):
        return (
            "no verdict line (expected 'Verdict: converged' or 'Verdict: N findings')"
        )
    if not TESTS_RE.search(text):
        return "no tests line (expected 'Tests: N passed ...' or 'Tests: none (docs-only)')"
    if require_codex_guard:
        if not CODEX_RUNG_GUARD_RE.search(text):
            return (
                "no codex_rung_guard line (expected 'codex_rung_guard: not fired', "
                "'codex_rung_guard: fired (N codex-implemented task(s))', or that "
                "fired form suffixed with '; eve unavailable, doubt lens fell back "
                "to claude' or '; constraint UNMET')"
            )
        gap = _guard_matches_roster(text, lines)
        if gap is not None:
            return gap
    return None


def _guard_matches_roster(text: str, lines: list[str]) -> str | None:
    """Check the guard's RECORD against the roster, not just its grammar.

    A well-formed line can still lie. Two ways it does:

    - `fired (0 ...)` is self-contradictory — the guard fires only when at
      least one task was codex-implemented.
    - plain `fired (N)` asserts a non-codex doubt reviewer covered the lens,
      which means Eve. If the file carries no Eve section, nothing backs that
      claim. The two documented suffixes are exempt: `; eve unavailable ...`
      self-documents her absence (Bob's Claude fallback covered doubt), and
      `; constraint UNMET` already records the constraint as not certified.
    """
    fired = FIRED_GUARD_RE.search(text)
    if fired is None:  # `not fired` — nothing to cross-check
        return None
    if int(fired.group(1)) == 0:
        return (
            "codex_rung_guard records 'fired (0 codex-implemented task(s))', which "
            "is self-contradictory: the guard fires only when at least one task "
            "was codex-implemented"
        )
    if fired.group(2) is None and not reviewer_section_nonempty(lines, "eve"):
        return (
            "codex_rung_guard records a plain 'fired (N codex-implemented "
            "task(s))', which claims a non-codex doubt reviewer covered the lens, "
            "but the file carries no non-empty eve section; use the "
            "'; eve unavailable, doubt lens fell back to claude' or "
            "'; constraint UNMET' form when Eve did not run"
        )
    return None


def run_gate(
    review_file: Path,
    reviewers: str | None = None,
    require_codex_guard: bool = False,
    assert_constraint_met: bool = False,
) -> int:
    """The full gate flow behind both entry points (`autopilot gate` and the
    direct script/shim invocation): read, resolve reviewers, check, exit code."""
    if not review_file.exists():
        sys.stderr.write(f"missing review file {review_file}\n")
        return 1
    try:
        text = review_file.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        # Fail open: infra error, not a coverage gap. Loud, never silent.
        sys.stderr.write(
            f"check_review_file: cannot read {review_file} ({exc}); "
            "allowing hand-off (infrastructure error, not a coverage gap)\n",
        )
        return 0

    if reviewers is not None:
        reviewer_list = [r for r in reviewers.split(",") if r.strip()]
    else:
        match = FRONTMATTER_REVIEWERS_RE.search(text)
        reviewer_list = (
            [r for r in match.group(1).split(",") if r.strip()] if match else []
        )

    gap = check(text, reviewer_list, require_codex_guard)
    if gap is not None:
        sys.stderr.write(gap + "\n")
        return 1

    if assert_constraint_met and CONSTRAINT_UNMET_RE.search(text):
        sys.stderr.write(
            "codex_rung_guard: constraint UNMET; doubt-roster constraint not certified\n",
        )
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-file", type=Path, required=True)
    parser.add_argument("--reviewers", default=None)
    parser.add_argument("--require-codex-guard", action="store_true", default=False)
    parser.add_argument("--assert-constraint-met", action="store_true", default=False)
    args = parser.parse_args()
    return run_gate(
        args.review_file,
        args.reviewers,
        args.require_codex_guard,
        args.assert_constraint_met,
    )


if __name__ == "__main__":
    sys.exit(main())
