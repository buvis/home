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
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import log_path, read_input  # noqa: E402

ICON_PATH = Path.home() / ".claude" / "hooks" / "claude-icon.png"
SECRET_PATH = Path.home() / ".claude" / "hooks" / ".ntfy-secret"
SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
PYBOOKLID = Path.home() / ".local" / "share" / "uv" / "tools" / "pybooklid" / "bin" / "python"
IDLE_THRESHOLD_SEC = 300
LID_CLOSED_BELOW = 70
NTFY_TIMEOUT_SEC = 3
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


def autopilot_loop_active() -> bool:
    """True when this process runs under a live autoclaude loop wrapper.

    `_AUTOPILOT_LOOP` is the wrapper's PID (exported as $$). An in-loop Stop is
    just a phase/PRD hand-off — the wrapper restarts Claude — so the user must
    not be paged for it. The wrapper owns the single terminal notification when
    the loop actually exits (drained / needs-attention), via `--send`.

    Checking the PID is alive (rather than trusting the env var alone) keeps a
    stale `_AUTOPILOT_LOOP` from leaking into a later session — a dead PID
    reads false.
    """
    val = os.environ.get("_AUTOPILOT_LOOP", "")
    if not val.isdigit():
        return False
    try:
        os.kill(int(val), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def notify_quiet() -> bool:
    """True when the parent dispatcher marked this session's noise as its own.

    sonnet-run.sh exports _CLAUDE_NOTIFY_QUIET=1 for nested claude reviewers:
    they load the full hook stack, but their Stop is a dispatch step inside a
    larger job, not a user-facing "done". Same suppression scope as
    autopilot_loop_active (Stop + idle_prompt); permission_prompt still pages.
    """
    # CLAUDE_NESTED is the unified nested-dispatch marker (2026-07-19, audit
    # decision 3) covering the same children; _CLAUDE_NOTIFY_QUIET stays for
    # back-compat with call sites that predate it.
    return os.environ.get("_CLAUDE_NOTIFY_QUIET", "") == "1" or bool(
        os.environ.get("CLAUDE_NESTED")
    )


def running_background_tasks(payload: dict[str, Any]) -> int:
    """Count background_tasks entries the harness reports as still running.

    A Stop with running tasks is a mid-job turn boundary, not completion —
    the session re-invokes when a task lands and the final Stop arrives with
    an empty list (2026-07-19: one fan-out job pinged "done" 4 times).
    """
    tasks = payload.get("background_tasks")
    if not isinstance(tasks, list):
        return 0
    return sum(1 for t in tasks if isinstance(t, dict) and t.get("status") == "running")


# Just under the 60s idle_prompt delay: a subagent write inside this window
# postdates the turn end, which only a live background agent can produce
# (foreground agents finish writing before the turn ends).
IDLE_BG_WINDOW_SEC = 55


def background_agents_active(payload: dict[str, Any]) -> bool:
    """True when a subagent transcript for this session was written in the
    last IDLE_BG_WINDOW_SEC — background work is live, so an idle_prompt is
    parked-on-tasks noise, not a real "waiting for you".

    idle_prompt payloads carry no background_tasks field; the session's
    subagents/agent-*.jsonl mtimes are the disk proxy.
    ponytail: mtime heuristic — an agent silent >55s inside one long tool
    call lets a ping through; parse task lifecycle from the transcript if
    that ever matters.
    """
    transcript = str(payload.get("transcript_path") or "")
    if not transcript.endswith(".jsonl"):
        return False
    subagents = Path(transcript[: -len(".jsonl")]) / "subagents"
    now = time.time()
    try:
        agent_files = list(subagents.glob("agent-*.jsonl"))
    except OSError:
        return False
    for agent_file in agent_files:
        try:
            if now - agent_file.stat().st_mtime < IDLE_BG_WINDOW_SEC:
                return True
        except OSError:
            continue
    return False


ROTATE_THRESHOLD_BYTES = 5 * 1024 * 1024


def log_line(line: str) -> None:
    """Append a single line (with newline) to notify.log, rotating past ~5 MB."""
    path = log_path("notify.log")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.stat().st_size > ROTATE_THRESHOLD_BYTES:
            path.replace(path.with_suffix(path.suffix + ".1"))
    except OSError:
        pass
    with path.open("a", encoding="utf-8") as fh:
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


def _header_safe(value: str) -> str:
    """urllib encodes headers as latin-1; emoji titles ("autopilot ✅ …")
    crash urlopen. ntfy accepts RFC 2047 encoded-words for non-latin-1."""
    try:
        value.encode("latin-1")
        return value
    except UnicodeEncodeError:
        token = base64.b64encode(value.encode("utf-8")).decode("ascii")
        return f"=?UTF-8?B?{token}?="


def build_ntfy_request(url: str, topic: str, title: str, msg: str, creds: str) -> urllib.request.Request:
    full_url = f"{url.rstrip('/')}/{topic}"
    # Override urllib's default `Python-urllib/*` UA — Cloudflare blocks it
    # (error code 1010, returned as HTTP 403) when ntfy is fronted by CF.
    headers = {"Title": _header_safe(title), "Tags": "computer", "User-Agent": "claude-notify-hook/1.0"}
    if creds:
        token = base64.b64encode(creds.encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    return urllib.request.Request(
        full_url,
        data=msg.encode("utf-8"),
        headers=headers,
        method="POST",
    )


def _settings_env(name: str) -> str:
    """Env-block value from settings.json, or "".

    The settings.json env block is injected only into Claude sessions, so a
    wrapper-level `--send` (autoclaude firing its loop-exit alert) runs with
    NTFY_URL/NTFY_TOPIC absent from os.environ — the 2026-07-12 loop death
    went unannounced because of exactly that.
    """
    try:
        env = json.loads(SETTINGS_PATH.read_text(encoding="utf-8")).get("env", {})
    except (OSError, ValueError, AttributeError):
        return ""
    value = env.get(name, "")
    return value if isinstance(value, str) else ""


def send_ntfy(title: str, msg: str) -> None:
    url = os.environ.get("NTFY_URL", "") or _settings_env("NTFY_URL")
    topic = os.environ.get("NTFY_TOPIC", "") or _settings_env("NTFY_TOPIC")
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
        proc = subprocess.run(
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
    if proc.returncode != 0:
        log_line(f"[{now_local()}] ERROR: terminal-notifier exited {proc.returncode}")
        return
    log_line(f"[{now_local()}] System notification shown (user present)")


def dispatch(title: str, msg: str) -> None:
    """Push to ntfy when the user is away, else show a desktop notification."""
    # The three presence probes are independent subprocess spawns (ioreg,
    # screensaver query, lid angle); run them concurrently so a Stop hook pays
    # one probe's latency, not three in series (PRD 00086 R4).
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_idle = ex.submit(read_idle_seconds)
        f_screen = ex.submit(screensaver_active)
        f_lid = ex.submit(lid_closed)
        idle_sec, screensaver, lid = f_idle.result(), f_screen.result(), f_lid.result()

    if should_notify(idle_sec, screensaver, lid):
        send_ntfy(title, msg)
    else:
        show_desktop_notification(title, msg)


def main() -> None:
    # CLI mode: `notify.py --send "Title" "Message"`. Used by the autoclaude
    # wrapper to fire the single terminal notification when its loop exits, so
    # in-loop Stop events can stay silent (see autopilot_loop_active).
    if len(sys.argv) >= 2 and sys.argv[1] == "--send":
        title = sys.argv[2] if len(sys.argv) >= 3 else "autopilot"
        msg = sys.argv[3] if len(sys.argv) >= 4 else ""
        log_line(f"[{now_local()}] CLI --send: {title} / {msg}")
        dispatch(title, msg)
        log_line("---")
        return

    payload = read_input()
    event, title, msg = build_event_strings(payload)

    # Log a one-line summary, never the raw payload: dumping the whole payload
    # bloats notify.log and can spill transcript paths / message text into a
    # plain log file (PRD 00086 R4). The event + title is enough to trace a ping.
    log_line(f"[{now_local()}] Hook triggered: {event} — {title}")

    # Inside a live loop, a `Stop` is a phase/PRD hand-off and an `idle_prompt`
    # Notification just means the session is parked while a background task runs
    # (the wrapper re-invokes Claude when it finishes). Both are loop noise the
    # wrapper summarizes at real exit. Nested reviewer CLIs (_CLAUDE_NOTIFY_QUIET)
    # are the same class of noise. A `permission_prompt` is a genuine "needs
    # you", so it must still page even mid-loop.
    notif_type = str(payload.get("notification_type") or "")
    loop_noise = event == "Stop" or (
        event == "Notification" and notif_type == "idle_prompt"
    )
    if loop_noise and autopilot_loop_active():
        log_line(f"[{now_local()}] Suppressed: autopilot loop active ({notif_type or event})")
        log_line("---")
        return
    if loop_noise and notify_quiet():
        log_line(f"[{now_local()}] Suppressed: _CLAUDE_NOTIFY_QUIET ({notif_type or event})")
        log_line("---")
        return

    # A Stop while background tasks run is a turn boundary, not "done" — the
    # final Stop (empty/terminal background_tasks) carries the real ping.
    running = running_background_tasks(payload)
    if event == "Stop" and running:
        log_line(f"[{now_local()}] Suppressed: {running} background task(s) still running")
        log_line("---")
        return

    # The ~60s-later idle_prompt after such a Stop is the same noise; its
    # payload lacks background_tasks, so fall back to subagent file activity.
    if event == "Notification" and notif_type == "idle_prompt" and background_agents_active(payload):
        log_line(f"[{now_local()}] Suppressed: idle_prompt with live subagent activity")
        log_line("---")
        return

    dispatch(title, msg)

    log_line("---")


if __name__ == "__main__":
    main()
