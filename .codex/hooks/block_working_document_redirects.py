"""Block shell redirects into development-artifact directories."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import allow, block, read_input  # noqa: E402

WORKING_DIR_RE = r"docs/dev/(?:project-management|tmp)/"
REDIRECT_RE = re.compile(rf"(>>?|&>)\|?\s*[^\s&|;]*{WORKING_DIR_RE}")
TEE_RE = re.compile(rf"\btee\b[^|;&<]*{WORKING_DIR_RE}")

REDIRECT_MSG = """\
BLOCKED: shell redirects into docs/dev/project-management/ or docs/dev/tmp/ are not allowed.

Use the Write tool for development artifacts.
See ~/.claude/rules/working-documents.md."""

TEE_MSG = """\
BLOCKED: tee writes into docs/dev/project-management/ or docs/dev/tmp/ are not allowed.

Use the Write tool for development artifacts.
See ~/.claude/rules/working-documents.md."""


def main() -> None:
    data = read_input()
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not cmd:
        allow()
    if REDIRECT_RE.search(cmd):
        block(REDIRECT_MSG)
    if TEE_RE.search(cmd):
        block(TEE_MSG)
    allow()


if __name__ == "__main__":
    main()
