#!/usr/bin/env python3
"""PostToolUse hook: keep an autopilot `build` session inside a context budget.

Reads PostToolUse JSON on stdin (`session_id`, `transcript_path`), tails the
session transcript to find the most recent `message.usage`, and acts on two
thresholds against a single cost ceiling:

- **Hard cap** — on overrun, ROTATES the build session. It appends one
  `{task_id, cycle}` entry to `state.cap_rotations`, sets `next_phase` to
  `"build"`, and emits an `additionalContext` envelope telling the model to
  hand off to a fresh session (write the loop signal, then STOP). The fresh
  session re-hydrates the TaskList from `state.tasks`, skips finished build
  sub-steps by artifact, and `/work` continues at the first non-completed
  task. No replan, no `stall_reason`, no lost work.
  **Livelock guard:** if `cap_rotations`' last entry already names the
  in-flight task, this is the second consecutive rotation for the same task
  — it is genuinely oversized. The hook does NOT append another rotation;
  instead it records the oversized-task stall (`stall_reason.stalled ==
  "oversized_task"`) and instructs the oversized-task stall recovery (move
  the PRD to `dev/local/prds/hold/`, advance to the next PRD).
- **Soft cap** (below the hard cap) — writes a `.handoff-requested` marker.
  This is non-destructive: state.json is untouched and no envelope is
  emitted. `/work` checks the marker at a task boundary (after a task
  commits) and hands off to a fresh session, which resumes build with the
  remaining pending tasks. The soft cap keeps a multi-task build from
  ballooning into the hard-cap rotation.

The cost ceiling is a single constant (`USAGE_CAP`), not a window-tiered
pair: cost scales linearly with context (every turn re-sends the whole window
as input), so the cap bounds per-task spend rather than tracking the model's
window. There is no window classification.

Active only when `dev/local/autopilot/state.json` exists with
`phase == "build"`. The autopilot directory is located by walking up from
cwd (the agent may have cd'd into a subdirectory during build; same fix as
a0c5b8e09 for the stop hook). One-shot per task via `.cap-fired` marker,
which carries the in-progress task id; when the in-progress task changes
between PostToolUse fires, the hook clears the stale marker itself rather
than relying on the `/work` step-2 Bash clear (which is a backstop). This
keeps the cap functional even if the model skips step 2 on a subsequent task.

Stdlib only. Self-contained — no `_common` import (this script lives outside
~/.claude/hooks/).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from _walk_up import find_autopilot_dir

# Per-task context cap as a single hard ceiling, applied regardless of the
# model's window (no window classification). The dispatch triangle is gone:
# every autopilot session — build included — now launches on Opus 1M, so the
# cap is sized for cost (cost scales linearly with context: every turn
# re-sends the whole window as input), not to dodge a small-window model's
# native auto-compact. 500K is the chosen ceiling: it bounds per-task spend
# while sitting well below the 1M-window compaction trigger, so the clean
# rotation handoff always runs. (The earlier 150K value misfired — the audit
# recorded every cap fire at ~163K inside Opus-1M sessions, aborting good
# plans the cap was meant to protect.)
USAGE_CAP = 500_000
# The soft cap sits below the hard cap. Crossing it writes the
# `.handoff-requested` marker so `/work` hands off at the next task boundary
# — a lossless alternative to the hard-cap rotation. The gap to the hard cap
# is sized to cover roughly one more build task. A task that still overruns
# the hard cap before `/work` reaches its boundary falls through to the
# rotation path.
SOFT_CAP = 320_000
# Walk the transcript backwards in 64KB chunks until a `message.usage`
# line is found or MAX_TAIL_BYTES is read. A fixed 64KB tail risked
# missing the latest usage line when a single large tool result (Bash
# output, big file read) appeared in the transcript between the latest
# usage line and EOF. 4MB caps the worst case at ~60ms of decode work.
TAIL_CHUNK_BYTES = 64 * 1024
MAX_TAIL_BYTES = 4 * 1024 * 1024

def _rotation_instructions(limit: int) -> str:
    """Build the rotation handoff instructions.

    The Stop hook owns the loop handoff from next_phase; no directive
    for that belongs here.
    """
    return (
        f"Context cap reached (~{limit // 1000}K tokens). This is a ROTATION: "
        "the rotation entry is already recorded in state.cap_rotations, the "
        "in-flight task was reset to pending so /work re-attempts it as the "
        "first pending task, and next_phase is set to build. Commit any safe "
        "partial work, then STOP. The autopilot Stop hook performs the loop "
        "handoff from next_phase. The fresh session re-hydrates the TaskList "
        "from state.tasks, skips finished build sub-steps by artifact, and "
        "/work continues at the first non-completed task. Do NOT set "
        "stall_reason; the PRD is not being re-planned."
    )


def _oversized_stall_instructions(task_id: str) -> str:
    """Build the oversized-task stall instructions for the livelock path.

    Reached when a task rotated twice in a row without finishing — it is
    genuinely too big for a single build session. The hook has already set
    state.stall_reason; the model performs the oversized-task stall recovery.
    The Stop hook owns the loop handoff from next_phase.
    """
    return (
        f"Context cap reached again on the same task ({task_id}) after a prior "
        "rotation — the task is oversized for a single build session. The hook "
        "has set state.stall_reason to {\"stalled\": \"oversized_task\"}. "
        "Perform the oversized-task stall recovery (references/recovery.md): "
        "move the PRD from dev/local/prds/wip/ to dev/local/prds/hold/, "
        "reset PRD-specific state fields, and advance to the next PRD. Then STOP. "
        "The autopilot Stop hook performs the loop handoff from next_phase."
    )


def _read_stdin() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _load_state(autopilot_dir: Path) -> dict[str, Any] | None:
    try:
        return json.loads((autopilot_dir / "state.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _usage_limit() -> int:
    """Return the single hard usage cap (a pure cost ceiling)."""
    return USAGE_CAP


def _soft_limit() -> int:
    """Return the single soft handoff threshold."""
    return SOFT_CAP


def _usage_total_from_line(line: str) -> int | None:
    """Parse a single transcript line; return usage total if present."""
    line = line.strip()
    if not line:
        return None
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(entry, dict):
        return None
    message = entry.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    return (
        int(usage.get("input_tokens", 0) or 0)
        + int(usage.get("cache_read_input_tokens", 0) or 0)
        + int(usage.get("cache_creation_input_tokens", 0) or 0)
    )


def _latest_usage_total(transcript_path: Path) -> int | None:
    """Return the most recent `message.usage` token total, or None if absent.

    Walks the file backwards in TAIL_CHUNK_BYTES chunks, accumulating bytes
    until either a usage line is found or MAX_TAIL_BYTES is read. A fixed
    64KB tail risked missing the latest usage line when a large tool result
    appeared in the transcript after the last usage line; reading backwards
    in chunks keeps memory bounded while handling arbitrarily large
    intervening lines.
    """
    try:
        size = transcript_path.stat().st_size
    except OSError:
        return None
    if size == 0:
        return None

    accumulated = b""
    pos = size

    try:
        with transcript_path.open("rb") as f:
            while pos > 0 and (size - pos) < MAX_TAIL_BYTES:
                read_start = max(0, pos - TAIL_CHUNK_BYTES)
                f.seek(read_start)
                accumulated = f.read(pos - read_start) + accumulated
                pos = read_start

                if pos > 0:
                    # Mid-file: drop the leading partial line if there is
                    # already a newline in the buffer. If no newline yet,
                    # the entire buffer is one partial line — read another
                    # chunk before parsing.
                    newline = accumulated.find(b"\n")
                    if newline == -1:
                        continue
                    search_buf = accumulated[newline + 1 :]
                else:
                    search_buf = accumulated

                text = search_buf.decode("utf-8", errors="ignore")
                for line in reversed(text.splitlines()):
                    total = _usage_total_from_line(line)
                    if total is not None:
                        return total
    except OSError:
        return None
    return None


def _in_progress_task_id(state: dict[str, Any]) -> str:
    tasks = state.get("tasks")
    if isinstance(tasks, list):
        for task in tasks:
            if isinstance(task, dict) and task.get("status") == "in_progress":
                task_id = task.get("id")
                if isinstance(task_id, str) and task_id:
                    return task_id
    return "unknown"


def _last_rotation_task(state: dict[str, Any]) -> str | None:
    """Return the task_id of the most recent cap_rotations entry, or None."""
    rotations = state.get("cap_rotations")
    if isinstance(rotations, list) and rotations:
        last = rotations[-1]
        if isinstance(last, dict):
            task_id = last.get("task_id")
            if isinstance(task_id, str) and task_id:
                return task_id
    return None


def _append_rotation_to_state(
    autopilot_dir: Path, task_id: str
) -> bool:
    """Re-read state.json, append one cap_rotations entry, reset the in-flight
    task to pending, write atomically.

    Re-reading immediately before writing minimizes the race window with
    concurrent model writes via the Edit tool. The model writes fields like
    tasks[].status and tasks_completed that the hook must not overwrite;
    merging onto a fresh read rather than the initial read (done earlier for
    phase/task checks) captures those concurrent updates.

    A rotation touches cap_rotations, next_phase, and the in-flight task's
    status. The rotated-into /work iterates pending tasks, so the in-flight
    task is reset from in_progress to pending for it to be re-attempted as the
    first non-completed task. It does not set stall_reason and does not modify
    tasks_completed, other tasks, phases_completed, or replan_count.
    """
    fresh = _load_state(autopilot_dir)
    if fresh is None:
        return False
    rotations = fresh.get("cap_rotations")
    if not isinstance(rotations, list):
        rotations = []
    rotations.append({"task_id": task_id, "cycle": fresh.get("cycle")})
    fresh["cap_rotations"] = rotations
    # Reset the in-flight task to pending so the rotated /work re-attempts it.
    # The sentinel "unknown" (no in_progress task) matches nothing -> no-op.
    if task_id != "unknown":
        for task in fresh.get("tasks", []):
            if isinstance(task, dict) and task.get("id") == task_id:
                task["status"] = "pending"
                break
    # next_phase stays on the build gate: the fresh session resumes build and
    # /work continues at the first non-completed task.
    fresh["next_phase"] = "build"
    return _atomic_write_state(autopilot_dir, fresh)


def _set_oversized_stall(autopilot_dir: Path, task_id: str, total: int) -> bool:
    """Re-read state.json, set the oversized-task stall, write atomically.

    The livelock path: a task rotated twice in a row without finishing, so it
    is genuinely too big for one build session. The hook records the
    oversized-task stall and the model performs the recovery (move the PRD to
    dev/local/prds/hold/, advance to the next PRD). It does NOT append
    another rotation.
    """
    fresh = _load_state(autopilot_dir)
    if fresh is None:
        return False
    fresh["stall_reason"] = {
        "stalled": "oversized_task",
        "task": task_id,
        "total_input_tokens": total,
    }
    return _atomic_write_state(autopilot_dir, fresh)


def _atomic_write_state(autopilot_dir: Path, state: dict[str, Any]) -> bool:
    """Write state.json atomically. Return True on success, False on failure.

    The fire path is only safe if the rotation entry (or the oversized stall)
    lands on disk — otherwise the next session's livelock guard loses the
    record and cannot tell a rotation happened. Callers must gate the
    envelope and the .cap-fired marker on this return value.
    """
    state_file = autopilot_dir / "state.json"
    tmp = state_file.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(state, indent=2))
        os.replace(tmp, state_file)
        return True
    except OSError as exc:
        print(
            f"autopilot_context_cap_hook: state.json write failed ({exc}); "
            "skipping rotation envelope to avoid a handoff with no record",
            file=sys.stderr,
        )
        try:
            tmp.unlink()
        except OSError:
            pass
        return False


def _request_handoff(autopilot_dir: Path, task_id: str) -> None:
    """Write the `.handoff-requested` marker (one-shot per task).

    Unlike the hard-cap rotation, this is non-destructive: state.json is left
    untouched and no envelope is emitted. `/work` checks the marker at a task
    boundary (after a task commits) and hands off cleanly to a fresh session,
    which resumes build with the remaining pending tasks.

    The marker carries the in-progress task id, mirroring `.cap-fired`. When
    it already names the current task this is a redundant PostToolUse fire
    and the function is a no-op; when it names an earlier task (the session
    advanced without `/work` honoring the marker) it is overwritten so the
    request stays current. Best-effort: an unwritable autopilot dir is
    swallowed, same contract as the marker write on the rotation path.
    """
    marker = autopilot_dir / ".handoff-requested"
    if marker.exists():
        try:
            if marker.read_text().strip() == task_id:
                return
        except OSError:
            return
    try:
        marker.write_text(task_id)
    except OSError:
        pass


def _emit_envelope(context: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": context,
        }
    }
    print(json.dumps(payload))


def _marker_dedup_blocks(
    marker_file: Path, task_id: str, last_rotation_task: str | None
) -> bool:
    """Return True if a `.cap-fired` marker means main() should stop now.

    The marker carries the task id the cap fired for. If the in-progress
    task is still the same, this is a redundant PostToolUse fire and we're
    done. If the task changed, the model advanced past the rotated task
    without `/work` step 2's Bash clear running (or the marker survived from
    a different reason); clear the stale marker so this task gets its own cap
    check. A failed unlink also stops (the stale marker would otherwise block
    the cap check anyway).
    """
    if not marker_file.exists():
        return False
    try:
        marker_task = marker_file.read_text().strip()
    except OSError:
        marker_task = ""
    if marker_task and marker_task == task_id:
        return True
    if (
        marker_task
        and task_id == "unknown"
        and marker_task == last_rotation_task
    ):
        # Post-reset wind-down re-fire: a rotation already reset the in-flight
        # task to pending, so there is no in-progress task to act on and the
        # model was already told to STOP. Keep the marker and block. Scoped to
        # the LAST rotation's task so a stale marker from a prior PRD (whose
        # cap_rotations were cleared by a livelock stall) does NOT match — it
        # falls through to self-clear below and the prologue cap fire is not
        # suppressed.
        return True
    try:
        marker_file.unlink()
    except OSError:
        return True
    return False


def _handle_below_cap(autopilot_dir: Path, task_id: str, total: int) -> None:
    # Below the hard cap. Above the soft cap, request a clean
    # task-boundary handoff (lossless) instead of the hard-cap rotation.
    if total > _soft_limit():
        _request_handoff(autopilot_dir, task_id)


def _handle_livelock(
    autopilot_dir: Path, marker_file: Path,
    task_id: str, total: int,
) -> None:
    # Marker first, gated (same invariant as _handle_rotation): the marker is
    # present iff the stall is recorded, so a marker-write failure cannot leave
    # an oversized-task stall the next fire would act on spuriously.
    try:
        marker_file.write_text(task_id)
    except OSError:
        return
    # State write is failure-critical. On failure, roll back the marker so the
    # next fire is a clean retry.
    if not _set_oversized_stall(autopilot_dir, task_id, total):
        try:
            marker_file.unlink()
        except OSError:
            pass
        return
    _emit_envelope(_oversized_stall_instructions(task_id))


def _handle_rotation(
    autopilot_dir: Path, marker_file: Path, task_id: str, limit: int,
) -> None:
    # Marker first, gated: if it can't be written, return and retry on the next
    # PostToolUse. The marker is present iff the rotation is recorded, so a
    # marker-write failure leaves cap_rotations untouched and the next fire is a
    # clean rotation, never a false livelock.
    try:
        marker_file.write_text(task_id)
    except OSError:
        return

    # State append is failure-critical. On failure, roll back the marker so the
    # next fire is a clean retry — never a marker-without-rotation (blocks
    # forever) nor a rotation-without-marker (re-fires as a false livelock).
    # _append_rotation_to_state re-reads state.json fresh before writing so
    # concurrent model edits (tasks[].status, tasks_completed) are not silently
    # overwritten by this hook's stale initial read.
    if not _append_rotation_to_state(autopilot_dir, task_id):
        try:
            marker_file.unlink()
        except OSError:
            pass
        return

    _emit_envelope(_rotation_instructions(limit))


def main() -> None:
    stdin = _read_stdin()
    transcript_path_str = stdin.get("transcript_path")
    if not isinstance(transcript_path_str, str) or not transcript_path_str:
        return

    autopilot_dir = find_autopilot_dir(Path.cwd())
    if autopilot_dir is None:
        return

    state = _load_state(autopilot_dir)
    if not state or state.get("phase") != "build":
        return

    task_id = _in_progress_task_id(state)
    last_rotation_task = _last_rotation_task(state)
    marker_file = autopilot_dir / ".cap-fired"
    if _marker_dedup_blocks(marker_file, task_id, last_rotation_task):
        return

    limit = _usage_limit()
    transcript_path = Path(transcript_path_str)
    total = _latest_usage_total(transcript_path)
    if total is None:
        return
    if total <= limit:
        _handle_below_cap(autopilot_dir, task_id, total)
        return

    # Livelock guard FIRST: if the last cap_rotations entry already names the
    # in-flight task, this is the second consecutive rotation for the same
    # task — it is genuinely oversized. Record the oversized-task stall
    # instead of appending another rotation.
    if last_rotation_task == task_id:
        _handle_livelock(
            autopilot_dir, marker_file, task_id, total
        )
        return

    _handle_rotation(autopilot_dir, marker_file, task_id, limit)


if __name__ == "__main__":
    main()
