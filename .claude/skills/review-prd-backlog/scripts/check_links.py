#!/usr/bin/env python3
"""Check working-document references for rot (PRD 00081).

Scans dev/local/**/*.md (minus .trash/) — plus the project auto-memory dir
when run in ~/.claude — for three reference kinds and verifies each resolves:

  1. explicit paths:   dev/local/..., ~/.claude/..., /Users/...
  2. PRD/discovery citations: five-digit `NNNNN-` tokens, resolved against
     dev/local/prds/** (all buckets incl. hold/) and dev/local/discovery/**
     (unlike purge_devlocal.prd_numbers, which splits live/done for GC —
     here a hold-parked PRD is still a valid citation target)
  3. memory links:     [[memory-name]], resolved against the memory dir

A line containing the literal token `link-ok:` is exempt (prose naming
intentionally-removed paths). Findings quote the citing line.

Exit codes: 0 clean, 1 dangling references or scan errors found.
"""
import argparse
import json
import re
import sys
from pathlib import Path

PATH_RE = re.compile(r"(?:~/\.claude/|/Users/|dev/local/)[\w@%+=./-]*")
PRD_RE = re.compile(r"(?<![\d/.-])(\d{5})-")
MEM_RE = re.compile(r"\[\[([\w-]+)\]\]")
WAIVER = "link-ok:"
# tokens that are patterns/placeholders, not real paths
PLACEHOLDER = re.compile(r"[*?<>{}$]|\.\.\.|NNNNN|XXXX|YYYY")


def project_memory_dir(root: Path) -> Path:
    return Path.home() / ".claude" / "projects" / re.sub(r"[/.]", "-", str(root)) / "memory"


def memory_names(mem_dir: Path) -> set[str]:
    """Set of resolvable memory names: file stems plus frontmatter `name:` slugs."""
    names: set[str] = set()
    if not mem_dir.is_dir():
        return names
    for f in mem_dir.glob("*.md"):
        names.add(f.stem)
        try:
            head = f.read_text(errors="replace")[:500]
        except OSError:
            continue
        m = re.search(r"^name:\s*(\S+)", head, re.M)
        if m:
            names.add(m.group(1))
    return names


def resolvable_numbers(root: Path) -> set[str]:
    """Five-digit citation targets: any file under prds/** or discovery/**."""
    nums: set[str] = set()
    for base in (root / "dev/local/prds", root / "dev/local/discovery"):
        if base.is_dir():
            for f in base.rglob("*"):
                m = re.match(r"(\d{5})-", f.name)
                if m:
                    nums.add(m.group(1))
    return nums


def resolve_path(token: str, root: Path) -> bool:
    if token.startswith("dev/local/"):
        p = root / token
    else:
        p = Path(token.replace("~", str(Path.home()), 1))
    return p.exists()


def scan_file(path: Path, root: Path, prds: set[str], memories: set[str]):
    findings, errors = [], []
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError as e:
        return [], [f"{path}: unreadable ({e})"]
    for ln, line in enumerate(lines, 1):
        if WAIVER in line:
            continue
        for m in PATH_RE.finditer(line):
            token = m.group(0).rstrip(".,;:!?)")
            if PLACEHOLDER.search(token) or token.rstrip("/").endswith(("dev/local", ".claude")):
                continue
            if not resolve_path(token, root):
                findings.append((path, ln, token, line.strip()))
        for m in PRD_RE.finditer(line):
            if m.group(1) not in prds:
                findings.append((path, ln, f"{m.group(1)}- (no PRD/discovery file)", line.strip()))
        for m in MEM_RE.finditer(line):
            if m.group(1) not in memories:
                findings.append((path, ln, f"[[{m.group(1)}]] (no memory)", line.strip()))
    return findings, errors


def run(root: Path):
    findings, errors = [], []
    prds = resolvable_numbers(root)
    mem_dir = project_memory_dir(root)
    memories = memory_names(mem_dir)
    sources = []
    devlocal = root / "dev/local"
    if devlocal.is_dir():
        sources += [p for p in devlocal.rglob("*.md") if ".trash" not in p.parts]
    if mem_dir.is_dir():
        sources += sorted(mem_dir.glob("*.md"))
    for src in sources:
        f, e = scan_file(src, root, prds, memories)
        findings += f
        errors += e
    return findings, errors


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", help="repo root (default cwd)")
    ap.add_argument("--json", action="store_true", help="machine output")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    findings, errors = run(root)
    if args.json:
        print(json.dumps({
            "findings": [{"file": str(f), "line": ln, "target": t, "citing_line": q}
                         for f, ln, t, q in findings],
            "scan_errors": errors,
        }, indent=2))
    else:
        for f, ln, target, quote in findings:
            print(f"{f}:{ln} -> missing {target}\n    | {quote}")
        for e in errors:
            print(f"SCAN ERROR: {e}", file=sys.stderr)
        print(f"{len(findings)} dangling, {len(errors)} scan errors")
    sys.exit(1 if findings or errors else 0)


if __name__ == "__main__":
    main()
