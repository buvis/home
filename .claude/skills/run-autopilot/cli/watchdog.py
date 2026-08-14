"""cli/watchdog.py - wall-clock cap for a spawned phase session (PRD 00106).

Ports the `_autopilot_session_cap` contract from
development.plugin.bash: a session that exceeds its cap gets SIGTERM,
then SIGKILL after a grace period if TERM was ignored; a session that
exits on its own under the cap is never signaled. The bash sidecar had
to FIND the claude child via pgrep/comm exact-matching (and so carried a
bystander contract); here the spawner owns the Popen handle directly,
so only that process can ever be signaled - the bystander guarantee
holds by construction and needs no resolver.

The wrapper's cap kills the WHOLE session, and a capped session is a
died session: it takes the loop's no-progress branch. Nothing here
records anything - the loop's decision table owns that.
"""

from __future__ import annotations

import subprocess
import sys
import threading


class Watchdog:
    """TERM-then-KILL cap on one child process.

    start() arms a daemon thread; the thread blocks on the child's own
    exit, so a session that finishes under the cap wakes it immediately
    and nothing is signaled. cancel() disarms a not-yet-fired cap and
    joins the thread (the post-exit `kill $_cap_pid; wait` parity).
    `fired` reports whether the cap ever signaled the child.
    """

    def __init__(
        self,
        proc: subprocess.Popen,
        cap_secs: float,
        grace_secs: float,
    ) -> None:
        self._proc = proc
        self._cap = cap_secs
        self._grace = grace_secs
        self._cancelled = threading.Event()
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self.fired = False

    def start(self) -> "Watchdog":
        self._thread.start()
        return self

    def cancel(self) -> None:
        self._cancelled.set()
        # The thread is parked in proc.wait(); the child is gone by the
        # time the loop calls cancel(), so the join is immediate.
        if self._thread.is_alive():
            self._thread.join()

    def _watch(self) -> None:
        try:
            self._proc.wait(timeout=self._cap)
            return  # exited under the cap: never signaled
        except subprocess.TimeoutExpired:
            pass
        if self._cancelled.is_set():
            return
        print(
            f"\nautoclaude: session exceeded the {int(self._cap)}s wall-clock "
            "cap; SIGTERM (session cap).",
            file=sys.stderr,
        )
        self.fired = True
        self._proc.terminate()
        try:
            self._proc.wait(timeout=self._grace)
        except subprocess.TimeoutExpired:
            print(
                "\nautoclaude: session ignored SIGTERM; SIGKILL (session cap).",
                file=sys.stderr,
            )
            self._proc.kill()
