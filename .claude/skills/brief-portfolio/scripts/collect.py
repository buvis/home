#!/usr/bin/env python3
"""Collect portfolio state from gita-registered repos into ~/.claude/portfolio-brief/data.json.

Deterministic gathering only: GitHub API via gh CLI + local git. No LLM here.
Usage: collect.py [--days N] [--no-fetch] [--out DIR]
"""
import argparse
import csv
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

GITA_CSV = Path.home() / ".config/gita/repos.csv"
REMOTE_RE = re.compile(r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?/?$")
MAX_COMMITS = 200
DIGEST_COMMITS = 50


def run(cmd, cwd=None, timeout=120):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} {cmd[1] if len(cmd) > 1 else ''}: {r.stderr.strip()[:300]}")
    return r.stdout


def gh_json(path):
    return json.loads(run(["gh", "api", path]) or "null")


def iso_day(s):
    return s[:10] if s else None


def repo_slug(path):
    url = run(["git", "remote", "get-url", "origin"], cwd=path).strip()
    m = REMOTE_RE.search(url)
    if not m:
        raise RuntimeError(f"not a github remote: {url}")
    return m.group(1), m.group(2)


def collect_commits(path, branch, days):
    out = run(["git", "log", f"origin/{branch}", f"--since={days} days ago",
               f"--max-count={MAX_COMMITS}", "--date=short",
               "--pretty=%h\x1f%ad\x1f%an\x1f%s"], cwd=path)
    return [dict(zip(("sha", "date", "author", "subject"), line.split("\x1f")))
            for line in out.splitlines() if "\x1f" in line]


def collect_releases(owner, name, path, branch):
    rels = [{"tag": r["tag_name"], "name": r.get("name") or r["tag_name"],
             "date": iso_day(r.get("published_at")),
             "prerelease": r.get("prerelease", False)}
            for r in gh_json(f"repos/{owner}/{name}/releases?per_page=5")
            if not r.get("draft")]
    last_tag = rels[0]["tag"] if rels else None
    if not last_tag:
        try:
            last_tag = run(["git", "describe", "--tags", "--abbrev=0", f"origin/{branch}"],
                           cwd=path).strip() or None
        except RuntimeError:
            last_tag = None
    unreleased = None
    if last_tag:
        try:
            unreleased = int(run(["git", "rev-list", "--count",
                                  f"{last_tag}..origin/{branch}"], cwd=path).strip())
        except RuntimeError:
            pass
    return rels, last_tag, unreleased


def collect_issues(owner, name):
    items = gh_json(f"repos/{owner}/{name}/issues?state=open&per_page=100")
    return [{"number": i["number"], "title": i["title"],
             "created": iso_day(i["created_at"]),
             "labels": [l["name"] for l in i.get("labels", [])],
             "comments": i.get("comments", 0)}
            for i in items if "pull_request" not in i]


def collect_prs(owner, name):
    out = run(["gh", "pr", "list", "-R", f"{owner}/{name}", "--limit", "50", "--json",
               "number,title,author,isDraft,createdAt,reviewDecision,labels"])
    return [{"number": p["number"], "title": p["title"],
             "author": p["author"]["login"] if p.get("author") else "?",
             "created": iso_day(p["createdAt"]), "draft": p["isDraft"],
             "review": p.get("reviewDecision") or "",
             "labels": [l["name"] for l in p.get("labels", [])]}
            for p in json.loads(out)]


def collect_ci(owner, name, branch):
    try:
        runs = gh_json(f"repos/{owner}/{name}/actions/runs?branch={branch}&per_page=20")["workflow_runs"]
    except RuntimeError:
        return []  # Actions disabled
    latest = {}
    for r in runs:  # API returns newest first
        latest.setdefault(r["name"], {
            "workflow": r["name"], "status": r["status"],
            "conclusion": r.get("conclusion"), "url": r["html_url"],
            "date": iso_day(r["created_at"])})
    return list(latest.values())


def collect_prds(path):
    base = Path(path) / "dev/local/prds"
    def titles(sub):
        out = []
        for f in sorted((base / sub).glob("*.md")) if (base / sub).is_dir() else []:
            first = next((l[2:].strip() for l in f.read_text(errors="replace").splitlines()
                          if l.startswith("# ")), f.stem)
            out.append(first)
        return out
    return {"backlog": titles("backlog"), "wip": titles("wip"),
            "done_count": len(titles("done"))}


def collect_local(path, branch):
    dirty = len([l for l in run(["git", "status", "--porcelain"], cwd=path).splitlines() if l])
    cur = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path).strip()
    ahead = behind = 0
    try:
        b, a = run(["git", "rev-list", "--left-right", "--count",
                    f"origin/{branch}...HEAD"], cwd=path).split()
        ahead, behind = int(a), int(b)
    except (RuntimeError, ValueError):
        pass
    stashes = len(run(["git", "stash", "list"], cwd=path).splitlines())
    return {"branch": cur, "dirty": dirty, "ahead": ahead, "behind": behind,
            "stashes": stashes}


def collect_repo(path, days, fetch):
    errors = []
    owner, name = repo_slug(path)
    repo = {"owner": owner, "name": name, "org": owner, "path": path, "errors": errors}
    if fetch:
        try:
            run(["git", "fetch", "--quiet", "origin"], cwd=path, timeout=180)
        except RuntimeError as e:
            errors.append(f"fetch: {e}")
    try:
        meta = gh_json(f"repos/{owner}/{name}")
        repo.update(description=meta.get("description") or "",
                    visibility=meta.get("visibility", "public"),
                    language=meta.get("language") or "",
                    default_branch=meta["default_branch"],
                    stars=meta.get("stargazers_count", 0),
                    pushed_at=iso_day(meta.get("pushed_at")))
    except (RuntimeError, KeyError) as e:
        errors.append(f"meta: {e}")
        return repo
    branch = repo["default_branch"]
    for key, fn in [("commits", lambda: collect_commits(path, branch, days)),
                    ("issues", lambda: collect_issues(owner, name)),
                    ("prs", lambda: collect_prs(owner, name)),
                    ("ci", lambda: collect_ci(owner, name, branch)),
                    ("prds", lambda: collect_prds(path)),
                    ("local", lambda: collect_local(path, branch))]:
        try:
            repo[key] = fn()
        except Exception as e:
            repo["errors"].append(f"{key}: {e}")
    try:
        repo["releases"], repo["last_tag"], repo["unreleased_commits"] = \
            collect_releases(owner, name, path, branch)
    except Exception as e:
        repo["errors"].append(f"releases: {e}")
    return repo


def write_digest(repos, out):
    lines = []
    for r in sorted(repos, key=lambda r: f"{r['owner']}/{r['name']}"):
        commits = r.get("commits", [])
        if not commits:
            continue
        lines.append(f"## {r['owner']}/{r['name']}")
        lines += [f"{c['sha']} {c['date']} {c['subject']}" for c in commits[:DIGEST_COMMITS]]
        if len(commits) > DIGEST_COMMITS:
            lines.append(f"... and {len(commits) - DIGEST_COMMITS} more commits")
        lines.append("")
    out.write_text("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--out", default=str(Path.home() / ".claude/portfolio-brief"))
    args = ap.parse_args()

    paths = [row[0] for row in csv.reader(GITA_CSV.open()) if row and row[0].strip()]
    paths = [p for p in paths if (Path(p) / ".git").exists()]
    if not paths:
        sys.exit("no repos found in gita registry")

    print(f"collecting {len(paths)} repos (days={args.days}, fetch={not args.no_fetch})",
          file=sys.stderr)
    with ThreadPoolExecutor(max_workers=8) as ex:
        repos = list(ex.map(lambda p: collect_repo(p, args.days, not args.no_fetch), paths))

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    data = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "since_days": args.days, "repos": repos}
    (outdir / "data.json").write_text(json.dumps(data, indent=1))
    write_digest(repos, outdir / "commits-digest.md")

    failed = [(r["owner"] + "/" + r["name"], r["errors"]) for r in repos if r["errors"]]
    for slug, errs in failed:
        print(f"WARN {slug}: {'; '.join(errs)}", file=sys.stderr)
    print(f"wrote {outdir / 'data.json'} and {outdir / 'commits-digest.md'}; "
          f"{len(repos)} repos, {len(failed)} with warnings")


if __name__ == "__main__":
    main()
