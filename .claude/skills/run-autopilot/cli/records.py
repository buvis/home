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
    do_stall(state_path, *, prd, site, detail, prds_dir, autopilot_dir,
             extra_mutator=None) -> int
        The Loop-mode stall procedure (references/recovery.md) as ONE call
        with a durable intent record (state.stall_op), recoverable on retry
        from a kill at any of its three internal boundaries. See
        test_records_stall.py's module docstring for the full 0-5 step /
        exit-code / retry contract.
    do_park(state_path, *, prds_dir, autopilot_dir) -> int
        The Phase 0 park-request handler as one callable: consumes
        `<autopilot_dir>/park-requested`, reconciles any pending stall_op
        first, then parks via `do_stall(site="wrapper_died", ...)`. Never
        writes state itself - every effect rides through do_stall's
        transactions. See test_records_park.py's module docstring for the
        full marker/stall_op match matrix and exit-code contract.
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

from . import schema
from . import state

# scripts/ is a sibling of cli/ under the skill root; resume_target.py is
# stdlib-pure (no circular import risk) and exposes park_decision.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from resume_target import park_decision

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


def _new_op_id() -> str:
    return uuid.uuid4().hex[:12]


def _trip(boundary: str) -> None:
    """Raise RuntimeError("failpoint: <boundary>") when
    _AUTOPILOT_CLI_FAILPOINT is set to `boundary`, simulating a kill at that
    point. Zero cost when unset."""
    if os.environ.get("_AUTOPILOT_CLI_FAILPOINT") == boundary:
        raise RuntimeError(f"failpoint: {boundary}")


def _validate_stall_op(new_state: dict) -> None:
    """Owned-fields validator for do_stall's step-2 intent stamp: checks
    only the stall_op shape this write sets, never the whole state."""
    stall_op = new_state.get("stall_op")
    if not isinstance(stall_op, dict):
        raise schema.SchemaError(f"stall_op: expected dict, got {stall_op!r}")
    for key in ("op_id", "prd", "site", "detail"):
        if not isinstance(stall_op.get(key), str):
            raise schema.SchemaError(
                f"stall_op.{key}: expected str, got {stall_op.get(key)!r}"
            )


def _validate_stall_commit(new_state: dict) -> None:
    """Owned-fields validator for do_stall's step-5 commit: checks only the
    reset scalars, batch.parks_consecutive, and stall_op absence this write
    sets. A malformed unrelated field elsewhere in state must not block a
    stall - statectl.py stays an unvalidated writer until PRD 00089, so
    whole-state schema.validate would wedge real states here."""
    if "stall_op" in new_state:
        raise schema.SchemaError("stall_op: must be absent after commit")
    if not isinstance(new_state.get("phase"), str):
        raise schema.SchemaError(f"phase: expected str, got {new_state.get('phase')!r}")
    if not isinstance(new_state.get("next_phase"), str):
        raise schema.SchemaError(
            f"next_phase: expected str, got {new_state.get('next_phase')!r}"
        )
    if not isinstance(new_state.get("phases_completed"), list):
        raise schema.SchemaError(
            f"phases_completed: expected list, got {new_state.get('phases_completed')!r}"
        )
    for field in ("cycle", "tasks_total", "tasks_completed", "replan_count"):
        value = new_state.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            raise schema.SchemaError(f"{field}: expected int, got {value!r}")
    batch = new_state.get("batch")
    parks = batch.get("parks_consecutive") if isinstance(batch, dict) else None
    if isinstance(parks, bool) or not isinstance(parks, int):
        raise schema.SchemaError(f"batch.parks_consecutive: expected int, got {parks!r}")


def do_stall(
    state_path: str | Path,
    *,
    prd: str,
    site: str,
    detail: str,
    prds_dir: str | Path,
    autopilot_dir: str | Path,
    extra_mutator=None,
) -> int:
    """Run the Loop-mode stall procedure (references/recovery.md) as ONE
    call with a durable intent record (state.stall_op), so a kill at any of
    the three internal boundaries is recoverable on retry. Returns the exit
    code (0 stalled | 4 move failed/unverified | 9 deferred-record I/O
    failed | 2 state unreadable | 10 stall_op conflict). See
    test_records_stall.py's module docstring for the full contract.
    """
    state_path = Path(state_path)
    prds_dir = Path(prds_dir)
    autopilot_dir = Path(autopilot_dir)

    try:
        current, _version = state.load(state_path)
    except state.StateError:
        return 2

    # Step 0: identity guard, before any effect.
    stall_op = current.get("stall_op")
    if stall_op:
        if stall_op.get("prd") != prd:
            return 10
        state_prd = current.get("prd")
        if state_prd and state_prd != prd:
            return 10
        op_id = stall_op["op_id"]
    else:
        op_id = _new_op_id()

    # Step 1: mkdir -p <prds_dir>/hold.
    hold_dir = prds_dir / "hold"
    try:
        hold_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return 4

    # Step 2: stamp the intent (idempotent on retry: same op_id).
    def _stamp_intent(s: dict) -> dict:
        new_s = dict(s)
        new_s["stall_op"] = {"op_id": op_id, "prd": prd, "site": site, "detail": detail}
        return new_s

    state.transaction(state_path, _stamp_intent, validator=_validate_stall_op)

    _trip("after-intent-before-move")

    # Step 3: move the PRD, verify arrival. Already-in-hold + absent-from-wip
    # counts as success (retry-idempotent).
    wip_path = prds_dir / "wip" / prd
    hold_path = hold_dir / prd
    if wip_path.exists():
        wip_path.rename(hold_path)
    if not hold_path.exists():
        return 4

    _trip("after-move-before-append")

    # Step 4: append the deferred record, deduped by op_id.
    try:
        record_defer(
            autopilot_dir,
            prd,
            (current.get("batch") or {}).get("id"),
            {"type": "stall", "site": site, "detail": detail, "op_id": op_id},
        )
    except (OSError, ValueError):
        return 9

    _trip("after-append-before-commit")

    # Step 5: single commit - reset_prd_fields, the parks_consecutive rule,
    # extra_mutator, then the stall_op delete.
    def _commit(s: dict) -> dict:
        new_s = reset_prd_fields(s)
        batch = dict(new_s.get("batch") or {})
        if site != "wrapper_died":
            batch["parks_consecutive"] = 0
        new_s["batch"] = batch
        if extra_mutator is not None:
            new_s = extra_mutator(new_s)
        new_s.pop("stall_op", None)
        return new_s

    state.transaction(state_path, _commit, validator=_validate_stall_commit)

    return 0


def _park_mutator(pause_detail: str | None = None):
    """Compose into do_stall's step-5 commit: increment
    batch.parks_consecutive by 1; when `pause_detail` is given, also set the
    systemic-halt phase/next_phase/pause_reason fields."""
    def _mutator(s: dict) -> dict:
        new_s = dict(s)
        batch = dict(new_s.get("batch") or {})
        batch["parks_consecutive"] = batch.get("parks_consecutive", 0) + 1
        new_s["batch"] = batch
        if pause_detail is not None:
            new_s["phase"] = "paused"
            new_s["next_phase"] = "paused"
            new_s["pause_reason"] = {"site": "systemic_park", "detail": pause_detail}
        return new_s
    return _mutator


def _parse_marker(marker_path: Path) -> None | str | dict:
    """Return None (absent), "malformed" (unparseable or missing/empty
    prd), or {"prd": str, "reason": str} for a present, usable marker."""
    if not marker_path.exists():
        return None
    try:
        raw = json.loads(marker_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return "malformed"
    if not isinstance(raw, dict) or not raw.get("prd"):
        return "malformed"
    return {"prd": raw["prd"], "reason": raw.get("reason", "")}


def do_park(
    state_path: str | Path,
    *,
    prds_dir: str | Path,
    autopilot_dir: str | Path,
) -> int:
    """Consume `<autopilot_dir>/park-requested` end-to-end: the Phase 0 park
    handler as one callable, reconciling command. See
    test_records_park.py's module docstring for the full contract. Returns
    the exit code (0 parked | 3 no/ignored/reconciled marker | 5 parked AND
    systemic halt | 10 stall_op conflict | 2 state error | 4/9 propagated
    from an inner do_stall move/append failure).
    """
    state_path = Path(state_path)
    prds_dir = Path(prds_dir)
    autopilot_dir = Path(autopilot_dir)
    marker_path = autopilot_dir / "park-requested"

    def _delete_marker() -> None:
        _trip("after-commit-before-marker-delete")
        marker_path.unlink()

    marker = _parse_marker(marker_path)

    try:
        current, _version = state.load(state_path)
    except state.StateError:
        return 2

    stall_op = current.get("stall_op")

    # Conflict: the marker names a different PRD than a stored stall_op -
    # refuse before any effect, regardless of wip/ placement.
    if isinstance(marker, dict) and stall_op and stall_op.get("prd") != marker["prd"]:
        return 10

    if marker == "malformed":
        _delete_marker()
        print("autopilot: park-requested malformed; ignoring")
        return 3

    if marker is None:
        if not stall_op:
            print("autopilot: no park-requested; nothing to do")
            return 3
        extra = _park_mutator() if stall_op["site"] == "wrapper_died" else None
        rc = do_stall(
            state_path, prd=stall_op["prd"], site=stall_op["site"], detail=stall_op["detail"],
            prds_dir=prds_dir, autopilot_dir=autopilot_dir, extra_mutator=extra,
        )
        if rc != 0:
            return rc
        print(f"autopilot: reconciled pending {stall_op['site']} stall for {stall_op['prd']}")
        return 3

    # marker is a valid dict ({"prd": ..., "reason": ...}) from here on.
    prd = marker["prd"]
    reason = marker["reason"]
    wip_filenames = [p.name for p in (prds_dir / "wip").glob("*.md")]
    prd_in_wip = prd in wip_filenames

    # A stall_op that isn't simply "this same wrapper_died park being
    # resumed" must be reconciled (its own stored prd/site/detail) before the
    # marker is acted on.
    if stall_op and not (prd_in_wip and stall_op["site"] == "wrapper_died"):
        extra = _park_mutator() if stall_op["site"] == "wrapper_died" else None
        rc = do_stall(
            state_path, prd=stall_op["prd"], site=stall_op["site"], detail=stall_op["detail"],
            prds_dir=prds_dir, autopilot_dir=autopilot_dir, extra_mutator=extra,
        )
        if rc != 0:
            return rc

    if not prd_in_wip:
        _delete_marker()
        print(f"autopilot: park-requested named {prd} not in wip/; ignoring")
        return 3

    try:
        consult_state, _version = state.load(state_path)
    except state.StateError:
        return 2
    parks_consecutive = (consult_state.get("batch") or {}).get("parks_consecutive", 0)

    decision = park_decision(marker, wip_filenames, parks_consecutive)
    if decision.endswith("systemic halt"):
        pause_detail = f"{parks_consecutive + 1} consecutive PRDs parked via wrapper_died; batch halted"
        extra = _park_mutator(pause_detail=pause_detail)
        exit_code = 5
    else:
        extra = _park_mutator()
        exit_code = 0

    rc = do_stall(
        state_path, prd=prd, site="wrapper_died", detail=reason,
        prds_dir=prds_dir, autopilot_dir=autopilot_dir, extra_mutator=extra,
    )
    if rc != 0:
        return rc
    _delete_marker()
    suffix = " (systemic halt)" if exit_code == 5 else ""
    print(f"autopilot: parked {prd}{suffix}")
    return exit_code
