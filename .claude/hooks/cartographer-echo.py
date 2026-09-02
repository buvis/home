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

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

# Reuse the shared cartographer substrate (project hash, audit, session-state,
# tree-sitter wrapper). The hooks/ directory is on sys.path when invoked via
# subprocess from settings.json; for completeness, prepend it explicitly so
# `python3 cartographer-echo.py` from any cwd resolves the lib.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib_cartographer as lib
from _echo_bash import detect_bash_bypass, is_claude_settings_path
from _echo_catalog import _pick_rationalization
from _echo_search import (
    _resolve_project_root,
    filter_stopwords,
    is_test_file_path,
    search_candidates_batch,
)
from _echo_symbols import (
    decide,
    extract_content,
    extract_symbols,
    file_extension,
    has_supported_extension,
)

# --- constants ---

# 500 KB cap on `tool_input.content` (Write/Edit reconstructed). Files bigger
# than this are common in generated/minified bundles; tree-sitter parsing
# them blows the latency budget. Skip + audit instead.
LARGE_CONTENT_BYTES: int = 500_000

# Tools Echo gates. Other tool names pass through with no audit event.
_TARGETED_TOOLS: frozenset[str] = frozenset(
    {"Edit", "Write", "MultiEdit", "Bash"},
)


# --- helpers ---


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


# --- two-attempt deny gate ---

_ECHO_NAMESPACE: str = "echo"


def deny_key(file_path: str, symbols: list[str]) -> str:
    """`sha256(file_path + "|" + "|".join(sorted(symbols)))[:24]`."""
    payload = file_path + "|" + "|".join(sorted(symbols))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


_DENY_REASON_CAP: int = 1500
_RATIONALIZATION_EXCERPT_CAP: int = 400


def _deny_envelope(reason: str) -> dict:
    """The gateguard-format PreToolUse deny envelope around `reason`."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
    }


def _rationalization_lines(symbols: list[str]) -> list[str]:
    """The catalog excerpt block for `symbols`, or [] when no trigger matches."""
    rationalization = _pick_rationalization(symbols)
    if rationalization is None:
        return []
    excuse, why, counter = rationalization
    excerpt = f'"{excuse}". Why it\'s wrong: {why} Counter-action: {counter}'
    if len(excerpt) > _RATIONALIZATION_EXCERPT_CAP:
        excerpt = excerpt[: _RATIONALIZATION_EXCERPT_CAP - 1].rstrip() + "…"
    return [
        "",
        "Rationalization (`rules-library/rationalizations.md`):",
        "> " + excerpt,
    ]


def build_deny_envelope(matches: list[dict]) -> dict:
    """Compose the gateguard-format deny envelope with a rationalization excerpt."""
    if not matches:
        return _deny_envelope("Echo: duplicate-detection deny — retry to override.")

    strongest = next((m for m in matches if m.get("score") == "strong"), None)
    if strongest is None:
        strongest = next((m for m in matches if m.get("score") == "medium"), matches[0])

    sym = strongest.get("symbol", "?")
    fp = strongest.get("file", "?")
    ln = strongest.get("line", 0)

    symbols_in_play = sorted({m.get("symbol", "") for m in matches if m.get("symbol")})
    parts = [
        f"Echo: `{sym}` likely duplicates `{fp}:{ln}`.",
        "",
        f"Existing implementation is at `{fp}:{ln}` — import it instead of writing a parallel one.",
        *_rationalization_lines(symbols_in_play),
        "",
        "If this is genuinely new, retry — the second attempt will pass.",
    ]
    reason = "\n".join(parts)
    if len(reason) > _DENY_REASON_CAP:
        reason = reason[: _DENY_REASON_CAP - 1].rstrip() + "…"
    return _deny_envelope(reason)


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


def _bash_deny_reason(pattern_name: str, resolved_path: str) -> str:
    return (
        f"Echo: this Bash command writes source code via `{pattern_name}`. "
        f"Use the Write tool — Echo cannot inspect content written through "
        f"shell redirects.\n\nDetected target: `{resolved_path}`.\n\n"
        f"If you must use shell, retry — the second attempt will pass."
    )


def _handle_bash(session: str, tool_input: dict) -> None:
    """Gate a Bash command that writes source behind the Write tool's back."""
    cmd = tool_input.get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return
    hit = detect_bash_bypass(cmd, Path.cwd())
    if hit is None:
        audit_event(
            session=session,
            tool="Bash",
            file="",
            decision="allow",
            reason="bash-clean",
        )
        return
    pattern_name, resolved_path = hit
    key = hashlib.sha256(
        ("bash:" + pattern_name + ":" + resolved_path).encode("utf-8"),
    ).hexdigest()[:24]
    matches = [{"pattern": pattern_name}]
    if lib.is_checked(session, _ECHO_NAMESPACE, key):
        audit_event(
            session=session,
            tool="Bash",
            file=resolved_path,
            decision="allow",
            reason="second-attempt",
            matches=matches,
        )
        return
    lib.mark_checked(session, _ECHO_NAMESPACE, key)
    envelope = _deny_envelope(_bash_deny_reason(pattern_name, resolved_path))
    sys.stdout.write(json.dumps(envelope))
    audit_event(
        session=session,
        tool="Bash",
        file=resolved_path,
        decision="deny",
        reason="bash-bypass",
        matches=matches,
    )


def _deny_or_second_attempt(
    session: str,
    tool_name: str,
    file_path: str,
    symbols: list[str],
    matches: list[dict],
) -> None:
    """The two-attempt gate: deny once per (file, symbols) key, allow the retry."""
    key = deny_key(file_path, symbols)
    if lib.is_checked(session, _ECHO_NAMESPACE, key):
        audit_event(
            session=session,
            tool=tool_name,
            file=file_path,
            decision="allow",
            reason="second-attempt",
            symbols=symbols,
            matches=matches,
        )
        return
    lib.mark_checked(session, _ECHO_NAMESPACE, key)
    sys.stdout.write(json.dumps(build_deny_envelope(matches)))
    # Audit reason matches the strongest hit's score.
    strongest_score = matches[0]["score"] if matches else "unknown"
    audit_event(
        session=session,
        tool=tool_name,
        file=file_path,
        decision="deny",
        reason=f"{strongest_score}-match",
        symbols=symbols,
        matches=matches,
    )


def _handle_write(
    session: str,
    tool_name: str,
    tool_input: dict,
    file_path: str,
) -> None:
    """Gate an Edit/Write/MultiEdit on the symbols it is about to define."""
    content = extract_content(tool_name, tool_input)
    raw_symbols = extract_symbols(content, file_extension(file_path))
    symbols = filter_stopwords(raw_symbols, file_path)
    if not symbols:
        audit_event(
            session=session,
            tool=tool_name,
            file=file_path,
            decision="allow",
            reason="no-symbols",
        )
        return

    # Resolve project root. lib.project_hash returns (hash, name, remote)
    # — the remote_url, not a usable path. Use git toplevel when in a
    # repo; otherwise fall back to the target file's parent directory.
    project_root = _resolve_project_root(file_path)
    # One rg over an alternation of all symbols (PRD 00088 R3) — not one
    # spawn per symbol, which blew the 5s hook budget on symbol-dense files.
    candidate_groups = search_candidates_batch(symbols, project_root, Path(file_path))

    decision, matches = decide(symbols, candidate_groups)
    if decision == "allow":
        audit_event(
            session=session,
            tool=tool_name,
            file=file_path,
            decision="allow",
            reason="weak-only" if any(candidate_groups.values()) else "no-matches",
            symbols=symbols,
            matches=matches,
        )
        return
    _deny_or_second_attempt(session, tool_name, file_path, symbols, matches)


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

    if tool_name == "Bash":
        _handle_bash(session, tool_input)
        return

    if tool_name.startswith("mcp__serena__"):
        # MCP serena tools shadow file writes but with tool-specific input
        # shapes. Surface them in the audit log so audit-echo can flag the
        # coverage gap; do not gate.
        audit_event(
            session=session,
            tool=tool_name,
            file=file_path,
            decision="skip",
            reason="mcp-unsupported",
        )
        return

    if tool_name in ("Edit", "Write", "MultiEdit"):
        _handle_write(session, tool_name, tool_input, file_path)


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


def run(payload):
    """Dispatcher entry point (hooks/dispatch.py). The handler owns its own
    capture: `capture_main` feeds `payload` as stdin, captures stdout/stderr and
    maps main()'s exit, so run() RETURNS the (exit_code, stdout, stderr) triple
    the dispatcher surfaces unchanged. `_common` is imported here, not at module
    scope, so the standalone `__main__` path is unaffected."""
    from _common import capture_main

    return capture_main(main, payload)


if __name__ == "__main__":
    sys.exit(main())
