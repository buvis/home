"""Rationalization catalog for the Echo deny envelope.

Extracted from `cartographer-echo.py` (`# --- two-attempt deny gate ---`,
PRD 00158). Parses `~/.claude/rules-library/rationalizations.md` once per
process into `{excuse: (why, counter, triggers)}` and picks the first entry
whose trigger terms substring-match a duplicate symbol (PRD 00157).

Tests patch `_RATIONALIZATIONS_PATH` and `_RATIONALIZATIONS_CACHE` on THIS
module. Stdlib only. Python 3.10+.
"""

from __future__ import annotations

import re
from pathlib import Path

_RATIONALIZATIONS_PATH: Path = (
    Path.home() / ".claude" / "rules-library" / "rationalizations.md"
)

_RATIONALIZATIONS_CACHE: dict[str, tuple[str, str, tuple[str, ...]]] | None = None


def _load_rationalizations() -> dict[str, tuple[str, str, tuple[str, ...]]]:
    """Parse the rationalizations catalog into {excuse: (why, counter, triggers)}
    once per process. Triggers come from the entry's own `- **Triggers**:`
    bullet; an entry without one parses but is never auto-cited (PRD 00157)."""
    global _RATIONALIZATIONS_CACHE
    if _RATIONALIZATIONS_CACHE is not None:
        return _RATIONALIZATIONS_CACHE

    out: dict[str, tuple[str, str, tuple[str, ...]]] = {}
    try:
        text = _RATIONALIZATIONS_PATH.read_text(encoding="utf-8")
    except OSError:
        _RATIONALIZATIONS_CACHE = out
        return out

    header_re = re.compile(r"^###\s+\"([^\"]+)\"\s*$", re.MULTILINE)
    why_re = re.compile(
        r"-\s*\*\*Why it's wrong\*\*:\s*(.+?)(?:\n-|\n\n|\Z)",
        re.DOTALL,
    )
    counter_re = re.compile(
        r"-\s*\*\*Counter-action\*\*:\s*(.+?)(?:\n-|\n\n|\Z)",
        re.DOTALL,
    )
    # Single-line by design: an empty bullet must yield (), never swallow the
    # next bullet's text the way the DOTALL idiom above would.
    triggers_re = re.compile(r"-\s*\*\*Triggers\*\*:[ \t]*([^\n]*)")

    matches = list(header_re.finditer(text))
    for i, m in enumerate(matches):
        excuse = m.group(1).strip()
        section_start = m.end()
        section_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[section_start:section_end]
        why_m = why_re.search(section)
        counter_m = counter_re.search(section)
        trig_m = triggers_re.search(section)
        raw_triggers = trig_m.group(1) if trig_m else ""
        triggers = tuple(
            t.strip().lower() for t in raw_triggers.split(",") if t.strip()
        )
        if why_m and counter_m:
            out[excuse] = (
                " ".join(why_m.group(1).split()),
                " ".join(counter_m.group(1).split()),
                triggers,
            )

    _RATIONALIZATIONS_CACHE = out
    return out


def _pick_rationalization(symbols: list[str]) -> tuple[str, str, str] | None:
    """Return (excuse, why, counter) for the first catalog entry (file order)
    whose trigger terms substring-match a duplicate symbol, else None.

    No match means no rationalization: an irrelevant excuse is worse than
    none, and the deny envelope renders correctly without one.
    """
    rats = _load_rationalizations()
    if not rats:
        return None
    lows = [sym.lower() for sym in symbols]
    for excuse, (why, counter, triggers) in rats.items():
        if any(t in low for t in triggers for low in lows):
            return (excuse, why, counter)
    return None
