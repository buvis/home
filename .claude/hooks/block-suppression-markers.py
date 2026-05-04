#!/usr/bin/env python3
"""PreToolUse hook: block Edit/Write/MultiEdit that newly adds lint or
type-checker suppression markers. Policy is to fix the root cause.
Exit 0 = allow, Exit 2 = block."""

import json
import re
import sys

SUPPRESSION_PATTERNS = [
    (r"#!?\[allow\(", "Rust #[allow(...)] / #![allow(...)]"),
    (r"#\s*type:\s*ignore", "Python # type: ignore"),
    (r"#\s*noqa", "Python # noqa"),
    (r"#\s*pylint:\s*disable", "Python # pylint: disable"),
    (r"//\s*eslint-disable", "JS/TS // eslint-disable"),
    (r"/\*\s*eslint-disable", "JS/TS /* eslint-disable */"),
    (r"//\s*@ts-ignore", "TS // @ts-ignore"),
    (r"//\s*@ts-nocheck", "TS // @ts-nocheck"),
    (r"//\s*@ts-expect-error", "TS // @ts-expect-error"),
    (r"@SuppressWarnings", "Java @SuppressWarnings"),
    (r"//\s*nolint", "Go //nolint"),
    (r"//\s*NOLINT", "C/C++ // NOLINT"),
]


def count_markers(text: str) -> dict[str, int]:
    if not text:
        return {}
    out = {}
    for pattern, label in SUPPRESSION_PATTERNS:
        n = len(re.findall(pattern, text))
        if n:
            out[label] = n
    return out


def diff_added(old_text: str, new_text: str) -> list[tuple[str, int]]:
    old = count_markers(old_text)
    new = count_markers(new_text)
    added = []
    for label, n in new.items():
        delta = n - old.get(label, 0)
        if delta > 0:
            added.append((label, delta))
    return added


def main() -> None:
    payload = json.loads(sys.stdin.read())
    tool = payload.get("tool_name", "")
    inp = payload.get("tool_input", {})

    additions: list[tuple[str, int, str]] = []

    if tool == "Edit":
        for label, n in diff_added(inp.get("old_string", ""), inp.get("new_string", "")):
            additions.append((label, n, "Edit"))
    elif tool == "MultiEdit":
        for i, edit in enumerate(inp.get("edits", [])):
            for label, n in diff_added(edit.get("old_string", ""), edit.get("new_string", "")):
                additions.append((label, n, f"MultiEdit edit #{i + 1}"))
    elif tool == "Write":
        new_text = inp.get("content", "")
        path = inp.get("file_path", "")
        old_text = ""
        try:
            with open(path) as f:
                old_text = f.read()
        except (FileNotFoundError, IsADirectoryError, PermissionError):
            pass
        for label, n in diff_added(old_text, new_text):
            additions.append((label, n, "Write"))
    else:
        sys.exit(0)

    if not additions:
        sys.exit(0)

    print("BLOCKED: change adds lint/type-checker suppression markers.", file=sys.stderr)
    print("", file=sys.stderr)
    for label, n, where in additions:
        print(f"  + {label} (x{n}, in {where})", file=sys.stderr)
    print("", file=sys.stderr)
    print("Policy: fix the root cause, don't silence warnings.", file=sys.stderr)
    print("See ~/.claude/rules/coding-style.md (Warnings section).", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
