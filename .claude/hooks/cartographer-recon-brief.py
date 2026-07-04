#!/usr/bin/env python3
"""cartographer-recon-brief: inject a <=1KB atlas excerpt per (repo, UTC-day)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import _lib_cartographer

GROUNDING_HEADER = (
    "Atlas for this repo (consult before editing). Before adding new code: "
    "know the role of the file you touch, find two existing files with "
    "similar shape, and use a declared extension point or justify a new one."
)
NO_ATLAS_LINE = "No atlas for this repo yet — run `/survey` to generate one."
STALE_WARNING = "\u26a0 atlas is stale - recommend /survey --refresh"
_STORE_PATH = Path.home() / ".claude" / "cache" / "cartographer" / "recon" / "injected.json"


def _load_store(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_store(path: Path, store: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(store, fh)
        os.replace(tmp, path)
    except OSError as exc:
        print(f"[cartographer-recon] store write failed: {exc}", file=sys.stderr)


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
        if not isinstance(data, dict):
            return
        cwd = data.get("cwd", "")
        session_id = data.get("session_id", "")
        repo_hash, _name, _remote = _lib_cartographer.project_hash(cwd)
        if repo_hash == "global":
            return
        store = _load_store(_STORE_PATH)
        today = datetime.now(timezone.utc).date().isoformat()
        if store.get(repo_hash) == today:
            return
        atlas_path = _lib_cartographer.atlas_dir(repo_hash) / "atlas.md"
        stale = False
        if atlas_path.is_file():
            try:
                atlas_text = atlas_path.read_text(encoding="utf-8")
            except Exception:
                atlas_text = ""
            excerpt = atlas_text.encode("utf-8")[:1024].decode("utf-8", "ignore")
            additional_context = GROUNDING_HEADER + "\n\n" + excerpt
            atlas_excerpt_bytes = len(excerpt.encode("utf-8"))
            decision = "inject"
            if (atlas_path.parent / "staleness.flag").is_file():
                additional_context += "\n\n" + STALE_WARNING
                stale = True
        else:
            additional_context = NO_ATLAS_LINE
            atlas_excerpt_bytes = 0
            decision = "atlas-missing"
        envelope = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": additional_context,
            }
        }
        print(json.dumps(envelope))
        store[repo_hash] = today
        _save_store(_STORE_PATH, store)
        _lib_cartographer.append_audit({
            "session": session_id,
            "phase": "recon",
            "decision": decision,
            "repo_hash": repo_hash,
            "atlas_excerpt_bytes": atlas_excerpt_bytes,
            "stale": stale,
        })
    except Exception:
        return


if __name__ == "__main__":
    main()
