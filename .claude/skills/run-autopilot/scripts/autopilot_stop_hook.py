#!/usr/bin/env python3
"""Stop hook for autopilot session loop.

Reads state.json and $_AUTOPILOT_LOOP, then COMPUTES and WRITES the loop
signal. Auto-exits by SIGINTing the claude parent process so the shell wrapper
loop can restart with a fresh session.

Decision table (first match wins):
1. $_AUTOPILOT_LOOP unset/empty -> no signal, no auto-exit.
2. dev/local/autopilot dir not found -> no signal, no auto-exit.
3. state.json absent or corrupt -> no signal, no auto-exit (fail open).
4. state["phase"] == "paused" -> no signal, no auto-exit.
5. stall_reason.stalled == "subagent_prompt_overrun" -> signal = "task_aborted".
6. next_phase == "" (empty string) -> signal = "done".
7. next_phase is a non-empty string -> signal = "next".
8. Otherwise -> no signal, no auto-exit (fail open).

After computing a signal (cases 5-7):
- Consult the review-coverage gate. If a review surface just completed but its
  coverage is incomplete, the gate blocks: write NO signal and do NOT auto-exit,
  so the session stays alive for review_coverage_hook.py (same Stop event) to
  inject its blocking feedback and let the model finish the review. Without this
  the SIGINT below killed the session before it could act on that feedback, the
  coverage hook deleted the signal, and the loop reported "ended without a
  signal" (observed 2026-06-11 and 2026-06-12).
- If the session ended its turn WAITING for a harness re-invoke it cannot avoid
  — an (auto-)backgrounded Bash still running, or a scheduled wakeup — abstain
  in EVERY phase. A long FOREGROUND Bash (codex, `cargo test`) is silently
  AUTO-BACKGROUNDED by the harness into a tracked task whose recorded tool_use
  still says foreground, so neither the agent-launch ack nor the
  run_in_background flag appears; the doubt phase's review/test runs hit this on
  every cycle. SIGINTing while one is in flight strands the run and thrash-halts
  the loop (observed 2026-06-21 ddb doubt: `cargo test-ci` auto-backgrounded,
  the session waited via ScheduleWakeup, the hook — blind to the tracked task —
  halted on the 3rd yield). See _waiting_on_async; a hand-off always advances
  state.json via an Edit, so this never mis-fires on a completed phase.
- If an async Agent dispatch is still in flight (or its result unconsumed),
  abstain — but OUTSIDE review-gated phases only. This harness backgrounds
  Agent dispatches and re-invokes the model with a <task-notification> when the
  agent finishes; SIGINTing on the yield turn killed the session before that
  re-invoke could land and stranded the phase (observed 2026-06-19: design
  reviewer + /work Tess/Ivan each stranded 3x, then the breaker halted the
  loop). In a review-gated phase a completed-review hand-off can leave an
  orphaned reviewer agent that would otherwise stall forever, so there the
  coverage gate is the keep-alive instead. See _pending_background_task.
- Otherwise write to <autopilot_dir>/signal, UNLESS already present with the
  same value, then call find_and_signal_claude(os.getppid()) to auto-exit.

Stdlib only, plus the sibling review_coverage_hook module for the shared gate
decision (both live in this scripts/ dir). No _common import (this script
lives outside ~/.claude/hooks/).
"""

import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

from _walk_up import find_autopilot_dir

try:
    # Sibling module in this scripts/ dir. Shared so the signal hook and the
    # coverage hook never disagree about a review handoff. If it cannot be
    # imported, fall open (gate_blocks=None -> hand-off proceeds as before).
    # surface_for_phase tells whether a phase is review-gated (blind/doubt/done)
    # so the pending-background-task abstain can defer to the coverage gate there
    # instead of doubling it (see main()).
    from review_coverage_hook import gate_blocks, surface_for_phase
except ImportError:
    gate_blocks = None
    surface_for_phase = None

try:
    # Reuse the cap hook's atomic state writer (temp + os.replace) so both hooks
    # persist state.json the same way and never drift, and its stdin parser so
    # both read transcript_path identically. If the sibling can't be imported,
    # the phase-thrash guard does not persist and stdin is only drained (both
    # fail open, no worse than before these helpers existed).
    from autopilot_context_cap_hook import _atomic_write_state, _read_stdin
except ImportError:
    _atomic_write_state = None

    def _read_stdin() -> dict:
        """Fallback: drain stdin and return {} (no transcript_path -> the
        pending-background-task check is a no-op and the hand-off proceeds)."""
        try:
            sys.stdin.read()
        except OSError:
            pass
        return {}

PS_TIMEOUT_SEC = 2

# A review/build phase that hands off "next" with no forward progress this many
# consecutive times is a thrash, not progress (blind-review async-dispatch loop,
# observed 2026-06-17 on PRD 00157: 18 dead restarts, ~885k output tokens, zero
# progress). At the limit the hook withholds the signal so the wrapper loop
# exits cleanly — the same halt a PAUSE uses.
PHASE_THRASH_LIMIT = 3

# Real background-task markers, ANCHORED to the start of the relevant turn so
# that prose merely MENTIONING these strings is not mistaken for an actual launch
# or completion. A genuine Agent launch ack IS the tool_result and starts with
# the launch phrase, carrying `agentId: <hex>`; a genuine completion is a user
# turn that starts with `<task-notification>`, carrying `<task-id> <hex>`. The
# two ids are the same value, so launches and completions PAIR BY ID — which is
# what lets a session run many background tasks without one masking another.
#
# The count-based predecessor got this wrong twice: it matched a phantom
# `<task-notification>` inside SKILL.md text (injected as a user turn at session
# start) as a real completion, and its global launch>notif arithmetic let an
# earlier consumed task cancel a newly-dispatched one — stranding the blind
# reviewer and the work-phase Tess after the build/work fix already landed
# (2026-06-19 round 2). Per-id, start-anchored matching closes both holes.
_LAUNCH_PREFIX = "async agent launched successfully"
_TASK_NOTIF_PREFIX = "<task-notification>"
_AGENT_ID = re.compile(r"agentid:\s*([0-9a-f]+)", re.IGNORECASE)
_TASK_ID = re.compile(r"<task-id>\s*([0-9a-f]+)\s*</task-id>", re.IGNORECASE)
# Skip pending-detection on an absurdly large transcript (fail open — no SIGINT
# change). A once-per-turn full parse of a sub-25MB JSONL is cheap.
_MAX_TRANSCRIPT_BYTES = 25 * 1024 * 1024

# A long FOREGROUND Bash is AUTO-BACKGROUNDED by the harness into a tracked task
# whose launch ack (a tool_result) starts with this phrase and carries an id;
# completion arrives as a <task-notification> with the same id, exactly like an
# Agent. The recorded tool_use still says foreground (run_in_background unset),
# so only this ack text reveals the in-flight task. Edits/Writes mark a hand-off
# (the model advances state.json), which is how _waiting_on_async tells "still
# waiting" from "already handed off".
_BG_BASH_LAUNCH = "command running in background with id:"
# Backgrounded-Bash task ids are base-36 (e.g. "b6qi55ate"), NOT hex like the
# Agent ids that _TASK_ID matches — so the completion <task-notification> needs
# a base-36 matcher or it never pairs and the launch looks forever unconsumed.
_BG_BASH_ID = re.compile(r"id:\s*([0-9a-z]+)", re.IGNORECASE)
_BG_TASK_ID = re.compile(r"<task-id>\s*([0-9a-z]+)\s*</task-id>", re.IGNORECASE)
_EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def _progress_key(state: dict) -> str:
    """Fingerprint of forward progress across a hand-off. Two consecutive "next"
    hand-offs with the same key means the phase advanced nothing — a thrash. Any
    real step (phase/cycle change, a phase or task completing, a replan or cap
    rotation, a new review cycle) changes the key and resets the counter."""
    return "|".join(
        str(x)
        for x in (
            state.get("phase", ""),
            state.get("next_phase", ""),
            len(state.get("phases_completed") or []),
            state.get("tasks_completed", 0),
            state.get("cycle", 0),
            state.get("replan_count") or 0,
            len(state.get("cap_rotations") or []),
            len(state.get("review_cycles") or []),
        )
    )


def _text_blocks_join(content) -> str:
    """Concatenate the text of a message's content (str, or a list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def _pending_background_task(transcript_path: "Path | None") -> bool:
    """True when the session is ending its turn with a background task (an async
    Agent dispatch, or a backgrounded Bash) still in flight, or whose result the
    model has not yet consumed.

    Why this exists: this harness dispatches Agent calls in the BACKGROUND and
    re-invokes the model with a <task-notification> when the agent completes. The
    Stop hook used to SIGINT on the yield turn, killing the session before that
    re-invoke could land, so every dispatched subagent stranded (2026-06-19).
    Abstaining while a task is pending keeps the session alive for the re-invoke;
    the model cannot avoid the yield (the Agent tool has no foreground mode and
    Monitor is blocked), so making it safe is the only durable fix.

    Detection is PER-AGENTID, not count-based. A genuine launch ack is a
    tool_result whose text STARTS with "Async agent launched successfully" and
    carries `agentId: <hex>`; a genuine completion is a user turn that STARTS
    with `<task-notification>` and carries `<task-id> <hex>` (same value).
    Anchoring to the turn START ignores prose that merely mentions these strings
    (SKILL.md text injected as a user turn — the phantom that masked the blind
    reviewer in round 2). Only the MOST-RECENT launch decides: if it has no
    completion, or a completion the model has not produced a turn after, work is
    in flight -> abstain. An older unconsumed launch the model dispatched newer
    agents past is an orphan, not a wait, and must NOT stall the hand-off. A
    run_in_background Bash as the final action counts too. Fail-open: any parse
    miss degrades to the prior SIGINT, never worse.
    """
    if transcript_path is None:
        return False
    try:
        if transcript_path.stat().st_size > _MAX_TRANSCRIPT_BYTES:
            return False
        raw = transcript_path.read_text(errors="replace")
    except OSError:
        return False

    launched: dict[str, int] = {}  # agentId -> launch line index
    notified: dict[str, int] = {}  # task-id  -> completion line index
    last_assistant_idx = -1
    last_turn_backgrounded_bash = False

    for idx, line in enumerate(raw.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        message = entry.get("message")
        role = message.get("role") if isinstance(message, dict) else None
        content = message.get("content") if isinstance(message, dict) else None

        if role == "assistant":
            last_assistant_idx = idx
            # Track whether THIS (latest) assistant turn backgrounded a Bash.
            last_turn_backgrounded_bash = False
            if isinstance(content, list):
                for b in content:
                    if (
                        isinstance(b, dict)
                        and b.get("type") == "tool_use"
                        and b.get("name") == "Bash"
                        and isinstance(b.get("input"), dict)
                        and b["input"].get("run_in_background") is True
                    ):
                        last_turn_backgrounded_bash = True
            continue

        # Non-assistant (harness/user) turn. A real completion is a turn whose
        # text STARTS with the notification marker and carries a task-id.
        joined = _text_blocks_join(content)
        if joined.lstrip().startswith(_TASK_NOTIF_PREFIX):
            m = _TASK_ID.search(joined)
            if m:
                notified[m.group(1).lower()] = idx
            continue
        # A real launch ack is a tool_result whose text STARTS with the launch
        # phrase and carries an agentId.
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    cc = b.get("content")
                    if isinstance(cc, list):
                        cc = " ".join(
                            x.get("text", "") for x in cc if isinstance(x, dict)
                        )
                    cc = str(cc).lstrip()
                    if cc.lower().startswith(_LAUNCH_PREFIX):
                        m = _AGENT_ID.search(cc)
                        if m:
                            launched[m.group(1).lower()] = idx

    # Only the MOST-RECENT launch decides. If the model just dispatched a task
    # and is waiting on it, that task is the latest launch and is unconsumed ->
    # abstain. An EARLIER launch left unconsumed while the model dispatched newer
    # agents and moved on is an ORPHAN (a reviewer that never reported, a
    # superseded retry) — NOT something to keep the session alive for; the model
    # already handed off past it. Keying on the latest launch abstains for a real
    # wait yet hands off past an orphan. (2026-06-19 round-2 false positive: a
    # 6-reviewer review session handed off with one orphaned reviewer; the
    # per-id "any unconsumed launch" rule would have stalled that hand-off.)
    if launched:
        latest_id = max(launched, key=launched.get)
        notif_idx = notified.get(latest_id)
        if notif_idx is None or last_assistant_idx <= notif_idx:
            return True
    if last_turn_backgrounded_bash:
        return True
    return False


def _waiting_on_async(transcript_path: "Path | None") -> bool:
    """True when the session ended its turn WAITING for a harness re-invoke it
    cannot avoid — an (auto-)backgrounded Bash task still running, or a scheduled
    wakeup — rather than handing off. Safe to honour in EVERY phase.

    Why a separate check from _pending_background_task: a long FOREGROUND Bash
    (codex review, `cargo test`) is silently AUTO-BACKGROUNDED by the harness
    into a tracked task. Its recorded tool_use still says foreground, so neither
    the agent-launch ack nor the run_in_background flag fires — the only evidence
    is the launch-ack text "Command running in background with ID: <id>". The
    harness WILL re-invoke (the task completes -> <task-notification>; the wakeup
    timer fires), so SIGINTing now strands the run. The doubt phase hits this on
    every cycle and the review-coverage gate does not cover it (the gate protects
    the PREVIOUS surface, not the in-phase test/codex run), which is why this must
    run even in review-gated phases — the 2026-06-21 ddb doubt thrash-halt.

    "Still waiting" vs "already handed off" is decided structurally, not by
    guessing: a hand-off ALWAYS advances state.json via an Edit/Write, so if the
    most-recent wait marker (an UNCONSUMED bg-bash launch, a run_in_background
    Bash, or a ScheduleWakeup) is AFTER the last Edit/Write, the model has not
    handed off and is waiting. A real review hand-off Edits state after any
    reviewer launch, so a leftover orphan never trips this. Fail-open: a parse
    miss returns False (degrades to the prior behaviour, never worse).
    """
    if transcript_path is None:
        return False
    try:
        if transcript_path.stat().st_size > _MAX_TRANSCRIPT_BYTES:
            return False
        raw = transcript_path.read_text(errors="replace")
    except OSError:
        return False

    last_wait_tool = -1  # newest ScheduleWakeup or run_in_background Bash tool_use
    last_edit = -1  # newest state-mutating tool_use (the hand-off marker)
    bg_launched: dict[str, int] = {}  # bg-bash task-id -> launch-ack line index
    bg_notified: dict[str, int] = {}  # task-id -> completion line index

    for idx, line in enumerate(raw.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        message = entry.get("message")
        role = message.get("role") if isinstance(message, dict) else None
        content = message.get("content") if isinstance(message, dict) else None

        if role == "assistant":
            if isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict) or b.get("type") != "tool_use":
                        continue
                    name = b.get("name")
                    if name == "ScheduleWakeup":
                        last_wait_tool = idx
                    elif name in _EDIT_TOOLS:
                        last_edit = idx
                    elif (
                        name == "Bash"
                        and isinstance(b.get("input"), dict)
                        and b["input"].get("run_in_background") is True
                    ):
                        last_wait_tool = idx
            continue

        # Non-assistant turn. A bg-bash completion is a <task-notification>
        # carrying the same id the launch ack reported.
        joined = _text_blocks_join(content)
        if joined.lstrip().startswith(_TASK_NOTIF_PREFIX):
            m = _BG_TASK_ID.search(joined)
            if m:
                bg_notified[m.group(1).lower()] = idx
            continue
        # A bg-bash launch ack is a tool_result whose text STARTS with the
        # auto-background phrase and carries an id.
        if isinstance(content, list):
            for b in content:
                if not isinstance(b, dict) or b.get("type") != "tool_result":
                    continue
                cc = b.get("content")
                if isinstance(cc, list):
                    cc = " ".join(x.get("text", "") for x in cc if isinstance(x, dict))
                cc = str(cc).lstrip()
                if cc.lower().startswith(_BG_BASH_LAUNCH):
                    m = _BG_BASH_ID.search(cc)
                    bg_launched[m.group(1).lower() if m else str(idx)] = idx

    # An UNCONSUMED bg-bash launch is one with no later completion notification.
    # A consumed one already re-invoked the model (the notification IS the
    # re-invoke), so it is the hand-off path, not a wait.
    unconsumed_bg = -1
    for bid, lidx in bg_launched.items():
        notif = bg_notified.get(bid)
        if notif is None or notif < lidx:
            unconsumed_bg = max(unconsumed_bg, lidx)

    waiting_marker = max(last_wait_tool, unconsumed_bg)
    return waiting_marker >= 0 and waiting_marker > last_edit


def _ps(args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["ps", *args],
            capture_output=True,
            text=True,
            timeout=PS_TIMEOUT_SEC,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def comm_for(pid: int) -> str:
    return _ps(["-p", str(pid), "-o", "comm="])


def parent_of(pid: int) -> int:
    raw = _ps(["-o", "ppid=", "-p", str(pid)])
    if not raw.isdigit():
        return 0
    return int(raw)


def find_and_signal_claude(start_pid: int) -> bool:
    pid = start_pid
    while pid > 1:
        comm = comm_for(pid)
        if comm and os.path.basename(comm) == "claude":
            try:
                os.kill(pid, signal.SIGINT)
            except OSError:
                return False
            return True
        next_pid = parent_of(pid)
        if next_pid <= 0 or next_pid == pid:
            break
        pid = next_pid
    return False


def _compute_signal(state: dict) -> str | None:
    """Return the signal string, or None if no signal should be written."""
    if state.get("phase") == "paused":
        return None
    stall = state.get("stall_reason")
    if isinstance(stall, dict) and stall.get("stalled") == "subagent_prompt_overrun":
        return "task_aborted"
    next_phase = state.get("next_phase")
    if next_phase == "":
        return "done"
    if next_phase:
        return "next"
    return None


def main() -> None:
    stdin_data = _read_stdin()

    # Step 1: check _AUTOPILOT_LOOP.
    loop_val = os.environ.get("_AUTOPILOT_LOOP", "")
    if not loop_val:
        return

    # Step 2: locate autopilot dir.
    autopilot_dir = find_autopilot_dir(Path.cwd())
    if autopilot_dir is None:
        return

    # Step 3: read and parse state.json (fail open on missing/corrupt).
    state_path = autopilot_dir / "state.json"
    try:
        state: dict = json.loads(state_path.read_text())
    except (OSError, json.JSONDecodeError):
        return

    # Steps 4-8: compute signal.
    computed = _compute_signal(state)
    if computed is None:
        return

    # Defer to the review-coverage gate before signaling. When a review
    # surface just completed but its coverage is incomplete, the session must
    # stay alive so the model can finish the review — review_coverage_hook.py
    # (same Stop event) emits the block + feedback. Writing the signal and
    # SIGINTing here would kill the session before it could act on that
    # feedback, and the coverage hook's signal deletion would leave the loop
    # reporting "ended without a signal" (observed 2026-06-11 and 2026-06-12).
    # gate_blocks is phase-aware: it returns (False, ...) for non-review phases,
    # so build/PRD-to-PRD/task_aborted hand-offs are unaffected. Fail open on
    # any gate error — the coverage hook runs the same gate and likewise won't
    # block, so the hand-off proceeds without a race.
    if gate_blocks is not None:
        try:
            blocked, _ = gate_blocks(autopilot_dir, state)
        except Exception as exc:
            sys.stderr.write(
                f"autopilot stop hook: review gate check errored ({exc}); "
                "proceeding with hand-off (fail open)\n"
            )
            blocked = False
        if blocked:
            return

    transcript_str = stdin_data.get("transcript_path")
    transcript_path = (
        Path(transcript_str)
        if isinstance(transcript_str, str) and transcript_str
        else None
    )

    # Waiting on an (auto-)backgrounded Bash or a scheduled wakeup: abstain in
    # EVERY phase. A long foreground Bash (codex review, `cargo test`) is silently
    # auto-backgrounded into a harness-tracked task that re-invokes the model on
    # completion; SIGINTing now strands the run. This is the keep-alive the
    # review-coverage gate above CANNOT provide for a review-gated phase, because
    # that gate protects the PREVIOUS surface, not the in-phase test/codex run
    # (2026-06-21 ddb doubt: `cargo test-ci` auto-backgrounded, the session waited
    # via ScheduleWakeup, and the hook thrash-halted on the 3rd yield). Honouring
    # it everywhere is safe: a hand-off always advances state.json via an Edit, so
    # a completed-phase orphan never trips _waiting_on_async. No thrash-counter
    # touch — this is real in-flight work. Fail open if transcript_path is None.
    if _waiting_on_async(transcript_path):
        return

    # In-flight Agent dispatch: abstain — but OUTSIDE review-gated phases only.
    # This harness backgrounds Agent dispatches and re-invokes the model with a
    # <task-notification> on completion; SIGINTing now would kill the session
    # before that re-invoke lands and strand the phase (the 2026-06-19
    # design-reviewer / Tess / Ivan deaths). Do NOT touch the thrash counter —
    # real in-flight work, not a no-progress thrash.
    #
    # SCOPE: only OUTSIDE review-gated phases. In a review-gated phase
    # (blind/doubt/done) the gate_blocks check above is already the keep-alive —
    # it blocks while the review is incomplete and passes only when it is done,
    # so reaching this point means the review COMPLETED and any reviewer still
    # in flight is an orphan whose result is not needed. Abstaining on such an
    # orphan strands the loop forever: no <task-notification> ever arrives, so
    # the harness never re-invokes, and the session idles at its prompt while the
    # wrapper waits for an exit that never comes (2026-06-20 warden PRD 00013: a
    # 3-reviewer batch whose last-launched reviewer never reported; the phase
    # finished and the gate passed, yet the per-id detector saw that orphan as
    # the most-recent unconsumed launch and abstained on every Stop). The
    # build/review hand-off is NOT review-gated and has no completeness gate, so
    # its dispatched implementors (Tess/Ivan) still need this abstain — the
    # 2026-06-19 strand fix — and keep it. If surface_for_phase is unimportable,
    # there is no gate at all, so fall back to always running the check (safe).
    phase_is_review_gated = (
        surface_for_phase is not None
        and surface_for_phase(state.get("phase", "")) is not None
    )
    if not phase_is_review_gated:
        if _pending_background_task(transcript_path):
            return

    # Phase-thrash circuit-breaker (the "next" hand-off only). A phase that
    # re-enters with no forward progress PHASE_THRASH_LIMIT times is stuck: the
    # 2026-06-17 blind-review loop dispatched an async reviewer and yielded
    # before the result landed, so "blind" never reached phases_completed and
    # the loop re-ran it 18 times (~885k output tokens, zero progress). On trip,
    # withhold the signal — the wrapper sees no signal and exits its loop
    # cleanly (same halt as a PAUSE) — and record the stall for the user.
    # "done"/"task_aborted" are out of scope: batch end and the replan_count cap
    # bound those on their own.
    if computed == "next":
        guard = state.get("phase_guard") or {}
        key = _progress_key(state)
        count = guard.get("count", 0) + 1 if guard.get("key") == key else 1
        state["phase_guard"] = {"key": key, "count": count}
        tripped = count >= PHASE_THRASH_LIMIT
        if tripped:
            state["needs_attention"] = True
            state["thrash_halt"] = {
                "phase": state.get("phase", ""),
                "next_phase": state.get("next_phase", ""),
                "repeats": count,
            }
        if _atomic_write_state is not None:
            _atomic_write_state(autopilot_dir, state)
        if tripped:
            sys.stderr.write(
                "autopilot stop hook: PHASE THRASH — phase "
                f"\"{state.get('phase', '')}\" handed off \"next\" {count}x with "
                "no progress. Withholding the loop signal and halting "
                "(needs_attention set, thrash_halt recorded in state.json). The "
                "phase is not advancing; inspect before re-running.\n"
            )
            # Exit the session WITHOUT writing a signal: claude exits, the
            # wrapper reads an empty signal, hits its `*)` case ("NOT drained")
            # and breaks the loop. SIGINT (not a passive return) makes the
            # unattended loop halt deterministically instead of idling on a live
            # session.
            find_and_signal_claude(os.getppid())
            return

    # Write signal (idempotent: skip rewrite if value matches).
    signal_path = autopilot_dir / "signal"
    if signal_path.exists() and signal_path.read_text().strip() == computed:
        pass  # already correct; leave file untouched
    else:
        signal_path.write_text(computed)

    # Batch end: delete state.json after emitting "done" so the next batch
    # starts from a clean slate (no stale phases_completed -> no skipped
    # reviews). This is the durable-marker cleanup the model used to do by
    # deleting state itself; the hook owns it now.
    if computed == "done":
        try:
            state_path.unlink()
        except OSError:
            pass

    find_and_signal_claude(os.getppid())


if __name__ == "__main__":
    main()
