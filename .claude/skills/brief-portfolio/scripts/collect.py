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
from datetime import datetime, timedelta, timezone
from pathlib import Path

GITA_CSV = Path.home() / ".config/gita/repos.csv"
REMOTE_RE = re.compile(r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?/?$")
BRUSH_RE = re.compile(r"^\s*-\s*generated:\s*(\d{4}-\d{2}-\d{2})")
MAX_COMMITS = 200
DIGEST_COMMITS = 50
MAX_BRANCHES = 50
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def run(cmd, cwd=None, timeout=120):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} {cmd[1] if len(cmd) > 1 else ''}: {r.stderr.strip()[:300]}")
    return r.stdout


def gh_json(path):
    return json.loads(run(["gh", "api", path]) or "null")


def iso_day(s):
    return s[:10] if s else None


def days_since_mtime(f):
    return max(0, int((datetime.now().timestamp() - f.stat().st_mtime) // 86400))


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
             "comments": i.get("comments", 0),
             "reactions": (i.get("reactions") or {}).get("total_count", 0),
             "milestone": ({"title": i["milestone"]["title"],
                            "due": iso_day(i["milestone"].get("due_on"))}
                           if i.get("milestone") else None)}
            for i in items if "pull_request" not in i]


FAIL_CHECKS = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}
PASS_CHECKS = {"SUCCESS", "NEUTRAL", "SKIPPED"}


def checks_state(rollup):
    """Fold a PR's statusCheckRollup into passing|failing|pending ('' = no checks)."""
    if not rollup:
        return ""
    states = [(c.get("conclusion") or c.get("state") or "").upper() for c in rollup]
    if any(s in FAIL_CHECKS for s in states):
        return "failing"
    if all(s in PASS_CHECKS for s in states):
        return "passing"
    return "pending"


def collect_prs(owner, name):
    out = run(["gh", "pr", "list", "-R", f"{owner}/{name}", "--limit", "50", "--json",
               "number,title,author,isDraft,createdAt,reviewDecision,labels,statusCheckRollup"])
    return [{"number": p["number"], "title": p["title"],
             "author": p["author"]["login"] if p.get("author") else "?",
             "created": iso_day(p["createdAt"]), "draft": p["isDraft"],
             "review": p.get("reviewDecision") or "",
             "checks": checks_state(p.get("statusCheckRollup")),
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


def _gh_alerts(path):
    """Alert endpoints 403/404 on repos where the feature is off — that's absence,
    not an error. Anything else propagates into the repo's errors field."""
    try:
        return gh_json(path) or []
    except RuntimeError as e:
        if re.search(r"HTTP (403|404)", str(e)):
            return []
        raise


def collect_security(owner, name):
    alerts = [{"kind": "dependabot",
               "severity": (a.get("security_vulnerability") or {}).get("severity")
               or a["security_advisory"]["severity"],
               "title": f'{a["dependency"]["package"]["name"]}: {a["security_advisory"]["summary"]}',
               "url": a["html_url"]}
              for a in _gh_alerts(f"repos/{owner}/{name}/dependabot/alerts?state=open&per_page=100")]
    alerts += [{"kind": "secret", "severity": "critical",
                "title": f'leaked secret: {a.get("secret_type_display_name") or a.get("secret_type") or "?"}',
                "url": a.get("html_url") or ""}
               for a in _gh_alerts(f"repos/{owner}/{name}/secret-scanning/alerts?state=open&per_page=100")]
    return sorted(alerts, key=lambda a: SEV_ORDER.get(a["severity"], 9))


def collect_branches(path, branch):
    merged = set(run(["git", "branch", "-a", "--merged", f"origin/{branch}",
                      "--format=%(refname:short)"], cwd=path).split())
    current = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path).strip()
    # %(refname:short) renders origin/HEAD as bare "origin"
    keep = {f"origin/{branch}", "origin/HEAD", "origin", branch, current}
    out = []
    for ref in ("refs/remotes/origin", "refs/heads"):
        for line in run(["git", "for-each-ref", ref,
                         "--format=%(refname:short)\x1f%(committerdate:short)"],
                        cwd=path).splitlines():
            name, date = line.split("\x1f")
            if name in keep:
                continue
            out.append({"name": name, "date": date, "merged": name in merged})
    worktrees = [l[9:] for l in run(["git", "worktree", "list", "--porcelain"],
                                    cwd=path).splitlines() if l.startswith("worktree ")][1:]
    return {"stray": sorted(out, key=lambda b: b["date"])[:MAX_BRANCHES],
            "worktrees": worktrees}


def collect_prds(path):
    base = Path(path) / "dev/local/prds"
    def entries(sub):
        out = []
        for f in sorted((base / sub).glob("*.md")) if (base / sub).is_dir() else []:
            first = next((l[2:].strip() for l in f.read_text(errors="replace").splitlines()
                          if l.startswith("# ")), f.stem)
            out.append({"title": first, "idle_days": days_since_mtime(f)})
        return out
    return {"backlog": [e["title"] for e in entries("backlog")], "wip": entries("wip"),
            "done_count": len(entries("done"))}


def collect_changelog(path):
    """True/False = [Unreleased] section has/lacks bullet entries; None = no CHANGELOG.md."""
    f = Path(path) / "CHANGELOG.md"
    if not f.is_file():
        return None
    in_unreleased = False
    for line in f.read_text(errors="replace").splitlines():
        if line.startswith("## "):
            in_unreleased = "unreleased" in line.lower()
        elif in_unreleased and line.lstrip().startswith(("- ", "* ")):
            return True
    return False


def collect_brush(path):
    """ISO day of the last brush hygiene run (report's `generated:` line); None = never."""
    f = Path(path) / "dev/local/audit-results/brush-report.md"
    if not f.is_file():
        return None
    for line in f.read_text(errors="replace").splitlines():
        m = BRUSH_RE.match(line)
        if m:
            return m.group(1)
    return None


def collect_claude_skill_adherence(base=None):
    """Last-30-day skill-invocation summary from ~/.claude/metrics/skills.jsonl
    (PRD 00086 R2, numerator-only). Returns {count, distinct, top} or None when
    there is no metrics file yet. `ts` rows are ISO-8601 UTC (track_skills.py)."""
    f = Path(base) if base else Path.home() / ".claude/metrics/skills.jsonl"
    if not f.is_file():
        return None
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    per_skill = {}
    try:
        for line in f.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or row.get("ts", "") < cutoff:
                continue
            skill = row.get("skill")
            if skill:
                per_skill[skill] = per_skill.get(skill, 0) + 1
    except OSError:
        return None
    if not per_skill:
        return {"count": 0, "distinct": 0, "top": []}
    top = sorted(per_skill.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    return {"count": sum(per_skill.values()), "distinct": len(per_skill),
            "top": [{"skill": s, "n": n} for s, n in top]}


def collect_claude_maintenance(base=None):
    """ISO day of the newest entry under ~/.claude/dev/local/audit-results/;
    None = never. mtime proxy: audit-filesystem writes no report file, so any
    audit-results artifact counts (the UI row states the imprecision)."""
    d = Path(base) if base else Path.home() / ".claude/dev/local/audit-results"
    try:
        times = [e.stat().st_mtime for e in d.iterdir()]
    except OSError:
        return None
    if not times:
        return None
    return datetime.fromtimestamp(max(times), timezone.utc).strftime("%Y-%m-%d")


def collect_external(known_slugs):
    """Open PRs involving the user outside the gita portfolio (review requests + own PRs)."""
    def search(flag):
        out = run(["gh", "search", "prs", flag, "--state=open", "--limit", "50", "--json",
                   "repository,number,title,createdAt,url,isDraft"])
        return [{"repo": p["repository"]["nameWithOwner"], "number": p["number"],
                 "title": p["title"], "created": iso_day(p["createdAt"]),
                 "url": p["url"], "draft": p["isDraft"]}
                for p in json.loads(out)
                if p["repository"]["nameWithOwner"] not in known_slugs]
    return {"review_requested": search("--review-requested=@me"),
            "authored": search("--author=@me")}


def history_counts(repo):
    l = repo.get("local") or {}
    prds = repo.get("prds") or {}
    failing = sum(1 for w in repo.get("ci", [])
                  if w.get("conclusion") in ("failure", "timed_out", "startup_failure"))
    return {"c": len(repo.get("commits", [])), "i": len(repo.get("issues", [])),
            "p": len(repo.get("prs", [])), "a": len(repo.get("security", [])),
            "f": failing, "d": l.get("dirty", 0), "ah": l.get("ahead", 0),
            "b": len(prds.get("backlog", [])), "w": len(prds.get("wip", [])),
            "s": repo.get("stars", 0), "u": repo.get("unreleased_commits") or 0}


def collect_local(path, branch):
    lines = [l for l in run(["git", "status", "--porcelain"], cwd=path).splitlines() if l]
    # ponytail: oldest mtime among dirty files approximates "dirty since"
    ages = []
    for l in lines:
        f = Path(path) / l[3:].split(" -> ")[-1].strip('"')
        if f.is_file():
            ages.append(days_since_mtime(f))
    cur = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path).strip()
    ahead = behind = 0
    try:
        b, a = run(["git", "rev-list", "--left-right", "--count",
                    f"origin/{branch}...HEAD"], cwd=path).split()
        ahead, behind = int(a), int(b)
    except (RuntimeError, ValueError):
        pass
    stashes = len(run(["git", "stash", "list"], cwd=path).splitlines())
    return {"branch": cur, "dirty": len(lines), "dirty_since_days": max(ages, default=None),
            "ahead": ahead, "behind": behind, "stashes": stashes}


def collect_repo(path, days, fetch):
    errors = []
    try:
        owner, name = repo_slug(path)
    except RuntimeError as e:
        print(f"WARN {path}: skipped ({e})", file=sys.stderr)
        return None
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
                    ("security", lambda: collect_security(owner, name)),
                    ("branches", lambda: collect_branches(path, branch)),
                    ("prds", lambda: collect_prds(path)),
                    ("local", lambda: collect_local(path, branch)),
                    ("changelog_unreleased", lambda: collect_changelog(path)),
                    ("brush_last_run", lambda: collect_brush(path))]:
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
    repos = [r for r in repos if r]

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    data = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "since_days": args.days, "repos": repos}
    known = {f'{r["owner"]}/{r["name"]}' for r in repos}
    try:
        data["external"] = collect_external(known)
    except Exception as e:
        print(f"WARN external: {e}", file=sys.stderr)
        data["external"] = {"review_requested": [], "authored": []}
    data["external"]["claude_maintenance_last"] = collect_claude_maintenance()
    data["skill_adherence"] = collect_claude_skill_adherence()

    # keep the previous snapshot for the "since last brief" diff
    data_file = outdir / "data.json"
    if data_file.exists():
        data_file.replace(outdir / "data-prev.json")
    data_file.write_text(json.dumps(data, indent=1))
    hist = {"at": data["generated_at"],
            "repos": {f'{r["owner"]}/{r["name"]}': history_counts(r) for r in repos}}
    with (outdir / "history.jsonl").open("a") as hf:
        hf.write(json.dumps(hist) + "\n")
    write_digest(repos, outdir / "commits-digest.md")

    failed = [(r["owner"] + "/" + r["name"], r["errors"]) for r in repos if r["errors"]]
    for slug, errs in failed:
        print(f"WARN {slug}: {'; '.join(errs)}", file=sys.stderr)
    print(f"wrote {outdir / 'data.json'} and {outdir / 'commits-digest.md'}; "
          f"{len(repos)} repos, {len(failed)} with warnings")


if __name__ == "__main__":
    main()
