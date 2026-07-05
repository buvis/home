#!/usr/bin/env python3
"""Run a codex review pass (`codex exec --json`) with live progress.

Used by autopilot Phase 8 to have codex conduct the doubt review (skeptical
review + de-slop) over the PRD's diff. Wraps `codex exec --json` so a long
run is visibly alive rather than a silent black box, WITHOUT a hard timeout.

What it adds over a bare `codex exec` call:

- **Live progress** — one readable line per codex event, parsed from `--json`.
- **Heartbeat** — during quiet stretches prints elapsed/quiet time, the last
  action, whether the codex process ITSELF is alive, whether it is making
  progress (CPU climbing) or idle, and any tool subprocess it spawned. A long
  model turn in `--json` mode is silent with no child process, so codex-alive
  + CPU-climbing is normal work, not a hang.
- **Idle banner** — past a quiet stretch, a soft note when codex is alive AND
  still consuming CPU (working a slow turn), or a loud warning when it is alive
  but has used no CPU and produced nothing (most likely blocked on a stuck
  connection). It never kills anything; Ctrl-C is the only stop.
- **Review capture** — codex's agent-message text is written to
  `<autopilot_dir>/codex-review-output.md` on a clean run, for the caller to read.

The raw `--json` stream is teed to `<autopilot_dir>/codex-review-last.jsonl`.

EXIT CONTRACT (the doubt phase falls back to a Claude review on non-zero):
  0  codex ran clean.
  2  bad arguments (missing/unreadable prompt file).
  3  codex unavailable (not on PATH, or failed to launch).
  4  codex ran but failed (non-zero exit, OR a usage-limit/quota/error event
     in the stream — codex can emit those and still exit 0).

Usage:
    codex_review_run.py <prompt_file> [--model MODEL] [--sandbox MODE]

Stdlib only.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _walk_up import find_autopilot_dir

# Heartbeat cadence and the quiet threshold past which a note prints. Neither
# bound kills codex — they only change what the operator sees. 60s keeps the
# terminal feeling live; past 10 minutes of silence the note distinguishes a
# codex still burning CPU (working a slow turn) from one idle at 0 CPU (most
# likely blocked).
HEARTBEAT_SECS = 60
IDLE_BANNER_SECS = 600

# Minimum CPU-seconds a live codex must accrue between two heartbeats to count
# as "making progress". A reasoning/streaming codex easily clears this in 60s;
# one blocked on a dead socket accrues exactly 0 (the 1h44m-at-0-CPU hang).
# The epsilon only filters ps's hundredths-of-a-second rounding noise.
CPU_PROGRESS_EPSILON = 0.05

# codex emits a usage-limit / quota message as a normal event and still
# exits 0 — so a quota-blocked run looks like success unless we scan the
# stream for these markers. The doubt phase treats any hit as a failure
# (exit 4) and falls back to a Claude review rather than silently skipping
# a mandated review.
_FAILURE_TEXT_MARKERS = ("usage limit", "rate limit", "quota",
                         "insufficient_quota")


def _event_signals_failure(obj: object) -> bool:
    """True when a codex --json event indicates the run failed in a way the
    caller must surface: an explicit error/failed event, or a
    usage-limit/quota message codex prints without a nonzero exit."""
    blob = obj.lower() if isinstance(obj, str) else json.dumps(obj).lower()
    if any(marker in blob for marker in _FAILURE_TEXT_MARKERS):
        return True
    if isinstance(obj, dict):
        inner = obj
        for key in ("msg", "item"):
            nested = obj.get(key)
            if isinstance(nested, dict):
                inner = nested
                break
        for key in ("type", "event", "kind"):
            val = inner.get(key) or obj.get(key)
            if isinstance(val, str) and ("error" in val.lower()
                                         or "failed" in val.lower()):
                return True
    return False


def _agent_message_text(obj: object) -> str:
    """Return the text of a codex agent/message event, else "".

    Used to capture codex's review output (the doubt phase reads this back as
    the reviewer's findings + verdicts + coverage block)."""
    if not isinstance(obj, dict):
        return ""
    inner = obj
    for key in ("msg", "item"):
        nested = obj.get(key)
        if isinstance(nested, dict):
            inner = nested
            break
    etype = ""
    for key in ("type", "event", "kind"):
        val = inner.get(key) or obj.get(key)
        if isinstance(val, str):
            etype = val
            break
    if "message" in etype.lower() or "agent" in etype.lower():
        for key in ("message", "text", "content"):
            text = inner.get(key)
            if isinstance(text, str) and text.strip():
                return text
    return ""


def _collect_qwen_task_ids(autopilot_dir: Path | None) -> list[str]:
    """Return task IDs whose `state.tasks[i].attempts[]` include a
    qwen-implemented + completed dispatch in this PRD's state.

    The de-sloppify pass uses the returned list as a hint so codex can scope
    over qwen-implemented commit ranges (qwen has known idiom drift the
    batched pass exists to catch). When the list is empty (no qwen
    completions in the current PRD), the pass still runs over the full
    `CLEANUP_SINCE..HEAD` range — the qwen scope is additive, not a filter.

    Schema-tolerant: any missing/malformed state.json yields an empty list,
    falling back to today's behavior (codex sees no `QWEN_TASK_IDS` hint).
    """
    if autopilot_dir is None:
        return []
    state_path = autopilot_dir / "state.json"
    try:
        state = json.loads(state_path.read_text())
    except (OSError, ValueError):
        return []
    qwen_ids: list[str] = []
    # `state.get("tasks", [])` returns None when the JSON key is present
    # with a null value; `or []` collapses that to an iterable. Same
    # defensive pattern as `task.get("attempts") or []` below.
    for task in state.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        for attempt in task.get("attempts") or []:
            if not isinstance(attempt, dict):
                continue
            if (attempt.get("implementor") == "qwen"
                    and attempt.get("outcome") == "completed"):
                tid = task.get("id")
                if tid is not None:
                    qwen_ids.append(str(tid))
                break
    return qwen_ids


def summarize_event(obj: object) -> tuple[str, bool]:
    """Render one parsed `--json` event as `(summary, worth_printing)`.

    Schema-tolerant on purpose: codex's JSONL event shape varies across
    versions (`{"msg": {"type": ...}}`, `{"type": "item.completed",
    "item": {...}}`, etc.). This digs for whichever of a small set of
    known keys is present and falls back to a compact dump. `worth_printing`
    is False for high-frequency low-signal events (token counts, reasoning
    deltas) so the terminal is not flooded — they still count as activity
    for the idle timer, they just are not echoed.
    """
    if not isinstance(obj, dict):
        return (str(obj)[:200], True)

    # Unwrap the common envelopes: top-level, `msg`, or `item`.
    inner = obj
    for key in ("msg", "item"):
        nested = obj.get(key)
        if isinstance(nested, dict):
            inner = nested
            break

    etype = ""
    for key in ("type", "event", "kind"):
        val = inner.get(key) or obj.get(key)
        if isinstance(val, str):
            etype = val
            break
    etype_l = etype.lower()

    # Low-signal: keep the idle timer fresh but do not echo.
    if any(s in etype_l for s in ("token_count", "token_usage", "reasoning",
                                   "delta", "heartbeat")):
        return ("", False)

    def _cmd(value: object) -> str:
        if isinstance(value, list):
            return " ".join(str(p) for p in value)
        return str(value)

    if "error" in etype_l or "failed" in etype_l:
        msg = inner.get("message") or inner.get("error") or inner.get("text")
        return (f"⚠ error: {str(msg)[:300]}" if msg
                else f"⚠ {etype or 'error'}", True)

    if "exec" in etype_l or "command" in etype_l:
        cmd = inner.get("command") or inner.get("cmd")
        if "end" in etype_l or "complete" in etype_l:
            code = inner.get("exit_code")
            tail = f" (exit {code})" if code is not None else ""
            return (f"✓ ran: {_cmd(cmd)[:200]}{tail}" if cmd
                    else f"✓ command finished{tail}", True)
        if cmd:
            return (f"▸ running: {_cmd(cmd)[:200]}", True)
        return (f"▸ {etype}", bool(etype))

    if "patch" in etype_l or "edit" in etype_l or "file" in etype_l:
        path = inner.get("path") or inner.get("file") or inner.get("filename")
        return (f"▸ editing: {path}" if path else f"▸ {etype}", True)

    if "message" in etype_l or "agent" in etype_l:
        text = inner.get("message") or inner.get("text") or inner.get("content")
        if isinstance(text, str) and text.strip():
            return (f"▸ codex: {text.strip()[:300]}", True)
        return ("", False)

    if "complete" in etype_l or "finished" in etype_l or "done" in etype_l:
        return (f"✓ {etype}", True)

    if etype:
        return (f"· {etype}", True)
    return (str(obj)[:200], True)


def _descendants(root_pid: int) -> list[str]:
    """Return `comm` names of the live descendant processes of `root_pid`.

    Used by the heartbeat to show what tool work codex is doing (a
    `cargo`/`rustc`/`git` child churning). Absence of children does NOT mean
    hung — during a pure model turn codex spawns nothing. Best-effort: any
    `ps` failure yields an empty list, rendered as "no tool subprocs".
    """
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid=,ppid=,comm="],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    children: dict[int, list[tuple[int, str]]] = {}
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        children.setdefault(ppid, []).append((pid, parts[2]))
    found: list[str] = []
    stack = [root_pid]
    seen: set[int] = set()
    while stack:
        cur = stack.pop()
        for pid, comm in children.get(cur, []):
            if pid in seen:
                continue
            seen.add(pid)
            found.append(Path(comm.split()[0]).name if comm.split() else comm)
            stack.append(pid)
    return found


def _proc_alive(pid: int) -> bool:
    """True if `pid` is a live process (read-only probe; never reaps).

    The heartbeat uses this to confirm codex ITSELF is still running — the one
    signal `_descendants` cannot give, because a codex on a long model turn
    has no children yet is very much alive. `kill(pid, 0)` sends no signal, it
    only checks existence, so it is safe to call from the heartbeat thread
    while the main thread owns `proc.wait()`. PermissionError means the pid
    exists but is not ours to signal (still alive).
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _cpu_seconds(pid: int) -> float | None:
    """Cumulative CPU seconds consumed by `pid`, or None if unknown.

    Lets the heartbeat tell a working-but-quiet codex (CPU climbing as it
    reasons/streams) from a BLOCKED one (CPU flat — stuck on a dead socket,
    the 1h44m-at-0-CPU hang this guards against). Best-effort: any ps/parse
    failure yields None, which the caller treats as 'unknown', never a hang
    claim. Parses ps TIME format `[[dd-]hh:]mm:ss[.ss]`.
    """
    try:
        out = subprocess.run(
            ["ps", "-o", "time=", "-p", str(pid)],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not out:
        return None
    days = 0
    if "-" in out:
        day_str, out = out.split("-", 1)
        try:
            days = int(day_str)
        except ValueError:
            return None
    try:
        nums = [float(p) for p in out.split(":")]
    except ValueError:
        return None
    secs = 0.0
    for n in nums:
        secs = secs * 60 + n
    return days * 86400 + secs


class _Progress:
    """Shared activity state plus a serialized writer for terminal lines."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.last_activity = time.monotonic()
        self.last_summary = "(no events yet)"

    def note_activity(self, summary: str | None) -> None:
        with self._lock:
            self.last_activity = time.monotonic()
            if summary:
                self.last_summary = summary

    def snapshot(self) -> tuple[float, str]:
        with self._lock:
            return (time.monotonic() - self.last_activity, self.last_summary)

    def write_line(self, line: str) -> None:
        with self._lock:
            print(line, flush=True)


def _fmt_secs(s: float) -> str:
    s = int(s)
    return f"{s // 60}m{s % 60:02d}s" if s >= 60 else f"{s}s"


def _liveness_phrase(alive: bool, kids: list[str], advancing: bool,
                     codex_pid: int) -> str:
    """The process-state half of a heartbeat line.

    Always leads with codex's OWN state so the operator never has to infer
    'is codex running?' from the absence of children — and distinguishes a
    working-but-quiet codex (CPU climbing) from one idle at 0 CPU, the misread
    that first hid a real hang and then nearly killed a working review.
    """
    if not alive:
        return f"codex pid {codex_pid} EXITED"
    if kids:
        uniq = sorted(set(kids))
        return (f"codex pid {codex_pid} alive — tool subprocs: "
                f"{', '.join(uniq)} ({len(kids)})")
    if advancing:
        return (f"codex pid {codex_pid} alive — working (cpu active), "
                "no tool subproc")
    return (f"codex pid {codex_pid} alive but IDLE — no cpu use, no output "
            "(awaiting model or blocked)")


def _idle_banner(alive: bool, kids: list[str], idle: float, advancing: bool,
                 codex_pid: int) -> str | None:
    """A note when codex has been quiet past IDLE_BANNER_SECS, else None.

    The decision turns on PROGRESS, not on the presence of a child process: a
    codex still burning CPU is working a slow model turn (silent in --json
    mode) and must not be flagged; a codex idle at 0 CPU with no output is most
    likely blocked on a stuck connection (the 1h44m-at-0-CPU hang) and IS worth
    flagging. The old wording keyed on 'no child process' and so could neither
    spot a real hang nor clear a working turn.
    """
    if idle < IDLE_BANNER_SECS or kids:
        return None
    if not alive:
        return (f"⚠⚠ de-sloppify: codex (pid {codex_pid}) is GONE with no "
                "output — it likely died at launch; the caller falls back to "
                "a Claude review.")
    if advancing:
        return (f"⏳ de-sloppify: codex (pid {codex_pid}) is alive and still "
                f"using CPU after {_fmt_secs(idle)} of quiet — a long model "
                "turn is silent in --json mode, so this is working, not a "
                "hang. Let it run.")
    return (f"⚠⚠ de-sloppify: codex (pid {codex_pid}) has used no CPU and "
            f"produced no output for {_fmt_secs(idle)} — most likely BLOCKED "
            "on a stuck connection, not working. Ctrl-C to abort; the doubt "
            "phase falls back to a Claude review.")


def _heartbeat_loop(
    progress: _Progress, codex_pid: int, started: float, stop: threading.Event
) -> None:
    """Print a heartbeat every HEARTBEAT_SECS until `stop` is set."""
    prev_cpu = _cpu_seconds(codex_pid)
    while not stop.wait(HEARTBEAT_SECS):
        idle, last = progress.snapshot()
        elapsed = time.monotonic() - started
        alive = _proc_alive(codex_pid)
        kids = _descendants(codex_pid)
        cpu = _cpu_seconds(codex_pid)
        # Unknown CPU (ps failed) gets the benefit of the doubt — never claim a
        # hang we cannot measure.
        advancing = (cpu is None or prev_cpu is None
                     or (cpu - prev_cpu) > CPU_PROGRESS_EPSILON)
        if cpu is not None:
            prev_cpu = cpu
        progress.write_line(
            f"⏱ {_liveness_phrase(alive, kids, advancing, codex_pid)} — "
            f"elapsed {_fmt_secs(elapsed)}, quiet {_fmt_secs(idle)} "
            f"— last: {last}"
        )
        banner = _idle_banner(alive, kids, idle, advancing, codex_pid)
        if banner:
            progress.write_line(banner)


def main(argv: list[str]) -> int:
    args = argv[1:]
    prompt_file = ""
    model = ""
    sandbox = "workspace-write"
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--model", "-m") and i + 1 < len(args):
            model = args[i + 1]
            i += 2
        elif a == "--sandbox" and i + 1 < len(args):
            sandbox = args[i + 1]
            i += 2
        elif not a.startswith("-") and not prompt_file:
            prompt_file = a
            i += 1
        else:
            i += 1

    if not prompt_file:
        print("desloppify_run: prompt file argument required", file=sys.stderr)
        return 2
    prompt_path = Path(prompt_file)
    try:
        prompt = prompt_path.read_text()
    except OSError as exc:
        print(f"desloppify_run: cannot read {prompt_file}: {exc}",
              file=sys.stderr)
        return 2

    codex = shutil.which("codex")
    if codex is None:
        # codex is unavailable. Exit 3 so the doubt phase falls back to a
        # Claude review instead of silently skipping a mandated review.
        print("codex_review_run: 'codex' not on PATH; caller should fall back",
              file=sys.stderr)
        return 3

    log_dir = find_autopilot_dir(Path.cwd())
    raw_log = (log_dir / "codex-review-last.jsonl") if log_dir else None
    review_out = (log_dir / "codex-review-output.md") if log_dir else None

    cmd = [codex, "exec", "--json", "--skip-git-repo-check",
           "--sandbox", sandbox]
    if model:
        cmd += ["-m", model]
    cmd.append(prompt)

    qwen_ids = _collect_qwen_task_ids(log_dir)
    env = os.environ.copy()
    env["QWEN_TASK_IDS"] = ",".join(qwen_ids)
    qwen_note = (f"qwen task ids: {','.join(qwen_ids)}" if qwen_ids
                 else "no qwen-implemented tasks in this PRD")
    print(f"▸ de-sloppify: launching codex exec (model={model or 'default'}, "
          f"sandbox={sandbox}, {qwen_note})", flush=True)

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            env=env, stdin=subprocess.DEVNULL,
        )
    except OSError as exc:
        print(f"codex_review_run: failed to launch codex: {exc}",
              file=sys.stderr)
        return 3

    progress = _Progress()
    started = time.monotonic()
    stop = threading.Event()
    hb = threading.Thread(
        target=_heartbeat_loop,
        args=(progress, proc.pid, started, stop),
        daemon=True,
    )
    hb.start()

    saw_failure = False
    review_chunks: list[str] = []
    raw_handle = None
    if raw_log is not None:
        try:
            raw_handle = raw_log.open("w")
        except OSError:
            raw_handle = None

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if raw_handle is not None:
                try:
                    raw_handle.write(line)
                    raw_handle.flush()
                except OSError:
                    pass
            line = line.rstrip("\n")
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                # Non-JSON line (a codex banner or stderr text). It is
                # still output, so it counts as activity; echo it plain.
                if any(m in line.lower() for m in _FAILURE_TEXT_MARKERS):
                    saw_failure = True
                progress.note_activity(None)
                progress.write_line(f"  {line[:300]}")
                continue
            if _event_signals_failure(obj):
                saw_failure = True
            review_text = _agent_message_text(obj)
            if review_text:
                review_chunks.append(review_text)
            summary, show = summarize_event(obj)
            progress.note_activity(summary or None)
            if show and summary:
                progress.write_line(summary)
    except KeyboardInterrupt:
        stop.set()
        progress.write_line(
            "desloppify_run: interrupted; waiting for codex to exit")
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
        return 130
    finally:
        stop.set()
        if raw_handle is not None:
            try:
                raw_handle.close()
            except OSError:
                pass

    rc = proc.wait()
    elapsed = time.monotonic() - started
    if rc != 0 or saw_failure:
        reason = f"exit code {rc}" if rc != 0 else "usage-limit/error event"
        progress.write_line(
            f"⚠ codex_review: codex FAILED — {reason}, "
            f"total {_fmt_secs(elapsed)} (caller should fall back)"
        )
        return 4
    if review_out is not None and review_chunks:
        try:
            review_out.write_text("\n\n".join(review_chunks))
        except OSError:
            pass
    progress.write_line(
        f"✓ codex_review: codex finished clean — total {_fmt_secs(elapsed)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
