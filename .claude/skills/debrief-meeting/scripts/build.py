#!/usr/bin/env python3
"""Inject transcript.json (+ optional extract.json) into the SPA template.

Applies the model's text corrections to the turns first, keeping the original
wording in `raw` so the page can show what was changed.

Usage: build.py DIR [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "assets/template.html"
PLACEHOLDER = "__MEETING_PAYLOAD__"
KNOWN_KEYS = {
    "meta", "tldr", "summary", "agenda", "topics", "decisions", "actions",
    "questions", "risks", "blockers", "assumptions", "disagreements", "entities",
    "glossary", "quotes", "sentiment", "followups", "quality", "dynamics",
    "email", "corrections",
}


def build_pattern(needle: str) -> re.Pattern[str]:
    """Word-bounded where the edges are word characters, literal otherwise."""
    head = r"\b" if needle[:1].isalnum() else ""
    tail = r"\b" if needle[-1:].isalnum() else ""
    return re.compile(head + re.escape(needle) + tail, re.IGNORECASE)


def apply_corrections(turns: list[dict], corrections: list[dict]) -> list[dict]:
    log: list[dict] = []
    for fix in corrections:
        old, new = fix.get("from"), fix.get("to")
        if not old or new is None:
            continue
        pattern = build_pattern(old)
        only = fix.get("turn")
        hits = 0
        for turn in turns:
            if only is not None and turn["i"] != only:
                continue
            text, count = pattern.subn(new, turn["text"])
            if count:
                turn.setdefault("raw", turn["text"])
                turn["text"] = text
                hits += count
        log.append({"kind": "text", "from": old, "to": new,
                    "reason": fix.get("reason"), "applied": hits})
    return log


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dir", help="debrief dir holding transcript.json and extract.json")
    ap.add_argument("--out", help="output html (default: <dir>/debrief.html)")
    args = ap.parse_args()

    workdir = Path(args.dir).expanduser().resolve()
    source = workdir / "transcript.json"
    if not source.is_file():
        sys.exit(f"missing {source} — run parse.py first")
    transcript = json.loads(source.read_text(encoding="utf-8"))

    extract_file = workdir / "extract.json"
    if extract_file.is_file():
        extract = json.loads(extract_file.read_text(encoding="utf-8"))
    else:
        print(f"WARN: {extract_file} not found — building the transcript view only",
              file=sys.stderr)
        extract = {}

    for key in extract:
        if key not in KNOWN_KEYS:
            print(f"WARN: extract.json has unknown key '{key}' — the page will ignore it",
                  file=sys.stderr)

    fixes = apply_corrections(transcript["turns"], extract.get("corrections") or [])
    for fix in fixes:
        if not fix["applied"]:
            print(f"WARN: correction '{fix['from']}' -> '{fix['to']}' matched nothing",
                  file=sys.stderr)
    transcript["corrections"] = (transcript.get("corrections") or []) + fixes

    template = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        sys.exit(f"template {TEMPLATE} has no {PLACEHOLDER} marker")
    # <\/ keeps a literal </script> inside the transcript from ending the tag
    payload = json.dumps({"transcript": transcript, "extract": extract},
                         ensure_ascii=False).replace("</", "<\\/")

    out = Path(args.out).expanduser() if args.out else workdir / "debrief.html"
    out.write_text(template.replace(PLACEHOLDER, payload), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} kB)")


if __name__ == "__main__":
    main()
