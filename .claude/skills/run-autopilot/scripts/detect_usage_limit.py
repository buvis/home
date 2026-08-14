#!/usr/bin/env python3
"""detect_usage_limit.py - re-export shim over cli/usage_limit.py (PRD 00106).

The detection logic moved into the autopilot CLI package with the loop
cutover, so the orchestrator, tracon and the tests all read one
implementation. This path stays because tracon/discovery.py,
render_stream.py and several suites import it by file location; the CLI
contract is unchanged:

    detect_usage_limit.py [--log PATH] <cwd> [projects_root]

    exit 0 + reset epoch on stdout when limit-stuck; exit 1 otherwise.

Everything below is the same object as its `cli.usage_limit`
counterpart, not a copy.
"""

from __future__ import annotations

import sys
from pathlib import Path

# FRONT of sys.path, unconditionally, mirroring cli/__main__.py's bootstrap: a
# decoy top-level `cli/` package elsewhere on sys.path (e.g. the invoking
# process's cwd) must never shadow the real one this shim delegates to.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cli.usage_limit import (
    DEFAULT_PROJECTS_ROOT,
    FALLBACK_MAX_AGE_SECS,
    FALLBACK_WAIT_SECS,
    GRACE_SECS,
    LIMIT_TEXT,
    RESET_TIME,
    TAIL_BYTES,
    detect,
    detect_from_log,
    main,
)

__all__ = [
    "DEFAULT_PROJECTS_ROOT",
    "FALLBACK_MAX_AGE_SECS",
    "FALLBACK_WAIT_SECS",
    "GRACE_SECS",
    "LIMIT_TEXT",
    "RESET_TIME",
    "TAIL_BYTES",
    "detect",
    "detect_from_log",
    "main",
]


if __name__ == "__main__":
    sys.exit(main())
