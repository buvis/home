"""Diagnose spec gaps in a task description file.

Verdict shape (single JSON object to stdout):
    {"verdict": "spec_gap", "gaps": ["missing_contract", ...]}
    {"verdict": "pass", "gaps": []}

Gap types:
    - missing_contract: no line (after stripping leading whitespace) starts with "Contract".
    - missing_acceptance: no line contains the substring "Acceptance criteria".
    - dangling_file:<path>: backtick-quoted code path absent under --repo-root.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

CODE_EXTENSIONS = {".py", ".rs", ".js", ".ts", ".tsx", ".jsx", ".go", ".sh"}
GLOB_CHARS = set("*?[]")
CREATION_VERBS = re.compile(
    r"\b(create|new|add|write)\b", re.IGNORECASE
)
# A Contract line: optional Markdown heading prefix, then the word "contract" on
# a word boundary. The `\b` stops "contractor"/"contractual" from counting.
CONTRACT_LINE = re.compile(r"^\s*#{0,6}\s*contract\b", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose spec gaps in a task file.")
    parser.add_argument("task_file", help="Path to the task description file.")
    parser.add_argument(
        "--repo-root",
        default=os.getcwd(),
        help="Repository root for resolving file paths (default: cwd).",
    )
    return parser.parse_args()


def check_contract(lines: list[str]) -> bool:
    """Return True if a Contract line is present.

    Word-boundary match (case-insensitive), tolerant of a leading Markdown
    heading prefix ("## Contract"), so a repaired or hand-edited description
    does not false-positive to a missing_contract spec_gap. "Contractor" /
    "contractual" do NOT count (the word boundary stops the over-broad match).
    """
    return any(CONTRACT_LINE.match(line) for line in lines)


def check_acceptance(lines: list[str]) -> bool:
    """Return True if an 'acceptance criteria' substring appears on any line.

    Case-insensitive so "Acceptance Criteria" does not false-positive to a
    missing_acceptance spec_gap.
    """
    for line in lines:
        if "acceptance criteria" in line.lower():
            return True
    return False


def is_creation_target(path_str: str, line: str, all_lines: list[str]) -> bool:
    """Return True if the path is a creation target (should not be flagged)."""
    # Rule: line begins with "Location:"
    if line.lstrip().startswith("Location:"):
        return True

    # Rule: path appears within ~20 characters after a creation verb
    # Look for creation verbs within 20 chars before the path in the line
    # Find the position of the path in the line
    idx = line.find(path_str)
    if idx >= 0:
        # Check up to 20 characters before the path start
        preceding = line[max(0, idx - 20) : idx]
        if CREATION_VERBS.search(preceding):
            return True

    # Rule: path is in a Markdown table row containing "NEW"
    # Check if any line is a table row containing both the path and "NEW"
    for other_line in all_lines:
        if path_str in other_line and "NEW" in other_line:
            # Verify it looks like a table row (contains pipes)
            if "|" in other_line:
                return True

    return False


def find_dangling_files(lines: list[str], repo_root: Path) -> list[str]:
    """Find backtick-quoted code paths that don't exist under repo_root.

    Scans each line independently so every backtick token is checked against
    its own containing line. Mapping match offsets from the full text back onto
    ``splitlines()`` output drifts (the separator is stripped), so the per-line
    scan is the correct-by-construction form.
    """
    gaps: list[str] = []

    for line in lines:
        for match in re.finditer(r"`([^`]+)`", line):
            token = match.group(1)

            # Must contain "/"
            if "/" not in token:
                continue

            # Must end in a code extension
            _, ext = os.path.splitext(token)
            if ext not in CODE_EXTENSIONS:
                continue

            # Must not contain glob characters
            if any(c in token for c in GLOB_CHARS):
                continue

            # Skip creation targets
            if is_creation_target(token, line, lines):
                continue

            # Check if file exists under repo_root
            full_path = repo_root / token
            if not full_path.exists():
                gaps.append(f"dangling_file:{token}")

    return gaps


def main() -> None:
    args = parse_args()

    task_path = Path(args.task_file)
    repo_root = Path(args.repo_root)

    # Read task file
    if not task_path.exists():
        json.dump({"error": f"Task file not found: {args.task_file}"}, sys.stderr)
        sys.exit(2)

    try:
        text = task_path.read_text(encoding="utf-8")
    except Exception as e:
        json.dump({"error": str(e)}, sys.stderr)
        sys.exit(2)

    lines = text.splitlines()
    gaps: list[str] = []

    # Check contract
    if not check_contract(lines):
        gaps.append("missing_contract")

    # Check acceptance criteria
    if not check_acceptance(lines):
        gaps.append("missing_acceptance")

    # Check dangling files
    gaps.extend(find_dangling_files(lines, repo_root))

    verdict = "spec_gap" if gaps else "pass"
    result = {"verdict": verdict, "gaps": gaps}
    json.dump(result, sys.stdout)
    print()  # trailing newline
    sys.exit(0)


if __name__ == "__main__":
    main()
