#!/usr/bin/env python3
"""Inject data.json (+ optional epics.json) into the SPA template.

Usage: build.py [--dir DIR] [--out FILE]  (defaults under ~/.claude/portfolio-brief/)
"""
import argparse
import json
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "assets/template.html"
PLACEHOLDER = "__PORTFOLIO_PAYLOAD__"


def main():
    ap = argparse.ArgumentParser()
    default_dir = Path.home() / ".claude/portfolio-brief"
    ap.add_argument("--dir", default=str(default_dir))
    ap.add_argument("--out", default=str(default_dir / "portfolio-brief.html"))
    args = ap.parse_args()

    workdir = Path(args.dir)
    data_file = workdir / "data.json"
    if not data_file.is_file():
        sys.exit(f"missing {data_file} — run collect.py first")
    data = json.loads(data_file.read_text())

    epics_file = workdir / "epics.json"
    if epics_file.is_file():
        epics = json.loads(epics_file.read_text())
    else:
        print(f"WARN: {epics_file} not found — building without epic grouping", file=sys.stderr)
        epics = {"summary": "", "repos": {}}

    template = TEMPLATE.read_text()
    if PLACEHOLDER not in template:
        sys.exit(f"template {TEMPLATE} has no {PLACEHOLDER} marker")
    # <\/ keeps a literal </script> inside any commit subject from ending the tag
    payload = json.dumps({"data": data, "epics": epics}).replace("</", "<\\/")
    out = Path(args.out)
    out.write_text(template.replace(PLACEHOLDER, payload))
    print(f"wrote {out} ({out.stat().st_size // 1024} kB)")


if __name__ == "__main__":
    main()
