#!/usr/bin/env python3
"""cli/status.py - plain-text `autopilot status` (PRD 00107).

Pure function of state.json: one screen of what the loop is doing, for a
shell or a headless log. The watch/dashboard surface stays with tracon
(scripts/tracon/); this is deliberately plain (the discovery's open
question resolved to "plain status only" for this PRD).

Missing fields degrade to `?` or drop their line - a status surface must
render whatever state exists, never crash on a legacy or partial file.
"""

from __future__ import annotations


def render_status(state: dict) -> str:
    prd = state.get("prd") or "(none)"
    phase = state.get("phase", "?")
    next_phase = state.get("next_phase", "?")
    lines = [
        f"PRD:    {prd}",
        f"Phase:  {phase} -> next: {next_phase or '(drained)'}",
        f"Cycle:  {state.get('cycle', '?')}/{state.get('rework_cap', '?')} (rework cap)",
        f"Tasks:  {state.get('tasks_completed', '?')}/{state.get('tasks_total', '?')} completed",
    ]
    batch = state.get("batch") or {}
    if batch:
        completed = batch.get("completed_prds") or []
        lines.append(
            f"Batch:  {batch.get('id', '?')} — {len(completed)} PRD(s) completed"
        )

    stall = state.get("stall_reason") or {}
    if stall:
        lines.append(
            f"STALL:  {stall.get('stalled', '?')} (task: {stall.get('task', '-')})"
        )
    cap_pause = state.get("cap_pause_reason") or {}
    if cap_pause:
        unresolved = len(cap_pause.get("unresolved_findings") or [])
        lines.append(
            f"CAP-PAUSE: cycle {cap_pause.get('cycle', '?')} at cap "
            f"{cap_pause.get('cap', '?')}, {unresolved} unresolved finding(s)",
        )
    pause = state.get("pause_reason") or {}
    if pause:
        lines.append(f"PAUSED: {pause.get('site', '?')} — {pause.get('detail', '')}")
    if state.get("needs_attention"):
        lines.append("FLAG:   needs_attention")
    return "\n".join(lines)
