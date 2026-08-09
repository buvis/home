#!/usr/bin/env python3
"""check_review_file.py - re-export shim over run-autopilot's cli/gate.py
(PRD 00107).

The review-file shape gate (PRD 00016) moved into the autopilot CLI as
`autopilot gate` so all deterministic review gating lives in one tested
codebase. This path stays because four skills, the review-coverage format
doc, and several suites name it; the CLI and exit codes are unchanged:

    check_review_file.py --review-file <path> [--reviewers alice,bob,...]
    [--require-codex-guard] [--assert-constraint-met]

    0  shape holds (or unreadable file — fail open, loud)
    1  shape gap (or missing review file)
    2  --assert-constraint-met and the guard records `; constraint UNMET`

Flag semantics, the accepted codex_rung_guard forms, and the docs-only
sentinel (`Tests: none (docs-only)`) are documented in cli/gate.py's module
docstring. Everything below is the same object as its `cli.gate`
counterpart, not a copy.
"""

from __future__ import annotations

import sys
from pathlib import Path

# FRONT of sys.path, unconditionally, mirroring cli/__main__.py's bootstrap: a
# decoy top-level `cli/` package elsewhere on sys.path (e.g. the invoking
# process's cwd) must never shadow the real one this shim delegates to.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "run-autopilot"))

from cli.gate import (
    CODEX_RUNG_GUARD_RE,
    CONSTRAINT_UNMET_RE,
    FIRED_GUARD_RE,
    FRONTMATTER_REVIEWERS_RE,
    TESTS_RE,
    VERDICT_RE,
    check,
    main,
    reviewer_section_nonempty,
    run_gate,
)

__all__ = [
    "CODEX_RUNG_GUARD_RE",
    "CONSTRAINT_UNMET_RE",
    "FIRED_GUARD_RE",
    "FRONTMATTER_REVIEWERS_RE",
    "TESTS_RE",
    "VERDICT_RE",
    "check",
    "main",
    "reviewer_section_nonempty",
    "run_gate",
]


if __name__ == "__main__":
    sys.exit(main())
