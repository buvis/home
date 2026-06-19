#!/usr/bin/env python3
"""Claim ladder scan: find compressed qualifiers without measurement.

Scans a markdown design doc for vague qualifiers ("scalable", "robust",
"fast", "secure", "elegant", etc.) and reports their locations so the
reviewer can run the claim ladder on each.

Heuristic: a qualifier is suspect when it appears WITHOUT a nearby
measurement (a number, unit, or percentage within ±2 lines). The script
flags suspect occurrences; the reviewer judges whether each one needs
the claim ladder applied.

Usage: claim_ladder_scan.py <path/to/doc.md>

Called from: ~/.claude/skills/review-design-doc/SKILL.md Workflow step 6.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Vague qualifiers commonly used in design docs without measurement.
QUALIFIERS = [
    "scalable", "robust", "fast", "slow", "secure", "modular", "extensible",
    "simple", "elegant", "intuitive", "performant", "efficient", "lightweight",
    "high-quality", "world-class", "best-in-class", "industry-leading",
    "battle-tested", "production-ready", "enterprise-grade", "resilient",
    "highly available", "low-latency", "real-time", "near-real-time",
    "easy to use", "user-friendly", "seamless", "smooth", "powerful",
    "flexible", "configurable", "future-proof", "well-designed",
]

# Patterns that indicate a measurement is nearby (number + unit, percentages,
# latency budgets, etc.). If any of these appear within ±2 lines of a
# qualifier, the qualifier is considered grounded.
MEASUREMENT_PATTERNS = [
    r"\d+\s*(?:ms|s|sec|second|minute|min|hour|h|day|week|month|year)s?\b",
    r"\d+\s*(?:%|percent|percentile)",
    r"\d+\s*(?:rps|qps|tps|req/s|requests?/sec)",
    r"\d+\s*(?:GB|MB|KB|TB|PB|bytes?)",
    r"p\d{1,3}\b",
    r"\b\d{2,}\b",
    r"\$\d+",
    r"\bx\d+\b|\b\d+x\b",
]


def has_measurement_nearby(lines: list[str], idx: int, radius: int = 2) -> bool:
    start = max(0, idx - radius)
    end = min(len(lines), idx + radius + 1)
    context = " ".join(lines[start:end])
    for pat in MEASUREMENT_PATTERNS:
        if re.search(pat, context, flags=re.IGNORECASE):
            return True
    return False


def scan(path: Path) -> list[dict]:
    # Strip fenced code blocks so qualifiers in examples are not flagged.
    text = re.sub(r"```[^`]*?```", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    lines = text.split("\n")

    qualifier_pattern = re.compile(
        r"\b(" + "|".join(re.escape(q) for q in QUALIFIERS) + r")\b",
        flags=re.IGNORECASE,
    )

    findings: list[dict] = []
    for i, line in enumerate(lines):
        for m in qualifier_pattern.finditer(line):
            qualifier = m.group(1)
            grounded = has_measurement_nearby(lines, i)
            findings.append({
                "line": i + 1,
                "qualifier": qualifier,
                "context": line.strip()[:120],
                "grounded": grounded,
            })

    return findings


def main():
    if len(sys.argv) != 2:
        print("usage: claim_ladder_scan.py <path/to/doc.md>", file=sys.stderr)
        sys.exit(2)

    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"error: not a file: {path}", file=sys.stderr)
        sys.exit(1)

    findings = scan(path)

    if not findings:
        print("No compressed qualifiers found.")
        return

    ungrounded = [f for f in findings if not f["grounded"]]
    grounded = [f for f in findings if f["grounded"]]

    print(f"=== Ungrounded qualifiers ({len(ungrounded)}) — run the claim ladder ===")
    for f in ungrounded:
        print(f"L{f['line']:>4}  [{f['qualifier']}]  {f['context']}")

    if grounded:
        print(f"\n=== Grounded qualifiers ({len(grounded)}) — measurement nearby ===")
        for f in grounded:
            print(f"L{f['line']:>4}  [{f['qualifier']}]  {f['context']}")

    print()
    summary = {
        "total": len(findings),
        "ungrounded": len(ungrounded),
        "grounded": len(grounded),
        "ungrounded_unique": sorted(set(f["qualifier"].lower() for f in ungrounded)),
    }
    print("SUMMARY: " + json.dumps(summary))


if __name__ == "__main__":
    main()
