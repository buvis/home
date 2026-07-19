"""PostToolUse hook: log structural tool observations for instinct detection.

Replaces ~/.claude/hooks/observe-tool.sh. Appends JSONL rows to project-scoped
observation files under ~/.claude/instincts/projects/{hash}/.

Stdlib only. Latency budget <100ms — at most two short subprocess calls
(`git remote get-url origin`, fallback `git rev-parse --show-toplevel`).
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import read_input  # noqa: E402

INSTINCTS_DIR = Path.home() / ".claude" / "instincts"
PROJECTS_DIR = INSTINCTS_DIR / "projects"
REGISTRY_FILE = INSTINCTS_DIR / "projects.json"
ROTATE_THRESHOLD_BYTES = 5 * 1024 * 1024
GIT_TIMEOUT_SEC = 2

ERROR_PATTERN = re.compile(
    r"error|Error|ERROR|failed|FAILED|exception|Exception|"
    r"command not found|No such file|Permission denied"
)


def is_automated_session() -> bool:
    if os.environ.get("CLAUDE_NESTED"):
        # Nested dispatch children (sonnet-run.sh reviewers) are automated by
        # definition; their tool calls are not user-habit signal.
        return True
    name = os.environ.get("CLAUDE_SESSION_NAME") or ""
    return "autopilot" in name or "de-sloppify" in name


def build_tool_in(tool_input: dict[str, Any]) -> str:
    """Strip content; keep only structural fields for instinct detection."""
    out: dict[str, Any] = {}
    for key in ("file_path", "path", "pattern"):
        value = tool_input.get(key)
        if value:
            out[key] = value
    cmd = tool_input.get("command")
    if isinstance(cmd, str) and cmd:
        binary = cmd.split()[0] if cmd.split() else ""
        if binary:
            out["command"] = binary
    return json.dumps(out, separators=(",", ":"))


def build_tool_out(tool_response: Any) -> str:
    text = "" if tool_response is None else str(tool_response)
    if ERROR_PATTERN.search(text):
        return text[:500]
    return "ok"


def _git(args: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SEC,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip()
    return out or None


def strip_git_credentials(remote: str) -> str:
    return re.sub(r"://[^@]+@", "://", remote)


def detect_project() -> tuple[str, str, str]:
    """Return (proj_hash, proj_name, proj_remote). Falls back to ('global', 'global', '')."""
    remote = _git(["remote", "get-url", "origin"])
    if remote:
        clean = strip_git_credentials(remote)
        proj_hash = hashlib.sha256(clean.encode("utf-8")).hexdigest()[:12]
        name = clean.rsplit("/", 1)[-1]
        if name.endswith(".git"):
            name = name[:-4]
        return proj_hash, name, clean
    toplevel = _git(["rev-parse", "--show-toplevel"])
    if toplevel:
        proj_hash = hashlib.sha256(toplevel.encode("utf-8")).hexdigest()[:12]
        name = toplevel.rsplit("/", 1)[-1]
        return proj_hash, name, ""
    return "global", "global", ""


def rotate_if_needed(obs_file: Path) -> None:
    if not obs_file.is_file():
        return
    try:
        size = obs_file.stat().st_size
    except OSError:
        return
    if size > ROTATE_THRESHOLD_BYTES:
        rotated = obs_file.with_suffix(obs_file.suffix + ".1")
        try:
            obs_file.replace(rotated)
        except OSError:
            pass


def update_registry(proj_hash: str, proj_name: str, proj_remote: str) -> None:
    INSTINCTS_DIR.mkdir(parents=True, exist_ok=True)
    if REGISTRY_FILE.is_file():
        try:
            registry = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
            if not isinstance(registry, dict):
                registry = {}
        except (OSError, json.JSONDecodeError):
            registry = {}
    else:
        registry = {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    registry[proj_hash] = {
        "name": proj_name,
        "remote": proj_remote,
        "last_seen": today,
    }
    tmp = NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(INSTINCTS_DIR), delete=False
    )
    try:
        json.dump(registry, tmp)
        tmp_path = Path(tmp.name)
    finally:
        tmp.close()
    tmp_path.replace(REGISTRY_FILE)


def main() -> None:
    if is_automated_session():
        return
    payload = read_input()
    tool_name = str(payload.get("tool_name") or "")
    if not tool_name:
        return
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    tool_response = payload.get("tool_response", "")
    sid = str(payload.get("session_id") or "")

    proj_hash, proj_name, proj_remote = detect_project()
    proj_dir = PROJECTS_DIR / proj_hash
    proj_dir.mkdir(parents=True, exist_ok=True)
    obs_file = proj_dir / "observations.jsonl"
    rotate_if_needed(obs_file)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {
        "ts": ts,
        "tool": tool_name,
        "in": build_tool_in(tool_input),
        "out": build_tool_out(tool_response),
        "sid": sid,
        "pid": proj_hash,
    }
    with obs_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":")) + "\n")

    update_registry(proj_hash, proj_name, proj_remote)


if __name__ == "__main__":
    main()
