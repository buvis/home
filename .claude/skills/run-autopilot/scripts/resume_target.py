"""resume_target.py - re-export shim over cli/resume.py (PRD 00089).

The two decision cores moved into the `cli/` package so PRD 00106 can import
them without a sys.path dance. This path stays because the SKILL prose and two
test suites name it, and because both functions' RETURN STRINGS are the
contract - `test_autopilot_resume.py` and `test_golden_contracts.py` assert on
them and must keep passing unmodified.

`resume_target` and `park_decision` below are the same objects as
`cli.resume`'s, not copies. See that module for the full contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

# FRONT of sys.path, mirroring cli/__main__.py's bootstrap, so a decoy `cli/`
# package elsewhere cannot shadow the real one. The import follows it.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.resume import park_decision, resume_target

__all__ = ["park_decision", "resume_target"]
