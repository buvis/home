"""Stop hook: detect atlas staleness after a session ends."""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))

from _lib_cartographer import (
    append_audit,
    atlas_dir,
    is_checked,
    mark_checked,
    project_hash,
    resolve_session_key,
)

# ponytail: 14-day threshold is a guess (PRD 00049); tune from audit-atlas data
NUDGE_MAX_AGE_DAYS = 14


def maybe_nudge(data: dict, h: str, adir: Path) -> None:
    """PRD 00049 Phase A: one stderr nudge per repo-week when this session
    edited files in a repo whose atlas.md is missing or older than
    NUDGE_MAX_AGE_DAYS. The edit marker is stamped by cartographer-echo
    (namespace "survey-edits"); the throttle bucket is the ISO repo-week.
    Cost when silent: one state-file read plus an mtime stat."""
    session = resolve_session_key(data)
    if not is_checked(session, "survey-edits", h):
        return  # this session edited no files in this repo
    atlas_md = adir / "atlas.md"
    if atlas_md.exists():
        age_days = (time.time() - atlas_md.stat().st_mtime) / 86400
        if age_days <= NUDGE_MAX_AGE_DAYS:
            return
        detail = f"atlas stale ({int(age_days)} days)"
    else:
        age_days = None
        detail = "atlas missing"
    week_bucket = "week-" + datetime.now(timezone.utc).strftime("%G-W%V")
    if is_checked(week_bucket, "survey-nudge", h):
        return  # throttle: one nudge per repo per week
    mark_checked(week_bucket, "survey-nudge", h)
    print(f"[cartographer] {detail} - run /survey", file=sys.stderr)
    append_audit({
        "phase": "survey",
        "event": "stale-nudge",
        "repo": h,
        "age_days": None if age_days is None else round(age_days, 1),
    })


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())

        cwd = os.getcwd()
        h, _, _ = project_hash(cwd)
        adir = atlas_dir(h)

        maybe_nudge(data, h, adir)

        atlas_json = adir / "atlas.json"

        if not atlas_json.exists():
            append_audit({"event": "cartographer-stop", "reason": "no-atlas"})
            return

        data = json.loads(atlas_json.read_text(encoding="utf-8"))
        head_sha = data.get("head_sha")
        if head_sha is None:
            append_audit({"event": "cartographer-stop", "reason": "no-git"})
            return
        surveyed_at = datetime.fromisoformat(data["surveyed_at"])

        max_commits = 50
        max_days = 14
        staleness = data.get("staleness") or {}
        if "max_commits" in staleness:
            max_commits = staleness["max_commits"]
        if "max_days" in staleness:
            max_days = staleness["max_days"]

        result = subprocess.run(
            ["git", "rev-list", "--count", f"{head_sha}..HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,  # a hung git must not stall the Stop hook (PRD 00086 R4)
        )
        if result.returncode != 0:
            append_audit({"event": "cartographer-stop", "reason": "git-error"})
            return
        commits = int(result.stdout.strip())

        now = datetime.now(timezone.utc)
        if surveyed_at.tzinfo is None:
            surveyed_at = surveyed_at.replace(tzinfo=timezone.utc)
        age_days = (now - surveyed_at).total_seconds() / 86400

        if commits > max_commits or age_days > max_days:
            (adir / "staleness.flag").touch()
            append_audit({
                "event": "cartographer-stop",
                "reason": "stale-flag-set",
                "commits": commits,
                "age_days": age_days,
            })
        else:
            append_audit({
                "event": "cartographer-stop",
                "reason": "fresh",
                "commits": commits,
                "age_days": age_days,
            })
    except Exception:
        try:
            append_audit({"event": "cartographer-stop", "reason": "skip"})
        except Exception:
            pass


if __name__ == "__main__":
    main()
