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

DESTRUCTIVE_BASH = re.compile(
    r"\b(rm\s+-rf|git\s+reset\s+--hard|git\s+checkout\s+--|git\s+clean\s+-f|"
    r"drop\s+table|delete\s+from|truncate|git\s+push\s+--force|dd\s+if=)\b",
    re.IGNORECASE,
)

_QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")


def _strip_quoted(command: str) -> str:
    """Remove quoted substrings so destructive tokens in regex args don't trigger.

    `grep -iE 'rm -rf|...'` should not be treated as a destructive command —
    the literal string is search input, not a command. Quote stripping makes
    the destructive regex match only on unquoted shell content.
    """
    return _QUOTED_RE.sub("", command)

CLAUDE_SETTINGS_PATH = re.compile(r"(^|/)\.claude/settings(?:\.[^/]+)?\.json$")

# Working-doc exemptions: paths where the gate's questions ("list importers",
# "public functions affected") are inapplicable, so gating just trains the
# model to fabricate empty answers.
# Temp/scratch segments (tmp, var/folders, session scratchpads) are throwaway
# by the same policy settings.json autoMode declares; gating them produced
# consecutive-deny retry storms (14x Write in one session) with zero signal.
_WORKING_DOC_DIR_SEGMENTS = (
    "/dev/local/",
    "/.claude/plans/",
    "/.claude/projects/",
    "/.claude/scratch/",
    "/.claude/sessions/",
    "/.claude/cache/",
    "/prds/backlog/",
    "/prds/wip/",
    "/prds/done/",
    "/tmp/",
    "/var/folders/",
    "/scratchpad/",
)

_WORKING_DOC_EXTENSIONS = (".md", ".markdown", ".txt", ".rst")

_WORKING_DOC_FILENAMES = frozenset({".gitignore", ".env.example"})

# Extensions for which "public functions/classes affected" is a sensible
# prompt. Anything else gets the consumer/schema variant.
_CODE_EXTENSIONS = (
    ".py", ".pyx",
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".rs", ".go",
    ".java", ".kt", ".scala", ".swift", ".m", ".mm",
    ".rb", ".php",
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp",
    ".cs", ".fs", ".vb",
    ".lua", ".ex", ".exs",
    ".dart", ".clj", ".cljs", ".hs", ".erl",
    ".sh", ".bash", ".zsh",
    ".vue", ".svelte",
)


def is_code_file(file_path: str) -> bool:
    """Return True for source-code extensions where 'public functions/classes
    affected' is a sensible question. Default for unknown/no extension is True
    so we keep the stricter prompt by default."""
    if not file_path:
        return True
    name = file_path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if "." not in name:
        return True
    return name.endswith(_CODE_EXTENSIONS)


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
    session_keys = [k for k in checked if k.startswith("__")]
    file_keys = [k for k in checked if not k.startswith("__")]
    capped_session = session_keys[-MAX_SESSION_KEYS:]
    file_slots = max(MAX_CHECKED_ENTRIES - len(capped_session), 0)
    capped_files = file_keys[-file_slots:]
    return capped_session + capped_files


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


def is_working_doc_path(file_path: str) -> bool:
    """Return True for working-doc paths where the gate adds no signal.

    Matches:
    - directory segments listed in _WORKING_DOC_DIR_SEGMENTS (e.g. dev/local,
      ~/.claude/plans, prds/{backlog,wip,done})
    - filename extensions listed in _WORKING_DOC_EXTENSIONS (.md, .txt, .rst, ...)
    - exact filenames listed in _WORKING_DOC_FILENAMES (.gitignore, .env.example)

    Substring-only matches do not count: "/dev/local.backup/" must not match
    "/dev/local/", and "cmd.py" must not match the ".md" extension.
    """
    if not file_path:
        return False
    normalized = file_path.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    if name in _WORKING_DOC_FILENAMES:
        return True
    if normalized.lower().endswith(_WORKING_DOC_EXTENSIONS):
        return True
    padded = "/" + normalized.lstrip("/")
    return any(seg in padded for seg in _WORKING_DOC_DIR_SEGMENTS)


def transcript_has_read_of(transcript_path: str, file_path: str, max_bytes: int = 200_000) -> bool:
    """Return True if a prior assistant turn issued a Read tool_use against
    file_path. Scans only the trailing max_bytes of the JSONL to bound latency.

    Treat parse failures as "no match" so a malformed transcript never causes
    a crash in PreToolUse. Cheap pre-filter (bytes-in-line) skips the JSON
    parse for the vast majority of lines."""
    if not transcript_path or not file_path:
        return False
    try:
        size = os.path.getsize(transcript_path)
    except OSError:
        return False
    needle = file_path.encode("utf-8", errors="ignore")
    try:
        with open(transcript_path, "rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                f.readline()  # discard partial line
            for raw_line in f:
                if not raw_line.strip():
                    continue
                if b'"Read"' not in raw_line or needle not in raw_line:
                    continue
                try:
                    entry = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                msg = entry.get("message") or {}
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use" or block.get("name") != "Read":
                        continue
                    inp = block.get("input") or {}
                    if inp.get("file_path") == file_path:
                        return True
    except OSError:
        return False
    return False


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
    if is_code_file(file_path):
        return _msg(
            "[Fact-Forcing Gate]",
            "",
            f"Before editing {safe}, present these facts:",
            "",
            "1. List ALL files that import/require this file (use Grep)",
            "2. List the public functions/classes affected by this change",
            "3. If this file reads/writes data files, show field names, structure, and date format (use redacted or synthetic values, not raw production data)",
            "",
            "Present the facts, then retry the same operation.",
        )
    return _msg(
        "[Fact-Forcing Gate]",
        "",
        f"Before editing {safe}, present these facts:",
        "",
        "1. List ALL code or tooling that consumes this file (use Grep)",
        "2. Show the expected fields/structure (or schema reference)",
        "",
        "Present the facts, then retry the same operation.",
    )


def multiedit_gate_msg(file_paths: list[str]) -> str:
    safe_paths = [sanitize_path(p) for p in file_paths]
    bullets = [f"  - {p}" for p in safe_paths]
    return _msg(
        "[Fact-Forcing Gate]",
        "",
        "Before this MultiEdit batch, present these facts (covering ALL listed files):",
        "",
        *bullets,
        "",
        "1. List ALL files that import/require any of these files (use Grep)",
        "2. List the public functions/classes affected across the batch",
        "3. If any file reads/writes data files, show field names, structure, and date format (use redacted or synthetic values, not raw production data)",
        "",
        "Present the facts, then retry the same operation.",
    )


def write_gate_msg(file_path: str) -> str:
    safe = sanitize_path(file_path)
    if is_code_file(file_path):
        return _msg(
            "[Fact-Forcing Gate]",
            "",
            f"Before creating {safe}, present these facts:",
            "",
            "1. Name the file(s) and line(s) that will call this new file",
            "2. Confirm no existing file serves the same purpose (use Glob)",
            "3. If this file reads/writes data files, show field names, structure, and date format (use redacted or synthetic values, not raw production data)",
            "",
            "Present the facts, then retry the same operation.",
        )
    return _msg(
        "[Fact-Forcing Gate]",
        "",
        f"Before creating {safe}, present these facts:",
        "",
        "1. Name the code or tooling that will consume this file",
        "2. Confirm no existing file serves the same purpose (use Glob)",
        "3. Show the expected fields/structure (or schema reference)",
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
    transcript_path = data.get("transcript_path") or data.get("transcriptPath") or ""

    if tool in {"Edit", "Write"}:
        file_path = tool_input.get("file_path") or ""
        if not file_path or is_claude_settings_path(file_path) or is_working_doc_path(file_path):
            return None
        if is_checked(state_file, file_path):
            return None
        # Edit on a file already Read this session: investigation already
        # happened, the gate would just force restating known facts. Mark it
        # checked so we don't re-scan the transcript on subsequent edits.
        if tool == "Edit" and transcript_has_read_of(transcript_path, file_path):
            mark_checked(state_file, file_path)
            return None
        mark_checked(state_file, file_path)
        return deny(edit_gate_msg(file_path) if tool == "Edit" else write_gate_msg(file_path))

    if tool == "MultiEdit":
        edits = tool_input.get("edits") or []
        unchecked: list[str] = []
        seen: set[str] = set()
        for edit in edits:
            if not isinstance(edit, dict):
                continue
            file_path = edit.get("file_path") or ""
            if (
                not file_path
                or file_path in seen
                or is_claude_settings_path(file_path)
                or is_working_doc_path(file_path)
                or is_checked(state_file, file_path)
            ):
                continue
            if transcript_has_read_of(transcript_path, file_path):
                # Already investigated upstream; mark and skip.
                mark_checked(state_file, file_path)
                seen.add(file_path)
                continue
            seen.add(file_path)
            unchecked.append(file_path)
        if not unchecked:
            return None
        for fp in unchecked:
            mark_checked(state_file, fp)
        return deny(multiedit_gate_msg(unchecked))

    if tool == "Bash":
        command = tool_input.get("command") or ""
        if is_read_only_git(command):
            return None
        if DESTRUCTIVE_BASH.search(_strip_quoted(command)):
            key = "__destructive__" + hashlib.sha256(command.encode("utf-8")).hexdigest()[:16]
            if is_checked(state_file, key):
                return None
            mark_checked(state_file, key)
            return deny(destructive_bash_msg())
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
