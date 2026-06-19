#!/usr/bin/env python3
"""Section weight audit for markdown design documents.

Counts words per top-level (##) section, computes the median, flags
outliers (>3x or <1/3 the median). Skips fenced code blocks and recurses
into container sections (those that hold multiple parallel sub-sections).

Usage: section_weight_audit.py <path/to/doc.md>

Called from: ~/.claude/skills/review-design-doc/SKILL.md Workflow step 6.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Section:
    title: str
    level: int
    start_line: int
    lines: list[str] = field(default_factory=list)
    children: list["Section"] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return sum(len(line.split()) for line in self.lines)

    @property
    def is_container(self) -> bool:
        if len(self.children) < 2:
            return False
        if len(set(c.level for c in self.children)) != 1:
            return False
        own_words = self.word_count
        children_words = sum(
            c.word_count + sum(gc.word_count for gc in c.children)
            for c in self.children
        )
        return own_words < children_words * 0.3


def strip_code_blocks(text: str) -> str:
    return re.sub(r"```[^`]*?```", "", text, flags=re.DOTALL)


def parse_sections(text: str) -> list[Section]:
    text = strip_code_blocks(text)
    lines = text.split("\n")
    top_sections: list[Section] = []
    stack: list[Section] = []

    for i, line in enumerate(lines):
        m = re.match(r"^(#{2,})\s+(.+?)\s*$", line)
        if m:
            level = len(m.group(1))
            title = m.group(2)
            section = Section(title=title, level=level, start_line=i + 1)
            while stack and stack[-1].level >= level:
                stack.pop()
            if stack:
                stack[-1].children.append(section)
            else:
                top_sections.append(section)
            stack.append(section)
        else:
            if stack:
                stack[-1].lines.append(line)

    return top_sections


def audit_sections(sections: list[Section], context: str = "top-level") -> list[dict]:
    if not sections:
        return []

    findings = []
    auditable: list[Section] = []
    for s in sections:
        if s.is_container:
            findings.append({
                "title": s.title,
                "level": context,
                "word_count": s.word_count,
                "flag": "container",
                "note": f"container of {len(s.children)} sub-sections",
            })
            findings.extend(audit_sections(s.children, context=f"sub:{s.title[:30]}"))
        else:
            auditable.append(s)

    if not auditable:
        return findings

    weights = [s.word_count for s in auditable]
    median = statistics.median(weights) if weights else 0
    heavy_threshold = 3 * median
    light_threshold = median / 3

    for s in auditable:
        flag = "ok"
        note = ""
        if median > 0:
            if s.word_count > heavy_threshold:
                flag = "heavy"
                note = f"{s.word_count / median:.1f}x median"
            elif s.word_count < light_threshold:
                flag = "light"
                note = f"{s.word_count / median:.2f}x median"
        findings.append({
            "title": s.title,
            "level": context,
            "word_count": s.word_count,
            "flag": flag,
            "note": note,
        })

    return findings


def format_table(findings: list[dict]) -> str:
    if not findings:
        return "(no sections found)"

    title_width = min(max(len(f["title"]) for f in findings), 60)
    level_width = min(max(len(f["level"]) for f in findings), 25)

    lines = [
        f"{'Section':<{title_width}}  {'Level':<{level_width}} {'Words':>7}  {'Flag':<12} Note",
        "-" * (title_width + level_width + 35),
    ]
    flag_markers = {
        "heavy": "HEAVY",
        "light": "LIGHT",
        "container": "(container)",
        "ok": "ok",
    }
    for f in findings:
        title = f["title"][:title_width]
        marker = flag_markers.get(f["flag"], f["flag"])
        lines.append(
            f"{title:<{title_width}}  {f['level']:<{level_width}} "
            f"{f['word_count']:>7}  {marker:<12} {f['note']}"
        )
    return "\n".join(lines)


def main():
    if len(sys.argv) != 2:
        print("usage: section_weight_audit.py <path/to/doc.md>", file=sys.stderr)
        sys.exit(2)

    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"error: not a file: {path}", file=sys.stderr)
        sys.exit(1)

    text = path.read_text(encoding="utf-8")
    sections = parse_sections(text)
    findings = audit_sections(sections)

    print(format_table(findings))

    summary = {
        "total_sections": len([f for f in findings if f["flag"] != "container"]),
        "heavy_outliers": [f["title"] for f in findings if f["flag"] == "heavy"],
        "light_outliers": [f["title"] for f in findings if f["flag"] == "light"],
        "containers": [f["title"] for f in findings if f["flag"] == "container"],
    }
    print()
    print("SUMMARY: " + json.dumps(summary))


if __name__ == "__main__":
    main()
