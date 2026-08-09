#!/usr/bin/env python3
"""cli/render_audit.py - render audit.md from state decision arrays (PRD 00107).

Pure function of state: phase-done Phase 9 step 6a renders the PRD's
`dev/local/reviews/<prd-base>-audit.md` ONCE from `autonomous_decisions`
(label `autonomous`), `deferred_decisions` (`deferred`), and `doubts`
(`doubt`) - the closed label set the decisions.md projection filters on.
Wired as `autopilot render audit`; the CLI preserves an existing file's
`Started:` stamp and derives the output path from the state file's own tree.

Entry field mapping is deterministic and tolerant (state arrays predate this
render and vary by writer): Decision <- issue|question|description,
Recommendation <- research.evidence_summary, Choice <- action|resolution|
assumption|status, Rationale <- reason|justification. Absent fields render
nothing; all-empty arrays render the header plus `no decisions recorded`.
"""

from __future__ import annotations

import re

STARTED_RE = re.compile(r"^Started: (.+)$", re.MULTILINE)

_SOURCES = (
    ("autonomous_decisions", "autonomous"),
    ("deferred_decisions", "deferred"),
    ("doubts", "doubt"),
)


def _entry(item: dict, label: str, stamp: str) -> str:
    decision = item.get("issue") or item.get("question") or item.get("description")
    research = item.get("research") or {}
    recommendation = research.get("evidence_summary")
    choice = (
        item.get("action")
        or item.get("resolution")
        or item.get("assumption")
        or item.get("status")
    )
    rationale = item.get("reason") or item.get("justification")
    lines = [f"### [{label}] {stamp}", ""]
    for name, value in (
        ("Decision", decision),
        ("Recommendation", recommendation),
        ("Choice", choice),
        ("Rationale", rationale),
    ):
        if value:
            lines.append(f"**{name}**: {value}")
            lines.append("")
    return "\n".join(lines)


def render_audit(state: dict, started: str, completed: str) -> str:
    """The full audit.md text for the current PRD."""
    prd = str(state.get("prd", ""))
    prd_base = prd.removesuffix(".md")
    counts = {key: len(state.get(key) or []) for key, _label in _SOURCES}
    header = [
        f"# Decision Audit Log: {prd_base}",
        "",
        f"PRD: `{prd}`",
        f"Started: {started}",
        f"Completed: {completed}",
        "Autonomous: {autonomous_decisions}  |  Deferred: {deferred_decisions}"
        "  |  Doubts: {doubts}".format(**counts),
        "",
    ]
    blocks = []
    for key, label in _SOURCES:
        for item in state.get(key) or []:
            if isinstance(item, dict):
                blocks.append(_entry(item, label, completed))
    if not blocks:
        return "\n".join(header + ["no decisions recorded", ""])
    return "\n".join(header) + "\n" + "\n".join(blocks)


def existing_started(text: str) -> str | None:
    """The `Started:` stamp of a previously rendered audit file, if any."""
    match = STARTED_RE.search(text)
    return match.group(1).strip() if match else None
