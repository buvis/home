#!/usr/bin/env python3
"""policy.py - plan-size policy for unattended runs (F5).

Exposes:
    LOOP_TASK_CEILING
        Task-count ceiling above which a PRD is too big to finish in one
        unattended run.
    plan_over_ceiling(state, ceiling=LOOP_TASK_CEILING) -> (over, count)
        PURE. `count` is always len(state["tasks"]) computed here, never a
        caller-supplied number: a model that miscounts its own plan is the
        exact failure this gate exists to catch. A missing or non-list
        "tasks" counts as 0 - nothing planned yet is not oversized.

Origin: the 2026-07-28 loop evaluation, fix F5. PRD 00077 planned to 28
tasks, then burned 15 sessions / 21.5h / $351 across three wall-clock cap
kills without converging, and halted the batch for four days. PRD 00071
(22 tasks) did land, so the ceiling is deliberately conservative rather
than fitted to those two points - it stalls for a human, it never refuses
to plan.
"""

from __future__ import annotations

LOOP_TASK_CEILING = 15


def plan_over_ceiling(
    state: dict, ceiling: int = LOOP_TASK_CEILING
) -> tuple[bool, int]:
    """Return (over_ceiling, task_count) for `state`'s task snapshot."""
    tasks = state.get("tasks")
    count = len(tasks) if isinstance(tasks, list) else 0
    return count > ceiling, count
