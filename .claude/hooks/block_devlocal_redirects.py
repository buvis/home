"""PreToolUse Bash hook: block shell redirects writing into dev/local/.

Files in dev/local/ must be created via the Write tool. Replaces
~/.claude/hooks/block-devlocal-redirects.sh.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import allow, block, read_input  # noqa: E402

REDIRECT_RE = re.compile(r"(>>?|&>)\s*[^\s&|;]*dev/local/")
TEE_RE = re.compile(r"\btee\b[^|;&]*dev/local/")

REDIRECT_MSG = """\
BLOCKED: shell redirect (`>` / `>>` / `&>`) into `dev/local/` is not allowed.

Use the Write tool for `dev/local/` files instead.
See ~/.claude/rules/working-documents.md (dev/local/ section)."""

TEE_MSG = """\
BLOCKED: `tee` writing into `dev/local/` is not allowed.

Use the Write tool for `dev/local/` files instead.
See ~/.claude/rules/working-documents.md (dev/local/ section)."""


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
