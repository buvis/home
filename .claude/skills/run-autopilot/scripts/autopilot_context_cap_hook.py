#!/usr/bin/env python3
"""PostToolUse hook: keep autopilot Work sessions inside a context budget.

Reads PostToolUse JSON on stdin (`session_id`, `transcript_path`), tails the
session transcript to find the most recent `message.usage`, and acts on two
thresholds:

- **Hard cap** — on overrun, emits an `additionalContext` envelope telling
  the model to abort cleanly; `/run-autopilot` Phase 0 then replans the PRD.
- **Soft cap** (below the hard cap) — writes a `.handoff-requested` marker.
  This is non-destructive: state.json is untouched and no envelope is
  emitted. `/work` checks the marker at a task boundary (after a task
  commits) and hands off to a fresh session, which resumes Phase 3 with the
  remaining pending tasks — no replan, no lost work. The soft cap keeps a
  multi-task Work phase from ballooning into the destructive hard-cap path.

Active only when `dev/local/autopilot/state.json` exists with `phase == "work"`.
The autopilot directory is located by walking up from cwd (the agent may
have cd'd into a subdirectory during work; same fix as a0c5b8e09 for the
stop hook). One-shot per task via `.cap-fired` marker, which carries the
in-progress task id; when the in-progress task changes between PostToolUse
fires, the hook clears the stale marker itself rather than relying on the
`/work` step-2 Bash clear (which is a backstop). This keeps the cap
functional even if the model skips step 2 on a subsequent task.

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

# Per-task context cap, sized to the model's context window. The window
# is read from state.json `context_window`, written by autoclaude before
# each launch (it knows the --model it picked). The hook cannot derive the
# window itself: transcript assistant messages record the plain model id
# (`claude-sonnet-4-6`), never the `[1m]` window variant.
#
# Standard 200K-window models (Sonnet 4.6, today's Work-phase model): the
# cap MUST sit below the native auto-compact trigger (~165-169K; observed
# compactMetadata preTokens 168737) or native compaction fires first and
# the clean abort+replan path never runs.
#
# 1M-window models: native compaction is far off (~820K), so the cap is a
# pure cost ceiling. Cost scales linearly with context (every turn
# re-sends the whole window as input), so the cap bounds per-task spend
# rather than tracking the window — 500K is the chosen ceiling.
CAP_STANDARD_WINDOW = 150_000
CAP_LARGE_WINDOW = 500_000
# A context_window at or above this counts as a large (1M-class) window.
LARGE_WINDOW_MIN = 400_000
# Soft caps sit below the hard caps. Crossing one writes the
# `.handoff-requested` marker so `/work` hands off at the next task
# boundary — a lossless alternative to the hard-cap abort+replan. The gap
# between soft and hard is sized to cover roughly one more Work task:
# ~45K for a standard-window task, ~180K for a large-window task (the
# observed per-task footprint of ~125K plus margin). A task that still
# overruns the hard cap before `/work` reaches its boundary falls through
# to the unchanged abort path.
SOFT_STANDARD_WINDOW = 105_000
SOFT_LARGE_WINDOW = 320_000
# Walk the transcript backwards in 64KB chunks until a `message.usage`
# line is found or MAX_TAIL_BYTES is read. A fixed 64KB tail risked
# missing the latest usage line when a single large tool result (Bash
# output, big file read) appeared in the transcript between the latest
# usage line and EOF. 4MB caps the worst case at ~60ms of decode work.
TAIL_CHUNK_BYTES = 64 * 1024
MAX_TAIL_BYTES = 4 * 1024 * 1024

def _abort_instructions(signal_path: Path, limit: int) -> str:
    """Build the abort instructions with the resolved absolute signal path.

    Two robustness rules:

    1. **Absolute path.** The agent may have cd'd into a subdirectory by
       abort time; a relative `dev/local/autopilot/signal` write would
       land in the wrong place and the stop hook walk-up would miss it.
       The hook has already resolved the autopilot dir via walk-up, so
       we pass that resolved path through.
    2. **`$_AUTOPILOT_LOOP` gate.** Per SKILL.md "Loop Detection", the
       signal file must only be written when the shell loop wrapper is
       active. Writing it from a manual `/run-autopilot` session SIGINTs
       the user with no restart wrapper. The model checks the env var
       before writing.
    """
    return (
        f"Context cap reached (~{limit // 1000}K tokens). Abort current task cleanly: "
        "commit any safe partial work, then — only if $_AUTOPILOT_LOOP is "
        f"set (autopilot shell loop wrapper) — write 'task_aborted' to "
        f"{signal_path} and exit. If $_AUTOPILOT_LOOP is unset, skip the "
        "signal write (the session is manual; the next /run-autopilot "
        "invocation resumes via state.json). The hook has already "
        "appended the abort record to state.task_aborts and set "
        "state.stall_reason; /run-autopilot Phase 0 will replan the PRD "
        "in place on the next session (PRD stays in dev/local/prds/wip/) "
        "with the remaining scope split into smaller tasks."
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


def _usage_limit(state: dict[str, Any]) -> int:
    """Pick the context cap for this session from its model's window.

    `context_window` is written into state.json by autoclaude before each
    launch. Absent → assume the 200K standard tier (the conservative
    default: capping a large-window session too low only over-triggers
    replan, it never breaks the abort path).
    """
    window = state.get("context_window")
    if isinstance(window, int) and window >= LARGE_WINDOW_MIN:
        return CAP_LARGE_WINDOW
    return CAP_STANDARD_WINDOW


def _soft_limit(state: dict[str, Any]) -> int:
    """Pick the soft handoff threshold for this session's model window.

    Mirrors `_usage_limit`'s window classification. Absent `context_window`
    → standard tier (conservative: a lower soft cap only triggers an earlier
    handoff, never breaks anything).
    """
    window = state.get("context_window")
    if isinstance(window, int) and window >= LARGE_WINDOW_MIN:
        return SOFT_LARGE_WINDOW
    return SOFT_STANDARD_WINDOW


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


def _merge_abort_to_state(
    autopilot_dir: Path,
    abort_entry: dict[str, Any],
    stall_reason: dict[str, Any],
) -> bool:
    """Re-read state.json, merge abort fields, write atomically.

    Re-reading immediately before writing minimizes the race window with
    concurrent model writes via the Edit tool. The model writes fields like
    tasks[].status and tasks_completed that the hook must not overwrite;
    merging onto a fresh read rather than the initial read (done earlier for
    phase/task checks) captures those concurrent updates.
    """
    fresh = _load_state(autopilot_dir)
    if fresh is None:
        return False
    aborts = fresh.get("task_aborts")
    if not isinstance(aborts, list):
        aborts = []
    aborts.append(abort_entry)
    fresh["task_aborts"] = aborts
    fresh["stall_reason"] = stall_reason
    return _atomic_write_state(autopilot_dir, fresh)


def _atomic_write_state(autopilot_dir: Path, state: dict[str, Any]) -> bool:
    """Write state.json atomically. Return True on success, False on failure.

    The abort path is only safe if state.stall_reason and state.task_aborts
    land on disk — otherwise the next session's Phase 0 finds no stall to
    recover from and silently re-enters Work on the same PRD. Callers must
    gate the abort envelope and the .cap-fired marker on this return value.
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
            "skipping abort envelope to avoid corrupt task_aborted handoff",
            file=sys.stderr,
        )
        try:
            tmp.unlink()
        except OSError:
            pass
        return False


def _append_task_abort_log(autopilot_dir: Path, entry: dict[str, Any]) -> None:
    try:
        with (autopilot_dir / "task-abort").open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def _request_handoff(autopilot_dir: Path, task_id: str) -> None:
    """Write the `.handoff-requested` marker (one-shot per task).

    Unlike the hard-cap abort, this is non-destructive: state.json is left
    untouched, no abort record is appended, and no envelope is emitted.
    `/work` checks the marker at a task boundary (after a task commits) and
    hands off cleanly to a fresh session, which resumes Phase 3 with the
    remaining pending tasks — no replan.

    The marker carries the in-progress task id, mirroring `.cap-fired`. When
    it already names the current task this is a redundant PostToolUse fire
    and the function is a no-op; when it names an earlier task (the session
    advanced without `/work` honoring the marker) it is overwritten so the
    request stays current. Best-effort: an unwritable autopilot dir is
    swallowed, same contract as the marker write on the abort path.
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


def _emit_abort_envelope(autopilot_dir: Path, limit: int) -> None:
    signal_path = autopilot_dir / "signal"
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": _abort_instructions(signal_path, limit),
        }
    }
    print(json.dumps(payload))


def main() -> None:
    stdin = _read_stdin()
    transcript_path_str = stdin.get("transcript_path")
    if not isinstance(transcript_path_str, str) or not transcript_path_str:
        return

    autopilot_dir = find_autopilot_dir(Path.cwd())
    if autopilot_dir is None:
        return

    state = _load_state(autopilot_dir)
    if not state or state.get("phase") != "work":
        return

    task_id = _in_progress_task_id(state)
    marker_file = autopilot_dir / ".cap-fired"
    if marker_file.exists():
        # The marker carries the task id the cap fired for. If the
        # in-progress task is still the same, this is a redundant
        # PostToolUse fire and we're done. If the task changed, the model
        # advanced past the aborted task without `/work` step 2's Bash
        # clear running (or the marker survived from a different reason);
        # clear the stale marker so this task gets its own cap check.
        try:
            marker_task = marker_file.read_text().strip()
        except OSError:
            marker_task = ""
        if marker_task and marker_task == task_id:
            return
        try:
            marker_file.unlink()
        except OSError:
            return

    limit = _usage_limit(state)
    transcript_path = Path(transcript_path_str)
    total = _latest_usage_total(transcript_path)
    if total is None:
        return
    if total <= limit:
        # Below the hard cap. Above the soft cap, request a clean
        # task-boundary handoff (lossless) instead of the destructive
        # abort+replan the hard cap triggers.
        if total > _soft_limit(state):
            _request_handoff(autopilot_dir, task_id)
        return

    abort_entry = {
        "task_id": task_id,
        # The transcript usage line carries no turn counter, so we cannot
        # derive the actual turn. -1 signals "unknown" (matches the
        # work-skill subagent_prompt_overrun convention) rather than the
        # misleading "first turn" that 0 implied previously.
        "turn": -1,
        "total_input_tokens": total,
        "cause": "context_overrun",
    }

    stall_reason = {
        "stalled": "context_overrun",
        "task": task_id,
        "total_input_tokens": total,
    }

    # State write is the failure-critical step. If it fails, do NOT touch
    # the marker, do NOT append to task-abort, do NOT emit the abort
    # envelope — the model would write task_aborted into the loop signal
    # and the next session's Phase 0 would find no stall_reason to recover
    # from, silently degrading to a normal PRD start with the original PRD
    # still in wip/. Better to let the hook fire again on the next
    # PostToolUse and try the write again.
    #
    # _merge_abort_to_state re-reads state.json fresh before writing so
    # concurrent model edits (tasks[].status, tasks_completed) are not
    # silently overwritten by this hook's stale initial read.
    if not _merge_abort_to_state(autopilot_dir, abort_entry, stall_reason):
        return

    try:
        marker_file.write_text(task_id)
    except OSError:
        # State landed on disk but marker didn't; the hook may double-fire
        # this task. Better than the alternative (marker without state).
        pass

    _append_task_abort_log(autopilot_dir, abort_entry)

    _emit_abort_envelope(autopilot_dir, limit)


if __name__ == "__main__":
    main()
