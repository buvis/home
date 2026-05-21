#!/usr/bin/env python3
"""Run the autopilot de-sloppify codex pass with live progress.

Wraps `codex exec --json` so a long run — a legitimate `cargo test
--workspace` can take 40 minutes — is visibly alive rather than a silent
black box, WITHOUT imposing a hard timeout (the operator rejected an
auto-kill: long test runs are expected).

What it adds over a bare `codex exec` call:

- **Live progress** — one readable line per codex event (commands run,
  files edited, agent messages, errors), parsed from the `--json` stream.
- **Heartbeat** — during quiet stretches (codex blocked on a long child
  process), prints elapsed time, idle time, the last action, and a
  snapshot of codex's descendant processes. A running `cargo`/`rustc`
  child is the signal that the pass is working, not hung.
- **Idle banner** — when codex emits nothing AND has no descendant
  process for a long stretch, prints a loud banner so the operator knows
  to look. It still does not kill anything; Ctrl-C stays the only stop.

The raw `--json` stream is teed to `<autopilot_dir>/desloppify-last.jsonl`
for post-mortem.

Invoked by the `autoclaude` shell loop in place of a bare codex-run.sh
call. Exits with codex's exit code; exits 0 when codex is not installed —
the de-sloppify pass is best-effort and must never break the loop.

Usage:
    desloppify_run.py <prompt_file> [--model MODEL] [--sandbox MODE]

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

# Heartbeat cadence and the idle threshold past which the quiet stretch is
# loud-bannered. Neither bound kills codex — they only change what the
# operator sees. 60s keeps the terminal feeling live; 10 minutes of total
# silence with no child process is well past any normal think/tool gap.
HEARTBEAT_SECS = 60
IDLE_BANNER_SECS = 600


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
    for task in state.get("tasks", []):
        if not isinstance(task, dict):
            continue
        for attempt in task.get("attempts", []) or []:
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

    Used by the heartbeat to tell a working pass (a `cargo`/`rustc` child
    churning) from a hung one (codex alive, no children). Best-effort: any
    `ps` failure yields an empty list, which the caller renders as "none".
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


class _Progress:
    """Shared activity state plus a serialized writer for terminal lines."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.last_activity = time.monotonic()
        self.last_summary = "(starting codex)"

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


def _heartbeat_loop(
    progress: _Progress, codex_pid: int, started: float, stop: threading.Event
) -> None:
    """Print a heartbeat every HEARTBEAT_SECS until `stop` is set."""
    while not stop.wait(HEARTBEAT_SECS):
        idle, last = progress.snapshot()
        elapsed = time.monotonic() - started
        kids = _descendants(codex_pid)
        if kids:
            uniq = sorted(set(kids))
            kid_str = f"children active: {', '.join(uniq)} ({len(kids)})"
        else:
            kid_str = "no child processes"
        progress.write_line(
            f"⏱ de-sloppify alive — elapsed {_fmt_secs(elapsed)}, "
            f"idle {_fmt_secs(idle)} — last: {last} — {kid_str}"
        )
        if idle >= IDLE_BANNER_SECS and not kids:
            progress.write_line(
                "⚠⚠ de-sloppify: codex has produced no output and "
                f"has no child process for {_fmt_secs(idle)}. It may be "
                "stuck — check the terminal. (Not killing it; Ctrl-C to "
                "abort the autopilot loop.)"
            )


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
        # Best-effort pass: a missing codex must not break the autopilot
        # loop. Report and succeed.
        print("desloppify_run: 'codex' not on PATH; skipping de-sloppify pass")
        return 0

    log_dir = find_autopilot_dir(Path.cwd())
    raw_log = (log_dir / "desloppify-last.jsonl") if log_dir else None

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
            env=env,
        )
    except OSError as exc:
        print(f"desloppify_run: failed to launch codex: {exc}",
              file=sys.stderr)
        return 0

    progress = _Progress()
    started = time.monotonic()
    stop = threading.Event()
    hb = threading.Thread(
        target=_heartbeat_loop,
        args=(progress, proc.pid, started, stop),
        daemon=True,
    )
    hb.start()

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
                progress.note_activity(None)
                progress.write_line(f"  {line[:300]}")
                continue
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
    verdict = "clean exit" if rc == 0 else f"exit code {rc}"
    progress.write_line(
        f"✓ de-sloppify: codex finished — {verdict}, "
        f"total {_fmt_secs(elapsed)}"
    )
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
