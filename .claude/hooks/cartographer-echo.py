#!/usr/bin/env python3
"""PreToolUse hook — Cartographer Phase 1 (Echo) duplicate-detection gate.

Reads a single JSON payload from stdin, dispatches on `tool_name`, and emits
an audit event for every decision (allow/deny/skip). At this scaffolding
phase (PRD 00010 Task 1) only the skip rules are wired; symbol extraction,
match search, and the deny envelope are added in later tasks.

Allow path: exit 0 with empty stdout (mirrors gateguard-fact-force.py).
Deny path: exit 0 with a `hookSpecificOutput.permissionDecision = "deny"`
JSON envelope on stdout (added in later tasks).

Stdlib-only. Optional `tree_sitter_language_pack` accessed lazily via
`_lib_cartographer.try_import_tree_sitter`. Python 3.10+.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# Reuse the shared cartographer substrate (project hash, audit, session-state,
# tree-sitter wrapper). The hooks/ directory is on sys.path when invoked via
# subprocess from settings.json; for completeness, prepend it explicitly so
# `python3 cartographer-echo.py` from any cwd resolves the lib.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib_cartographer as lib  # noqa: E402

# --- constants ---

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go"}
)

# Map dotted extension -> tree_sitter_language_pack language name. `.jsx`
# uses the javascript grammar (no dedicated jsx grammar in the pack).
_LANG_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".rs": "rust",
    ".go": "go",
}

# StructureItem kinds we treat as name-bearing symbols worth duplicate-
# checking. `process()` returns kinds as enums whose `str()` is the variant
# name (e.g. "Function", "Method"). Compare via string.
_SYMBOL_KINDS: frozenset[str] = frozenset(
    {"Function", "Method", "Class", "Struct", "Enum", "Type", "Trait", "Interface"}
)

# Low-signal names dropped before match scoring. The duplicate-prone verbs
# (`format`/`parse`/`validate`/`normalize`/`serialize`/`transform`) are
# deliberately ABSENT from this list (PRD success metric).
_STOPWORDS: frozenset[str] = frozenset(
    {
        "__init__", "__main__", "main", "init", "setup", "run", "start", "stop",
        "new", "default", "clone", "eq", "hash", "to_string", "from_string",
    }
)
_MIN_SYMBOL_LEN: int = 4  # drop length <= 3

# 500 KB cap on `tool_input.content` (Write/Edit reconstructed). Files bigger
# than this are common in generated/minified bundles; tree-sitter parsing
# them blows the latency budget. Skip + audit instead.
LARGE_CONTENT_BYTES: int = 500_000

CLAUDE_SETTINGS_RE = re.compile(r"(^|/)\.claude/settings(?:\.[^/]+)?\.json$")

# Test-file path patterns. Matched as substrings (segments) or filename
# suffixes; tests in the project's `tests/` or `test/` dirs, `*_test.go`
# (Go convention), and `*.test.{ts,tsx,js,jsx}` (JS/TS convention).
_TEST_DIR_SEGMENTS: tuple[str, ...] = ("/tests/", "/test/")
_TEST_FILE_SUFFIXES: tuple[str, ...] = (
    "_test.go",
    "_test.py",
    ".test.ts",
    ".test.tsx",
    ".test.js",
    ".test.jsx",
)

# Tools Echo gates. Other tool names pass through with no audit event.
_TARGETED_TOOLS: frozenset[str] = frozenset(
    {"Edit", "Write", "MultiEdit", "Bash"}
)


# --- helpers ---


def is_claude_settings_path(file_path: str) -> bool:
    """Match any `.claude/settings*.json` path (mirrors gateguard convention)."""
    if not file_path:
        return False
    return bool(CLAUDE_SETTINGS_RE.search(file_path.replace("\\", "/")))


def is_test_file_path(file_path: str) -> bool:
    if not file_path:
        return False
    norm = file_path.replace("\\", "/")
    if any(seg in norm for seg in _TEST_DIR_SEGMENTS):
        return True
    return any(norm.endswith(suffix) for suffix in _TEST_FILE_SUFFIXES)


def file_extension(file_path: str) -> str:
    """Return the dotted extension (`.py`, `.ts`, …) or `""` if none."""
    if not file_path:
        return ""
    name = file_path.replace("\\", "/").rsplit("/", 1)[-1]
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1].lower()


def has_supported_extension(file_path: str) -> bool:
    return file_extension(file_path) in SUPPORTED_EXTENSIONS


def content_size(tool_input: dict) -> int:
    """Best-effort size estimate from `tool_input.content` or Edit strings."""
    content = tool_input.get("content")
    if isinstance(content, str):
        return len(content)
    new_string = tool_input.get("new_string")
    if isinstance(new_string, str):
        return len(new_string)
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        total = 0
        for ed in edits:
            if isinstance(ed, dict):
                ns = ed.get("new_string")
                if isinstance(ns, str):
                    total += len(ns)
        if total:
            return total
    return 0


def target_file_path(tool_name: str, tool_input: dict) -> str:
    """Extract the target file path for the supported write tools."""
    if tool_name in ("Edit", "Write", "MultiEdit"):
        fp = tool_input.get("file_path")
        if isinstance(fp, str):
            return fp
    return ""


# --- content reconstruction & symbol extraction ---


def extract_content(tool_name: str, tool_input: dict) -> str:
    """Best-effort assembly of the new content to scan.

    Write: `content` directly.
    Edit: `new_string` (treats the diff fragment as the scan target; this
    intentionally over-scans for the substring being added, which keeps
    Echo's symbol coverage on small edits).
    MultiEdit: concatenate all `new_string` values.
    """
    if tool_name == "Write":
        c = tool_input.get("content")
        return c if isinstance(c, str) else ""
    if tool_name == "Edit":
        ns = tool_input.get("new_string")
        return ns if isinstance(ns, str) else ""
    if tool_name == "MultiEdit":
        edits = tool_input.get("edits")
        if isinstance(edits, list):
            parts = []
            for ed in edits:
                if isinstance(ed, dict):
                    ns = ed.get("new_string")
                    if isinstance(ns, str):
                        parts.append(ns)
            return "\n".join(parts)
    return ""


def _walk_structure(items, kinds: frozenset[str], collected: list[str], seen: set[str]) -> None:
    """Depth-first walk over `process(...).structure`, collecting named items.

    Anonymous items (`name is None` or empty) are skipped — they cannot be
    matched as duplicates by name. De-dup preserves first-seen order.
    """
    if not items:
        return
    for it in items:
        name = getattr(it, "name", None)
        kind = str(getattr(it, "kind", ""))
        if name and kind in kinds and name not in seen:
            seen.add(name)
            collected.append(name)
        children = getattr(it, "children", None)
        if children:
            _walk_structure(children, kinds, collected, seen)


def extract_symbols(content: str, ext: str) -> list[str]:
    """Extract defined symbol names from `content` for the given extension.

    Returns [] when the extension is unsupported, content is empty, the
    tree-sitter pack is unavailable, or parsing fails. Never raises.
    """
    if not content:
        return []
    lang = _LANG_BY_EXT.get(ext.lower())
    if lang is None:
        return []
    mod = lib.try_import_tree_sitter()
    if mod is None:
        return []
    try:
        config = mod.ProcessConfig(language=lang, symbols=True, structure=True)
        result = mod.process(content, config)
    except Exception as exc:  # noqa: BLE001
        # Parsing fails on syntactically invalid content; record a warn and
        # treat as no symbols (the host write proceeds).
        lib.append_audit({"event": "tree_sitter_parse_failed", "language": lang, "error": str(exc)})
        return []

    collected: list[str] = []
    seen: set[str] = set()
    _walk_structure(getattr(result, "structure", None) or [], _SYMBOL_KINDS, collected, seen)
    # Also merge in top-level `symbols` (some grammars — e.g. go's
    # `type` declarations — surface only here, not in `structure`).
    for s in getattr(result, "symbols", None) or []:
        name = getattr(s, "name", None)
        kind = str(getattr(s, "kind", ""))
        if name and kind in _SYMBOL_KINDS and name not in seen:
            seen.add(name)
            collected.append(name)
    return collected


def filter_stopwords(symbols: list[str], file_path: str) -> list[str]:
    """Drop low-signal symbols. Returns [] when `file_path` is a test file.

    Test-file detection: any path containing `/tests/` or `/test/`, or
    ending with `_test.go`, `_test.py`, `.test.{ts,tsx,js,jsx}`. Echo
    intentionally never gates writes to test files (those write paths are
    where duplicate-detection produces the most false positives).
    """
    if is_test_file_path(file_path):
        return []
    out: list[str] = []
    for name in symbols:
        if not isinstance(name, str) or not name:
            continue
        if len(name) < _MIN_SYMBOL_LEN:
            continue
        if name in _STOPWORDS:
            continue
        out.append(name)
    return out


# --- audit emission ---


def audit_event(
    *,
    session: str,
    tool: str,
    file: str,
    decision: str,
    reason: str,
    symbols: list[str] | None = None,
    matches: list[dict] | None = None,
) -> None:
    """Append one audit event with the Echo schema (PRD 00010 §Audit)."""
    event = {
        "session": session,
        "tool": tool,
        "file": file,
        "decision": decision,
        "reason": reason,
        "symbols": symbols or [],
        "matches": matches or [],
        "phase": "echo",
    }
    lib.append_audit(event)


# --- skip evaluation ---


def evaluate_skip(tool_name: str, tool_input: dict) -> tuple[str, str] | None:
    """Return `(decision, reason)` for a skip case, or None to continue.

    Order matters: settings check runs before extension check so the
    audit log records the *primary* skip reason consistently.
    """
    file_path = target_file_path(tool_name, tool_input)

    if file_path and is_claude_settings_path(file_path):
        return ("skip", "settings")

    if content_size(tool_input) > LARGE_CONTENT_BYTES:
        return ("skip", "large-file")

    if file_path and is_test_file_path(file_path):
        return ("skip", "test-file")

    if file_path and not has_supported_extension(file_path):
        return ("skip", "unsupported-ext")

    # tree-sitter availability is checked last because the import is cached
    # process-wide and emits its own `tree_sitter_missing` audit on first
    # failure. We still record a skip:no-tree-sitter so audit-echo can
    # surface the rate.
    if lib.try_import_tree_sitter() is None:
        return ("skip", "no-tree-sitter")

    return None


# --- main dispatch ---


def handle(data: dict) -> None:
    tool_name = data.get("tool_name") or ""
    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    if tool_name not in _TARGETED_TOOLS and not tool_name.startswith("mcp__serena__"):
        # Echo does not gate this tool; emit no audit event.
        return

    session = lib.resolve_session_key(data)
    file_path = target_file_path(tool_name, tool_input)

    skip = evaluate_skip(tool_name, tool_input)
    if skip is not None:
        decision, reason = skip
        audit_event(
            session=session,
            tool=tool_name,
            file=file_path,
            decision=decision,
            reason=reason,
        )
        return

    # Symbol extraction + stopword filter (PRD 00010 Tasks 3-4). Match
    # search, scoring, and the two-attempt deny gate land in Tasks 5-8.
    if tool_name in ("Edit", "Write", "MultiEdit"):
        content = extract_content(tool_name, tool_input)
        ext = file_extension(file_path)
        raw_symbols = extract_symbols(content, ext)
        symbols = filter_stopwords(raw_symbols, file_path)
        reason = "extracted" if symbols else "no-symbols"
        audit_event(
            session=session,
            tool=tool_name,
            file=file_path,
            decision="allow",
            reason=reason,
            symbols=symbols,
        )
        return

    return


def main() -> int:
    if sys.stdin.isatty():
        return 0
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if not isinstance(data, dict):
        return 0
    try:
        handle(data)
    except Exception as exc:  # noqa: BLE001
        # Hooks must never crash the host tool. Surface to stderr and exit
        # 0 so the Edit/Write proceeds.
        print(f"[cartographer-echo] handle failed: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
