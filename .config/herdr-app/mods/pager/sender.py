"""Route a Herdr alert using local presence detection and notification support."""

import json
import math
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from notifications import (
    LID_CLOSED_BELOW,
    read_idle_seconds,
    screensaver_active,
    send_ntfy,
    should_notify,
)


def read_lid_angle() -> float:
    """Resolve the installed sensor library through mise, not its former uv path."""
    try:
        location = subprocess.run(
            ["mise", "where", "pipx:pybooklid"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        python = Path(location.stdout.strip()) / "pybooklid" / "bin" / "python"
        result = subprocess.run(
            [str(python), "-B", "-c", "import pybooklid; print(pybooklid.read_lid_angle())"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        angle = float(result.stdout.strip())
        if not math.isfinite(angle) or not 0 <= angle <= 360:
            raise ValueError("Invalid lid angle")
        return angle
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise RuntimeError("Cannot read the lid angle from mise's pybooklid") from exc


def deliver(title: str, message: str) -> bool:
    """Send to the phone when away, otherwise to the desktop."""
    with ThreadPoolExecutor(max_workers=3) as pool:
        idle = pool.submit(read_idle_seconds)
        screen = pool.submit(screensaver_active)
        lid = pool.submit(read_lid_angle)
        idle_sec, screen_active, angle = idle.result(), screen.result(), lid.result()
        closed = angle < LID_CLOSED_BELOW
        away = should_notify(idle_sec, screen_active, closed)
    diagnostic = {
        "channel": "phone" if away else "desktop",
        "idle_seconds": idle_sec,
        "screensaver": screen_active,
        "lid_closed": closed,
        "lid_angle": angle,
    }
    if away:
        ok = send_ntfy(title, message)
    else:
        try:
            result = subprocess.run(
                [
                    "terminal-notifier", "-title", title, "-message", message,
                    "-sender", "dev.herdr.app", "-activate", "dev.herdr.app",
                ],
                capture_output=True,
                timeout=5,
                check=False,
            )
            ok = result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
    print(json.dumps({**diagnostic, "accepted": ok}), flush=True)
    return ok


if __name__ == "__main__":
    sys.exit(0 if deliver(sys.argv[1], sys.argv[2]) else 1)
