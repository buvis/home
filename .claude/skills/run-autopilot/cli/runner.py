"""cli/runner.py - spawn one routed phase session (PRD 00106).

Ports the wrapper's headless launch pipeline (PRD 00014 semantics):

    WARDEN_UNATTENDED=1 CLAUDE_UNATTENDED=1 CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0 \
      claude -p --permission-mode auto --model M --effort E \
      [--fallback-model F] --output-format stream-json --verbose "/run-autopilot" \
      </dev/null 2>&1 | tee last-session.log | _autopilot_present

One session = one -p turn = one process that exits at turn end; the
loop's decision table reads state.json after exit, never this process's
words. The raw stream-json log stays untouched and greppable
(detect_usage_limit, the metrics parse, tracon's incremental reader all
consume it); the presenter renders one-line summaries for the operator,
degrading to the raw stream if the renderer is missing or dies (the
bash `|| cat` - a dead pipe stage must never SIGPIPE-kill the session),
and discarding entirely in tracon child mode (the TUI owns the screen
and reads the log file).

WARDEN_UNATTENDED is command-scoped, exactly as in bash: warden
(claude's hook child) turns an unanswerable `ask` into a fast `deny`
instead of a forever-hang; interactive `claude` outside the loop still
prompts normally. CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0 waits
indefinitely for live subagents after the final result - the review
Watcher holds the session open while external-CLI reviewers still run;
the wall-clock cap stays the backstop.

The runner binary is an injected extension point: a routed non-claude
runner needs no spawn-layer redesign.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from cli.watchdog import Watchdog

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
RENDER_STREAM = _SCRIPTS_DIR / "render_stream.py"

LAUNCH_ENV = {
    "WARDEN_UNATTENDED": "1",
    "CLAUDE_UNATTENDED": "1",
    "CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS": "0",
}

DEFAULT_PROMPT = "/run-autopilot"
DEFAULT_GRACE_SECS = 60


@dataclass(frozen=True)
class SpawnResult:
    returncode: int
    log_path: Path
    cap_fired: bool


class _DiscardPresenter:
    """Tracon child mode: `cat >/dev/null` - the TUI reads the log file."""

    def write(self, line: bytes) -> None:
        pass

    def close(self) -> None:
        pass


class _PassthroughPresenter:
    """The `|| cat` degradation: raw stream to stdout, errors swallowed
    (a closed stdout must not kill the tee)."""

    def write(self, line: bytes) -> None:
        try:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
        except (OSError, ValueError):
            pass

    def close(self) -> None:
        pass


class _RenderStreamPresenter:
    """render_stream.py as a child, falling back to passthrough the
    moment it dies - the remaining stream keeps flowing raw, exactly as
    `python3 -u render_stream.py || cat` behaved."""

    def __init__(self) -> None:
        self._fallback: _PassthroughPresenter | None = None
        try:
            self._proc = subprocess.Popen(
                [sys.executable, "-u", str(RENDER_STREAM)],
                stdin=subprocess.PIPE,
            )
        except OSError:
            self._proc = None
            self._fallback = _PassthroughPresenter()

    def write(self, line: bytes) -> None:
        if self._fallback is not None:
            self._fallback.write(line)
            return
        assert self._proc is not None and self._proc.stdin is not None
        try:
            self._proc.stdin.write(line)
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError):
            self._fallback = _PassthroughPresenter()
            self._fallback.write(line)

    def close(self) -> None:
        if self._proc is not None:
            try:
                if self._proc.stdin is not None:
                    self._proc.stdin.close()
            except OSError:
                pass
            self._proc.wait()


def make_presenter(env: dict | None = None):
    """The wrapper's `_autopilot_present` routing: discard under
    _AUTOPILOT_TRACON_CHILD, else render with raw fallback."""
    if env is None:
        env = dict(os.environ)
    if env.get("_AUTOPILOT_TRACON_CHILD"):
        return _DiscardPresenter()
    return _RenderStreamPresenter()


def build_argv(
    model: str,
    effort: str,
    fallback_model: str | None,
    runner_bin: str = "claude",
    prompt: str = DEFAULT_PROMPT,
) -> list[str]:
    """The launch line. --fallback-model rides out primary-model
    brownouts (a ConnectionRefused relaunch storm killed a batch
    silently, 2026-07); skipped when it equals the launch model."""
    argv = [
        runner_bin,
        "-p",
        "--permission-mode",
        "auto",
        "--model",
        model,
        "--effort",
        effort,
    ]
    if fallback_model and fallback_model != model:
        argv += ["--fallback-model", fallback_model]
    argv += ["--output-format", "stream-json", "--verbose", prompt]
    return argv


def spawn(
    model: str,
    effort: str,
    cap_secs: float,
    autopilot_dir: Path,
    env: dict | None = None,
    runner_bin: str = "claude",
    prompt: str = DEFAULT_PROMPT,
    grace_secs: float = DEFAULT_GRACE_SECS,
    presenter=None,
    proc_slot: list | None = None,
) -> SpawnResult:
    """Run one phase session: launch, tee to last-session.log, present,
    enforce the wall-clock cap. Returns after the session exits (on its
    own or capped). `proc_slot[0]` receives the live Popen so the
    caller's signal teardown can terminate a mid-flight session."""
    if env is None:
        env = dict(os.environ)
    fallback = env.get("_AUTOPILOT_FALLBACK_MODEL", "claude-sonnet-5[1m]")
    argv = build_argv(model, effort, fallback, runner_bin=runner_bin, prompt=prompt)
    log_path = autopilot_dir / "last-session.log"
    if presenter is None:
        presenter = make_presenter(env)

    child_env = {**env, **LAUNCH_ENV}
    with open(log_path, "wb") as log:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=child_env,
        )
        if proc_slot is not None:
            proc_slot[0] = proc
        dog = Watchdog(proc, cap_secs=cap_secs, grace_secs=grace_secs).start()
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                log.write(line)
                log.flush()  # tracon tails this file live
                presenter.write(line)
        finally:
            rc = proc.wait()
            dog.cancel()
            presenter.close()
    return SpawnResult(returncode=rc, log_path=log_path, cap_fired=dog.fired)
