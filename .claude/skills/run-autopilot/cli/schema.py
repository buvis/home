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


class SchemaError(Exception):
    """Raised by validate() naming the offending field path and value."""


_ENUMS: dict[str, set[str]] = {
    "phase": {"build", "review", "done", "paused", "blind", "doubt"},
    "next_phase": {"build", "review", "done", "paused", ""},
    "catchup_mode": {"run", "skip", "force", "skipped"},
    "design_mode": {"run", "skip", "skipped"},
    "doubt_reviewer": {"codex", "fable"},
    "consensus_engine": {"legacy", "shadow", "workflow"},
}

_INT_FIELDS = ("cycle", "rework_cap", "tasks_total", "tasks_completed")

_LIST_FIELDS = (
    "tasks",
    "phases_completed",
    "autonomous_decisions",
    "deferred_decisions",
    "review_cycles",
    "doubts",
)


def validate(state: dict) -> None:
    """Raise SchemaError naming the first offending known field, else None."""
    for field, allowed in _ENUMS.items():
        if field in state and state[field] not in allowed:
            raise SchemaError(f"{field}: invalid value {state[field]!r}")

    for field in _INT_FIELDS:
        if field in state:
            value = state[field]
            if isinstance(value, bool) or not isinstance(value, int):
                raise SchemaError(f"{field}: expected int, got {value!r}")

    for field in _LIST_FIELDS:
        if field in state and not isinstance(state[field], list):
            raise SchemaError(f"{field}: expected list, got {state[field]!r}")

    if "batch" in state:
        batch = state["batch"]
        if not isinstance(batch, dict):
            raise SchemaError(f"batch: expected dict, got {batch!r}")
        if "id" in batch and not isinstance(batch["id"], str):
            raise SchemaError(f"batch.id: expected str, got {batch['id']!r}")


def version_status(state: dict) -> str:
    """Classify state["schema_version"]: unstamped/current/old/future/invalid."""
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
