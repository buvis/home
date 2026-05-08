"""Notification/Stop hook: forward event to ntfy and/or system notifier.

Replaces ~/.claude/hooks/notify.sh. Reads JSON payload from stdin, builds an
event-specific title/message, logs to ~/.claude/hooks/notify.log, and either
posts to ntfy (when the user is away) or shows a desktop notification.

Stdlib only. macOS-specific presence detection (idle time, screensaver, lid
angle) preserved verbatim from the bash original.
"""

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import log_path, read_input  # noqa: E402

ICON_PATH = Path.home() / ".claude" / "hooks" / "claude-icon.png"
SECRET_PATH = Path.home() / ".claude" / "hooks" / ".ntfy-secret"
PYBOOKLID = Path.home() / ".local" / "share" / "uv" / "tools" / "pybooklid" / "bin" / "python"
IDLE_THRESHOLD_SEC = 300
LID_CLOSED_BELOW = 70
NTFY_TIMEOUT_SEC = 8
PRESENCE_TIMEOUT_SEC = 5


def project_name(cwd: str) -> str:
    """Last path segment of cwd, or empty string if cwd is empty."""
    if not cwd:
        return ""
    return cwd.rstrip("/").rsplit("/", 1)[-1]


def build_event_strings(payload: dict[str, Any]) -> tuple[str, str, str]:
    """Return (event, title, msg) for the payload's hook_event_name."""
    event = str(payload.get("hook_event_name") or "")
    project = project_name(str(payload.get("cwd") or ""))
    if event == "Stop":
        return event, f"Claude [{project}]: done", "Task complete"
    if event == "Notification":
        msg = str(payload.get("message") or "Awaiting input")
        return event, f"Claude [{project}]: waiting", msg
    msg = str(payload.get("message") or "Event triggered")
    return event, f"Claude [{project}]: {event}", msg


def log_line(line: str) -> None:
    """Append a single line (with newline) to notify.log."""
    log_path("notify.log").parent.mkdir(parents=True, exist_ok=True)
    with log_path("notify.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def now_local() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_idle_seconds(ioreg_output: str) -> int:
    """Extract HIDIdleTime nanoseconds from ioreg output, return seconds (0 if missing)."""
    for raw in ioreg_output.splitlines():
        if "HIDIdleTime" in raw:
            tokens = raw.split()
            if not tokens:
                continue
            try:
                ns = int(tokens[-1])
            except ValueError:
                continue
            return ns // 1_000_000_000
    return 0


def read_idle_seconds() -> int:
    try:
        proc = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem"],
            capture_output=True,
            text=True,
            timeout=PRESENCE_TIMEOUT_SEC,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return 0
    return parse_idle_seconds(proc.stdout or "")


def screensaver_active() -> bool:
    try:
        proc = subprocess.run(
            ["pgrep", "-q", "ScreenSaverEngine"],
            capture_output=True,
            timeout=PRESENCE_TIMEOUT_SEC,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def parse_lid_angle(stdout: str) -> int | None:
    """Parse the integer part of pybooklid's float output, or None on failure."""
    text = (stdout or "").strip()
    if not text:
        return None
    leading = text.split(".", 1)[0]
    try:
        return int(leading)
    except ValueError:
        return None


def lid_closed() -> bool:
    if not PYBOOKLID.is_file():
        return False
    try:
        proc = subprocess.run(
            [str(PYBOOKLID), "-c", "import pybooklid; print(pybooklid.read_lid_angle())"],
            capture_output=True,
            text=True,
            timeout=PRESENCE_TIMEOUT_SEC,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return False
    angle = parse_lid_angle(proc.stdout)
    if angle is None:
        return False
    return angle < LID_CLOSED_BELOW


def should_notify(idle_sec: int, screensaver: bool, lid: bool) -> bool:
    return idle_sec > IDLE_THRESHOLD_SEC or screensaver or lid


def read_credentials() -> str:
    try:
        return SECRET_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def build_ntfy_request(url: str, topic: str, title: str, msg: str, creds: str) -> urllib.request.Request:
    full_url = f"{url.rstrip('/')}/{topic}"
    # Override urllib's default `Python-urllib/*` UA — Cloudflare blocks it
    # (error code 1010, returned as HTTP 403) when ntfy is fronted by CF.
    headers = {"Title": title, "Tags": "computer", "User-Agent": "claude-notify-hook/1.0"}
    if creds:
        token = base64.b64encode(creds.encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    return urllib.request.Request(
        full_url,
        data=msg.encode("utf-8"),
        headers=headers,
        method="POST",
    )


def send_ntfy(title: str, msg: str) -> None:
    url = os.environ.get("NTFY_URL", "")
    topic = os.environ.get("NTFY_TOPIC", "")
    if not url or not topic:
        log_line(f"[{now_local()}] Skipped ntfy: NTFY_URL or NTFY_TOPIC unset")
        return
    creds = read_credentials()
    req = build_ntfy_request(url, topic, title, msg, creds)
    try:
        with urllib.request.urlopen(req, timeout=NTFY_TIMEOUT_SEC) as resp:
            code = resp.status
        log_line(f"[{now_local()}] Notification sent successfully (http={code})")
    except urllib.error.HTTPError as exc:
        log_line(f"[{now_local()}] ERROR: Failed to send notification (exit code: HTTP {exc.code})")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log_line(f"[{now_local()}] ERROR: Failed to send notification (exit code: {type(exc).__name__})")


def show_desktop_notification(title: str, msg: str) -> None:
    if shutil.which("terminal-notifier") is None:
        log_line(f"[{now_local()}] Skipped: user present, terminal-notifier not available")
        return
    try:
        subprocess.run(
            [
                "terminal-notifier",
                "-title", title,
                "-message", msg,
                "-contentImage", str(ICON_PATH),
                # Impersonate Terminal.app so the left-side app icon resolves to
                # an installed bundle (terminal-notifier's own icon is otherwise
                # what shows there, which macOS often suppresses).
                "-sender", "com.apple.Terminal",
            ],
            capture_output=True,
            timeout=PRESENCE_TIMEOUT_SEC,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        log_line(f"[{now_local()}] ERROR: terminal-notifier failed")
        return
    log_line(f"[{now_local()}] System notification shown (user present)")


def main() -> None:
    payload = read_input()
    event, title, msg = build_event_strings(payload)

    log_line(f"[{now_local()}] Hook triggered: {event}")
    log_line(json.dumps(payload, ensure_ascii=False))

    idle_sec = read_idle_seconds()
    screensaver = screensaver_active()
    lid = lid_closed()

    if should_notify(idle_sec, screensaver, lid):
        send_ntfy(title, msg)
    else:
        show_desktop_notification(title, msg)

    log_line("---")


if __name__ == "__main__":
    main()
