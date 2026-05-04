"""Shared helpers for Claude Code hooks under ~/.claude/hooks/.

Stdlib only. Python 3.10+. Safe to import from any PreToolUse / PostToolUse /
Notification / Stop hook script.

Conventions
-----------
- Hooks read a single JSON object from stdin and signal allow/block via exit
  code: 0 = allow, 2 = block (with a human-readable reason on stderr).
- Gateguard-style hooks that emit a JSON envelope on stdout instead of exiting
  with code 2 do not use this module's `block()` helper.
"""

import json
import sys
from pathlib import Path
from typing import Any, NoReturn


def read_input() -> dict[str, Any]:
    """Parse stdin as JSON. Return {} on empty input or parse failure.

    Hooks must remain non-fatal on bad input so a malformed payload never
    blocks an otherwise-valid tool call.
    """
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def block(reason: str) -> NoReturn:
    """Print reason to stderr and exit 2 (block the tool call)."""
    print(reason, file=sys.stderr)
    sys.exit(2)


def allow() -> NoReturn:
    """Exit 0 (allow the tool call)."""
    sys.exit(0)


def log_path(name: str) -> Path:
    """Resolve a log file under ~/.claude/hooks/."""
    return Path.home() / ".claude" / "hooks" / name


def secret_path(name: str) -> Path:
    """Resolve a secret file under ~/.claude/secrets/."""
    return Path.home() / ".claude" / "secrets" / name
