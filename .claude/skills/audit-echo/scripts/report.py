#!/usr/bin/env python3
"""audit-echo report generator.

Reads ~/.claude/cartographer/audit.jsonl, keeps `phase == "echo"` events, and
prints the aggregates the audit-echo skill turns into a findings report:
windows (7d/28d), top-noise symbols, false-positive samples, per-language deny
rates, and the skip distribution.

Read-only. Never mutates the audit log.
"""
from __future__ import annotations

import datetime
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

AUDIT_PATH = Path.home() / ".claude" / "cartographer" / "audit.jsonl"
WINDOW_TOOLS = ("Edit", "Write", "MultiEdit", "Bash", "mcp__serena__*")
LANG_BY_EXT = {
    ".py": "py", ".ts": "ts", ".tsx": "ts", ".js": "js", ".jsx": "js",
    ".rs": "rust", ".go": "go",
}
SKIP_REASONS = (
    "settings", "large-file", "no-tree-sitter", "test-file", "unsupported-ext",
    "mcp-unsupported", "ripgrep-timeout", "tree-sitter-parse-failed",
)
# Timezone-aware sort fallback: event timestamps are aware, so a naive
# datetime.min would raise TypeError when an event is missing its `ts`.
_EPOCH = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)


def _parse_ts(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _tool_key(tool: str | None) -> str:
    if tool in WINDOW_TOOLS:
        return tool
    if tool and tool.startswith("mcp__serena__"):
        return "mcp__serena__*"
    return tool or "<none>"


def load_echo_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events: list[dict] = []
    with path.open() as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("phase") == "echo":
                event["_ts"] = _parse_ts(event.get("ts"))
                events.append(event)
    return events


def print_windows(events: list[dict], now: datetime.datetime) -> None:
    print("=== Windows (decision x tool) ===")
    for days in (7, 28):
        cutoff = now - datetime.timedelta(days=days)
        window = [e for e in events if e["_ts"] and e["_ts"] >= cutoff]
        grid: dict[str, Counter] = defaultdict(Counter)
        for event in window:
            grid[event.get("decision")][_tool_key(event.get("tool"))] += 1
        print(f"-- {days}d (n={len(window)}) --")
        for decision in ("allow", "deny", "skip"):
            row = grid.get(decision, Counter())
            cells = {col: row[col] for col in WINDOW_TOOLS if row[col]}
            print(f"  {decision:6} {cells}")


def sessions(events: list[dict]) -> dict[str, list[dict]]:
    by_session: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        by_session[event.get("session")].append(event)
    for items in by_session.values():
        items.sort(key=lambda e: e["_ts"] or _EPOCH)
    return by_session


def analyze_denies(
    by_session: dict[str, list[dict]],
) -> tuple[int, int, Counter, Counter, list[tuple]]:
    """Return (deny_total, second_attempt, noise, noise_second, fp_samples).

    A deny is "overridden" when a later allow in the same session carries
    `reason == "second-attempt"` with the same file and symbol set. That allow
    is the hook's own retry signal (emitted only when a prior deny's deny_key
    matches), so it is the authoritative override marker — not a heuristic.
    Each retry allow is consumed once so two identical denies need two retries.
    """
    deny_total = 0
    second_attempt = 0
    noise: Counter = Counter()
    noise_second: Counter = Counter()
    fp_samples: list[tuple] = []
    for events in by_session.values():
        retries = [
            {"i": i, "file": e.get("file"), "syms": frozenset(e.get("symbols") or [])}
            for i, e in enumerate(events)
            if e.get("decision") == "allow" and e.get("reason") == "second-attempt"
        ]
        used: set[int] = set()
        for i, event in enumerate(events):
            if event.get("decision") != "deny":
                continue
            deny_total += 1
            symbols = event.get("symbols") or []
            sym_key = ",".join(symbols) if symbols else "<none>"
            target = event.get("file")
            noise[(sym_key, target)] += 1
            key_syms = frozenset(symbols)
            retry = next(
                (
                    r for r in retries
                    if r["i"] > i and r["i"] not in used
                    and r["file"] == target and r["syms"] == key_syms
                ),
                None,
            )
            if retry is not None:
                used.add(retry["i"])
                second_attempt += 1
                noise_second[(sym_key, target)] += 1
                matches = event.get("matches") or []
                first = matches[0] if matches else ""
                sample = first.get("snippet") or first if isinstance(first, dict) else first
                fp_samples.append((event["_ts"], sym_key, target, sample))
    return deny_total, second_attempt, noise, noise_second, fp_samples


def print_noise(
    deny_total: int, second_attempt: int, noise: Counter, noise_second: Counter,
) -> None:
    print("\n=== Noise (top deny symbols) ===")
    ratio = f"{100 * second_attempt / deny_total:.0f}%" if deny_total else "n/a"
    print(f"deny_total={deny_total} second-attempt-allow={second_attempt} ({ratio})")
    for key, count in noise.most_common(10):
        sym, target = key
        seconds = noise_second.get(key, 0)
        pct = 100 * seconds / count if count else 0
        name = os.path.basename(target) if target else target
        print(f"  {count:3}x 2nd={seconds}({pct:.0f}%)  {sym[:40]:40}  {name}")


def print_fp_samples(fp_samples: list[tuple]) -> None:
    print("\n=== False-positive samples (most recent, max 20) ===")
    fp_samples.sort(key=lambda x: x[0] or _EPOCH, reverse=True)
    for _ts, sym, target, match in fp_samples[:20]:
        name = os.path.basename(target) if target else target
        print(f"  {sym[:30]:30} | {name} | {str(match)[:50]}")


def print_languages(events: list[dict]) -> None:
    print("\n=== Per-language deny rates ===")
    by_lang: dict[str, Counter] = defaultdict(Counter)
    for event in events:
        ext = os.path.splitext(event.get("file") or "")[1]
        by_lang[LANG_BY_EXT.get(ext, "other")][event.get("decision")] += 1
    total_deny = sum(c["deny"] for c in by_lang.values())
    total = sum(sum(c.values()) for c in by_lang.values())
    mean = total_deny / total if total else 0
    for lang, counts in sorted(by_lang.items(), key=lambda kv: -sum(kv[1].values())):
        n = sum(counts.values())
        rate = counts["deny"] / n if n else 0
        flag = "  <-- >1.5x mean" if mean and rate > 1.5 * mean and counts["deny"] else ""
        print(
            f"  {lang:6} n={n:6} allow={counts['allow']:6} "
            f"deny={counts['deny']:4} skip={counts['skip']:6} "
            f"deny_rate={rate * 100:.2f}%{flag}"
        )
    print(f"  overall mean deny_rate={mean * 100:.3f}% "
          "(note: diluted by Bash; compare code files to each other)")


def print_skips(events: list[dict]) -> None:
    print("\n=== Skip distribution ===")
    total = len(events)
    reasons = Counter(
        e.get("reason") for e in events if e.get("decision") == "skip"
    )
    for reason in SKIP_REASONS:
        count = reasons.get(reason, 0)
        if count:
            print(f"  {reason}: {count} ({100 * count / total:.2f}% of all)")
    other = {r: c for r, c in reasons.items() if r not in SKIP_REASONS}
    if other:
        print(f"  other reasons: {other}")


def main() -> int:
    events = load_echo_events(AUDIT_PATH)
    if not events:
        print("LOW: no Echo events recorded in window "
              f"(audit log: {AUDIT_PATH})")
        return 0
    timestamps = [e["_ts"] for e in events if e["_ts"]]
    now = max(timestamps) if timestamps else datetime.datetime.now(datetime.timezone.utc)
    decisions = Counter(e.get("decision") for e in events)
    print(f"audit log: {AUDIT_PATH}")
    print(f"total echo events: {len(events)}")
    if timestamps:
        print(f"ts range: {min(timestamps).isoformat()} -> {max(timestamps).isoformat()}")
    print(f"allow/deny/skip: {decisions['allow']}/{decisions['deny']}/{decisions['skip']}\n")

    print_windows(events, now)
    by_session = sessions(events)
    deny_total, second_attempt, noise, noise_second, fp_samples = analyze_denies(by_session)
    print_noise(deny_total, second_attempt, noise, noise_second)
    print_fp_samples(fp_samples)
    print_languages(events)
    print_skips(events)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
