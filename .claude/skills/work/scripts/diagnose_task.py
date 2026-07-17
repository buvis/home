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
    """Return True if a Contract line is present."""
    for line in lines:
        if line.lstrip().startswith("Contract"):
            return True
    return False


def check_acceptance(lines: list[str]) -> bool:
    """Return True if 'Acceptance criteria' substring appears on any line."""
    for line in lines:
        if "Acceptance criteria" in line:
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


def find_dangling_files(text: str, lines: list[str], repo_root: Path) -> list[str]:
    """Find backtick-quoted code paths that don't exist under repo_root."""
    gaps: list[str] = []

    # Find all backtick-quoted tokens
    for match in re.finditer(r"`([^`]+)`", text):
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

        # Find the line containing this token
        line = ""
        start_pos = match.start()
        char_count = 0
        for l in lines:
            if char_count + len(l) > start_pos:
                line = l
                break
            char_count += len(l)  # accounts for newline

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
        text = task_path.read_text()
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
    gaps.extend(find_dangling_files(text, lines, repo_root))

    verdict = "spec_gap" if gaps else "pass"
    result = {"verdict": verdict, "gaps": gaps}
    json.dump(result, sys.stdout)
    print()  # trailing newline
    sys.exit(0)


if __name__ == "__main__":
    main()
