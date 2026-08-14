"""Port of the `test_autoclaude_watchdog.sh` contract (PRD 00106).

The bash suite's sections map here as: A (under the cap nothing is
signaled; the sidecar returns when the child dies), B (over the cap a
TERM-obeying child dies by SIGTERM), C (a TERM-immune child is
KILL-escalated after the grace). The bash comm-resolution rows
(claude_immune invisible, bystanders untouched) are retired by
construction: the watchdog holds the Popen handle and can signal
nothing else.
"""

from __future__ import annotations

import signal
import subprocess
import sys
import time

from cli.watchdog import Watchdog


def _spawn_sleeper(secs: float = 300) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({secs})"])


def _spawn_term_immune() -> subprocess.Popen:
    code = (
        "import signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "print('armed', flush=True)\n"
        "time.sleep(300)\n"
    )
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE)
    assert proc.stdout is not None
    proc.stdout.readline()  # handler installed before the cap can fire
    return proc


def test_under_cap_child_untouched_and_watchdog_returns_on_exit():
    proc = _spawn_sleeper(0.3)
    dog = Watchdog(proc, cap_secs=60, grace_secs=1).start()
    proc.wait(timeout=10)
    dog.cancel()
    assert dog.fired is False
    # A negative returncode would mean the watchdog signaled it.
    assert proc.returncode == 0


def test_over_cap_term_obeying_child_dies_by_sigterm():
    proc = _spawn_sleeper(300)
    dog = Watchdog(proc, cap_secs=0.2, grace_secs=5).start()
    proc.wait(timeout=10)
    dog.cancel()
    assert dog.fired is True
    assert proc.returncode == -signal.SIGTERM


def test_term_immune_child_is_kill_escalated_after_grace():
    proc = _spawn_term_immune()
    dog = Watchdog(proc, cap_secs=0.2, grace_secs=0.3).start()
    proc.wait(timeout=10)
    dog.cancel()
    assert dog.fired is True
    assert proc.returncode == -signal.SIGKILL


def test_cancel_disarms_a_pending_cap():
    proc = _spawn_sleeper(300)
    dog = Watchdog(proc, cap_secs=60, grace_secs=1).start()
    # The loop's post-exit path: the session is being torn down by its
    # owner, not by the cap.
    proc.terminate()
    proc.wait(timeout=10)
    dog.cancel()
    assert dog.fired is False


def test_cap_messages_name_term_then_kill(capsys):
    proc = _spawn_term_immune()
    dog = Watchdog(proc, cap_secs=0.2, grace_secs=0.3).start()
    proc.wait(timeout=10)
    dog.cancel()
    err = capsys.readouterr().err
    assert "wall-clock cap; SIGTERM (session cap)." in err
    assert "ignored SIGTERM; SIGKILL (session cap)." in err


def test_watchdog_never_fires_for_a_fast_child():
    proc = _spawn_sleeper(0.1)
    dog = Watchdog(proc, cap_secs=30, grace_secs=1).start()
    proc.wait(timeout=10)
    dog.cancel()
    dog.cancel()  # second cancel is a no-op, not a re-signal
    assert dog.fired is False


def _wait_watchdog_settled(dog: Watchdog, secs: float = 5.0) -> None:
    deadline = time.monotonic() + secs
    while dog._thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)


def test_thread_exits_after_child_death_without_cancel():
    # The bash sidecar exited when the child died even if nobody killed
    # the sidecar; the thread must not linger either.
    proc = _spawn_sleeper(0.1)
    dog = Watchdog(proc, cap_secs=30, grace_secs=1).start()
    proc.wait(timeout=10)
    _wait_watchdog_settled(dog)
    assert dog._thread.is_alive() is False
