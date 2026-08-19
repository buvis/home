"""Persona frontmatter stripping and {PLACEHOLDER} substitution CLI.

Strips a leading YAML frontmatter block (if present) from a persona file,
substitutes {PLACEHOLDER} tokens using values supplied via --set/--set-file/
--set-cmd, and writes the rendered body to --out.

Exit codes: 0 success, 1 unfilled placeholder, 2 persona file unreadable,
3 unterminated frontmatter, 4 --set-file unreadable or --set-cmd
failed/timed out/produced no output, 5 --out parent directory missing,
6 a --set/--set-file/--set-cmd argument is missing its '=' separator,
7 a --require-file/--require-parent path is relative or does not resolve.
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
        description="Render a persona prompt with {PLACEHOLDER} substitution.",
    )
    parser.add_argument("persona")
    parser.add_argument("--out", required=True)
    parser.add_argument("--set", action=_RecordAssignment, const="set")
    parser.add_argument("--set-file", action=_RecordAssignment, const="set_file")
    parser.add_argument("--set-cmd", action=_RecordAssignment, const="set_cmd")
    parser.add_argument("--require-file", action="append", default=[])
    parser.add_argument("--require-parent", action="append", default=[])
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


def _run_set_cmd(key: str, cmd: str) -> tuple[str | None, int]:
    """Run a --set-cmd command, returning (value, 0) or (None, exit_code)
    after printing the cause."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=SET_CMD_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        print(
            f"render_prompt: --set-cmd failed for {{{key}}}: {cmd} "
            f"(timed out after {SET_CMD_TIMEOUT_SECONDS}s)",
            file=sys.stderr,
        )
        return None, 4
    if result.returncode != 0:
        stderr_line = " ".join(result.stderr.split())
        print(
            f"render_prompt: --set-cmd failed for {{{key}}}: {cmd} "
            f"(exit {result.returncode}): {stderr_line}",
            file=sys.stderr,
        )
        return None, 4
    stdout = result.stdout
    stdout = stdout.removesuffix("\n")
    if stdout == "":
        print(
            f"render_prompt: --set-cmd produced no output for {{{key}}}: {cmd}",
            file=sys.stderr,
        )
        return None, 4
    return stdout, 0


def _resolve_assignments(
    assignments: list[tuple[str, str]],
) -> tuple[dict[str, str] | None, int]:
    """Return (values, 0) or (None, exit_code) after printing the cause."""
    flag_names = {"set": "--set", "set_file": "--set-file", "set_cmd": "--set-cmd"}
    values: dict[str, str] = {}
    for kind, raw in assignments:
        if "=" not in raw:
            print(
                f"render_prompt: {flag_names[kind]} argument missing '=': {raw}",
                file=sys.stderr,
            )
            return None, 6
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
                return None, 4
        else:  # set_cmd
            value, code = _run_set_cmd(key, val)
            if value is None:
                return None, code
            values[key] = value
    return values, 0


def _check_required_paths(require_file: list[str], require_parent: list[str]) -> int:
    """Return 0 when every dispatch-target path is absolute and resolves, 7 otherwise.

    A subagent given an unanchored or dangling target path goes hunting for it
    and can land outside the repo (Tess edited a synced vault copy, 2026-08-18).
    """
    for raw in require_file + require_parent:
        if not Path(raw).is_absolute():
            print(f"render_prompt: required path not absolute: {raw}", file=sys.stderr)
            return 7
    for raw in require_file:
        if not Path(raw).is_file():
            print(f"render_prompt: required file does not exist: {raw}", file=sys.stderr)
            return 7
    for raw in require_parent:
        if not Path(raw).parent.is_dir():
            print(
                f"render_prompt: parent directory of required path does not exist: {raw}",
                file=sys.stderr,
            )
            return 7
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    code = _check_required_paths(args.require_file, args.require_parent)
    if code:
        return code

    try:
        text = Path(args.persona).read_text(encoding="utf-8")
    except OSError:
        print(
            f"render_prompt: persona file unreadable: {args.persona}",
            file=sys.stderr,
        )
        return 2

    body = _strip_frontmatter(text)
    if body is None:
        print(
            f"render_prompt: unterminated frontmatter: {args.persona}",
            file=sys.stderr,
        )
        return 3

    values, code = _resolve_assignments(getattr(args, "assignments", None) or [])
    if values is None:
        return code

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
