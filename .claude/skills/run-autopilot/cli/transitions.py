#!/usr/bin/env python3
"""transitions.py - (phase, outcome) -> the next phase AND its field effects.

PURE: every function returns a new state dict and touches no disk.

    TRANSITIONS                  the recognized (phase, outcome) pairs
    apply(state, outcome)        -> the advanced state
    next_phase(phase, outcome)   -> the value the transition writes to
                                    state["next_phase"]
    UnknownTransition            raised for any pair not in the table

The point of the table is that a transition owns EVERY field effect it
mandates, in one commit. Convergence appends `"review"` to `phases_completed`
because it is convergence - not because a caller remembered to pass a flag.
Rework increments `cycle` and clears `rework_task_ids` together, closing the
crash window `references/phase-review.md` documents between its four separate
`statectl set` writes: the increment is what the Phase 5 cap gate reads, and
losing it once let a loop run past its cap.

The caller still supplies DATA the transition cannot derive. `tasks_done`
advances the phase; `state.tasks` is maintained by the statectl task verbs as
work proceeds, so no transition rewrites it.
"""

from __future__ import annotations

from . import records, schema


class UnknownTransition(Exception):
    """No row in TRANSITIONS for this (phase, outcome) pair."""


def _to_review(state: dict) -> dict:
    """build -> review. `phases_completed` is untouched: the build gate
    leaves no membership marker."""
    return {**state, "phase": "review", "next_phase": "review"}


def _rework(state: dict) -> dict:
    """review -> review. The cycle increment and the rework-list clear land
    in the same commit, so a crash cannot keep one without the other."""
    cycle = state.get("cycle", 1)
    schema.require(cycle, int, "cycle")
    return {
        **state,
        "phase": "review",
        "next_phase": "review",
        "cycle": cycle + 1,
        "rework_task_ids": [],
    }


def _converged(state: dict) -> dict:
    """review -> done, appending the `"review"` convergence marker.

    Appends only when absent: a retry after a crash between the commit and
    the banner must not double the marker.
    """
    completed = state.get("phases_completed", [])
    schema.require(completed, list, "phases_completed")
    if "review" not in completed:
        completed = [*completed, "review"]
    return {
        **state,
        "phase": "done",
        "next_phase": "done",
        "phases_completed": completed,
    }


def _more_prds(state: dict) -> dict:
    """done -> build for the next PRD. The per-PRD reset IS this transition's
    effect set - `records.PER_PRD_RESET_FIELDS` stays the one authoritative
    list, and it already writes phase/next_phase and empties
    `phases_completed`."""
    return records.reset_prd_fields(state)


def _drained(state: dict) -> dict:
    """Batch end. The EMPTY `next_phase` is what the wrapper reads as drained;
    the literal string "done" is a phase with work queued after it and spins
    the loop until the safety kill."""
    return {**state, "phase": "done", "next_phase": ""}


TRANSITIONS = {
    ("build", "tasks_done"): _to_review,
    ("review", "rework"): _rework,
    ("review", "converged"): _converged,
    ("done", "more_prds"): _more_prds,
    ("done", "drained"): _drained,
    # A batch can also drain at Phase 0 selection rather than at Phase 9: the
    # "No PRDs anywhere" row is reached with phase still "build", and it needs
    # the same empty next_phase so the wrapper stops as drained, not died.
    ("build", "drained"): _drained,
}

OUTCOMES = tuple(sorted({outcome for _phase, outcome in TRANSITIONS}))


def apply(state: dict, outcome: str) -> dict:
    """Advance `state` by `outcome`, returning a new dict.

    The current phase comes from the state, never from the caller: a caller
    that supplies both halves of the pair can supply a mismatched one.
    """
    phase = state.get("phase")
    effect = TRANSITIONS.get((phase, outcome))
    if effect is None:
        raise UnknownTransition(
            f"no transition from phase {phase!r} on outcome {outcome!r}",
        )
    return effect(state)


def next_phase(phase: str, outcome: str) -> str:
    """The `next_phase` value the (phase, outcome) transition writes.

    Derived by running the transition rather than stored beside it, so the
    answer cannot drift away from what `apply` actually does.
    """
    return apply({"phase": phase}, outcome)["next_phase"]
