"""Herdr-owned presence probes and ntfy delivery; no agent-hook dependencies."""

import base64
import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[2] / "pager.local.json"
IDLE_THRESHOLD_SEC = 300
LID_CLOSED_BELOW = 70
NTFY_TIMEOUT_SEC = 3
PRESENCE_TIMEOUT_SEC = 5


def parse_idle_seconds(ioreg_output: str) -> int:
    """Extract HIDIdleTime nanoseconds, preserving the original zero fallback."""
    for raw in ioreg_output.splitlines():
        if "HIDIdleTime" in raw:
            tokens = raw.split()
            try:
                return int(tokens[-1]) // 1_000_000_000
            except (ValueError, IndexError):
                continue
    return 0


def read_idle_seconds() -> int:
    try:
        proc = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem"],
            capture_output=True,
            text=True,
            timeout=PRESENCE_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    return parse_idle_seconds(proc.stdout or "")


def screensaver_active() -> bool:
    try:
        proc = subprocess.run(
            ["pgrep", "-q", "ScreenSaverEngine"],
            capture_output=True,
            timeout=PRESENCE_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def should_notify(idle_sec: int, screensaver: bool, lid: bool) -> bool:
    return idle_sec > IDLE_THRESHOLD_SEC or screensaver or lid


def read_config() -> dict[str, str]:
    """Read private per-machine settings. Never log their contents."""
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or any(
        not isinstance(config.get(key), str) for key in ("url", "topic", "credentials")
    ):
        raise ValueError("Invalid pager configuration")
    return config


def _header_safe(value: str) -> str:
    """Encode Unicode and newline-bearing ntfy titles as RFC 2047 words."""
    if "\r" not in value and "\n" not in value:
        try:
            value.encode("latin-1")
            return value
        except UnicodeEncodeError:
            pass
    token = base64.b64encode(value.encode("utf-8")).decode("ascii")
    return f"=?UTF-8?B?{token}?="


def build_ntfy_request(
    url: str, topic: str, title: str, msg: str, creds: str
) -> urllib.request.Request:
    headers = {
        "Title": _header_safe(title),
        "Tags": "computer",
        "User-Agent": "herdr-pager/1.0",
    }
    if creds:
        token = base64.b64encode(creds.encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    return urllib.request.Request(
        f"{url.rstrip('/')}/{topic}",
        data=msg.encode("utf-8"),
        headers=headers,
        method="POST",
    )


def send_ntfy(title: str, msg: str) -> bool:
    try:
        config = read_config()
        url = os.environ.get("NTFY_URL", "") or config["url"]
        topic = os.environ.get("NTFY_TOPIC", "") or config["topic"]
        if not url or not topic:
            return False
        request = build_ntfy_request(url, topic, title, msg, config["credentials"])
        with urllib.request.urlopen(request, timeout=NTFY_TIMEOUT_SEC) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        # Pager records delivery failure and retries; no private URLs or secrets
        # escape through exception text, logs, or the mod's diagnostics.
        return False
