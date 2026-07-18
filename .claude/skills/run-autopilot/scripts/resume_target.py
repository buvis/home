"""Resume-target decision core for /run-autopilot (PRD 00047, C11).

`resume_target(state)` is the pure function that encodes the SKILL's
resume/skip contract in the three-gate vocabulary (build/review/done, plus
paused and the crash/replan stalls; legacy pre-00015 `blind`/`doubt` phase
values map to the review gate). It is the canonical executable encoding of
"given a parked state.json, what does the orchestrator do next?".

It was extracted verbatim from test_autopilot_resume.py so the resume test
imports the same function it asserts on: editing this logic now flips a test
red, rather than the test re-implementing the contract in isolation. The
SKILL.md Phase 0 / State Management resume prose names this module as the
canonical encoding of the phase + phases_completed + artifact resume decision.
"""

from __future__ import annotations


def _first_non_completed_task(tasks: list[dict]) -> dict | None:
    for task in tasks:
        if task.get("status") != "completed":
            return task
    return None


def _review_resume_target(state: dict) -> str:
    """Resume target for the review gate, driven by phases_completed."""
    completed = state.get("phases_completed", [])
    if "review" not in completed:
        return "run review loop"
    return "skip review -> done"


def resume_target(state: dict) -> str:
    """Return a string describing the next action for a parked state.

    Resolution order encodes the SKILL contract:

    1. Crash-recovery and replan stalls win first (stall_reason).
    2. Cap-pause (phase=="paused" + cap_pause_reason) gets its own handler.
    3. Review resume is driven by phases_completed; legacy `blind`/`doubt`
       phases (pre-00015 state files) run one full review cycle instead —
       the lenses that replaced those legs must not be skipped.
    4. Build re-entry is by ARTIFACT (capsule freshness, tasks-exist,
       all-done) — never a granular catchup/planning/work cascade.
    """
    stall = state.get("stall_reason") or {}
    stalled = stall.get("stalled")

    # Crash / replan stalls are checked before any phase routing.
    if stalled == "escalation_exhausted":
        return "crash-recovery at selection"
    if stalled == "subagent_prompt_overrun":
        return "replan: clear tasks, re-enter build at planning, write replan-context.md"

    phase = state.get("phase", "")

    if phase == "paused":
        if state.get("cap_pause_reason"):
            return "cap-pause resume handler: present unresolved findings, branch resume/abandon"
        return "paused: await user"

    if phase in ("blind", "doubt"):
        # Legacy pre-00015 values: the standalone legs are gone; run one full
        # review cycle (all lenses) rather than skipping their scrutiny.
        return "run review loop"

    if phase == "review":
        return _review_resume_target(state)

    if phase == "build":
        tasks = state.get("tasks", [])
        if tasks:
            pending = _first_non_completed_task(tasks)
            if pending is None:
                return "all tasks done -> review gate"
            return f"/work continues at first non-completed task {pending.get('id')}"
        # No tasks yet: planning has not produced a list.
        if state.get("capsule_fresh"):
            return "skip catchup -> planning"
        return "build: catchup then planning"

    return f"unknown phase: {phase}"


def park_decision(marker: dict | None, wip_filenames: list[str],
                  parks_consecutive: int) -> str:
    """Decide what Phase 0 does with a park-requested marker.

    Returns one of:
      "no marker"                         -> fall through to normal selection
      "malformed marker -> ignore"        -> marker present, no usable .prd
      "stale marker -> ignore"            -> named PRD not in wip/
      "park <prd> -> systemic halt"       -> park, but this is the 2nd+ consecutive park
      "park <prd> -> continue batch"      -> park and pick the next PRD
    """
    if marker is None:
        return "no marker"

    prd = marker.get("prd")
    if not prd:
        return "malformed marker -> ignore"

    if prd not in wip_filenames:
        return "stale marker -> ignore"

    if parks_consecutive >= 1:
        return f"park {prd} -> systemic halt"
    return f"park {prd} -> continue batch"
