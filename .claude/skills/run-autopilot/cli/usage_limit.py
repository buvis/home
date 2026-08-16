"""cli/usage_limit.py - usage-limit detection and the relaunch wait (PRD 00106).

Absorbs scripts/detect_usage_limit.py (that path stays as a re-export
shim: tracon, render_stream and several suites import it). Detection is
unchanged; `wait_decision` adds the loop's own branch-5 computation,
previously inline bash in autoclaude().

Observed 2026-07-02/03 (interactive era): when the Claude usage limit
hits mid-turn, the banner reads "You've hit your session limit · resets
8:10pm (Europe/Prague)".

Post-00014 (headless loop) a limit-hit `claude -p` session exits on its
own with the banner as the tail of the captured session log, so the
primary detection source is that log (detect_from_log). The transcript
path stays as fallback: given a cwd, find the project's newest session
transcript and report whether its LAST substantive entry
(assistant/user; metadata tails ignored) is a live usage-limit error.

A rejected rate_limit_event's `resetsAt` epoch wins over the prose
banner: the stream-json log carries the exact reset as machine-readable
JSON, and the banner's clock time is ambiguous for a seven_day limit
whose reset can be >24h out (observed 2026-07-19: "hit your weekly
limit" killed both loops).
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

LIMIT_TEXT = re.compile(
    r"hit your (?:session|usage|weekly) limit|usage limit reached",
    re.IGNORECASE,
)
RESET_TIME = re.compile(
    r"resets\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*([ap]m)(?:\s*\(([^)]+)\))?",
    re.IGNORECASE,
)
GRACE_SECS = 120  # reset already this far past -> stale record, not a live limit
FALLBACK_WAIT_SECS = 900  # unparseable reset time -> re-check in 15 min
FALLBACK_MAX_AGE_SECS = 7200  # ...but only trust an unparseable error this recent

DEFAULT_PROJECTS_ROOT = Path.home() / ".claude" / "projects"
TAIL_BYTES = 32768  # a limit banner is always in the log's final result event

RELAUNCH_MARGIN_SECS = 120  # sleep past the reset so the first relaunch clears it
MIN_WAIT_SECS = 60
DEFAULT_MAX_WAIT_SECS = 21600  # _AUTOPILOT_LIMIT_WAIT_MAX default


def _project_dir(cwd: str, projects_root: Path) -> Path:
    # Claude Code munges the cwd into a project dir name by replacing
    # '/' and '.' with '-' (/Users/bob/.claude -> -Users-bob--claude).
    return projects_root / re.sub(r"[/.]", "-", cwd)


def _last_substantive(path: Path) -> dict | None:
    """Last assistant/user entry; trailing metadata (mode, last-prompt,
    turn_duration) does not count as session activity."""
    last: dict | None = None
    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if entry.get("type") in ("assistant", "user"):
                    last = entry
    except OSError:
        return None
    return last


def _entry_text(entry: dict) -> str:
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def _entry_ts(entry: dict) -> datetime:
    raw = entry.get("timestamp")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _reset_epoch(text: str, anchor: datetime) -> int | None:
    """Reset time from the banner text, anchored to when the error was
    logged (the reset is always within the rolling window of the error, so
    "next occurrence after the anchor" is exact). None == stale record."""
    now = time.time()
    match = RESET_TIME.search(text)
    if match is None:
        if now - anchor.timestamp() > FALLBACK_MAX_AGE_SECS:
            return None
        return int(now) + FALLBACK_WAIT_SECS
    hour = int(match.group(1)) % 12
    if match.group(3).lower() == "pm":
        hour += 12
    minute = int(match.group(2) or 0)
    tz = None
    if match.group(4):
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(match.group(4).strip())
        except Exception:
            tz = None  # unknown zone name -> system local
    local_anchor = anchor.astimezone(tz)
    candidate = local_anchor.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local_anchor:
        candidate += timedelta(days=1)
    epoch = int(candidate.timestamp())
    if now > epoch + GRACE_SECS:
        return None
    return epoch


def detect(cwd: str, projects_root: Path = DEFAULT_PROJECTS_ROOT) -> int | None:
    """Reset epoch if the newest transcript for cwd is limit-stuck, else None."""
    project = _project_dir(cwd, Path(projects_root))
    try:
        newest = max(project.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    except (ValueError, OSError):
        return None
    entry = _last_substantive(newest)
    if (
        entry is None
        or entry.get("type") != "assistant"
        or not entry.get("isApiErrorMessage")
    ):
        return None
    text = _entry_text(entry)
    if not LIMIT_TEXT.search(text):
        return None
    return _reset_epoch(text, _entry_ts(entry))


def _rejected_reset(tail: str) -> int | None:
    """Reset epoch from the tail's last rejected rate_limit_event, else None."""
    epoch = None
    for line in tail.splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") != "rate_limit_event":
            continue
        info = entry.get("rate_limit_info", {})
        if info.get("status") == "rejected" and isinstance(info.get("resetsAt"), int):
            epoch = info["resetsAt"]
    if epoch is not None and time.time() > epoch + GRACE_SECS:
        return None  # reset already passed -> stale record, not a live limit
    return epoch


def detect_from_log(path: Path) -> int | None:
    """Reset epoch if the session log's tail shows a live limit, else None.

    Only the tail is consulted: a limit-hit `-p` run ENDS with the banner,
    while a healthy run ends with its hand-off text — an early, historical
    mention of limits in a long log must not read as a live limit. A
    rejected rate_limit_event's `resetsAt` epoch wins; the prose banner is
    the fallback, with the file's mtime anchoring the reset parse (the log
    stops being written the moment the session exits).
    """
    try:
        stat = path.stat()
        with open(path, "rb") as fh:
            if stat.st_size > TAIL_BYTES:
                fh.seek(stat.st_size - TAIL_BYTES)
            tail = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    epoch = _rejected_reset(tail)
    if epoch is not None:
        return epoch
    if not LIMIT_TEXT.search(tail):
        return None
    anchor = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    return _reset_epoch(tail, anchor)


def wait_decision(
    reset_epoch: int,
    now: float | None = None,
    max_wait_secs: int = DEFAULT_MAX_WAIT_SECS,
) -> int | None:
    """Seconds to sleep before relaunching, or None when the reset is
    beyond the wait cap (the loop's died branch).

    The wrapper's branch-5 arithmetic verbatim: reset − now + 120s
    margin, floored at 60s, honored only up to the cap.
    """
    if now is None:
        now = time.time()
    wait = int(reset_epoch - now) + RELAUNCH_MARGIN_SECS
    wait = max(wait, MIN_WAIT_SECS)
    if wait <= max_wait_secs:
        return wait
    return None


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=None)
    parser.add_argument("cwd", nargs="?", default=None)
    parser.add_argument("projects_root", nargs="?", default=None)
    args = parser.parse_args(argv)
    if args.log is None and args.cwd is None:
        sys.stderr.write(
            "usage: detect_usage_limit.py [--log PATH] <cwd> [projects_root]\n",
        )
        return 1
    epoch = None
    if args.log is not None:
        epoch = detect_from_log(args.log)
    if epoch is None and args.cwd is not None:
        root = Path(args.projects_root) if args.projects_root else DEFAULT_PROJECTS_ROOT
        epoch = detect(args.cwd, projects_root=root)
    if epoch is None:
        return 1
    print(epoch)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
