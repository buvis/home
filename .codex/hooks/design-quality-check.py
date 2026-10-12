#!/usr/bin/env python3
"""PostToolUse:Edit|Write|MultiEdit hook — frontend design-quality reminder.

Scans frontend files (.svelte, .tsx, .jsx, .vue, .astro, .html, .css, .scss)
modified by the tool call. Emits a checklist + heuristic warnings to stderr.

Exit code 0 always — this hook only reminds, never blocks.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

FRONTEND_EXTENSIONS = {".astro", ".css", ".html", ".jsx", ".scss", ".svelte", ".tsx", ".vue"}

GENERIC_SIGNALS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bget started\b", re.IGNORECASE), '"Get Started" CTA copy'),
    (re.compile(r"\blearn more\b", re.IGNORECASE), '"Learn more" CTA copy'),
    (re.compile(r"\bgrid-cols-(3|4)\b"), "uniform multi-card grid"),
    (re.compile(r"\bbg-gradient-to-[trbl]"), "stock gradient utility usage"),
    (re.compile(r"\btext-center\b"), "centered default layout cues"),
    (re.compile(r"\bfont-(sans|inter)\b", re.IGNORECASE), "default font utility"),
]

CHECKLIST = (
    "visual hierarchy with real contrast",
    "intentional spacing rhythm",
    "depth, layering, or overlap",
    "purposeful hover and focus states",
    "color and typography that feel specific",
)


def get_file_paths(tool_input: dict) -> list[str]:
    """Return all file_path values from tool_input (handles Edit/Write + MultiEdit)."""
    if isinstance(tool_input.get("file_path"), str):
        return [tool_input["file_path"]]
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        return [e["file_path"] for e in edits if isinstance(e, dict) and isinstance(e.get("file_path"), str)]
    return []


def is_frontend(path: str) -> bool:
    return Path(path).suffix.lower() in FRONTEND_EXTENSIONS


def detect_signals(content: str) -> list[str]:
    return [label for pattern, label in GENERIC_SIGNALS if pattern.search(content)]


def build_warning(frontend_paths: list[str], findings: list[str]) -> str:
    lines = ["[Hook] DESIGN CHECK: frontend file(s) modified:"]
    lines.extend(f"  - {p}" for p in frontend_paths)
    lines.append("[Hook] Review for generic/template drift. Frontend should have:")
    lines.extend(f"  - {item}" for item in CHECKLIST)
    lines.append("[Hook] Heuristic signals:")
    if findings:
        lines.extend(f"  - {item}" for item in findings)
    else:
        lines.append("  - no obvious canned-template strings detected")
    return "\n".join(lines)


def main() -> int:
    if sys.stdin.isatty():
        return 0
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0

    tool_input = payload.get("tool_input", {}) if isinstance(payload, dict) else {}
    frontend_paths = [p for p in get_file_paths(tool_input) if is_frontend(p)]
    if not frontend_paths:
        return 0

    findings: list[str] = []
    for path in frontend_paths:
        try:
            content = Path(path).read_text(encoding="utf-8")
        except OSError:
            continue
        findings.extend(detect_signals(content))

    sys.stderr.write(build_warning(frontend_paths, findings) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
