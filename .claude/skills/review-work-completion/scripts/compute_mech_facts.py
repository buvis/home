#!/usr/bin/env python3
"""compute_mech_facts.py - countable facts reviewers cite instead of counting.

PRD 00095. A reviewer's claim that a function is 58 lines when it is 44 cost
an orchestrator refutation pass on the engram batch. Countable claims should
be computed once, not asserted four times.

    compute_mech_facts.py <file>...

Prints a markdown facts block: for every Python file, each function's and
method's qualified name, start line, and line count, from `ast`. Non-Python
files and files that fail to parse are listed as skipped. Exit is always 0 -
a facts block is review context, and a missing fact must never fail the
cycle.

ponytail: Python-only via `ast`. Extend per language when a non-Python PRD
actually needs it.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


def _walk(node: ast.AST, prefix: str) -> list[tuple[str, int, int]]:
    """Every function/method under `node`, qualified by its enclosing class
    or function chain. Nested definitions are reported in their own right:
    a reviewer counting `outer` should see what `inner` costs it."""
    found: list[tuple[str, int, int]] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, FUNCTION_NODES):
            name = f"{prefix}{child.name}"
            # end_lineno covers the body; the decorator lines above the `def`
            # are not part of the function's own length.
            length = (child.end_lineno or child.lineno) - child.lineno + 1
            found.append((name, child.lineno, length))
            found.extend(_walk(child, f"{name}."))
        elif isinstance(child, ast.ClassDef):
            found.extend(_walk(child, f"{prefix}{child.name}."))
        else:
            found.extend(_walk(child, prefix))
    return found


def facts_for_file(path: Path) -> tuple[str, list[tuple[str, int, int]]]:
    """Return (status, rows). `status` is "ok" or a skip reason; `rows` is
    empty for anything skipped."""
    if path.suffix != ".py":
        return "skipped (non-python)", []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError, UnicodeDecodeError):
        return "skipped (parse error)", []
    return "ok", _walk(tree, "")


def render_facts_block(paths: list[Path]) -> str:
    lines = [
        "## Mechanical facts (computed, do not re-count)",
        "",
        "Function line counts from `ast`. Cite these for countable claims; a",
        "finding that contradicts this block is discarded at the review gate.",
        "",
    ]
    for path in paths:
        status, rows = facts_for_file(path)
        if status != "ok":
            lines.append(f"- `{path}` — {status}")
            continue
        if not rows:
            lines.append(f"- `{path}` — no functions")
            continue
        lines.append(f"- `{path}`")
        for name, start, length in rows:
            lines.append(f"  - `{name}` — line {start}, {length} lines")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print a markdown block of computed per-function line counts.",
    )
    parser.add_argument("files", nargs="+", type=Path, metavar="FILE")
    args = parser.parse_args(argv)
    print(render_facts_block(args.files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
