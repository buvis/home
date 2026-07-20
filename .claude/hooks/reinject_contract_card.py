"""SessionStart(compact) hook: re-anchor a compacted session to its skill contract.

Within-session compaction can drop an active skill's text mid-procedure (work is
600+ lines; run-autopilot and review-work-completion are long too), after which
the agent drifts off-contract with nothing to re-anchor it (PRD 00087 R1).

At each gate transition, work / run-autopilot / review-work-completion write a
compact "contract card" (current step, active invariants, next gate) — into the
autopilot `state.json` `contract_card` field where that world exists, or a
scratch `contract-card.md` for interactive runs. This hook, matched to the
`compact` SessionStart source ONLY (startup/resume/clear stay unmatched, so
there is no standing token cost on a normal session start), reads that card back
and re-injects it as SessionStart additionalContext.

Python, stdlib only. Fails silent: a hook must never crash the session.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def card_from_cwd(cwd: str) -> str | None:
    """The contract card for the repo rooted at `cwd`, or None.

    Prefers the autopilot `state.json` `contract_card` field; falls back to a
    scratch `contract-card.md`. Both live under `dev/local/autopilot/`.
    """
    if not cwd:
        return None
    base = Path(cwd) / "dev" / "local" / "autopilot"
    state = base / "state.json"
    if state.is_file():
        try:
            card = json.loads(state.read_text(encoding="utf-8")).get("contract_card")
        except (OSError, ValueError):
            card = None
        if isinstance(card, str) and card.strip():
            return card
    scratch = base / "contract-card.md"
    if scratch.is_file():
        try:
            text = scratch.read_text(encoding="utf-8")
        except OSError:
            text = ""
        if text.strip():
            return text
    return None


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except (ValueError, OSError):
        return
    if not isinstance(data, dict):
        return
    # Matched to `compact` in settings.json; the guard makes the hook correct
    # even if a future registration widens the matcher.
    if data.get("source") != "compact":
        return
    cwd = data.get("cwd") or os.getcwd()
    card = card_from_cwd(str(cwd))
    if not card:
        return
    envelope = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                "Contract card — re-anchoring after compaction. This is the "
                "active skill's contract; follow it, do not drift:\n\n" + card
            ),
        }
    }
    print(json.dumps(envelope))


if __name__ == "__main__":
    main()
