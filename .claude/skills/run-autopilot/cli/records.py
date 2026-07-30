#!/usr/bin/env python3
"""records.py - the per-PRD state reset and the idempotent deferred-record log.

Exposes:
    PER_PRD_RESET_FIELDS
        Tuple of state.json field names removed when a batch advances from
        one PRD to the next.
    reset_prd_fields(state) -> dict
        PURE. Returns a NEW dict; never mutates `state`. Removes every
        PER_PRD_RESET_FIELDS key (if present; absent is not an error),
        resets phases_completed/cycle/tasks_total/tasks_completed/
        replan_count/phase/next_phase by direct assignment, and preserves
        every other key - in particular `batch`, in full - unchanged. The
        caller wraps this in a `state.transaction`; this module never opens
        state.json's lock.
    record_defer(path, prd, batch_id, record) -> None
        Appends `record` (stamped with `record["prd"] = prd`, without
        mutating the caller's dict) to
        `<path>/deferred/<batch_id>-deferred.json`, creating the `deferred/`
        directory and the `{"batch_id": ..., "items": []}` skeleton file
        when absent. Idempotent by "op_id": a record whose op_id matches an
        existing item's op_id is skipped; a record with no op_id is always
        appended. Preserves the file's existing batch_id and prior items.
        Locked and written atomically via its own `.lock` sidecar next to
        the deferred file - a different lock from state.json's.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from pathlib import Path

# Fields removed by the per-PRD reset, grouped by why they're here:
#
# - Fields already named in every prose reset list today (per-PRD work
#   product: tasks, review/doubt history, design choices, pause/stall
#   reasons).
# - repo_root: reset only per phase-done.md step 10, not the general prose
#   lists, but still a per-PRD field.
# - The four fields that leak into the next PRD today (bug this reset
#   fixes): pause_on_ambiguity, review_lenses, contract_card,
#   needs_attention.
PER_PRD_RESET_FIELDS = (
    "tasks",
    "task_aborts",
    "cap_rotations",
    "autonomous_decisions",
    "deferred_decisions",
    "review_cycles",
    "doubts",
    "doubts_rubric_verdicts",
    "rework_task_ids",
    "work_start_sha",
    "design_doc",
    "design_gate",
    "design_mode",
    "pause_reason",
    "cap_pause_reason",
    "stall_reason",
    "repo_root",
    "pause_on_ambiguity",
    "review_lenses",
    "contract_card",
    "needs_attention",
)

# NOT reset here, deliberately:
# - batch: preserved in full - it tracks the whole batch, not one PRD.
# - catchup_mode, rework_cap, doubt_reviewer, consensus_engine: re-derived
#   by Phase 0 from the next PRD's frontmatter, not carried forward.
# - qwen_gate_failures_consecutive, qwen_breaker, codex_probe:
#   batch-scoped, each with its own lazy reset elsewhere.
# - schema_version: stamped by the state.transaction boundary, not here.


def reset_prd_fields(state: dict) -> dict:
    """Return a new dict with PER_PRD_RESET_FIELDS removed and per-PRD
    counters/phase markers reset by assignment. Pure: does not mutate
    `state`; every other key is preserved unchanged."""
    new_state = {k: v for k, v in state.items() if k not in PER_PRD_RESET_FIELDS}
    new_state.update({
        "phases_completed": [],
        "cycle": 1,
        "tasks_total": 0,
        "tasks_completed": 0,
        "replan_count": 0,
        "phase": "build",
        "next_phase": "build",
    })
    return new_state


def _atomic_write(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def record_defer(path: str | Path, prd: str, batch_id: str, record: dict) -> None:
    """Append `record` to `<path>/deferred/<batch_id>-deferred.json`.

    Creates the `deferred/` directory and the file (skeleton
    {"batch_id": batch_id, "items": []}) when absent. Stamps a COPY of
    `record` with `"prd": prd` (the caller's dict is never mutated). Skips
    the append when an existing item's "op_id" equals `record["op_id"]`; a
    record with no "op_id" is always appended. Locked and written
    atomically under its own `.lock` sidecar next to the deferred file.
    """
    deferred_dir = Path(path) / "deferred"
    deferred_dir.mkdir(parents=True, exist_ok=True)
    file_path = deferred_dir / f"{batch_id}-deferred.json"
    lock_path = Path(f"{file_path}.lock")

    with open(lock_path, "w", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if file_path.exists():
            content = json.loads(file_path.read_text(encoding="utf-8"))
        else:
            content = {"batch_id": batch_id, "items": []}

        op_id = record.get("op_id")
        already_present = op_id is not None and any(
            item.get("op_id") == op_id for item in content["items"]
        )
        if not already_present:
            item = dict(record)
            item["prd"] = prd
            content["items"].append(item)

        _atomic_write(file_path, content)
