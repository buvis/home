"""Stop hook: record which skills a session invoked (PRD 00086 R2).

Scans the session transcript for `Skill` tool_use blocks and appends one row
per invocation to ~/.claude/metrics/skills.jsonl:

    {"skill": "<name>", "session_id": "<id>", "ts": "<iso-utc>", "source": "loop|interactive"}

This is a numerator-only compliance counter (v1): it records how often skills
actually fire, giving brief-portfolio a monthly adherence signal. There is no
applicability denominator (how often a skill *should* have fired) — that is
out of scope. Sibling of track_cost.py's transcript parse; same dedup-by-id
discipline so a re-run over the same transcript never double-counts.

Stdlib only, self-contained. Never blocks or raises out of main — a metrics
hook must not disturb the session it observes.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

METRICS_DIR = Path.home() / ".claude" / "metrics"
SKILLS_FILE = METRICS_DIR / "skills.jsonl"


def read_stdin_json() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def skill_invocations(transcript_path: Path) -> list[tuple[str, str]]:
    """Return (tool_use_id, skill_name) for each Skill tool_use in the
    transcript, deduped by tool_use id (a re-run must not re-count)."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    try:
        text = transcript_path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict) or entry.get("type") != "assistant":
            continue
        msg = entry.get("message")
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use" or block.get("name") != "Skill":
                continue
            tool_id = block.get("id") or ""
            inp = block.get("input")
            skill = inp.get("skill") if isinstance(inp, dict) else None
            if not skill or not isinstance(skill, str):
                continue
            if tool_id and tool_id in seen:
                continue
            if tool_id:
                seen.add(tool_id)
            out.append((tool_id, skill))
    return out


def _already_recorded(session_id: str) -> set[str]:
    """(skill, tool_use_id) keys already logged for this session, so an
    idempotent re-run over the same transcript appends nothing new."""
    done: set[str] = set()
    if not SKILLS_FILE.exists():
        return done
    try:
        for raw in SKILLS_FILE.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("session_id") == session_id:
                done.add(f'{row.get("skill")}\x00{row.get("tool_use_id", "")}')
    except OSError:
        pass
    return done


def main() -> None:
    data = read_stdin_json()
    transcript_path_str = data.get("transcript_path")
    session_id = data.get("session_id") or ""
    if not isinstance(transcript_path_str, str) or not transcript_path_str:
        return
    invocations = skill_invocations(Path(transcript_path_str))
    if not invocations:
        return
    source = "loop" if os.environ.get("_AUTOPILOT_LOOP") else "interactive"
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    already = _already_recorded(session_id)
    rows = []
    for tool_id, skill in invocations:
        if f"{skill}\x00{tool_id}" in already:
            continue
        rows.append(json.dumps({
            "skill": skill, "session_id": session_id, "ts": ts,
            "source": source, "tool_use_id": tool_id,
        }))
    if not rows:
        return
    try:
        METRICS_DIR.mkdir(parents=True, exist_ok=True)
        with SKILLS_FILE.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(rows) + "\n")
    except OSError as exc:
        print(f"track_skills: write failed ({exc})", file=sys.stderr)


if __name__ == "__main__":
    main()
