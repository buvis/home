"""Stop hook: track per-session token usage and estimated cost.

Replaces ~/.claude/hooks/track-cost.sh. Reads transcript_path from the Stop
hook stdin payload, parses JSONL entries, deduplicates assistant messages by
message.id, sums token usage, and appends a single JSONL row to
~/.claude/metrics/costs.jsonl.

Stdlib only. Cost arithmetic uses Decimal so the formatted output matches the
bash awk template byte-for-byte on shared fixtures.
"""

import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import read_input  # noqa: E402

METRICS_DIR = Path.home() / ".claude" / "metrics"
COSTS_FILE = METRICS_DIR / "costs.jsonl"

# $/Mtok, verified 2026-07-19 against current docs (haiku 4.5 = 1/5,
# opus 4.6+ = 5/25, sonnet = 3/15, fable/mythos 5 = 10/50). cw is the
# 5-minute-TTL cache-write rate (1.25x input); 1h-TTL writes bill 2x, so cw
# underestimates sessions pinned to the long TTL.
PRICING: dict[str, dict[str, Decimal]] = {
    "haiku": {
        "in": Decimal("1.00"),
        "cw": Decimal("1.25"),
        "cr": Decimal("0.10"),
        "out": Decimal("5.00"),
    },
    "opus": {
        "in": Decimal("5.00"),
        "cw": Decimal("6.25"),
        "cr": Decimal("0.50"),
        "out": Decimal("25.00"),
    },
    "sonnet": {
        "in": Decimal("3.00"),
        "cw": Decimal("3.75"),
        "cr": Decimal("0.30"),
        "out": Decimal("15.00"),
    },
    "fable": {
        "in": Decimal("10.00"),
        "cw": Decimal("12.50"),
        "cr": Decimal("1.00"),
        "out": Decimal("50.00"),
    },
}

ONE_MILLION = Decimal("1000000")


def detect_tier(model: str) -> str:
    if "haiku" in model:
        return "haiku"
    if "opus" in model:
        return "opus"
    if "fable" in model or "mythos" in model:
        return "fable"
    if "sonnet" in model:
        return "sonnet"
    return "unknown"


def deduplicate(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group by message.id, keep the LAST occurrence (matches jq map(last))."""
    last_by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for entry in entries:
        msg = entry.get("message") or {}
        mid = msg.get("id")
        if mid is None:
            continue
        if mid not in last_by_id:
            order.append(mid)
        last_by_id[mid] = entry
    return [last_by_id[mid] for mid in order]


def aggregate(deduped: list[dict[str, Any]]) -> tuple[str, int, int, int, int]:
    """Sum token counts and pick the last non-empty model string. Returns model='' if empty."""
    in_tok = 0
    cw_tok = 0
    cr_tok = 0
    out_tok = 0
    model = ""
    for entry in deduped:
        msg = entry.get("message") or {}
        usage = msg.get("usage") or {}
        in_tok += int(usage.get("input_tokens") or 0)
        cw_tok += int(usage.get("cache_creation_input_tokens") or 0)
        cr_tok += int(usage.get("cache_read_input_tokens") or 0)
        out_tok += int(usage.get("output_tokens") or 0)
        candidate = msg.get("model") or ""
        if candidate:
            model = candidate
    return model, in_tok, cw_tok, cr_tok, out_tok


def parse_transcript(path: Path) -> list[dict[str, Any]]:
    """Read JSONL, return assistant entries that have message.usage."""
    out: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        if entry.get("type") != "assistant":
            continue
        msg = entry.get("message") or {}
        if not isinstance(msg, dict):
            continue
        if "usage" not in msg or not msg.get("usage"):
            continue
        out.append(entry)
    return out


def cost_usd(in_tok: int, cw: int, cr: int, out: int, tier: str) -> str:
    rates = PRICING.get(tier)
    if rates is None:
        return "null"
    total = (
        Decimal(in_tok) * rates["in"]
        + Decimal(cw) * rates["cw"]
        + Decimal(cr) * rates["cr"]
        + Decimal(out) * rates["out"]
    ) / ONE_MILLION
    return f"{total:.5f}"


def build_row(
    *,
    ts: str,
    sid: str,
    model: str,
    tier: str,
    in_tok: int,
    cw: int,
    cr: int,
    out: int,
    cost: str,
    nested: bool = False,
) -> str:
    """Emit JSONL row matching the bash printf template byte-for-byte.

    cost_usd is unquoted in the bash output (raw JSON number), so we build the
    string literally rather than going through json.dumps which would force
    fixed-width float formatting. Nested dispatches (CLAUDE_NESTED children,
    e.g. sonnet-run.sh reviewers) are tagged so cost analyses can split
    reviewer spend from interactive spend; the rows are real API spend, never
    duplicates, so they are tagged rather than dropped.
    """
    return (
        '{"ts":"' + ts + '","sid":"' + sid + '","model":"' + model + '",'
        '"tier":"' + tier + '",'
        + ('"nested":true,' if nested else '')
        + '"in":' + str(in_tok) + ','
        '"cache_write":' + str(cw) + ','
        '"cache_read":' + str(cr) + ','
        '"out":' + str(out) + ','
        '"cost_usd":' + cost + '}'
    )


def main() -> None:
    payload = read_input()
    transcript = str(payload.get("transcript_path") or "")
    sid = str(payload.get("session_id") or "")

    if not transcript:
        return
    transcript_path = Path(transcript)
    if not transcript_path.is_file():
        return

    entries = parse_transcript(transcript_path)
    if not entries:
        return

    deduped = deduplicate(entries)
    model, in_tok, cw, cr, out_tok = aggregate(deduped)
    if not model:
        return

    tier = detect_tier(model)
    if tier == "unknown":
        sys.stderr.write(f"track_cost: no pricing tier for model {model!r}; cost_usd=null\n")
    cost = cost_usd(in_tok, cw, cr, out_tok, tier)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    row = build_row(
        ts=ts, sid=sid, model=model, tier=tier,
        in_tok=in_tok, cw=cw, cr=cr, out=out_tok, cost=cost,
        nested=bool(os.environ.get("CLAUDE_NESTED")),
    )
    with COSTS_FILE.open("a", encoding="utf-8") as fh:
        fh.write(row + "\n")


def run(payload):
    """Dispatcher entry point (hooks/dispatch.py). dispatch._invoke already wraps
    this in _common.capture_main, which feeds `payload` via stdin and traps the
    exit, so run() is RAW: call main() and return its result. `return` preserves
    an int exit code; `payload` is unused here (main() reads it from the stdin
    capture)."""
    return main()


if __name__ == "__main__":
    main()
