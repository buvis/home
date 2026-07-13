#!/usr/bin/env python3
"""Collect read-only git hygiene facts for the brush skill; prints JSON.

Only mutation: the squash-merge probe writes a dangling commit object
(git commit-tree, the git-delete-squashed trick); gc removes it later.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

TIMEOUT = 30
GREP_CAP = 30
SQUASH_CAP = 20

OS_JUNK = (".DS_Store", "Thumbs.db", "desktop.ini")
JUNK_FILES = (
    "*.log", "*.tmp", "*.temp", "*.swp", "*.swo", "*~", "*.orig", "*.rej",
    "*.bak", "*.pyc", "*.pyo", "nohup.out", "npm-debug.log*",
    "yarn-error.log*", "core", "core.[0-9]*", "*.pid", ".coverage",
    "coverage.xml", "=", "-", "*.stackdump",
)
JUNK_DIRS = (
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    "htmlcov", ".ipynb_checkpoints",
)
IGNORE_GAP_DIRS = ("node_modules", "target", "dist", "build", ".venv", "venv")
SCRATCH = ("debug_*", "scratch*", "tmp_*", "test.py", "test.sh", "out.txt")
DOC_SUFFIXES = (".md", ".rst", ".txt", ".adoc")
DOC_NAMES = ("license", "readme", "changelog", "notice", "authors", "todo")
SECRETS = (".env*", "*.pem", "*.key", "id_rsa*", "id_ed25519*", "*.p12",
           "*.keystore")


def git_out(root: Path, *args: str, ok_rc: tuple = (0,)) -> str:
    p = subprocess.run(["git", "-C", str(root), *args],
                       capture_output=True, text=True, timeout=TIMEOUT)
    if p.returncode not in ok_rc:
        raise RuntimeError(
            f"git {' '.join(args)} rc={p.returncode}: {p.stderr.strip()[:200]}")
    return p.stdout


def git_rc(root: Path, *args: str) -> int:
    p = subprocess.run(["git", "-C", str(root), *args],
                       capture_output=True, text=True, timeout=TIMEOUT)
    return p.returncode


def gather_repo_ctx(start: Path) -> dict:
    ctx: dict = {"refusals": []}
    try:
        top = git_out(start, "rev-parse", "--show-toplevel").strip()
    except (RuntimeError, subprocess.SubprocessError) as e:
        return {"refusals": [f"not a git work-tree: {e}"]}
    root = Path(top)
    git_dir = git_out(start, "rev-parse", "--absolute-git-dir").strip()
    if git_dir.rstrip("/").endswith("/.buvis") or root == Path.home():
        ctx["refusals"].append("buvis home work-tree: brush refuses to run here")
    ctx.update(root=str(root), git_dir=git_dir,
               head=git_out(root, "rev-parse", "HEAD").strip()[:12],
               branch=git_out(root, "branch", "--show-current").strip() or None)
    ctx["autopilot_live"] = subprocess.run(
        ["pgrep", "-f", "autoclaude"], capture_output=True).returncode == 0
    ops = [m for m in ("rebase-merge", "rebase-apply", "MERGE_HEAD",
                       "CHERRY_PICK_HEAD", "BISECT_LOG", "REVERT_HEAD")
           if (Path(git_dir) / m).exists()]
    ctx["in_progress_op"] = ops or None
    return ctx


def detect_default_branch(root: Path) -> str:
    if git_rc(root, "show-ref", "--verify", "-q", "refs/heads/master") == 0:
        return "master"
    head = git_out(root, "symbolic-ref", "refs/remotes/origin/HEAD",
                   ok_rc=(0, 1, 128)).strip()
    if head:
        return head.rsplit("/", 1)[-1]
    if git_rc(root, "show-ref", "--verify", "-q", "refs/heads/main") == 0:
        return "main"
    return git_out(root, "branch", "--show-current").strip()


def classify_path(rel: str) -> str:
    """Order matters: protective classes win before junk classes."""
    parts = rel.split("/")
    name = parts[-1]
    if rel.startswith("dev/local/"):
        return "devlocal"  # kept local on purpose; purge-devlocal owns it
    if any(fnmatch.fnmatch(name, g) for g in SECRETS):
        return "secret"
    if any(seg in JUNK_DIRS for seg in parts[:-1]) or name in JUNK_DIRS:
        return "junk-dir"
    if name in OS_JUNK:
        return "os-junk"
    if parts[0] in ("docs", "doc") or name.lower().startswith(DOC_NAMES) \
            or Path(name).suffix in DOC_SUFFIXES:
        return "doc"
    if parts[0] in IGNORE_GAP_DIRS:
        return "heavy"
    if any(fnmatch.fnmatch(name, g) for g in JUNK_FILES):
        return "junk"
    if any(fnmatch.fnmatch(name.lower(), g) for g in SCRATCH) \
            and len(parts) <= 2:
        return "scratch"
    return "other"  # untracked is not disposable: kept, only counted


def is_referenced(root: Path, name: str) -> bool | None:
    """True if any tracked file mentions this basename (git grep)."""
    rc = git_rc(root, "grep", "-l", "-F", "--", name)
    return rc == 0 if rc in (0, 1) else None


def stat_entry(root: Path, rel: str, cls: str) -> dict:
    p = root / rel
    try:
        st = p.stat()
        age = int((time.time() - st.st_mtime) // 86400)
        size = st.st_size if p.is_file() else None
    except OSError:
        age, size = None, None
    return {"path": rel, "class": cls, "age_days": age, "size": size}


def gather_untracked(root: Path, fast: bool) -> dict:
    raw = git_out(root, "ls-files", "--others", "--exclude-standard", "-z")
    items: list[dict] = []
    counts: dict = {}
    heavy: set = set()
    junk_dir_seen: set = set()
    greps = 0
    for rel in filter(None, raw.split("\0")):
        cls = classify_path(rel)
        counts[cls] = counts.get(cls, 0) + 1
        if cls == "heavy":
            heavy.add(rel.split("/")[0])
            continue
        if cls in ("devlocal", "doc", "other"):
            continue  # keep by default; never candidates
        if cls == "junk-dir":  # collapse to the topmost junk dir
            parts = rel.split("/")
            idx = next(i for i, s in enumerate(parts) if s in JUNK_DIRS)
            rel = "/".join(parts[:idx + 1])
            if rel in junk_dir_seen:
                continue
            junk_dir_seen.add(rel)
        entry = stat_entry(root, rel, cls)
        wants_grep = cls == "scratch" or Path(rel).suffix in (
            ".py", ".sh", ".js", ".ts")
        if not fast and wants_grep and greps < GREP_CAP:
            greps += 1
            entry["referenced"] = is_referenced(root, Path(rel).name)
        items.append(entry)
    return {"counts": counts, "candidates": items[:200],
            "heavy_dirs": sorted(heavy)}


def probe_squash(root: Path, default: str, branch: str) -> bool | None:
    try:
        mb = git_out(root, "merge-base", default, branch).strip()
        tree = git_out(root, "rev-parse", f"{branch}^{{tree}}").strip()
        tmp = git_out(root, "commit-tree", tree, "-p", mb, "-m",
                      "brush-squash-probe").strip()
        return git_out(root, "cherry", default, tmp).startswith("-")
    except (RuntimeError, subprocess.SubprocessError):
        return None


def gather_branches(root: Path, default: str, fast: bool) -> list[dict]:
    fmt = ("%(refname:short)|%(objectname:short)|%(upstream:track)|"
           "%(committerdate:unix)")
    current = git_out(root, "branch", "--show-current").strip()
    out: list[dict] = []
    probes = 0
    for line in git_out(root, "for-each-ref", "refs/heads",
                        f"--format={fmt}").splitlines():
        name, sha, track, cdate = line.split("|")
        if name in (current, default):
            continue
        b = {"name": name, "sha": sha, "gone": track == "[gone]",
             "no_upstream": track == "",
             "age_days": int((time.time() - int(cdate)) // 86400),
             "merged": git_rc(root, "merge-base", "--is-ancestor",
                              sha, default) == 0}
        try:
            lr = git_out(root, "rev-list", "--left-right", "--count",
                         f"{default}...{name}").split()
            b["behind"], b["ahead"] = int(lr[0]), int(lr[1])
        except (RuntimeError, subprocess.SubprocessError, ValueError):
            b["behind"] = b["ahead"] = None
        if not fast and not b["merged"] and b["gone"] and probes < SQUASH_CAP:
            probes += 1
            b["squash_merged"] = probe_squash(root, default, name)
        out.append(b)
    return out


def gather_prs(root: Path) -> list[dict] | None:
    if not shutil.which("gh"):
        return None
    try:
        p = subprocess.run(["gh", "pr", "list", "--json",
                            "number,headRefName,state", "--limit", "100"],
                           capture_output=True, text=True, timeout=15,
                           cwd=root)
        return json.loads(p.stdout) if p.returncode == 0 else None
    except (subprocess.SubprocessError, json.JSONDecodeError):
        return None


def gather_worktrees(root: Path, default: str, fast: bool) -> list[dict]:
    blocks = git_out(root, "worktree", "list", "--porcelain").split("\n\n")
    out = []
    for block in filter(None, (b.strip() for b in blocks)):
        wt: dict = {"prunable": False, "locked": False}
        for line in block.splitlines():
            key, _, val = line.partition(" ")
            if key == "worktree":
                wt["path"] = val
            elif key == "branch":
                wt["branch"] = val.rsplit("/", 1)[-1]
            elif key == "prunable":
                wt["prunable"] = True
            elif key == "locked":
                wt["locked"] = True
        if wt.get("path") == str(root):
            continue
        wtp = Path(wt.get("path", ""))
        if not fast and wtp.is_dir():
            wt["dirty"] = bool(git_out(wtp, "status", "--porcelain").strip())
        if "branch" in wt:
            wt["merged"] = git_rc(root, "merge-base", "--is-ancestor",
                                  wt["branch"], default) == 0
        out.append(wt)
    return out


def gather_stashes(root: Path) -> list[dict]:
    out = []
    for line in git_out(root, "stash", "list",
                        "--format=%gd|%ct|%gs").splitlines():
        ref, ct, msg = line.split("|", 2)
        out.append({"ref": ref,
                    "age_days": int((time.time() - int(ct)) // 86400),
                    "msg": msg[:80]})
    return out


def gather_sizes(root: Path, fast: bool) -> dict:
    stats = {}
    for line in git_out(root, "count-objects", "-vH").splitlines():
        k, _, v = line.partition(": ")
        stats[k] = v.strip()
    big = []
    if not fast:
        for rel in filter(None, git_out(root, "ls-files", "-z").split("\0")):
            try:
                size = (root / rel).stat().st_size
            except OSError:
                continue
            if size > 5 * 1024 * 1024:
                big.append({"path": rel, "mb": round(size / 1048576, 1)})
        big.sort(key=lambda x: -x["mb"])
    return {"count_objects": stats, "big_tracked": big[:10]}


def probe_gitignore(root: Path) -> list[str]:
    probes = [".DS_Store"]
    if git_out(root, "ls-files", "--", "*.py")[:1]:
        probes += ["__pycache__/x.pyc", "x.pyc", ".pytest_cache/x"]
    if (root / "package.json").exists():
        probes.append("node_modules/x")
    if (root / "Cargo.toml").exists():
        probes.append("target/debug/x")
    if (root / "dev/local").is_dir():
        probes.append("dev/local/x")
    return [p for p in probes if git_rc(root, "check-ignore", "-q", p) != 0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--fast", action="store_true",
                    help="skip squash probes, greps, size and dirty scans")
    args = ap.parse_args()

    facts = gather_repo_ctx(Path(args.repo).resolve())
    if facts["refusals"]:
        print(json.dumps(facts, indent=2))
        return 1
    root = Path(facts["root"])
    facts["generated_unix"] = int(time.time())
    warnings: list[str] = []
    default = detect_default_branch(root)
    facts["default_branch"] = default

    sections = {
        "dirty": lambda: [l for l in git_out(
            root, "status", "--porcelain").splitlines()
            if not l.startswith("??")][:50],
        "untracked": lambda: gather_untracked(root, args.fast),
        "tracked_junk": lambda: list(filter(None, git_out(
            root, "ls-files", "-z", "--", ".DS_Store", "**/.DS_Store",
            "Thumbs.db", "**/Thumbs.db", "*.pyc").split("\0")))[:50],
        "branches": lambda: gather_branches(root, default, args.fast),
        "open_prs": lambda: gather_prs(root),
        "worktrees": lambda: gather_worktrees(root, default, args.fast),
        "stashes": lambda: gather_stashes(root),
        "sizes": lambda: gather_sizes(root, args.fast),
        "gitignore_missing": lambda: probe_gitignore(root),
        "submodules": lambda: git_out(root, "submodule",
                                      "status").splitlines(),
        "maintenance_registered": lambda: str(root) in git_out(
            root, "config", "--global", "--get-all", "maintenance.repo",
            ok_rc=(0, 1)),
    }
    for key, fn in sections.items():
        try:
            facts[key] = fn()
        except (RuntimeError, subprocess.SubprocessError, ValueError) as e:
            warnings.append(f"{key}: {e}")
            facts[key] = None
    facts["warnings"] = warnings
    print(json.dumps(facts, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
