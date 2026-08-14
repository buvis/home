#!/usr/bin/env python3
"""audit_qwen.py - qwen utilization report card (PRD 00112).

Sweeps batch reports and autopilot state files across the gita-registered
repos plus ~/.claude, computes utilization rates deterministically, and
prints a markdown report card ending in a WIDEN/NARROW/HOLD verdict.
stdlib only; every figure is a code-side parse, the skill only narrates.

Quinn precision (the PRD's fifth number) is not computable and is reported
as such: PRD 00094 (2026-08-09) retired Quinn and deleted the Advisory
bucket from output-formats.md, and the historical review files carrying
either were GC'd. Review files are therefore not parsed at all - they fed
no other metric.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Parse targets, pinned 2026-08-14 against:
# - cli/render_report.py::_implementor_mix + cli/golden/expected/
#   report-section.md (the code-rendered format, PRD 00107), and
# - the 2026-07 prose-era reports (ddb 202607161128): exclusion line
#   without the "(plan-time)" suffix, buckets outside today's enum
#   (docs-judgment, backend_down).
RE_PRD_HEADING = re.compile(r"^## (\S+\.md)(\s+\S.*)?$")
RE_MIX_HEADING = re.compile(r"^### Implementor Mix$")
RE_MIX_ROW = re.compile(r"^\| ([\w-]+) \| (\d+) \|$")
RE_PREFLIGHT = re.compile(r"^Qwen preflight outcomes: (.+)$")
RE_EXCLUSION = re.compile(r"^Excluded from qwen: (.+)$")
RE_BUCKET = re.compile(r"([\w-]+) (\d+)")

GATE_PASSED_OUTCOMES = ("completed", "review_flagged", "rework_failed")
HOLD_MIN_ATTEMPTS = 10
WIDEN_RATE, WIDEN_MIN = 0.8, 10
NARROW_RATE, NARROW_MIN = 0.5, 6


def _add(hist: dict, key: str, n: int = 1) -> None:
    hist[key] = hist.get(key, 0) + n


def parse_exclusion_line(text: str) -> tuple[dict, dict]:
    """Both exclusion-line eras: the code-rendered form splits plan-time
    buckets from dispatch-time reroutes; the prose era was one flat list
    (counted as plan-time - it had no reroute concept)."""
    plan: dict[str, int] = {}
    dispatch: dict[str, int] = {}
    if "(plan-time)" in text:
        plan_part, _, rest = text.partition("(plan-time)")
        reroute_part = rest.partition("dispatch-time reroutes:")[2]
        for bucket, n in RE_BUCKET.findall(plan_part):
            plan[bucket] = int(n)
        for bucket, n in RE_BUCKET.findall(reroute_part):
            dispatch[bucket] = int(n)
    else:
        for bucket, n in RE_BUCKET.findall(text):
            plan[bucket] = int(n)
    return plan, dispatch


def parse_report(path: Path) -> dict:
    """One batch report -> {batch, sections, unparsed}. A section is
    {prd, stalled, mix}; mix is None on a pre-00019 legacy section."""
    result = {
        "batch": path.name.removesuffix("-report.md"),
        "sections": [],
        "unparsed": None,
    }
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        result["unparsed"] = f"unreadable: {exc}"
        return result
    current, in_mix, saw_mix_heading = None, False, False
    for line in text.splitlines():
        if line.startswith("## "):
            m = RE_PRD_HEADING.match(line)
            current = (
                {"prd": m.group(1), "stalled": bool(m.group(2)), "mix": None}
                if m
                else None
            )
            if current:
                result["sections"].append(current)
            in_mix = False
            continue
        if current is None:
            continue
        if RE_MIX_HEADING.match(line):
            current["mix"] = {"attempts": {}, "preflight": {}, "plan": {}, "dispatch": {}}
            in_mix, saw_mix_heading = True, True
            continue
        if line.startswith("### "):
            in_mix = False
            continue
        if not in_mix:
            continue
        if m := RE_MIX_ROW.match(line):
            current["mix"]["attempts"][m.group(1)] = int(m.group(2))
        elif m := RE_PREFLIGHT.match(line):
            for bucket, n in RE_BUCKET.findall(m.group(1)):
                current["mix"]["preflight"][bucket] = int(n)
        elif m := RE_EXCLUSION.match(line):
            current["mix"]["plan"], current["mix"]["dispatch"] = parse_exclusion_line(
                m.group(1),
            )
    if not result["sections"]:
        result["unparsed"] = "no PRD sections found"
    elif "implementor" in text.lower() and not saw_mix_heading:
        result["unparsed"] = (
            "mentions 'Implementor' but no '### Implementor Mix' heading parsed"
            " - format drift?"
        )
    return result


def parse_state(path: Path) -> dict:
    """One state.json -> {batch, prd, eligible, plan, dispatch, attempts,
    unparsed}. attempts is the flattened chain view across tasks."""
    result = {
        "batch": None,
        "prd": None,
        "eligible": 0,
        "plan": {},
        "dispatch": {},
        "attempts": [],
        "unparsed": None,
    }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result["unparsed"] = f"{type(exc).__name__}: {exc}"
        return result
    if not isinstance(data, dict):
        result["unparsed"] = "not a JSON object"
        return result
    result["batch"] = (data.get("batch") or {}).get("id")
    result["prd"] = data.get("prd")
    for task in data.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        if task.get("qwen_eligible"):
            result["eligible"] += 1
        else:
            _add(result["plan"], task.get("qwen_excluded_reason") or "unknown")
        for attempt in task.get("attempts") or []:
            if not isinstance(attempt, dict):
                continue
            result["attempts"].append(attempt)
            if attempt.get("qwen_excluded_reason"):
                _add(result["dispatch"], attempt["qwen_excluded_reason"])
    return result


def classify_gate(attempt: dict) -> str:
    """Step-5.5 gate verdict for one qwen attempt, pinned to state-schema.md
    (PRD 00065): `qwen_gate_failed` is the durable failure signal; outcome
    "escalated" marks the rung the task escalated away from in-pass.
    review_flagged/rework_failed mean the gate PASSED and review judged the
    result later (the PRD's non-rework carve-out). Pre-00065 chains hold one
    entry per task, so an in-pass gate failure is invisible in them (the
    Claude fallback rewrote `implementor`) - disclosed in method notes."""
    if attempt.get("qwen_gate_failed"):
        return "failed"
    if attempt.get("outcome") == "escalated":
        return "failed"
    if attempt.get("outcome") in GATE_PASSED_OUTCOMES:
        return "passed"
    return "unclassified"


def discover_repos() -> tuple[list[Path], str]:
    """gita-registered repo paths (the brief-portfolio source) + ~/.claude."""
    paths: list[Path] = []
    note = ""
    try:
        proc = subprocess.run(
            ["gita", "freeze"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        rows = proc.stdout.splitlines() if proc.returncode == 0 else []
        if proc.returncode != 0:
            note = f"gita freeze exited {proc.returncode}; scanning ~/.claude only"
    except (OSError, subprocess.TimeoutExpired) as exc:
        rows, note = [], f"gita unavailable ({exc}); scanning ~/.claude only"
    for row in rows:
        parts = row.split(",")
        if len(parts) >= 3 and parts[2]:
            paths.append(Path(parts[2]))
    paths.append(Path.home() / ".claude")
    return paths, note


def scan_repo(repo: Path) -> dict:
    """All qwen telemetry in one repo. Missing dirs -> a no-data row."""
    auto = repo / "dev" / "local" / "autopilot"
    reports_dir = auto / "reports"
    record = {"repo": repo.name, "reports": [], "states": [], "archived": 0, "unparsed": []}
    if not auto.is_dir():
        return record
    if reports_dir.is_dir():
        for path in sorted(reports_dir.glob("*-report.md")):
            parsed = parse_report(path)
            if parsed["unparsed"]:
                record["unparsed"].append((str(path), parsed["unparsed"]))
            else:
                record["reports"].append(parsed)
        record["archived"] = len(list(reports_dir.glob("*state*archived*.json")))
    state_path = auto / "state.json"
    if state_path.is_file():
        parsed = parse_state(state_path)
        if parsed["unparsed"]:
            record["unparsed"].append((str(state_path), parsed["unparsed"]))
        else:
            record["states"].append(parsed)
    return record


def compute(records: list[dict]) -> dict:
    """Merge per-repo parses into the aggregate rate inputs. A report
    section whose (repo, prd) a state also covers is skipped - the state
    chain is richer and counting both would double-count."""
    agg = {
        "state_qwen": 0,
        "report_qwen": 0,
        "eligible": 0,
        "gate": {"passed": 0, "failed": 0, "unclassified": 0},
        "preflight": {},
        "plan": {},
        "dispatch": {},
        "batch_rows": [],
        "superseded": 0,
    }
    for record in records:
        state_prds = {s["prd"] for s in record["states"] if s["prd"]}
        for state in record["states"]:
            qwen = [a for a in state["attempts"] if a.get("implementor") == "qwen"]
            agg["state_qwen"] += len(qwen)
            agg["eligible"] += state["eligible"]
            for attempt in qwen:
                _add(agg["gate"], classify_gate(attempt))
                if attempt.get("preflight_outcome"):
                    _add(agg["preflight"], attempt["preflight_outcome"])
            for hist in ("plan", "dispatch"):
                for bucket, n in state[hist].items():
                    _add(agg[hist], bucket, n)
            agg["batch_rows"].append(
                [
                    state["batch"] or "?",
                    record["repo"],
                    "state (live)",
                    state["prd"] or "?",
                    len(qwen),
                    "",
                ],
            )
        for report in record["reports"]:
            for section in report["sections"]:
                if section["stalled"]:
                    continue
                if section["prd"] in state_prds:
                    agg["superseded"] += 1
                    continue
                mix = section["mix"]
                note = "" if mix else "legacy (no mix data)"
                qwen = mix["attempts"].get("qwen", 0) if mix else 0
                agg["report_qwen"] += qwen
                if mix:
                    for hist in ("preflight", "plan", "dispatch"):
                        for bucket, n in mix[hist].items():
                            _add(agg[hist], bucket, n)
                agg["batch_rows"].append(
                    [report["batch"], record["repo"], "report", section["prd"], qwen, note],
                )
    return agg


def verdict(agg: dict) -> tuple[str, str]:
    total = agg["state_qwen"] + agg["report_qwen"]
    gate = agg["gate"]
    classifiable = gate["passed"] + gate["failed"]
    rate = gate["passed"] / classifiable if classifiable else None
    if total < HOLD_MIN_ATTEMPTS:
        return "HOLD", (
            f"insufficient data: {total} qwen attempts on record, "
            f"{HOLD_MIN_ATTEMPTS} needed before any verdict moves"
        )
    if rate is not None and classifiable >= WIDEN_MIN and rate >= WIDEN_RATE:
        fences = sorted(agg["plan"].items(), key=lambda kv: (-kv[1], kv[0]))
        ranking = ", ".join(f"{b} ({n} tasks)" for b, n in fences) or "no exclusions recorded"
        caveat = (
            " CAVEAT: zero gate failures appear anywhere in these chains, and"
            " chains predating PRD 00065 cannot record one - verify the chains"
            " are post-00065 before acting on the rate."
            if gate["failed"] == 0
            else ""
        )
        return "WIDEN", (
            f"gate pass rate {rate:.2f} across {classifiable} classifiable attempts; "
            f"fence candidates by exclusion volume: {ranking}.{caveat}"
        )
    if rate is not None and classifiable >= NARROW_MIN and rate < NARROW_RATE:
        return "NARROW", (
            f"gate pass rate {rate:.2f} across {classifiable} classifiable attempts; "
            f"question the engine/eval choice first, then tighten fences"
        )
    return "HOLD", (
        f"{total} attempts on record but only {classifiable} are gate-classifiable "
        f"(rate {'n/a' if rate is None else format(rate, '.2f')}); no threshold met"
    )


def _hist(hist: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in sorted(hist.items())) or "none"


def render(records: list[dict], agg: dict, note: str) -> str:
    total = agg["state_qwen"] + agg["report_qwen"]
    gate = agg["gate"]
    classifiable = gate["passed"] + gate["failed"]
    word, reason = verdict(agg)
    lines = [
        "# Qwen Utilization Report Card",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
        + (f" — {note}" if note else ""),
        "",
        "## Discovery",
        "",
        "| Repo | Reports | States | Archived snapshots | Status |",
        "|------|---------|--------|--------------------|--------|",
    ]
    for r in records:
        status = (
            "UNPARSED entries"
            if r["unparsed"]
            else ("ok" if r["reports"] or r["states"] else "no data")
        )
        lines.append(
            f"| {r['repo']} | {len(r['reports'])} | {len(r['states'])} |"
            f" {r['archived']} | {status} |",
        )
    unparsed = [(p, why) for r in records for p, why in r["unparsed"]]
    if unparsed:
        lines += ["", "## UNPARSED", ""]
        lines += [f"- `{p}` — {why}" for p, why in unparsed]
    lines += [
        "",
        "## Per batch",
        "",
        "| Batch | Repo | Source | PRD | Qwen attempts | Notes |",
        "|-------|------|--------|-----|---------------|-------|",
    ]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in agg["batch_rows"]]
    if not agg["batch_rows"]:
        lines.append("| — | — | — | — | 0 | no batches found |")
    gate_rate = (
        f"{gate['passed']}/{classifiable} = {gate['passed'] / classifiable:.2f}"
        if classifiable
        else "n/a (0 classifiable)"
    )
    dispatch_rate = (
        f"{agg['state_qwen']}/{agg['eligible']} = {agg['state_qwen'] / agg['eligible']:.2f}"
        if agg["eligible"]
        else "n/a (0 eligible tasks observed)"
    )
    lines += [
        "",
        "## Aggregate",
        "",
        f"- Qwen attempts on record: **{total}** (state chains {agg['state_qwen']},"
        f" report sections {agg['report_qwen']})",
        f"- Dispatch rate (qwen attempts / qwen-eligible tasks, state chains only):"
        f" {dispatch_rate}",
        f"- Preflight outcomes: {_hist(agg['preflight'])}",
        f"- Gate pass rate (state chains only): {gate_rate}"
        + (f" — {gate['unclassified']} unclassified" if gate["unclassified"] else ""),
        f"- Exclusions, plan-time: {_hist(agg['plan'])};"
        f" dispatch-time reroutes: {_hist(agg['dispatch'])}",
        "- Quinn precision: **not computable** — PRD 00094 (2026-08-09) retired Quinn"
        " and deleted the Advisory bucket; the review files that carried either were"
        " GC'd. Metric dropped, not zero.",
        "",
        "## Verdict",
        "",
        f"**{word}** — {reason}",
        "",
        f"Thresholds (fixed): <{HOLD_MIN_ATTEMPTS} attempts → HOLD; pass rate"
        f" ≥{WIDEN_RATE} across ≥{WIDEN_MIN} → WIDEN; <{NARROW_RATE} across"
        f" ≥{NARROW_MIN} → NARROW; else HOLD.",
        "",
        "## Method notes",
        "",
        "- Gate verdicts read `qwen_gate_failed` / `outcome: escalated` (PRD 00065)."
        " Pre-00065 chains wrote one entry per task, so an in-pass gate failure is"
        " invisible in them (the Claude fallback rewrote `implementor`); their qwen"
        " rows can only ever read as passes.",
        "- Report sections whose PRD a live state also covers are counted from the"
        f" state only ({agg['superseded']} superseded this run).",
        "- Archived state snapshots (`*state*archived*.json`): the wrapper does not"
        " currently write any; the glob stays for when it does.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Qwen utilization report card (PRD 00112)")
    ap.add_argument(
        "--repo",
        action="append",
        type=Path,
        help="scan only these repo roots (repeatable; overrides discovery)",
    )
    ap.add_argument("--output", type=Path, help="write the report card here instead of stdout")
    args = ap.parse_args(argv)
    if args.repo:
        repos, note = args.repo, ""
    else:
        repos, note = discover_repos()
    records = [scan_repo(repo) for repo in repos]
    card = render(records, compute(records), note)
    if args.output:
        args.output.write_text(card, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(card)
    return 0


if __name__ == "__main__":
    sys.exit(main())
