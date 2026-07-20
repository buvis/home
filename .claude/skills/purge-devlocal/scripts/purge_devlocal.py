#!/usr/bin/env python3
"""Trash-first GC for dev/local artifact stores.

Relevance rules (first match wins, `live` always wins):

| rule            | target                                                | action |
|-----------------|-------------------------------------------------------|--------|
| prds            | prds/**                                               | keep   |
| keeper          | capsule, decisions, cursors, assumptions, trouble...  | keep   |
| live-linked     | 5-digit PRD token found in prds/backlog|wip           | keep   |
| prd-gone        | discovery/specs/notes/walkthroughs/audit-results/     | flag   |
|                 | spikes file whose PRD is done or missing              |        |
| done-linked     | PRD token found in prds/done                          | trash  |
| missing-prd     | numbered file in designs/reviews/plans/(root)/00XXX-* | trash  |
|                 | dir whose PRD exists nowhere                          |        |
| stale-tmp       | tmp/** older than --tmp-age-days                      | trash  |
| ledger          | autopilot/ledger/** (durable outcome ledger)          | keep   |
| stale-autopilot | autopilot/** (incl. deferred/, reports/) > age-days   | trash  |
| stale-log       | root *.log/*.bak/*.tmp older than --tmp-age-days      | trash  |
| root-stray      | un-numbered root file outside KEEP_NAMES              | flag   |
| unclassified    | everything else                                       | keep   |

autopilot/deferred/** and autopilot/reports/** are NOT special-cased: they age
out under the same stale-autopilot rule as the rest of autopilot/** (only
ledger/** is exempt). Same for numbered root debris of a DONE prd - it reaches
done-linked->trash. When such files nonetheless survive a run, the cause is the
--min-age-days guard (a same-day sweep leaves them fresher than the floor) or a
live PRD token, never a classifier gap (verified 2026-07-20, PRD 00082).

Trashed reviews/*.md leave their Verdict: lines in
autopilot/ledger/review-verdicts.jsonl before the move, so review outcomes
outlive the satellite GC (2026-07-14: the quarter's eval found zero surviving
metrics or verdicts).

Nothing is unlinked: trash moves files to <store>/.trash/<date>/<relpath> and
appends to .trash/manifest.tsv. A name collision inside the day's batch (a
pre-existing dest, or a dir blocked by a same-named file from an earlier sweep)
gets a -N suffix on the shallowest colliding component, never a failed move.
Manifest readers tolerate unknown rule tags (e.g. manual-sweep rows). With
--apply, trash batches older than --empty-trash-days are deleted for good. A
--min-age-days guard vetoes any trash of freshly touched files so live batches
are never disturbed.
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

DAY = 86400
PRD_NUM = re.compile(r"(?<!\d)(\d{5})(?!\d)")
TRASH_DIR = ".trash"
KEEP_NAMES = {
    "project-capsule.md", "decisions.md", "troubleshooting.md",
    "assumptions.md", "ecc-cursor", "upstream-cursor",
}
FLAG_DIRS = {"discovery", "specs", "notes", "walkthroughs", "audit-results", "spikes"}
# ponytail: missing-prd is scoped to dirs where 5-digit tokens are PRD prefixes
# by convention; tmp/ is excluded because review-context-<epoch>-<pid> names
# false-positive on the PID. Widen only with a smarter token parser.
MISSING_SCOPE = {"designs", "reviews", "plans", "(root)"}
LOG_SUFFIXES = (".log", ".bak", ".tmp")


def find_stores(home: Path) -> dict[str, Path]:
    """Map label -> real dev/local path for every repo plus ~/.claude, deduped."""
    stores: dict[str, Path] = {}
    seen: set[str] = set()

    def add(label: str, dev_local: Path) -> None:
        real = Path(os.path.realpath(dev_local))
        if real.is_dir() and str(real) not in seen:
            seen.add(str(real))
            stores[label] = real

    src = home / "git" / "src"
    if src.is_dir():
        for host in sorted(src.iterdir()):
            if not host.is_dir():
                continue
            for org in sorted(host.iterdir()):
                if not org.is_dir():
                    continue
                for repo in sorted(org.iterdir()):
                    dl = repo / "dev" / "local"
                    if dl.is_dir() or dl.is_symlink():
                        label = f"{org.name}/{repo.name}" if host.name == "github.com" \
                            else f"{host.name}/{org.name}/{repo.name}"
                        add(label, dl)
    add("~/.claude", home / ".claude" / "dev" / "local")
    return stores


def resolve_store(path: Path) -> Path:
    """Accept a repo root or a dev/local path itself."""
    cand = path / "dev" / "local"
    if cand.is_dir() or cand.is_symlink():
        return Path(os.path.realpath(cand))
    return Path(os.path.realpath(path))


def prd_numbers(store: Path) -> tuple[set[str], set[str]]:
    """Return (live, done) PRD numbers from prds/{backlog,wip,done}."""
    live: set[str] = set()
    done: set[str] = set()
    for bucket, target in (("backlog", live), ("wip", live), ("done", done)):
        d = store / "prds" / bucket
        if not d.is_dir():
            continue
        for entry in d.iterdir():
            m = PRD_NUM.search(entry.name)
            if m:
                target.add(m.group(1))
    return live, done


def walk_store(store: Path):
    """Yield (relpath, mtime) for every file, skipping .trash."""
    for base, dirs, files in os.walk(store, followlinks=False):
        if base == str(store):
            dirs[:] = [d for d in dirs if d != TRASH_DIR]
        for fn in files:
            fp = Path(base) / fn
            try:
                st = fp.lstat()
            except OSError:
                continue
            yield fp.relative_to(store), st.st_mtime


def classify_artifact(rel: Path, mtime: float, live: set[str], done: set[str],
                      now: float, args) -> tuple[str, str]:
    """Return (action, rule); action is keep | trash | flag."""
    top = rel.parts[0] if len(rel.parts) > 1 else "(root)"
    age = (now - mtime) / DAY
    toks = set(PRD_NUM.findall(rel.as_posix()))

    if top == "prds":
        return "keep", "prds"
    if rel.name in KEEP_NAMES:
        return "keep", "keeper"
    if len(rel.parts) > 2 and rel.parts[0] == "autopilot" and rel.parts[1] == "ledger":
        return "keep", "ledger"
    if toks & live:
        return "keep", "live-linked"
    if top in FLAG_DIRS:
        if toks and (toks & done or not toks & (live | done)):
            return "flag", "prd-gone"
        return "keep", "flagdir"

    action = rule = None
    if toks & done:
        action, rule = "trash", "done-linked"
    elif toks and not toks & (live | done) \
            and (top in MISSING_SCOPE or PRD_NUM.search(top)):
        action, rule = "trash", "missing-prd"
    elif top == "tmp" and age > args.tmp_age_days:
        action, rule = "trash", "stale-tmp"
    elif top == "autopilot" and age > args.autopilot_age_days:
        action, rule = "trash", "stale-autopilot"
    elif top == "(root)" and rel.suffix in LOG_SUFFIXES and age > args.tmp_age_days:
        action, rule = "trash", "stale-log"

    if action == "trash":
        if age < args.min_age_days:
            return "keep", f"fresh:{rule}"
        return action, rule
    # Root holds named keepers only (working-documents contract): an un-numbered
    # root file outside KEEP_NAMES is a stray. Flag, never auto-trash - a new
    # keeper often lands before anyone updates KEEP_NAMES.
    if top == "(root)" and not toks:
        return "flag", "root-stray"
    return "keep", "unclassified"


VERDICT_RE = re.compile(r"^Verdict:\s*(.+)$", re.M)
REVIEWERS_RE = re.compile(r"^reviewers?:\s*(.+)$", re.M)


def harvest_review_verdicts(store: Path, rel: Path, now: float) -> None:
    """Append a trashed review file's Verdict lines to the GC-exempt ledger."""
    try:
        text = (store / rel).read_text(errors="ignore")
    except OSError:
        return
    verdicts = VERDICT_RE.findall(text)
    if not verdicts:
        return
    prd = PRD_NUM.search(rel.name)
    reviewers = REVIEWERS_RE.search(text)
    row = {
        "ts": int(now),
        "file": rel.as_posix(),
        "prd": prd.group(1) if prd else None,
        "verdicts": [v.strip() for v in verdicts],
        "reviewers": reviewers.group(1).strip() if reviewers else None,
    }
    ledger = store / "autopilot" / "ledger" / "review-verdicts.jsonl"
    try:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError as exc:
        print(f"  WARN verdict harvest failed for {rel.as_posix()}: {exc}")


def _dedup_dest(batch_root: Path, rel: Path) -> Path:
    """A trash destination that collides with nothing: not a pre-existing dest,
    and no intermediate directory blocked by an existing file. Suffixes the
    shallowest colliding path component with -2, -3, ... (e.g. a same-day
    manual-sweep file at `<batch>/00017-drain-repo` forces `00017-drain-repo-2/`
    for a later dir of that name)."""
    parts = list(rel.parts)
    for depth, base in enumerate(rel.parts):
        is_leaf = depth == len(parts) - 1
        n = 1
        while True:
            candidate = batch_root.joinpath(*parts[: depth + 1])
            # a leaf collides if anything is there; an intermediate collides only
            # when a NON-directory blocks the nest (an existing dir is reusable).
            collides = candidate.exists() if is_leaf else (
                candidate.exists() and not candidate.is_dir())
            if not collides:
                break
            n += 1
            parts[depth] = f"{base}-{n}"
    return batch_root.joinpath(*parts)


def trash_file(store: Path, rel: Path, rule: str, batch: str) -> None:
    final = _dedup_dest(store / TRASH_DIR / batch, rel)
    final.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(store / rel), str(final))
    manifest = store / TRASH_DIR / "manifest.tsv"
    with manifest.open("a") as fh:
        fh.write(f"{batch}\t{rule}\t{rel.as_posix()}\t{final.relative_to(store).as_posix()}\n")


def prune_empty_dirs(store: Path) -> None:
    for base, dirs, files in os.walk(store, topdown=False):
        p = Path(base)
        if p == store or TRASH_DIR in p.parts or "prds" in p.parts:
            continue
        try:
            p.rmdir()  # fails on non-empty, which is the point
        except OSError:
            pass


def empty_old_trash(store: Path, now: float, days: float) -> int:
    trash = store / TRASH_DIR
    removed = 0
    if not trash.is_dir():
        return 0
    for batch in trash.iterdir():
        if not batch.is_dir():
            continue
        try:
            batch_ts = time.mktime(time.strptime(batch.name, "%Y-%m-%d"))
        except ValueError:
            continue
        if (now - batch_ts) / DAY > days:
            shutil.rmtree(batch)
            removed += 1
    return removed


def process_store(label: str, store: Path, args, now: float) -> dict:
    live, done = prd_numbers(store)
    batch = time.strftime("%Y-%m-%d", time.localtime(now))
    trash_counts: Counter = Counter()
    kept_fresh: Counter = Counter()
    unclassified: Counter = Counter()
    flags: list[str] = []
    trashed: list[tuple[str, str]] = []

    for rel, mtime in sorted(walk_store(store)):
        action, rule = classify_artifact(rel, mtime, live, done, now, args)
        if action == "trash":
            trash_counts[rule] += 1
            trashed.append((rule, rel.as_posix()))
            if args.apply:
                if len(rel.parts) > 1 and rel.parts[0] == "reviews" and rel.suffix == ".md":
                    harvest_review_verdicts(store, rel, now)
                trash_file(store, rel, rule, batch)
        elif action == "flag":
            flags.append((rule, rel.as_posix()))
        elif rule.startswith("fresh:"):
            kept_fresh[rule[6:]] += 1
        elif rule == "unclassified":
            top = rel.parts[0] if len(rel.parts) > 1 else "(root)"
            unclassified[top] += 1

    emptied = 0
    if args.apply:
        prune_empty_dirs(store)
        emptied = empty_old_trash(store, now, args.empty_trash_days)

    total = sum(trash_counts.values())
    if total or flags or args.verbose:
        detail = " ".join(f"{r}:{n}" for r, n in sorted(trash_counts.items()))
        fresh = f" fresh-skipped={sum(kept_fresh.values())}" if kept_fresh else ""
        uncl = f" unclassified={sum(unclassified.values())}" if unclassified else ""
        emp = f" trash-batches-emptied={emptied}" if emptied else ""
        print(f"{label}: trash={total} ({detail}){fresh}{uncl}{emp}")
        for rule, f in flags[:20]:
            label_txt = "prd gone" if rule == "prd-gone" else rule
            print(f"  FLAG ({label_txt}, kept): {f}")
        if args.verbose:
            for rule, rel in trashed:
                print(f"  {rule}: {rel}")
            for top, n in sorted(unclassified.items()):
                print(f"  unclassified {top}/: {n} kept")
    return {"trash": total, "flags": len(flags),
            "unclassified": sum(unclassified.values())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Trash-first GC for dev/local stores")
    scope = ap.add_mutually_exclusive_group(required=True)
    scope.add_argument("--all", action="store_true", help="all repos under ~/git/src plus ~/.claude")
    scope.add_argument("--repo", action="append", type=Path, help="repo root or dev/local path (repeatable)")
    ap.add_argument("--apply", action="store_true", help="move files to .trash (default: dry-run)")
    ap.add_argument("--min-age-days", type=float, default=3, help="never trash files newer than this")
    ap.add_argument("--tmp-age-days", type=float, default=7)
    ap.add_argument("--autopilot-age-days", type=float, default=14)
    ap.add_argument("--empty-trash-days", type=float, default=30)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    now = time.time()
    if args.all:
        stores = find_stores(Path.home())
    else:
        stores = {}
        for p in args.repo:
            if not p.exists():
                print(f"error: no such path: {p}", file=sys.stderr)
                return 2
            stores[str(p)] = resolve_store(p)

    totals = Counter()
    for label, store in stores.items():
        for k, v in process_store(label, store, args, now).items():
            totals[k] += v
    mode = "APPLIED" if args.apply else "DRY-RUN (use --apply)"
    print(f"{mode}: trash={totals['trash']} flags={totals['flags']} "
          f"unclassified-kept={totals['unclassified']} across {len(stores)} store(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
