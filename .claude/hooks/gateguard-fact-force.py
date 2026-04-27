#!/usr/bin/env python3
"""PreToolUse hook — GateGuard fact-forcing gate.

Forces the agent to investigate before editing files or running destructive
or first-time bash commands. On the first attempt it returns a structured
deny with a fact list to gather; on the second attempt for the same target
it allows through.

State persists per session under $GATEGUARD_STATE_DIR (default
~/.claude/cache/gateguard). Sessions expire after 30 minutes of inactivity.

Exit code is always 0; deny is communicated via the JSON envelope on stdout
(hookSpecificOutput.permissionDecision = "deny").
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

STATE_DIR = Path(os.environ.get("GATEGUARD_STATE_DIR", str(Path.home() / ".claude" / "cache" / "gateguard")))
SESSION_TIMEOUT_SEC = 30 * 60
READ_HEARTBEAT_SEC = 60

MAX_CHECKED_ENTRIES = 500
MAX_SESSION_KEYS = 50
ROUTINE_BASH_KEY = "__bash_session__"

DESTRUCTIVE_BASH = re.compile(
    r"\b(rm\s+-rf|git\s+reset\s+--hard|git\s+checkout\s+--|git\s+clean\s+-f|"
    r"drop\s+table|delete\s+from|truncate|git\s+push\s+--force|dd\s+if=)\b",
    re.IGNORECASE,
)

CLAUDE_SETTINGS_PATH = re.compile(r"(^|/)\.claude/settings(?:\.[^/]+)?\.json$")


# --- session-key resolution ---

def _hash_key(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"


def _sanitize_session_key(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", raw)
    if sanitized and len(sanitized) <= 64:
        return sanitized
    return _hash_key("sid", raw)


def resolve_session_key(data: dict) -> str:
    candidates = [
        data.get("session_id"),
        data.get("sessionId"),
        (data.get("session") or {}).get("id") if isinstance(data.get("session"), dict) else None,
        os.environ.get("CLAUDE_SESSION_ID"),
    ]
    for c in candidates:
        sanitized = _sanitize_session_key(c if isinstance(c, str) else None)
        if sanitized:
            return sanitized

    transcript = data.get("transcript_path") or data.get("transcriptPath") or os.environ.get("CLAUDE_TRANSCRIPT_PATH")
    if isinstance(transcript, str) and transcript.strip():
        return _hash_key("tx", str(Path(transcript.strip()).resolve()))

    project = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return _hash_key("proj", str(Path(project).resolve()))


# --- state I/O ---

def _state_file(session_key: str) -> Path:
    return STATE_DIR / f"state-{session_key}.json"


def load_state(state_file: Path) -> dict:
    if not state_file.exists():
        return {"checked": [], "last_active": time.time()}
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"checked": [], "last_active": time.time()}
    last_active = state.get("last_active", 0)
    if time.time() - last_active > SESSION_TIMEOUT_SEC:
        try:
            state_file.unlink()
        except OSError:
            pass
        return {"checked": [], "last_active": time.time()}
    if not isinstance(state.get("checked"), list):
        state["checked"] = []
    return state


def _prune_checked(checked: list[str]) -> list[str]:
    if len(checked) <= MAX_CHECKED_ENTRIES:
        return checked
    preserved = [ROUTINE_BASH_KEY] if ROUTINE_BASH_KEY in checked else []
    session_keys = [k for k in checked if k.startswith("__") and k != ROUTINE_BASH_KEY]
    file_keys = [k for k in checked if not k.startswith("__")]
    session_slots = max(MAX_SESSION_KEYS - len(preserved), 0)
    capped_session = session_keys[-session_slots:]
    file_slots = max(MAX_CHECKED_ENTRIES - len(preserved) - len(capped_session), 0)
    capped_files = file_keys[-file_slots:]
    return preserved + capped_session + capped_files


def save_state(state_file: Path, state: dict) -> None:
    state["last_active"] = time.time()
    state["checked"] = _prune_checked(state.get("checked", []))
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(STATE_DIR), prefix=state_file.name + ".tmp.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp_path, state_file)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def mark_checked(state_file: Path, key: str) -> None:
    state = load_state(state_file)
    if key not in state["checked"]:
        state["checked"].append(key)
        save_state(state_file, state)


def is_checked(state_file: Path, key: str) -> bool:
    state = load_state(state_file)
    found = key in state["checked"]
    if found and time.time() - state.get("last_active", 0) > READ_HEARTBEAT_SEC:
        save_state(state_file, state)
    return found


def prune_stale_state_files() -> None:
    """Best-effort cleanup of state files older than 1 hour."""
    if not STATE_DIR.exists():
        return
    cutoff = time.time() - SESSION_TIMEOUT_SEC * 2
    try:
        for f in STATE_DIR.iterdir():
            if not f.name.startswith("state-") or not f.name.endswith(".json"):
                continue
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError:
                continue
    except OSError:
        return


# --- path / command classification ---

_BIDI_RANGES = ((0x200E, 0x200F), (0x202A, 0x202E), (0x2066, 0x2069))


def sanitize_path(file_path: str | None) -> str:
    """Strip control chars, bidi overrides, and newlines from a path."""
    if not file_path:
        return ""
    out_chars: list[str] = []
    for ch in str(file_path):
        code = ord(ch)
        is_ascii_control = code <= 0x1F or code == 0x7F
        is_bidi = any(lo <= code <= hi for lo, hi in _BIDI_RANGES)
        out_chars.append(" " if (is_ascii_control or is_bidi) else ch)
    return "".join(out_chars).strip()[:500]


def is_claude_settings_path(file_path: str) -> bool:
    normalized = file_path.replace("\\", "/").lower()
    return bool(CLAUDE_SETTINGS_PATH.search(normalized))


def is_read_only_git(command: str) -> bool:
    """Allow common read-only git introspection without gating."""
    trimmed = (command or "").strip()
    if not trimmed or re.search(r"[\r\n;&|><`$()]", trimmed):
        return False
    tokens = trimmed.split()
    if len(tokens) < 2 or tokens[0] != "git":
        return False
    sub = tokens[1].lower()
    args = tokens[2:]
    if sub == "status":
        return all(a in {"--porcelain", "--short", "--branch"} for a in args)
    if sub == "diff":
        return len(args) <= 1 and all(a in {"--name-only", "--name-status"} for a in args)
    if sub == "log":
        return all(a == "--oneline" or re.fullmatch(r"--max-count=\d+", a) for a in args)
    if sub == "show":
        return len(args) == 1 and not args[0].startswith("-") and bool(re.fullmatch(r"[a-zA-Z0-9._:/-]+", args[0]))
    if sub == "branch":
        return args == ["--show-current"]
    if sub == "rev-parse":
        return len(args) == 2 and args[0] == "--abbrev-ref" and args[1].lower() == "head"
    return False


# --- gate messages ---

def _msg(*lines: str) -> str:
    return "\n".join(lines)


def edit_gate_msg(file_path: str) -> str:
    safe = sanitize_path(file_path)
    return _msg(
        "[Fact-Forcing Gate]",
        "",
        f"Before editing {safe}, present these facts:",
        "",
        "1. List ALL files that import/require this file (use Grep)",
        "2. List the public functions/classes affected by this change",
        "3. If this file reads/writes data files, show field names, structure, and date format (use redacted or synthetic values, not raw production data)",
        "4. Quote the user's current instruction verbatim",
        "",
        "Present the facts, then retry the same operation.",
    )


def write_gate_msg(file_path: str) -> str:
    safe = sanitize_path(file_path)
    return _msg(
        "[Fact-Forcing Gate]",
        "",
        f"Before creating {safe}, present these facts:",
        "",
        "1. Name the file(s) and line(s) that will call this new file",
        "2. Confirm no existing file serves the same purpose (use Glob)",
        "3. If this file reads/writes data files, show field names, structure, and date format (use redacted or synthetic values, not raw production data)",
        "4. Quote the user's current instruction verbatim",
        "",
        "Present the facts, then retry the same operation.",
    )


def destructive_bash_msg() -> str:
    return _msg(
        "[Fact-Forcing Gate]",
        "",
        "Destructive command detected. Before running, present:",
        "",
        "1. List all files/data this command will modify or delete",
        "2. Write a one-line rollback procedure",
        "3. Quote the user's current instruction verbatim",
        "",
        "Present the facts, then retry the same operation.",
    )


def routine_bash_msg() -> str:
    return _msg(
        "[Fact-Forcing Gate]",
        "",
        "Before the first Bash command this session, present these facts:",
        "",
        "1. The current user request in one sentence",
        "2. What this specific command verifies or produces",
        "",
        "Present the facts, then retry the same operation.",
    )


def deny(reason: str) -> str:
    return json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    })


# --- main routing ---

TOOL_MAP = {"edit": "Edit", "write": "Write", "multiedit": "MultiEdit", "bash": "Bash"}


def evaluate(data: dict) -> str | None:
    """Return a deny-JSON string if the call should be blocked, else None."""
    raw_tool = data.get("tool_name", "") or ""
    tool_input = data.get("tool_input", {}) or {}
    tool = TOOL_MAP.get(raw_tool.lower(), raw_tool)

    session_key = resolve_session_key(data)
    state_file = _state_file(session_key)

    if tool in {"Edit", "Write"}:
        file_path = tool_input.get("file_path") or ""
        if not file_path or is_claude_settings_path(file_path):
            return None
        if is_checked(state_file, file_path):
            return None
        mark_checked(state_file, file_path)
        return deny(edit_gate_msg(file_path) if tool == "Edit" else write_gate_msg(file_path))

    if tool == "MultiEdit":
        edits = tool_input.get("edits") or []
        for edit in edits:
            if not isinstance(edit, dict):
                continue
            file_path = edit.get("file_path") or ""
            if not file_path or is_claude_settings_path(file_path) or is_checked(state_file, file_path):
                continue
            mark_checked(state_file, file_path)
            return deny(edit_gate_msg(file_path))
        return None

    if tool == "Bash":
        command = tool_input.get("command") or ""
        if is_read_only_git(command):
            return None
        if DESTRUCTIVE_BASH.search(command):
            key = "__destructive__" + hashlib.sha256(command.encode("utf-8")).hexdigest()[:16]
            if is_checked(state_file, key):
                return None
            mark_checked(state_file, key)
            return deny(destructive_bash_msg())
        if not is_checked(state_file, ROUTINE_BASH_KEY):
            mark_checked(state_file, ROUTINE_BASH_KEY)
            return deny(routine_bash_msg())
        return None

    return None


def main() -> int:
    prune_stale_state_files()
    if sys.stdin.isatty():
        return 0
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if not isinstance(data, dict):
        return 0
    deny_json = evaluate(data)
    if deny_json is not None:
        sys.stdout.write(deny_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
