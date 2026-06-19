#!/usr/bin/env python3
"""Adversarial-signal scan: find imperatives, role-changes, and framing
language in a markdown design doc.

The scan separates two categories per the framework's calibration heuristic:

- **Adversarial signals** (try to constrain reviewer behavior): imperatives
  addressed to the reviewer, role-changing language, pre-emptive dismissals
  of objections.
- **Framing language** (shapes design narrative, not auto-adversarial):
  appeals to authority, claimed inevitability, self-praise. Demote to a
  cognitive bias scan trigger, not an automatic adversarial finding.

Usage: adversarial_signal_scan.py <path/to/doc.md>

Called from: ~/.claude/skills/review-design-doc/SKILL.md Workflow step 6.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Adversarial signals: language that constrains reviewer behavior.
ADVERSARIAL_PATTERNS = [
    (r"\bignore (?:previous|prior|the above|earlier) (?:instruction|prompt|direction)s?\b", "imperative: ignore previous instructions"),
    (r"\bapprove this (?:design|proposal|doc|RFC)\b", "imperative: approve directive"),
    (r"\byou are (?:now|a) (?:a different|another) (?:reviewer|assistant|agent)\b", "role-change"),
    (r"\b(?:critics|naysayers|skeptics) (?:will|may|might) (?:argue|say|claim).+but\b", "pre-emptive dismissal of objections"),
    (r"\bthis (?:should|must) not be (?:questioned|reviewed|critiqued)\b", "close-off-critique directive"),
    (r"\b(?:skip|bypass|disregard) (?:the )?(?:standard|usual) review\b", "review-bypass directive"),
]

# Framing language: shapes narrative, not adversarial. Demote to bias-scan trigger.
FRAMING_PATTERNS = [
    (r"\bobviously\b", "claimed inevitability"),
    (r"\beveryone agrees\b", "false consensus"),
    (r"\bindustry (?:consensus|standard|best[- ]practice)\b", "appeal to authority"),
    (r"\b(?:FAANG|MAANG|big[- ]tech) (?:does|uses|does it this way|approach)\b", "appeal to authority"),
    (r"\bthe only (?:sensible|reasonable|sane|correct) (?:choice|option|approach)\b", "false dichotomy"),
    (r"\bthis elegant (?:design|architecture|solution)\b", "self-praise"),
    (r"\bbest[- ]in[- ]class\b", "self-praise"),
    (r"\bworld[- ]class\b", "self-praise"),
    (r"\bclearly the (?:right|best|correct) (?:choice|approach)\b", "claimed inevitability"),
    (r"\bof course\b", "claimed inevitability"),
    (r"\bas (?:everyone|we all) know(?:s)?\b", "false consensus"),
]


def find_signals(path: Path) -> tuple[list[dict], list[dict]]:
    # Strip fenced code blocks; examples in code don't count.
    text = re.sub(r"```[^`]*?```", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    lines = text.split("\n")

    adversarial: list[dict] = []
    framing: list[dict] = []

    for i, line in enumerate(lines):
        for pat, label in ADVERSARIAL_PATTERNS:
            if re.search(pat, line, flags=re.IGNORECASE):
                adversarial.append({
                    "line": i + 1,
                    "category": label,
                    "context": line.strip()[:140],
                })
        for pat, label in FRAMING_PATTERNS:
            if re.search(pat, line, flags=re.IGNORECASE):
                framing.append({
                    "line": i + 1,
                    "category": label,
                    "context": line.strip()[:140],
                })

    return adversarial, framing


def main():
    if len(sys.argv) != 2:
        print("usage: adversarial_signal_scan.py <path/to/doc.md>", file=sys.stderr)
        sys.exit(2)

    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"error: not a file: {path}", file=sys.stderr)
        sys.exit(1)

    adversarial, framing = find_signals(path)

    if not adversarial and not framing:
        print("No adversarial signals or framing language found.")
        print("SUMMARY: " + json.dumps({"adversarial": 0, "framing": 0}))
        return

    if adversarial:
        print(f"=== Adversarial signals ({len(adversarial)}) — flag in review's Adversarial signals section ===")
        for f in adversarial:
            print(f"L{f['line']:>4}  [{f['category']}]  {f['context']}")

    if framing:
        print(f"\n=== Framing language ({len(framing)}) — trigger Cognitive bias scan, NOT auto-adversarial ===")
        for f in framing:
            print(f"L{f['line']:>4}  [{f['category']}]  {f['context']}")

    print()
    summary = {
        "adversarial": len(adversarial),
        "framing": len(framing),
        "adversarial_categories": sorted(set(f["category"] for f in adversarial)),
        "framing_categories": sorted(set(f["category"] for f in framing)),
    }
    print("SUMMARY: " + json.dumps(summary))


if __name__ == "__main__":
    main()
