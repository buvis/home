#!/usr/bin/env python3
"""Verify the tree_sitter_language_pack package is importable.

Exit codes:
  0  package imports cleanly
  1  any import-time failure (ImportError, SyntaxError from a corrupt wheel,
     OSError from a missing dylib on macOS, etc.): print remediation to stderr
     plus the underlying error name+message, then exit 1

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
    except Exception as exc:
        # Catch every import-time failure, not just ImportError. Broken wheels
        # raise SyntaxError (corrupt .py), OSError (missing dylib on macOS),
        # RuntimeError, etc. - all of which should land in the same remediation
        # path so the user always sees the pip-install hint, never a raw
        # traceback. The actual exception name+message is appended so a real
        # post-install failure is still diagnosable.
        print(REMEDIATION, file=sys.stderr)
        print(f"Underlying error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print("tree_sitter_language_pack: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
