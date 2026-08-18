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

import warnings
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

_COMPLETED_PRD_ENTRY_FIELDS: dict[str, type] = {
    "filename": str,
    "cycles": int,
    "autonomous_decisions": int,
    "escalated_decisions": int,
    "tasks_completed": int,
    "tasks_total": int,
}


def require(value: Any, type_: type, field: str) -> None:
    """Raise SchemaError naming `field` unless isinstance(value, type_).

    Mirrors validate()'s bool-is-not-int carve-out: a bool value checked
    against type_ is int raises the int-specific message, never a bool one.
    """
    if isinstance(value, bool) and type_ is int:
        raise SchemaError(f"{field}: expected int, got {_bounded_repr(value)}")
    if not isinstance(value, type_):
        raise SchemaError(
            f"{field}: expected {type_.__name__}, got {_bounded_repr(value)}",
        )


def _validate_task_entries(tasks: list) -> None:
    """Validate the `description`/`blocked_by` fields of each `tasks[]` entry."""
    for index, entry in enumerate(tasks):
        if not isinstance(entry, dict):
            continue
        if "description" in entry:
            require(entry["description"], str, f"tasks[{index}].description")
        if "blocked_by" in entry:
            field = f"tasks[{index}].blocked_by"
            require(entry["blocked_by"], list, field)
            for item in entry["blocked_by"]:
                require(item, int, field)


def _validate_completed_prds_entries(entries: list) -> None:
    """Validate each `batch.completed_prds[]` entry.

    A bare string is a legacy entry: `render_report.batch_summary`,
    `cli/status.py` and `scripts/tracon/model.py` all still count this list
    with a plain `len()`, and every archived batch state holds bare strings,
    so rejecting them would break three live readers and fail every archived
    state on its next write. PRD 00122 offered a choice between migrating
    legacy entries and tolerating them with a warning; the cycle-1 decision
    gate took the latter - the entry stays valid, but a warning still reaches
    the operator (never stdout, which carries machine-read output) so the
    tolerance isn't silent. A dict entry is checked field-by-field, each
    field optional. Anything else is rejected.
    """
    for index, entry in enumerate(entries):
        if isinstance(entry, str):
            warnings.warn(
                f"batch.completed_prds[{index}]: legacy bare-string entry "
                f"{_bounded_repr(entry)}",
                stacklevel=2,
            )
            continue
        if not isinstance(entry, dict):
            raise SchemaError(
                f"batch.completed_prds[{index}]: expected str or dict, "
                f"got {_bounded_repr(entry)}",
            )
        for field, type_ in _COMPLETED_PRD_ENTRY_FIELDS.items():
            if field in entry:
                require(entry[field], type_, f"batch.completed_prds[{index}].{field}")


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
                raise SchemaError(
                    f"{field}: invalid value {_bounded_repr(state[field])}",
                )

    for field in _INT_FIELDS:
        if field in state:
            require(state[field], int, field)

    for field in _STR_FIELDS:
        if field in state:
            require(state[field], str, field)

    for field in _LIST_FIELDS:
        if field in state:
            require(state[field], list, field)

    if "tasks" in state:
        _validate_task_entries(state["tasks"])

    if "batch" in state:
        batch = state["batch"]
        if not isinstance(batch, dict):
            raise SchemaError(f"batch: expected dict, got {_bounded_repr(batch)}")
        if "id" in batch and not isinstance(batch["id"], str):
            raise SchemaError(
                f"batch.id: expected str, got {_bounded_repr(batch['id'])}",
            )
        if "parks_consecutive" in batch:
            require(batch["parks_consecutive"], int, "batch.parks_consecutive")
        if "completed_prds" in batch:
            require(batch["completed_prds"], list, "batch.completed_prds")
            _validate_completed_prds_entries(batch["completed_prds"])


_MISSING = object()


def changed_fields(before: dict, after: dict) -> set[str]:
    """Top-level field names whose value differs between `before` and `after`.

    Covers additions, removals and edits alike, so a caller can ask "what did
    this write actually touch?" without declaring it by hand and watching the
    declaration drift away from the code.
    """
    return {
        key
        for key in set(before) | set(after)
        if before.get(key, _MISSING) != after.get(key, _MISSING)
    }


def validate_changed(before: dict, after: dict) -> None:
    """Validate ONLY the fields `after` changed relative to `before`.

    Whole-state validate() is the wrong gate for a targeted mutation: a
    pre-existing odd field, left there by a forensic hand-edit, would block
    every unrelated write afterwards and wedge the loop. Scoping to the
    changed set still rejects a mutation that writes a malformed value for
    the field it targets, which is the failure worth catching.
    """
    fields = changed_fields(before, after)
    validate({key: value for key, value in after.items() if key in fields})


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
