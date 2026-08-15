"""Persona frontmatter stripping and {PLACEHOLDER} substitution CLI.

Strips a leading YAML frontmatter block (if present) from a persona file,
substitutes {PLACEHOLDER} tokens using values supplied via --set/--set-file/
--set-cmd, and writes the rendered body to --out.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PLACEHOLDER_RE = re.compile(r"\{[A-Z_][A-Z0-9_]*\}")

# --set-cmd runs arbitrary shell commands as part of automated dispatch; bound
# it so a hung/interactive command can't wedge the pipeline forever (see
# check_memory_pressure.py's bounded-subprocess convention in this directory).
SET_CMD_TIMEOUT_SECONDS = 30


class _RecordAssignment(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        assignments = getattr(namespace, "assignments", None)
        if assignments is None:
            assignments = []
            namespace.assignments = assignments
        assignments.append((self.const, values))


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a persona prompt with {PLACEHOLDER} substitution."
    )
    parser.add_argument("persona")
    parser.add_argument("--out", required=True)
    parser.add_argument("--set", action=_RecordAssignment, const="set")
    parser.add_argument("--set-file", action=_RecordAssignment, const="set_file")
    parser.add_argument("--set-cmd", action=_RecordAssignment, const="set_cmd")
    return parser.parse_args(argv)


def _strip_frontmatter(text: str) -> str | None:
    """Return the body with leading frontmatter removed, or None if malformed."""
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        return text
    for i in range(1, len(lines)):
        if lines[i] == "---":
            return "\n".join(lines[i + 1 :])
    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        text = Path(args.persona).read_text(encoding="utf-8")
    except OSError:
        return 2

    body = _strip_frontmatter(text)
    if body is None:
        return 3

    values: dict[str, str] = {}
    for kind, raw in getattr(args, "assignments", None) or []:
        key, _, val = raw.partition("=")
        if kind == "set":
            values[key] = val
        elif kind == "set_file":
            try:
                values[key] = Path(val).read_text(encoding="utf-8")
            except OSError:
                print(
                    f"render_prompt: --set-file path not found for {{{key}}}: {val}",
                    file=sys.stderr,
                )
                return 4
        else:  # set_cmd
            try:
                result = subprocess.run(
                    val,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=SET_CMD_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                print(
                    f"render_prompt: --set-cmd failed for {{{key}}}: {val} "
                    f"(timed out after {SET_CMD_TIMEOUT_SECONDS}s)",
                    file=sys.stderr,
                )
                return 4
            if result.returncode != 0:
                stderr_line = " ".join(result.stderr.split())
                print(
                    f"render_prompt: --set-cmd failed for {{{key}}}: {val} "
                    f"(exit {result.returncode}): {stderr_line}",
                    file=sys.stderr,
                )
                return 4
            stdout = result.stdout
            if stdout.endswith("\n"):
                stdout = stdout[:-1]
            values[key] = stdout

    found = {match.group(0)[1:-1] for match in PLACEHOLDER_RE.finditer(body)}
    missing = sorted(found - values.keys())
    if missing:
        print(f"render_prompt: missing placeholder: {{{missing[0]}}}", file=sys.stderr)
        return 1

    body = PLACEHOLDER_RE.sub(lambda m: values[m.group(0)[1:-1]], body)

    out_path = Path(args.out)
    if not out_path.parent.exists():
        print(
            f"render_prompt: output directory does not exist: {out_path.parent}",
            file=sys.stderr,
        )
        return 5

    out_path.write_text(body, encoding="utf-8")
    print(len(body.encode("utf-8")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
