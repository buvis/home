#!/usr/bin/env python3
"""Move untracked repo debris into dev/local/.trash/<date>/ with a manifest.

Same trash and manifest convention as purge-devlocal (date, rule, original,
trash path in .trash/manifest.tsv), so its 30-day empty-trash pass collects
brush moves too. Refuses tracked files, anything under dev/local (important
local-only support material owned by purge-devlocal), docs, secrets, paths
outside the repo, and anything fresher than --min-age-days.
Restore: mv the file back per the manifest line.
"""

from __future__ import annotations

import argparse
import datetime
import fnmatch
import json
import shutil
import subprocess
import sys
from pathlib import Path

PROTECT_SUFFIXES = (".md", ".rst", ".txt", ".adoc")
PROTECT_PREFIXES = ("docs/", "doc/", "dev/local/", ".git/")
PROTECT_GLOBS = (".env*", "*.pem", "*.key", "id_rsa*", "id_ed25519*",
                 "readme*", "license*", "changelog*")


def repo_root(start: Path) -> Path:
    p = subprocess.run(["git", "-C", str(start), "rev-parse",
                        "--show-toplevel"],
                       capture_output=True, text=True, timeout=15)
    if p.returncode != 0:
        raise SystemExit(f"not a git work-tree: {p.stderr.strip()}")
    return Path(p.stdout.strip())


def load_tracked(root: Path) -> set[str]:
    p = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                       capture_output=True, text=True, timeout=30)
    return set(filter(None, p.stdout.split("\0")))


def newest_mtime(p: Path) -> float:
    if p.is_file():
        return p.stat().st_mtime
    times = [f.stat().st_mtime for f in p.rglob("*") if f.is_file()]
    return max(times, default=p.stat().st_mtime)


def veto_reason(rel: str, p: Path, tracked: set[str],
                min_age_days: int) -> str | None:
    if not p.exists():
        return "missing"
    if rel in tracked or any(t.startswith(rel + "/") for t in tracked):
        return "tracked (use git rm via a reviewed commit instead)"
    if rel.startswith(PROTECT_PREFIXES):
        return "protected path (dev/local, docs, .git)"
    if Path(rel).suffix in PROTECT_SUFFIXES:
        return "documentation suffix - never auto-trashed"
    if any(fnmatch.fnmatch(Path(rel).name.lower(), g) for g in PROTECT_GLOBS):
        return "protected name"
    age = (datetime.datetime.now().timestamp() - newest_mtime(p)) / 86400
    if age < min_age_days:
        return f"too fresh ({age:.1f}d < {min_age_days}d)"
    return None


def relocate(root: Path, rel: str, date: str) -> str:
    dest = root / "dev/local/.trash" / date / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        ts = int(datetime.datetime.now().timestamp())
        dest = dest.with_name(f"{dest.name}.dup{ts}")
    shutil.move(str(root / rel), str(dest))
    return str(dest.relative_to(root))


def note_manifest(root: Path, date: str, rule: str, rel: str,
                  trash_rel: str) -> None:
    manifest = root / "dev/local/.trash/manifest.tsv"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("a", encoding="utf-8") as fh:
        fh.write(f"{date}\t{rule}\t{rel}\t{trash_rel}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--rule", default="brush-junk")
    ap.add_argument("--min-age-days", type=int, default=3)
    ap.add_argument("paths", nargs="+", help="repo-relative paths to trash")
    args = ap.parse_args()

    root = repo_root(Path(args.repo).resolve())
    tracked = load_tracked(root)
    date = datetime.date.today().isoformat()
    moved, refused = [], []
    for raw in args.paths:
        rel = raw.strip("/")
        p = (root / rel).resolve()
        if not p.is_relative_to(root):
            refused.append({"path": rel, "reason": "outside repo"})
            continue
        reason = veto_reason(rel, p, tracked, args.min_age_days)
        if reason:
            refused.append({"path": rel, "reason": reason})
            continue
        trash_rel = relocate(root, rel, date)
        note_manifest(root, date, args.rule, rel, trash_rel)
        moved.append({"path": rel, "trash": trash_rel})
    print(json.dumps({"moved": moved, "refused": refused}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
