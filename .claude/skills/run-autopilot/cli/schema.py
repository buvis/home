#!/usr/bin/env python3
"""schema.py - whole-state shape/type/enum validation for autopilot state.json.

Every field is optional: `validate({})` passes, and any documented field may
be absent (statectl's `del` verb removes fields outright and must still
produce a valid state). Rules are "if present, must match" only - never
"must be present". Unknown top-level fields are tolerated so state.json can
grow ahead of this validator without breaking it.

`validate()` raises SchemaError on the FIRST offending known field, in field
declaration order, naming the field and its offending value. `version_status()`
separately classifies the `schema_version` stamp so callers can detect drift
without failing whole-state validation on it.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = 1

# Bound on the repr() embedded in a SchemaError message: a malformed giant
# value (e.g. a 100K-char string where an int was required) must never be
# interpolated in full. Values whose repr is under the bound are unaffected.
_MAX_VALUE_REPR = 200


class SchemaError(Exception):
    """Raised by validate() naming the offending field path and value."""


def _bounded_repr(value: Any) -> str:
    """repr(value), truncated so a giant/malformed value can't blow up the
    message. Under the bound, identical to plain repr()."""
    text = repr(value)
    if len(text) <= _MAX_VALUE_REPR:
        return text
    return f"{text[:_MAX_VALUE_REPR]}...({len(text)} chars)"


_ENUMS: dict[str, set[str]] = {
    "phase": {"build", "review", "done", "paused", "blind", "doubt"},
    "next_phase": {"build", "review", "done", "paused", ""},
    "catchup_mode": {"run", "skip", "force", "skipped"},
    "design_mode": {"run", "skip", "skipped"},
    "doubt_reviewer": {"codex", "fable"},
    "consensus_engine": {"legacy", "shadow", "workflow"},
}

_INT_FIELDS = ("cycle", "rework_cap", "tasks_total", "tasks_completed", "replan_count")

_STR_FIELDS = ("prd", "work_start_sha", "repo_root", "design_doc")

_LIST_FIELDS = (
    "tasks",
    "phases_completed",
    "autonomous_decisions",
    "deferred_decisions",
    "review_cycles",
    "doubts",
)


def require(value: Any, type_: type, field: str) -> None:
    """Raise SchemaError naming `field` unless isinstance(value, type_).

    Mirrors validate()'s bool-is-not-int carve-out: a bool value checked
    against type_ is int raises the int-specific message, never a bool one.
    """
    if isinstance(value, bool) and type_ is int:
        raise SchemaError(f"{field}: expected int, got {_bounded_repr(value)}")
    if not isinstance(value, type_):
        raise SchemaError(f"{field}: expected {type_.__name__}, got {_bounded_repr(value)}")


def validate(state: dict) -> None:
    """Raise SchemaError naming the first offending known field, else None."""
    if not isinstance(state, dict):
        raise SchemaError(f"state: expected dict, got {_bounded_repr(state)}")

    for field, allowed in _ENUMS.items():
        if field in state:
            try:
                invalid = state[field] not in allowed
            except TypeError:
                invalid = True
            if invalid:
                raise SchemaError(f"{field}: invalid value {_bounded_repr(state[field])}")

    for field in _INT_FIELDS:
        if field in state:
            require(state[field], int, field)

    for field in _STR_FIELDS:
        if field in state:
            require(state[field], str, field)

    for field in _LIST_FIELDS:
        if field in state:
            require(state[field], list, field)

    if "batch" in state:
        batch = state["batch"]
        if not isinstance(batch, dict):
            raise SchemaError(f"batch: expected dict, got {_bounded_repr(batch)}")
        if "id" in batch and not isinstance(batch["id"], str):
            raise SchemaError(f"batch.id: expected str, got {_bounded_repr(batch['id'])}")
        if "parks_consecutive" in batch:
            require(batch["parks_consecutive"], int, "batch.parks_consecutive")
        if "completed_prds" in batch:
            require(batch["completed_prds"], list, "batch.completed_prds")


def version_status(state: dict) -> str:
    """Classify state["schema_version"]: unstamped/current/old/future/invalid."""
    if not isinstance(state, dict):
        return "invalid"
    if "schema_version" not in state:
        return "unstamped"
    version: Any = state["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int):
        return "invalid"
    if version < 0:
        return "invalid"
    if version == SCHEMA_VERSION:
        return "current"
    if version < SCHEMA_VERSION:
        return "old"
    return "future"
