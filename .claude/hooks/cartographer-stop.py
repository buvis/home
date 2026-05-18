"""Stop hook: detect atlas staleness after a session ends."""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))

from _lib_cartographer import append_audit, atlas_dir, project_hash


def main() -> None:
    try:
        json.loads(sys.stdin.read())

        cwd = os.getcwd()
        h, _, _ = project_hash(cwd)
        adir = atlas_dir(h)
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
        )
        if result.returncode != 0:
            append_audit({"event": "cartographer-stop", "reason": "git-error"})
            return
        commits = int(result.stdout.strip())

        now = datetime.now(timezone.utc)
        if surveyed_at.tzinfo is None:
            surveyed_at = surveyed_at.replace(tzinfo=timezone.utc)
        age_days = (now - surveyed_at).total_seconds() / 86400

        if commits >= max_commits or age_days >= max_days:
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
