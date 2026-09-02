"""Bash bypass detection for the Echo duplicate-detection gate.

Extracted from `cartographer-echo.py` (`# --- Bash bypass pattern detection
---`, PRD 00158): recognise shell commands that write source files behind
the Write tool's back (`cat >`, `tee`, `python -c open(...,'w')`, `sed -i`,
unquoted `>` / `>>`) so Echo can nudge the caller back to a tool it can
inspect. The `.claude/settings*.json` predicate lives here because this is
its only consumer outside the entry hook, which imports it back.

Stdlib only. Python 3.10+.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

CLAUDE_SETTINGS_RE = re.compile(r"(^|/)\.claude/settings(?:\.[^/]+)?\.json$")


def is_claude_settings_path(file_path: str) -> bool:
    """Match any `.claude/settings*.json` path (mirrors gateguard convention)."""
    if not file_path:
        return False
    return bool(CLAUDE_SETTINGS_RE.search(file_path.replace("\\", "/")))


_BASH_SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".rs",
        ".go",
        ".md",
        ".yaml",
        ".yml",
        ".json",
        ".toml",
    },
)

_BASH_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cat-redirect", re.compile(r"\bcat\s*>>?\s*(\S+)")),
    ("tee", re.compile(r"\btee\b[^|;]*?(\S+\.[A-Za-z0-9]+)")),
    (
        "python-open-write",
        re.compile(
            r"python3?\s+-c\s+[\"'][^\"']*\bopen\s*\(\s*[\"']([^\"']+)[\"']\s*,\s*[\"']w[\"']",
        ),
    ),
    ("sed-inplace", re.compile(r"\bsed\s+-i\b[^|;\n]*?\s(\S+\.[A-Za-z0-9]+)(?:\s|$)")),
)


def _resolve_within_cwd(raw_path: str, cwd: Path) -> Path | None:
    """Resolve `raw_path` against `cwd`. Return Path if it stays within cwd, else None."""
    raw = raw_path.strip().rstrip("'\"").lstrip("'\"")
    if not raw:
        return None
    try:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = cwd / candidate
        resolved = candidate.resolve()
        cwd_resolved = cwd.resolve()
        resolved.relative_to(cwd_resolved)
        return resolved
    except (OSError, ValueError):
        return None


def _find_redirect_targets(command: str) -> list[str]:
    """Targets of real (unquoted) `>` / `>>` operators, via shlex tokenization.

    A `>` inside quotes dequotes into an ordinary token, so literal text like
    `"<prd>-review-<n>.md"` or regex arguments can never read as a redirect.
    """
    lex = shlex.shlex(command, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    try:
        tokens = list(lex)
    except ValueError:
        # Unparseable (heredoc body, unbalanced quotes) — fail open; the
        # cat-redirect regex still covers the heredoc form.
        return []
    targets = []
    for i, tok in enumerate(tokens[:-1]):
        if tok in (">", ">>") and not (i > 0 and tokens[i - 1].isdigit()):
            # ponytail: isdigit guard skips fd redirects (2> err.md) but also
            # `echo 2 > x.md`; acceptable, Echo is a soft nudge.
            targets.append(tokens[i + 1])
    return targets


def _check_target(target: str, cwd: Path) -> Path | None:
    """Apply the source-path heuristic to one candidate target path."""
    resolved = _resolve_within_cwd(target, cwd)
    if resolved is None:
        return None
    ext = "." + resolved.name.rsplit(".", 1)[-1].lower() if "." in resolved.name else ""
    if ext not in _BASH_SOURCE_EXTENSIONS:
        return None
    if is_claude_settings_path(str(resolved)):
        return None
    return resolved


def detect_bash_bypass(command: str, cwd: Path) -> tuple[str, str] | None:
    """Detect code-writing Bash patterns. Return `(pattern_name, resolved_path_str)` or None.

    Source-path heuristic: the target path resolves under `cwd` AND has an
    extension in `_BASH_SOURCE_EXTENSIONS`. Skips writes to
    `~/.claude/settings.json` so gateguard's own rules govern there.
    """
    if not command or not isinstance(command, str):
        return None
    for name, pat in _BASH_PATTERNS:
        for m in pat.finditer(command):
            target = m.group(1)
            if not target:
                continue
            resolved = _check_target(target, cwd)
            if resolved is None:
                continue
            return (name, str(resolved))
    for target in _find_redirect_targets(command):
        resolved = _check_target(target, cwd)
        if resolved is not None:
            return ("redirect-source", str(resolved))
    return None
