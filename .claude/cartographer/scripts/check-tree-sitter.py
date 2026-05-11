#!/usr/bin/env python3
"""Verify the tree_sitter_language_pack package is importable.

Exit codes:
  0  package imports cleanly
  1  ImportError: print remediation to stderr, then exit 1

Phase 1+ Cartographer hooks degrade gracefully via
`_lib_cartographer.try_import_tree_sitter`; they never call this script. This
CLI is for explicit installation verification.
"""

from __future__ import annotations

import importlib
import sys

REMEDIATION = """tree_sitter_language_pack is not importable in this Python.

Install it with:

    pip install tree-sitter-language-pack

If you use pyenv (or any tool that shims Python), make sure the active env is
the one Claude Code's hooks run under (typically the system Python or your
pyenv-shimmed Python 3.10+). Running `which python3` and comparing to the
`python3` your hooks invoke is the fastest check.

After install, re-run this script; it should print "tree_sitter_language_pack: ok".
"""


def main() -> int:
    try:
        importlib.import_module("tree_sitter_language_pack")
    except ImportError:
        print(REMEDIATION, file=sys.stderr)
        return 1
    print("tree_sitter_language_pack: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
