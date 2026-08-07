"""resume.py - the resume/park decision cores for /run-autopilot.

Absorbed VERBATIM from `scripts/resume_target.py` (PRD 00047 C11, PRD 00089
Phase 0). Both functions return strings and those strings are test-bound:
`scripts/test_autopilot_resume.py` and `scripts/test_golden_contracts.py`
assert on them, so a reworded return is a behavior change, not a cosmetic one.

`scripts/resume_target.py` is now a shim re-exporting these two names, which
is why the module docstring's history lives here rather than there.

`resume_target(state)` is the pure function that encodes the SKILL's
resume/skip contract in the three-gate vocabulary (build/review/done, plus
paused and the crash/replan stalls; legacy pre-00015 `blind`/`doubt` phase
values map to the review gate). It is the canonical executable encoding of
"given a parked state.json, what does the orchestrator do next?".

The schema-version signal the Phase-0 contract pairs with a resume is the
CLI's job, not this module's: `autopilot resume-target` runs the version
preflight before printing a target, so an old/future state.json is surfaced
rather than resumed blindly. Keeping it out of here preserves the
string-returning contract above.
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
    if "review" in completed:
        return "skip review -> done"
    cycle = state.get("cycle", 1)
    return f"run review loop at cycle {cycle}"


def resume_target(state: dict) -> str:
    """Return a string describing the next action for a parked state.

    Resolution order encodes the SKILL contract:

    1. A durable stall_op intent (do_stall's protocol) wins first — a stall
       interrupted mid-flight must be reconciled before any other resume
       branch runs.
    2. Crash-recovery and replan stalls run next (stall_reason).
    3. Cap-pause (phase=="paused" + cap_pause_reason) gets its own handler.
    4. Review resume is driven by phases_completed; legacy `blind`/`doubt`
       phases (pre-00015 state files) run one full review cycle instead —
       the lenses that replaced those legs must not be skipped.
    5. Build re-entry is by ARTIFACT (capsule freshness, tasks-exist,
       all-done) — never a granular catchup/planning/work cascade.
    """
    stall_op = state.get("stall_op")
    if stall_op:
        op_id = stall_op.get("op_id") if isinstance(stall_op, dict) else None
        stall_prd = stall_op.get("prd") if isinstance(stall_op, dict) else None
        op_id = op_id if isinstance(op_id, str) else "unknown"
        stall_prd = stall_prd if isinstance(stall_prd, str) else "unknown"
        return f"reconcile stall {op_id} for {stall_prd}"

    stall = state.get("stall_reason") or {}
    stalled = stall.get("stalled")

    # Crash / replan stalls are checked before any phase routing.
    if stalled == "escalation_exhausted":
        return "crash-recovery at selection"
    if stalled == "subagent_prompt_overrun":
        return (
            "replan: clear tasks, re-enter build at planning, write replan-context.md"
        )

    phase = state.get("phase", "")

    if phase == "paused":
        if state.get("cap_pause_reason"):
            return "cap-pause resume handler: present unresolved findings, branch resume/abandon"
        return "paused: await user"

    if phase in ("blind", "doubt"):
        # Legacy pre-00015 values: the standalone legs are gone; run one full
        # review cycle (all lenses) rather than skipping their scrutiny.
        return f"run review loop at cycle {state.get('cycle', 1)}"

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


def park_decision(
    marker: dict | None, wip_filenames: list[str], parks_consecutive: int
) -> str:
    """Decide what Phase 0 does with a park-requested marker.

    Returns one of:
      "no marker"                         -> fall through to normal selection
      "malformed marker -> ignore"        -> marker present, no usable .prd
      "stale marker -> ignore"            -> named PRD not in wip/
      "park <prd> -> systemic halt"       -> park, but this is the 2nd+ consecutive park
      "park <prd> -> continue batch"      -> park and pick the next PRD

    `parks_consecutive` is the PRE-increment count (the value before this park is
    counted). `>= 1` here therefore means this park makes it the 2nd+ consecutive
    — equivalent to the Phase 0 handler's post-increment `>= 2` systemic-halt
    check. A caller must pass the pre-increment value.
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
