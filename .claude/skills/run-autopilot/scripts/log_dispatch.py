#!/usr/bin/env python3
"""Append one JSON-object line to the autopilot dispatch log.

Gated on the _AUTOPILOT_LOOP env var: if unset or empty, exits 0 without
writing anything. On any error (bad args, unwritable path, missing autopilot
dir), exits 0 without writing anything.

Usage:
    python3 log_dispatch.py \
        --prd PRD --task-id ID --task-name NAME \
        --dispatch-type TYPE --model MODEL \
        --outcome OUTCOME --duration-s SECS --attempt N
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _walk_up import find_autopilot_dir

VALID_DISPATCH_TYPES = {"tess", "ivan", "devon", "reviewer", "codex", "gemini"}
VALID_OUTCOMES = {
    "completed", "hung", "timeout", "context_overrun",
    "subagent_prompt_overrun", "error", "infra_failure",
}


def _parse_args(argv: list[str]) -> dict | None:
    """Return parsed args as a dict, or None on any error."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--prd", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--task-name", required=True)
    parser.add_argument("--dispatch-type", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--outcome", required=True)
    parser.add_argument("--duration-s", required=True)
    parser.add_argument("--attempt", required=True)

    try:
        ns, unknown = parser.parse_known_args(argv)
    except (SystemExit, Exception):
        # argparse raises SystemExit (which is NOT an Exception subclass) when
        # a required argument is missing or malformed. Catch it explicitly,
        # alongside Exception, so a parse failure returns None for the caller
        # to handle rather than terminating the process — log_dispatch must
        # never abort /work.
        return None

    if unknown:
        return None

    if ns.dispatch_type not in VALID_DISPATCH_TYPES:
        return None

    if ns.outcome not in VALID_OUTCOMES:
        return None

    try:
        duration_s = float(ns.duration_s)
    except (ValueError, TypeError):
        return None

    try:
        attempt = int(ns.attempt)
    except (ValueError, TypeError):
        return None

    return {
        "prd": ns.prd,
        "task_id": ns.task_id,
        "task_name": ns.task_name,
        "dispatch_type": ns.dispatch_type,
        "model": ns.model,
        "outcome": ns.outcome,
        "duration_s": duration_s,
        "attempt": attempt,
    }


def main() -> None:
    try:
        loop_val = os.environ.get("_AUTOPILOT_LOOP", "")
        if not loop_val:
            return

        args = _parse_args(sys.argv[1:])
        if args is None:
            return

        autopilot_dir = find_autopilot_dir(Path.cwd())
        if autopilot_dir is None:
            return

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        record = {
            "ts": ts,
            "prd": args["prd"],
            "task_id": args["task_id"],
            "task_name": args["task_name"],
            "dispatch_type": args["dispatch_type"],
            "model": args["model"],
            "outcome": args["outcome"],
            "duration_s": args["duration_s"],
            "attempt": args["attempt"],
        }
        line = json.dumps(record) + "\n"
        log_path = autopilot_dir / "dispatch-log.jsonl"
        fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line.encode())
        finally:
            os.close(fd)
    except Exception:
        pass


if __name__ == "__main__":
    main()
