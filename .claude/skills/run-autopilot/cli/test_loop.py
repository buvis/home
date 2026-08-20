"""Tests for cli/loop.py (PRD 00106).

Re-expresses the bash loop contracts against the CLI driver: the
decision table (test_autoclaude_park.sh, test_autoclaude_review_cap.sh,
test_autoclaude_state_write_failed.sh), the preflights
(test_autoclaude_plugin_pin.sh, memory breaker, duplicate-loop guard),
the metrics line (test_loop_metrics.sh), the drained-path agoge run
(test_autoclaude_agoge_drain.sh), and the e2e launch-line assertions
from test_autoclaude_build_model.sh - all through injected
collaborators, no real claude/network/notifier.

Timing: the harness runs on a fake clock, and `state_touched` compares
the state file's mtime against it - so every scripted session that
writes state gets its mtime pinned to the fake clock, and states
pre-written by a test are stamped BEFORE the clock's start (a state
left by a previous session is by definition untouched by this one).
"""

from __future__ import annotations

import io
import json
import os
import re
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from cli import loop as loop_mod
from cli.loop import (
    Loop,
    died_next,
    fingerprint,
    last_result_field,
    live_wrapper_pid,
    pause_detail,
    plugin_drift,
    prune_registry,
    run_agoge,
)
from cli.runner import SpawnResult

_CLOCK_START = 1_000_000.0
_BEFORE_CLOCK = _CLOCK_START - 1000


class Recorder:
    def __init__(self) -> None:
        self.calls: list = []

    def __call__(self, *args, **kwargs) -> None:
        self.calls.append((args, kwargs))


class FakeClock:
    def __init__(self, start: float = _CLOCK_START) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def sleep(self, secs: float) -> None:
        self.now += secs


class ScriptedSpawn:
    """Each call runs the next step: a callable(ap_dir) that mutates the
    sandbox the way a real session would. A step that (re)writes
    state.json gets its mtime pinned to the fake clock so
    state_touched reads exactly as it would in real time."""

    def __init__(self, steps, clock: FakeClock) -> None:
        self.steps = list(steps)
        self.launches: list[dict] = []
        self.clock = clock

    def __call__(
        self,
        model,
        effort,
        *,
        cap_secs,
        autopilot_dir,
        env,
        runner_bin,
        proc_slot=None,
        **kwargs,
    ) -> SpawnResult:
        self.launches.append(
            {"model": model, "effort": effort, "cap_secs": cap_secs},
        )
        self.clock.now += 1  # a session takes wall time
        if not self.steps:
            raise AssertionError("spawned more sessions than the test scripted")
        step = self.steps.pop(0)
        state = autopilot_dir / "state.json"
        before = state.stat().st_mtime_ns if state.exists() else None
        step(autopilot_dir)
        after = state.stat().st_mtime_ns if state.exists() else None
        if after is not None and after != before:
            os.utime(state, (self.clock.now, self.clock.now))
        return SpawnResult(0, autopilot_dir / "last-session.log", False)


def write_state(ap_dir: Path, at: float = _BEFORE_CLOCK, **fields) -> None:
    path = ap_dir / "state.json"
    path.write_text(json.dumps(fields))
    os.utime(path, (at, at))


def write_log(ap_dir: Path, *events) -> None:
    lines = [json.dumps(event) for event in events]
    (ap_dir / "last-session.log").write_text("\n".join(lines) + "\n")


def terminal_step(prd: str = "00099-drained-v1.md", batch: str = "b-1", **extra):
    def step(ap_dir: Path) -> None:
        (ap_dir / "state.json").write_text(
            json.dumps({"prd": prd, "next_phase": "", "batch": {"id": batch, **extra}}),
        )
        write_log(
            ap_dir,
            {"type": "result", "total_cost_usd": 0.01, "usage": {"output_tokens": 10}},
        )

    return step


def noop_step(ap_dir: Path) -> None:  # session dies: touches nothing
    pass


def make_loop(tmp_path: Path, steps, env: dict | None = None, **kwargs):
    repo = tmp_path / "repo"
    ap_dir = repo / "dev" / "local" / "autopilot"
    ap_dir.mkdir(parents=True, exist_ok=True)
    clock = kwargs.pop("clock", None) or FakeClock()
    spawn = ScriptedSpawn(steps, clock=clock)
    notify = Recorder()
    sleeps: list[float] = []

    def sleep(secs: float) -> None:
        sleeps.append(secs)
        clock.sleep(secs)

    full_env = {"_AUTOPILOT_LOOPS_DIR": str(tmp_path / "loops")}
    full_env.update(env or {})
    out, err = io.StringIO(), io.StringIO()
    lp = Loop(
        cwd=repo,
        env=full_env,
        spawn_fn=kwargs.pop("spawn_fn", None) or spawn,
        notify_fn=notify,
        sleep_fn=sleep,
        pressure_fn=kwargs.pop("pressure_fn", lambda: 1),
        probe_fn=kwargs.pop("probe_fn", lambda: True),
        detect_limit_fn=kwargs.pop("detect_limit_fn", lambda path: None),
        clock=clock,
        out=out,
        err=err,
        **kwargs,
    )
    lp._test = {
        "ap_dir": ap_dir,
        "spawn": spawn,
        "notify": notify,
        "sleeps": sleeps,
        "out": out,
        "err": err,
        "clock": clock,
    }
    return lp


def _notified(lp, fragment: str) -> bool:
    return any(
        fragment in args[0] or fragment in args[1]
        for args, _ in lp._test["notify"].calls
    )


_REAL_CLEANUP_ORPHANS = Loop._cleanup_orphans


@pytest.fixture(autouse=True)
def _no_real_drain_side_effects(monkeypatch):
    """The drained branch shells to purge/agoge, and the orphan sweep
    shells to pgrep/ps on the REAL process table - keep loop runs
    hermetic and fast. Direct tests use the saved originals."""
    monkeypatch.setattr(loop_mod, "run_purge", lambda repo: None)
    monkeypatch.setattr(
        loop_mod,
        "run_agoge",
        lambda ap_dir, batch, drained, env, out, claude_bin="claude": None,
    )
    monkeypatch.setattr(Loop, "_cleanup_orphans", lambda self: None)


# ── pure ports ───────────────────────────────────────────────────────────────


def test_died_next_bootstrap_halts_loud():
    assert died_next("", 0, 1) == "die"


def test_died_next_retries_until_budget_then_parks():
    assert died_next("00001-x.md", 0, 1) == "retry"
    assert died_next("00001-x.md", 1, 1) == "park"


def test_pause_detail_prefers_the_reason_detail():
    assert pause_detail({"pause_reason": {"detail": "need a human"}}) == "need a human"


def test_pause_detail_string_reason_passes_through():
    assert pause_detail({"pause_reason": "blocked on credentials"}) == (
        "blocked on credentials"
    )


def test_pause_detail_summarizes_the_review_cap():
    state = {
        "phase": "paused",
        "cap_pause_reason": {
            "cycle": 3,
            "cap": 3,
            "unresolved_findings": [{"issue": "a"}, {"issue": "b"}],
        },
    }
    assert pause_detail(state) == "review cap hit: cycle 3/3 · 2 unresolved findings"


def test_pause_detail_paused_phase_alone_says_paused():
    assert pause_detail({"phase": "paused"}) == "paused"


def test_pause_detail_empty_when_not_paused():
    assert pause_detail({"phase": "review", "pause_reason": None}) == ""


def test_fingerprint_binds_the_progress_fields():
    state = {
        "prd": "p.md",
        "next_phase": "review",
        "tasks_completed": 3,
        "review_cycles": 1,
        "cycle": 2,
        "cap_rotations": [{}],
        "replan_count": 0,
    }
    assert fingerprint(state) == "p.md|review|3|1|2|1|0"


def test_fingerprint_defaults_missing_fields_like_jq():
    assert fingerprint({}) == "null|null|-1|-1|-1|0|-1"


def test_plugin_drift_names_the_rotated_plugin():
    state = {"batch": {"plugin_versions": {"aegis@buvis-plugins": "0.3.1"}}}
    installed = {"plugins": {"aegis@buvis-plugins": [{"version": "0.4.0"}]}}
    assert plugin_drift(state, installed) == (
        "aegis@buvis-plugins pinned=0.3.1 now=0.4.0"
    )


def test_plugin_drift_missing_install_reads_missing():
    state = {"batch": {"plugin_versions": {"warden@buvis-plugins": "0.13.0"}}}
    assert plugin_drift(state, {"plugins": {}}) == (
        "warden@buvis-plugins pinned=0.13.0 now=MISSING"
    )


def test_plugin_drift_unpinned_batch_never_blocks():
    assert plugin_drift({"batch": {}}, {"plugins": {}}) is None
    assert plugin_drift({}, {}) is None


def test_plugin_drift_matching_pins_pass():
    state = {"batch": {"plugin_versions": {"a": "1.0"}}}
    installed = {"plugins": {"a": [{"version": "1.0"}]}}
    assert plugin_drift(state, installed) is None


def test_last_result_field_takes_the_final_event(tmp_path):
    log = tmp_path / "log"
    log.write_text(
        json.dumps({"type": "result", "total_cost_usd": 1.0})
        + "\n"
        + "not json\n"
        + json.dumps({"type": "result", "total_cost_usd": 2.5})
        + "\n",
    )
    assert last_result_field(log, "total_cost_usd") == 2.5


def test_last_result_field_error_only_filters(tmp_path):
    log = tmp_path / "log"
    log.write_text(
        json.dumps({"type": "result", "result": "fine"})
        + "\n"
        + json.dumps({"type": "result", "is_error": True, "result": "ECONNREFUSED"})
        + "\n",
    )
    assert last_result_field(log, "result", error_only=True) == "ECONNREFUSED"


# ── the drained happy path (the bash e2e rows) ───────────────────────────────


def test_drained_batch_exits_zero_with_banner_and_notification(tmp_path):
    lp = make_loop(tmp_path, [terminal_step(batch="20260708-e2e")])
    ap = lp._test["ap_dir"]
    write_state(
        ap,
        prd="00088-thin-v1.md",
        next_phase="build",
        replan_count=0,
        cap_rotations=[],
        stall_reason=None,
        batch={"id": "20260708-e2e"},
    )
    rc = lp.run()
    assert rc == 0
    out = lp._test["out"].getvalue()
    assert "Backlog drained." in out
    assert "━━" in out and "phase build" in out
    assert _notified(lp, "Backlog drained.")
    assert (ap / "reports" / "20260708-e2e-state-final.json").exists()
    assert not (ap / "state.json").exists()


def test_signal_free_build_launches_sonnet_xhigh(tmp_path):
    lp = make_loop(tmp_path, [terminal_step()])
    ap = lp._test["ap_dir"]
    prds = ap.parent / "prds" / "wip"
    prds.mkdir(parents=True)
    (prds / "00088-thin-v1.md").write_text("# fixture\n")
    write_state(
        ap,
        prd="00088-thin-v1.md",
        next_phase="build",
        replan_count=0,
        cap_rotations=[],
        stall_reason=None,
        batch={"id": "b"},
    )
    assert lp.run() == 0
    launch = lp._test["spawn"].launches[0]
    assert launch["model"] == "claude-sonnet-5[1m]"
    assert launch["effort"] == "xhigh"


def test_build_kill_switch_wins(tmp_path):
    lp = make_loop(
        tmp_path,
        [terminal_step()],
        env={"_AUTOPILOT_MODEL_BUILD": "claude-opus-5[1m]"},
    )
    write_state(lp._test["ap_dir"], prd="p.md", next_phase="build", batch={"id": "b"})
    assert lp.run() == 0
    assert lp._test["spawn"].launches[0]["model"] == "claude-opus-5[1m]"


def test_bootstrap_without_state_is_a_build_launch(tmp_path):
    lp = make_loop(tmp_path, [terminal_step()])
    assert lp.run() == 0
    launch = lp._test["spawn"].launches[0]
    assert launch["model"] == "claude-sonnet-5[1m]"
    assert "bootstrap" in lp._test["out"].getvalue()


def test_review_branch_routes_opus_with_review_cap(tmp_path):
    lp = make_loop(tmp_path, [terminal_step()])
    write_state(lp._test["ap_dir"], prd="p.md", next_phase="review", batch={"id": "b"})
    assert lp.run() == 0
    launch = lp._test["spawn"].launches[0]
    assert launch["model"] == "claude-opus-5[1m]"
    assert launch["cap_secs"] == 10800


def test_done_branch_routes_sonnet_medium(tmp_path):
    lp = make_loop(tmp_path, [terminal_step()])
    write_state(lp._test["ap_dir"], prd="p.md", next_phase="done", batch={"id": "b"})
    assert lp.run() == 0
    launch = lp._test["spawn"].launches[0]
    assert launch["model"] == "claude-sonnet-5[1m]"
    assert launch["effort"] == "medium"


def test_continue_relaunches_until_drain(tmp_path):
    def review_step(ap_dir: Path) -> None:
        (ap_dir / "state.json").write_text(
            json.dumps({"prd": "p.md", "next_phase": "review", "batch": {"id": "b"}}),
        )
        write_log(ap_dir, {"type": "result"})

    lp = make_loop(tmp_path, [review_step, terminal_step()])
    write_state(lp._test["ap_dir"], prd="p.md", next_phase="build", batch={"id": "b"})
    assert lp.run() == 0
    assert len(lp._test["spawn"].launches) == 2
    assert "Continuing (next phase: review)" in lp._test["out"].getvalue()


# ── decision table ───────────────────────────────────────────────────────────


def test_state_write_failed_marker_wins_over_a_healthy_state(tmp_path):
    def step(ap_dir: Path) -> None:
        terminal_step()(ap_dir)
        (ap_dir / "state-write-failed").write_text(
            json.dumps({"detail": "transaction raised"}),
        )

    lp = make_loop(tmp_path, [step])
    assert lp.run() == 1
    assert "transaction raised" in lp._test["err"].getvalue()
    assert _notified(lp, "State write failed")


def test_paused_state_prints_detail_runbook_and_notifies(tmp_path):
    def step(ap_dir: Path) -> None:
        (ap_dir / "state.json").write_text(
            json.dumps(
                {
                    "prd": "p.md",
                    "next_phase": "review",
                    "pause_reason": {"detail": "design gate needs the operator"},
                    "batch": {"id": "b"},
                },
            ),
        )

    lp = make_loop(tmp_path, [step])
    assert lp.run() == 1
    err = lp._test["err"].getvalue()
    assert "design gate needs the operator" in err
    assert "/run-autopilot" in err
    assert _notified(lp, "Paused: design gate needs the operator")


def test_review_cap_pause_summarizes_and_lists_findings(tmp_path):
    def step(ap_dir: Path) -> None:
        (ap_dir / "state.json").write_text(
            json.dumps(
                {
                    "prd": "p.md",
                    "next_phase": "review",
                    "phase": "paused",
                    "cap_pause_reason": {
                        "cycle": 3,
                        "cap": 3,
                        "unresolved_findings": [
                            {"severity": "High", "issue": "the gate lies"},
                            {"severity": "Low", "issue": "typo"},
                        ],
                    },
                    "batch": {"id": "b"},
                },
            ),
        )

    lp = make_loop(tmp_path, [step])
    assert lp.run() == 1
    err = lp._test["err"].getvalue()
    assert "review cap hit: cycle 3/3 · 2 unresolved findings" in err
    assert "[High] the gate lies" in err


def test_subagent_prompt_overrun_replans_in_place(tmp_path):
    def overrun(ap_dir: Path) -> None:
        (ap_dir / "state.json").write_text(
            json.dumps(
                {
                    "prd": "p.md",
                    "next_phase": "build",
                    "stall_reason": {"stalled": "subagent_prompt_overrun"},
                    "batch": {"id": "b"},
                },
            ),
        )

    lp = make_loop(tmp_path, [overrun, terminal_step()])
    assert lp.run() == 0
    assert "replanned" in lp._test["out"].getvalue()


def test_bootstrap_death_halts_loud_with_no_state(tmp_path):
    lp = make_loop(tmp_path, [noop_step])
    assert lp.run() == 1
    assert "no state.json" in lp._test["err"].getvalue()
    assert _notified(lp, "Needs attention")


def test_unreadable_state_death_names_it(tmp_path):
    def step(ap_dir: Path) -> None:
        (ap_dir / "state.json").write_text("{broken")

    lp = make_loop(tmp_path, [step])
    assert lp.run() == 1
    assert "state.json unreadable" in lp._test["err"].getvalue()


def test_died_session_retries_once_then_parks_then_guard_halts(tmp_path):
    # A valid but never-touched state: retry 1/1, then park (marker +
    # notify ⏭), then the unconsumed-marker guard backs off once and
    # halts on the second relaunch. Four sessions total.
    lp = make_loop(tmp_path, [noop_step, noop_step, noop_step, noop_step])
    ap = lp._test["ap_dir"]
    write_state(ap, prd="00044-x-v1.md", next_phase="build", batch={"id": "b"})
    rc = lp.run()
    assert rc == 1
    out = lp._test["out"].getvalue()
    err = lp._test["err"].getvalue()
    # The retry detail is recorded in the decision, not printed - the
    # bash act branch prints the plain continue line (parity).
    assert "Continuing (next phase: build)" in out
    assert "parking 00044-x-v1.md" in out
    marker = json.loads((ap / "park-requested").read_text())
    assert marker["prd"] == "00044-x-v1.md"
    assert "died after 1 retries" in marker["reason"]
    assert "park-requested pending (relaunch 1)" in err
    assert 30 in lp._test["sleeps"]
    assert "park-requested unconsumed (2 relaunches" in err
    assert _notified(lp, "Park marker unconsumed")
    assert _notified(lp, "Parking 00044-x-v1.md.")
    assert len(lp._test["spawn"].launches) == 4


def test_usage_limit_waits_then_resumes(tmp_path):
    clock = FakeClock()
    reset = int(clock.now) + 300
    lp = make_loop(
        tmp_path,
        [noop_step, terminal_step()],
        clock=clock,
        detect_limit_fn=lambda path: reset,
    )
    write_state(lp._test["ap_dir"], prd="p.md", next_phase="build", batch={"id": "b"})
    assert lp.run() == 0
    assert any(secs >= 300 for secs in lp._test["sleeps"])
    assert _notified(lp, "Usage limit")
    assert "usage-limit; resuming ~" in lp._test["out"].getvalue()


def test_usage_limit_beyond_the_wait_cap_dies(tmp_path):
    clock = FakeClock()
    lp = make_loop(
        tmp_path,
        [noop_step],
        clock=clock,
        detect_limit_fn=lambda path: int(clock.now) + 50_000,
    )
    write_state(lp._test["ap_dir"], prd="p.md", next_phase="build", batch={"id": "b"})
    assert lp.run() == 1
    assert "beyond _AUTOPILOT_LIMIT_WAIT_MAX" in lp._test["err"].getvalue()


def test_network_outage_polls_and_resumes(tmp_path):
    def netfail(ap_dir: Path) -> None:
        write_log(
            ap_dir,
            {
                "type": "result",
                "is_error": True,
                "result": "fetch failed: unable to connect to api.anthropic.com",
            },
        )

    lp = make_loop(tmp_path, [netfail, terminal_step()], probe_fn=lambda: True)
    write_state(lp._test["ap_dir"], prd="p.md", next_phase="build", batch={"id": "b"})
    assert lp.run() == 0
    # The poll message lands on stderr during the decision; the act
    # branch then prints the plain continue line (bash parity).
    assert "Polling connectivity, max 1800s (retry 1/3)" in lp._test["err"].getvalue()
    assert "Backlog drained" in lp._test["out"].getvalue()


def test_network_outage_that_never_clears_dies(tmp_path):
    def netfail(ap_dir: Path) -> None:
        write_log(
            ap_dir,
            {"type": "result", "is_error": True, "result": "ECONNREFUSED"},
        )

    lp = make_loop(
        tmp_path,
        [netfail],
        probe_fn=lambda: False,
        env={"_AUTOPILOT_NET_WAIT_MAX": "60"},
    )
    write_state(lp._test["ap_dir"], prd="p.md", next_phase="build", batch={"id": "b"})
    assert lp.run() == 1
    assert "API unreachable for 60s" in lp._test["err"].getvalue()


def test_repeated_network_failures_exhaust_the_retry_cap(tmp_path):
    def netfail(ap_dir: Path) -> None:
        write_log(
            ap_dir,
            {"type": "result", "is_error": True, "result": "connection reset"},
        )

    lp = make_loop(tmp_path, [netfail], probe_fn=lambda: True)
    write_state(lp._test["ap_dir"], prd="p.md", next_phase="build", batch={"id": "b"})
    lp._net_retries = 3  # three prior relaunches this loop
    assert lp.run() == 1
    assert "repeated API connection failures (3 relaunches)" in (
        lp._test["err"].getvalue()
    )


def test_fingerprint_bound_parks_a_prd_burning_sessions(tmp_path):
    def same_state(ap_dir: Path) -> None:
        (ap_dir / "state.json").write_text(
            json.dumps(
                {
                    "prd": "p.md",
                    "next_phase": "review",
                    "review_cycles": 2,
                    "batch": {"id": "b"},
                },
            ),
        )
        write_log(ap_dir, {"type": "result"})

    def same_state_then_operator_pause(ap_dir: Path) -> None:
        same_state(ap_dir)
        (ap_dir / "pause-requested").touch()

    lp = make_loop(
        tmp_path,
        [same_state, same_state, same_state_then_operator_pause],
        env={"_AUTOPILOT_PHASE_REPEATS_MAX": "2"},
    )
    rc = lp.run()  # session 3 parks; iteration 4 consumes the pause
    assert rc == 0
    assert "no progress across 2 sessions; parking p.md" in (lp._test["out"].getvalue())
    assert (lp._test["ap_dir"] / "park-requested").exists()
    assert len(lp._test["spawn"].launches) == 3


def test_metrics_line_lands_in_primary_and_ledger_mirror(tmp_path):
    lp = make_loop(tmp_path, [terminal_step(batch="mb-1")])
    write_state(
        lp._test["ap_dir"],
        prd="00001-m-v1.md",
        next_phase="build",
        batch={"id": "mb-1"},
    )
    assert lp.run() == 0
    ap = lp._test["ap_dir"]
    primary = (ap / "loop-metrics.jsonl").read_text().strip().splitlines()
    mirror = (ap / "ledger" / "loop-metrics.jsonl").read_text().strip().splitlines()
    assert primary == mirror
    assert len(primary) == 1
    row = json.loads(primary[0])
    assert row["signal"] == "done"
    assert row["phase_launched"] == "build"
    assert row["phase_end"] == ""
    assert row["model"] == "claude-sonnet-5[1m]"
    assert row["cost_usd"] == 0.01
    assert row["tokens_out"] == 10
    assert row["wall_secs"] == row["ts_end"] - row["ts_start"]


def test_one_metrics_line_per_session(tmp_path):
    def review_step(ap_dir: Path) -> None:
        (ap_dir / "state.json").write_text(
            json.dumps({"prd": "p.md", "next_phase": "review", "batch": {"id": "b"}}),
        )
        write_log(ap_dir, {"type": "result"})

    lp = make_loop(tmp_path, [review_step, terminal_step()])
    write_state(lp._test["ap_dir"], prd="p.md", next_phase="build", batch={"id": "b"})
    assert lp.run() == 0
    rows = (lp._test["ap_dir"] / "loop-metrics.jsonl").read_text().strip().splitlines()
    assert [json.loads(row)["signal"] for row in rows] == ["continue", "done"]


# ── preflights ───────────────────────────────────────────────────────────────


def test_pause_marker_stops_before_any_spawn(tmp_path):
    lp = make_loop(tmp_path, [])
    ap = lp._test["ap_dir"]
    (ap / "pause-requested").touch()
    assert lp.run() == 0
    assert not (ap / "pause-requested").exists()
    assert lp._test["spawn"].launches == []
    assert _notified(lp, "Paused by operator")


def test_pause_exit_stamps_the_stop_for_the_observer(tmp_path):
    # The exit appends no metrics row, so the stamp is the only trace that
    # tells tracon this was a deliberate stop and not a dropped batch.
    lp = make_loop(tmp_path, [])
    ap = lp._test["ap_dir"]
    (ap / "pause-requested").touch()
    assert lp.run() == 0
    assert (ap / "paused-by-operator").is_file()


def test_pause_exit_names_autoclaude_as_the_resume(tmp_path):
    # An operator pause consumes its marker and blocks on nothing, so
    # autoclaude alone resumes. Only the _act_paused exit (a paused STATE
    # the loop would re-read) makes the interactive step mandatory.
    lp = make_loop(tmp_path, [])
    (lp._test["ap_dir"] / "pause-requested").touch()
    assert lp.run() == 0
    assert "Resume unattended: autoclaude" in lp._test["out"].getvalue()


def test_a_resumed_loop_clears_the_pause_stamp(tmp_path):
    lp = make_loop(tmp_path, [terminal_step()])
    ap = lp._test["ap_dir"]
    (ap / "paused-by-operator").touch()
    assert lp.run() == 0
    assert not (ap / "paused-by-operator").exists()


def test_plugin_drift_halts_before_any_spawn(tmp_path):
    plugins = tmp_path / "installed_plugins.json"
    plugins.write_text(
        json.dumps({"plugins": {"aegis@buvis-plugins": [{"version": "9.9.9"}]}}),
    )
    lp = make_loop(
        tmp_path,
        [],
        env={"_AUTOPILOT_PLUGINS_JSON": str(plugins)},
    )
    write_state(
        lp._test["ap_dir"],
        prd="p.md",
        next_phase="build",
        batch={"id": "b", "plugin_versions": {"aegis@buvis-plugins": "0.3.1"}},
    )
    assert lp.run() == 1
    assert "plugin version drift" in lp._test["err"].getvalue()
    assert lp._test["spawn"].launches == []
    assert _notified(lp, "Plugin drift")


def test_matching_plugin_pins_proceed(tmp_path):
    plugins = tmp_path / "installed_plugins.json"
    plugins.write_text(
        json.dumps({"plugins": {"aegis@buvis-plugins": [{"version": "0.3.1"}]}}),
    )
    lp = make_loop(
        tmp_path,
        [terminal_step()],
        env={"_AUTOPILOT_PLUGINS_JSON": str(plugins)},
    )
    write_state(
        lp._test["ap_dir"],
        prd="p.md",
        next_phase="build",
        batch={"id": "b", "plugin_versions": {"aegis@buvis-plugins": "0.3.1"}},
    )
    assert lp.run() == 0


def test_memory_pressure_that_never_clears_halts(tmp_path):
    lp = make_loop(
        tmp_path,
        [],
        pressure_fn=lambda: 4,
        env={"_AUTOPILOT_MEM_WAIT_MAX": "120", "_AUTOPILOT_MEM_POLL_SECS": "60"},
    )
    assert lp.run() == 1
    assert "memory pressure still elevated" in lp._test["err"].getvalue()
    assert lp._test["spawn"].launches == []
    assert _notified(lp, "memory pressure")


def test_memory_pressure_that_clears_resumes(tmp_path):
    readings = [4, 1, 1]
    lp = make_loop(
        tmp_path,
        [terminal_step()],
        pressure_fn=lambda: readings.pop(0) if readings else 1,
        env={"_AUTOPILOT_MEM_WAIT_MAX": "600"},
    )
    assert lp.run() == 0
    assert "memory pressure cleared" in lp._test["err"].getvalue()


def test_future_schema_state_refuses_before_spawn(tmp_path):
    lp = make_loop(tmp_path, [])
    write_state(
        lp._test["ap_dir"],
        prd="p.md",
        next_phase="build",
        schema_version=99,
        batch={"id": "b"},
    )
    assert lp.run() == 1
    assert "newer than this CLI understands" in lp._test["err"].getvalue()
    assert lp._test["spawn"].launches == []


def test_unstamped_state_warns_and_proceeds(tmp_path):
    lp = make_loop(tmp_path, [terminal_step()])
    write_state(lp._test["ap_dir"], prd="p.md", next_phase="build", batch={"id": "b"})
    assert lp.run() == 0
    assert "schema status 'unstamped'" in lp._test["err"].getvalue()


# ── registry ─────────────────────────────────────────────────────────────────


def _spawn_tagged_incumbent() -> subprocess.Popen:
    """A live process whose ps env carries its own _AUTOPILOT_LOOP=<pid>
    tag: exec keeps the shell's pid, so $$ IS the final pid."""
    proc = subprocess.Popen(
        [
            "bash",
            "-c",
            f"exec env _AUTOPILOT_LOOP=$$ {sys.executable} -c "
            '"import time; time.sleep(60)"',
        ],
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        out = subprocess.run(
            ["ps", "ewww", "-p", str(proc.pid), "-o", "command="],
            capture_output=True,
            text=True,
        ).stdout
        if f"_AUTOPILOT_LOOP={proc.pid}" in out:
            return proc
        time.sleep(0.05)
    raise AssertionError("tagged incumbent never appeared in ps")


def test_duplicate_loop_guard_refuses_a_second_loop(tmp_path):
    loops = tmp_path / "loops"
    loops.mkdir()
    lp = make_loop(tmp_path, [])
    root = tmp_path / "repo"
    incumbent = _spawn_tagged_incumbent()
    try:
        (loops / f"{incumbent.pid}.json").write_text(
            json.dumps({"pid": incumbent.pid, "root": str(root)}),
        )
        assert lp.run() == 1
        assert "already running" in lp._test["err"].getvalue()
        assert lp._test["spawn"].launches == []
    finally:
        incumbent.kill()
        incumbent.wait()


def test_cleanup_orphans_hups_a_tagged_ppid1_process(tmp_path):
    tag = "424242"
    # bash backgrounds python and exits, so the child reparents to
    # launchd (PPID 1) carrying the loop tag in its env - exactly the
    # stray the sweep exists to reap.
    # The child's fds must not inherit bash's stdout pipe, or
    # capture_output blocks until the ORPHAN exits, not bash.
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'{sys.executable} -c "import time; time.sleep(60)" '
            ">/dev/null 2>&1 & echo $!",
        ],
        env={**os.environ, "_AUTOPILOT_LOOP": tag},
        capture_output=True,
        text=True,
    )
    orphan_pid = int(result.stdout.strip())
    lp = make_loop(tmp_path, [], env={"_AUTOPILOT_LOOP": tag})
    assert lp.loop_pid == int(tag)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            _REAL_CLEANUP_ORPHANS(lp)
            try:
                os.kill(orphan_pid, 0)
            except ProcessLookupError:
                return  # HUP delivered; the orphan is gone
            time.sleep(0.1)
        raise AssertionError("tagged orphan survived the cleanup sweep")
    finally:
        try:
            os.kill(orphan_pid, 9)
        except (ProcessLookupError, PermissionError):
            pass


def test_registry_entry_written_and_removed_at_teardown(tmp_path):
    lp = make_loop(tmp_path, [terminal_step()])
    write_state(lp._test["ap_dir"], prd="p.md", next_phase="build", batch={"id": "b"})
    assert lp.run() == 0
    assert list((tmp_path / "loops").glob("*.json")) == []


def test_registry_entry_carries_the_tracon_contract_shape(tmp_path):
    # tracon.discovery parses these entries: pid int, root/ap_dir absolute
    # strings (root = ap_dir minus /dev/local/autopilot), started_at ISO.
    lp = make_loop(tmp_path, [])
    ap_dir = lp._resolve_ap_dir()
    assert lp._register(ap_dir) is None
    entries = list((tmp_path / "loops").glob("*.json"))
    assert len(entries) == 1
    entry = json.loads(entries[0].read_text())
    assert entry["pid"] == lp.loop_pid
    assert entry["ap_dir"] == str(ap_dir)
    assert Path(entry["root"]).is_absolute()
    assert str(ap_dir) == entry["root"] + "/dev/local/autopilot"
    assert entries[0].name == f"{lp.loop_pid}.json"
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", entry["started_at"])


def test_own_stale_registry_entry_is_overwritten_not_refused(tmp_path):
    # A SIGKILLed python driver leaves an entry naming this shell's own
    # (still-alive) pid; the relaunch from the same shell must overwrite
    # it rather than refuse against itself.
    loops = tmp_path / "loops"
    loops.mkdir()
    lp = make_loop(tmp_path, [terminal_step()])
    (loops / f"{lp.loop_pid}.json").write_text(
        json.dumps({"pid": lp.loop_pid, "root": str(tmp_path / "repo")}),
    )
    assert lp.run() == 0
    assert "already running" not in lp._test["err"].getvalue()
    assert list(loops.glob("*.json")) == []  # teardown removed the rewrite


def test_loop_drives_the_real_runner_spawn_end_to_end(tmp_path):
    # The scripted spawns mirror runner.spawn's signature; this test binds
    # Loop to the REAL runner.spawn with a stub claude binary, so a
    # signature drift between the two fails here, not in a live batch.
    stub = tmp_path / "stub-claude"
    ap_rel = "repo/dev/local/autopilot"
    stub.write_text(
        f"#!{sys.executable}\n"
        "import json, pathlib, sys\n"
        f"ap = pathlib.Path({str(tmp_path)!r}) / {ap_rel!r}\n"
        "(ap / 'state.json').write_text(json.dumps("
        "{'prd': 'p.md', 'next_phase': '', 'batch': {'id': 'real-1'}}))\n"
        "print(json.dumps({'type': 'result', 'total_cost_usd': 0.02,"
        " 'usage': {'output_tokens': 7}}))\n",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)

    repo = tmp_path / "repo"
    ap_dir = repo / "dev" / "local" / "autopilot"
    ap_dir.mkdir(parents=True)
    notify = Recorder()
    out, err = io.StringIO(), io.StringIO()
    lp = Loop(
        cwd=repo,
        env={
            "PATH": os.environ["PATH"],
            "_AUTOPILOT_LOOPS_DIR": str(tmp_path / "loops"),
            "_AUTOPILOT_TRACON_CHILD": "1",  # discard presenter: no render child
        },
        notify_fn=notify,
        pressure_fn=lambda: 1,
        out=out,
        err=err,
        runner_bin=str(stub),
    )
    lp._cleanup_orphans = lambda: None  # keep the real-spawn test hermetic too
    assert lp.run() == 0
    assert "Backlog drained." in out.getvalue()
    row = json.loads(
        (ap_dir / "loop-metrics.jsonl").read_text().strip().splitlines()[0],
    )
    assert row["signal"] == "done"
    assert row["cost_usd"] == 0.02
    assert (ap_dir / "last-session.log").read_bytes().startswith(b'{"type": "result"')


def test_registry_write_failure_runs_unregistered_loud(tmp_path):
    # A read-only loops dir: the write fails, the loop says so and keeps
    # going rather than halting (the bash jq-failure contract).
    loops = tmp_path / "loops"
    loops.mkdir()
    loops.chmod(0o500)
    try:
        lp = make_loop(tmp_path, [terminal_step()])
        assert lp.run() == 0
        assert "registry write failed; running unregistered" in (
            lp._test["err"].getvalue()
        )
    finally:
        loops.chmod(0o700)


def test_loops_dir_is_propagated_to_session_children(tmp_path):
    # The resolved loops dir must reach children via the env (tracon's
    # discovery.py reads it from its own environment at import time).
    lp = make_loop(tmp_path, [terminal_step()])
    assert lp.run() == 0
    assert lp.env["_AUTOPILOT_LOOPS_DIR"] == str(tmp_path / "loops")
    assert lp.env["_AUTOPILOT_LOOP"] == str(lp.loop_pid)


def _spawn_forked_loop_shell() -> subprocess.Popen:
    """The tracon layout: a shell that exports the tag AFTER its own exec
    and keeps a tagged child alive. ps reports the EXEC-time environment,
    so the tag is visible on the child only - never on the shell whose pid
    the registry stores."""
    proc = subprocess.Popen(
        [
            "bash",
            "-c",
            f"export _AUTOPILOT_LOOP=$$; {sys.executable} -c "
            '"import time; time.sleep(60)" & wait',
        ],
        start_new_session=True,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        kids = subprocess.run(
            ["pgrep", "-P", str(proc.pid)],
            capture_output=True,
            text=True,
        ).stdout
        if kids.strip():
            return proc
        time.sleep(0.05)
    os.killpg(proc.pid, signal.SIGKILL)
    raise AssertionError("forked loop shell never spawned its tagged child")


def test_prune_keeps_a_loop_shell_tagged_only_on_its_child(tmp_path):
    # The registry stores the process-group LEADER (the forked shell), but
    # the tag reaches ps only on the exec'd driver beneath it. Pruning that
    # entry blinds tracon to a live loop: no pause chip, no limit-wait, and
    # q -> s reports "nothing to stop".
    loops = tmp_path / "loops"
    loops.mkdir()
    shell = _spawn_forked_loop_shell()
    try:
        entry = loops / f"{shell.pid}.json"
        entry.write_text(json.dumps({"pid": shell.pid, "root": "/x"}))
        prune_registry(loops, own_pid=4242)
        assert entry.exists()
    finally:
        os.killpg(shell.pid, signal.SIGKILL)
        shell.wait()


def test_prune_removes_dead_untagged_and_malformed_entries(tmp_path):
    loops = tmp_path / "loops"
    loops.mkdir()
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    (loops / "dead.json").write_text(json.dumps({"pid": dead.pid, "root": "/x"}))
    (loops / "junk.json").write_text("{not json")
    # pid 1 is alive but its env carries no _AUTOPILOT_LOOP tag: recycled.
    (loops / "recycled.json").write_text(json.dumps({"pid": 1, "root": "/z"}))
    (loops / "own.json").write_text(json.dumps({"pid": 4242, "root": "/y"}))
    prune_registry(loops, own_pid=4242)
    assert not (loops / "dead.json").exists()
    assert not (loops / "junk.json").exists()
    assert not (loops / "recycled.json").exists()
    assert (loops / "own.json").exists()  # never our own entry


def test_live_wrapper_pid_ignores_an_alive_but_untagged_pid(tmp_path):
    # A recycled or borrowed pid can be genuinely alive at the right root
    # without ever having been the loop - only the _AUTOPILOT_LOOP tag
    # proves incumbency.
    loops = tmp_path / "loops"
    loops.mkdir()
    root = tmp_path / "repo"
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    try:
        (loops / f"{proc.pid}.json").write_text(
            json.dumps({"pid": proc.pid, "root": str(root)}),
        )
        assert live_wrapper_pid(root, loops) is None
    finally:
        proc.kill()
        proc.wait()


def test_prune_spares_an_unreadable_entry_and_it_resolves_once_readable(tmp_path):
    # An OSError reading the file means "I couldn't check this", not "this
    # is garbage" - prune must leave it alone, and once it can be read
    # again the tagged loop it names must still resolve.
    loops = tmp_path / "loops"
    loops.mkdir()
    root = tmp_path / "repo"
    shell = _spawn_forked_loop_shell()
    entry = loops / f"{shell.pid}.json"
    try:
        entry.write_text(json.dumps({"pid": shell.pid, "root": str(root)}))
        try:
            entry.chmod(0o000)
            prune_registry(loops, own_pid=4242)
            assert entry.exists()
            assert live_wrapper_pid(root, loops) is None
        finally:
            if entry.exists():
                entry.chmod(0o644)
        assert live_wrapper_pid(root, loops) == shell.pid
    finally:
        os.killpg(shell.pid, signal.SIGKILL)
        shell.wait()


def test_prune_deletes_an_entry_with_invalid_utf8_bytes_without_raising(tmp_path):
    # UnicodeDecodeError is a ValueError subclass, not an OSError: it must
    # not escape the except OSError guarding the read, and the entry is
    # garbage (like invalid JSON), not merely unreadable - it gets deleted.
    loops = tmp_path / "loops"
    loops.mkdir()
    entry = loops / "garbage.json"
    entry.write_bytes(b"\xff\xfe\x00binary")
    prune_registry(loops, own_pid=4242)
    assert not entry.exists()


def test_prune_deletes_a_utf16_encoded_entry_even_when_its_pid_is_live_and_tagged(
    tmp_path,
):
    # The registry is a UTF-8 JSON directory by contract. A spawned, live,
    # correctly TAGGED pid is used here so nothing else could explain a
    # deletion: json.loads auto-detects UTF-16 from the BOM and parses this
    # entry fine, so only the encoding - not liveness, not the tag - can be
    # the reason it gets pruned.
    loops = tmp_path / "loops"
    loops.mkdir()
    shell = _spawn_forked_loop_shell()
    try:
        entry = loops / f"{shell.pid}.json"
        entry.write_bytes(
            json.dumps({"pid": shell.pid, "root": "/x"}).encode("utf-16"),
        )
        prune_registry(loops, own_pid=4242)
        assert not entry.exists()
    finally:
        os.killpg(shell.pid, signal.SIGKILL)
        shell.wait()


def test_pid_tagged_matches_a_tag_ending_a_non_final_ps_line_not_a_longer_pid(
    monkeypatch,
):
    # `$` without re.MULTILINE matches only end-of-string, so when the
    # tagged pid's ps row isn't the LAST line, the current pattern misses
    # it - a false "untagged" that lets prune sweep a live loop.
    monkeypatch.setattr(loop_mod, "_child_pids", lambda pid: [])
    monkeypatch.setattr(
        loop_mod.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="bash -c something\n_AUTOPILOT_LOOP=4321\npython3 worker.py\n",
        ),
    )
    assert loop_mod._pid_tagged(999, 4321) is True

    # A longer pid whose digits merely start with the tag pid's digits must
    # still not match: looking for 432 must not match _AUTOPILOT_LOOP=4321.
    monkeypatch.setattr(
        loop_mod.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="_AUTOPILOT_LOOP=4321\n",
        ),
    )
    assert loop_mod._pid_tagged(999, 432) is False


def test_interrupt_tears_down_and_returns_130(tmp_path):
    # Ctrl-C reaches the loop as KeyboardInterrupt (the group signal):
    # teardown must remove the registry entry, terminate a mid-flight
    # child, and return the bash-parity code.
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])

    def interrupting_spawn(
        model,
        effort,
        *,
        cap_secs,
        autopilot_dir,
        env,
        runner_bin,
        proc_slot=None,
        **kwargs,
    ):
        if proc_slot is not None:
            proc_slot[0] = child
        raise KeyboardInterrupt

    lp = make_loop(tmp_path, [], spawn_fn=interrupting_spawn)
    try:
        assert lp.run() == 130
        assert list((tmp_path / "loops").glob("*.json")) == []
        child.wait(timeout=10)
        assert child.returncode != 0  # terminated, not exited
    finally:
        child.kill()
        child.wait()


def test_sigterm_translates_to_143(tmp_path):
    def terminating_spawn(
        model,
        effort,
        *,
        cap_secs,
        autopilot_dir,
        env,
        runner_bin,
        proc_slot=None,
        **kwargs,
    ):
        raise loop_mod._Terminated(143)

    lp = make_loop(tmp_path, [], spawn_fn=terminating_spawn)
    assert lp.run() == 143
    assert list((tmp_path / "loops").glob("*.json")) == []


def test_loop_verb_is_registered_in_the_cli():
    import importlib.util

    main_path = Path(__file__).resolve().parent / "__main__.py"
    spec = importlib.util.spec_from_file_location(
        "autopilot_main_under_test",
        main_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "loop" in module._SUBCOMMANDS
    args = module._build_parser().parse_args(["loop"])
    assert args.command == "loop"


# ── drained-path helpers ─────────────────────────────────────────────────────


def test_run_agoge_skips_a_zero_drain(tmp_path):
    out = io.StringIO()
    run_agoge(tmp_path, "b-1", 0, {}, out)
    assert "skipped — the batch drained no PRDs" in out.getvalue()


def _fake_claude(tmp_path: Path, exit_code: int = 0) -> str:
    path = tmp_path / "fake-claude"
    argv_file = tmp_path / "agoge-argv"
    path.write_text(
        f"#!{sys.executable}\nimport sys\n"
        f"open({str(argv_file)!r}, 'w').write(repr(sys.argv[1:]))\n"
        f"print('qa output')\nsys.exit({exit_code})\n",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def test_run_agoge_launches_authorized_and_logs(tmp_path):
    (tmp_path / "reports").mkdir()
    out = io.StringIO()
    run_agoge(
        tmp_path,
        "b-1",
        2,
        {"PATH": os.environ["PATH"]},
        out,
        claude_bin=_fake_claude(tmp_path),
    )
    argv = (tmp_path / "agoge-argv").read_text()
    assert "'-p', '--permission-mode', 'auto'" in argv
    assert "--authorized autoclaude-drain" in argv
    assert "walkthrough pending" in out.getvalue()
    assert "qa output" in (tmp_path / "reports" / "b-1-agoge.log").read_text()


def test_run_agoge_brake_removes_only_the_flag(tmp_path):
    (tmp_path / "reports").mkdir()
    out = io.StringIO()
    run_agoge(
        tmp_path,
        "b-1",
        2,
        {"PATH": os.environ["PATH"], "_AUTOPILOT_AGOGE_AUTHORIZED": "0"},
        out,
        claude_bin=_fake_claude(tmp_path),
    )
    argv = (tmp_path / "agoge-argv").read_text()
    assert "/run-agoge" in argv
    assert "--authorized" not in argv


def test_run_agoge_failure_is_swallowed_and_reported(tmp_path, capsys):
    (tmp_path / "reports").mkdir()
    out = io.StringIO()
    run_agoge(
        tmp_path,
        "b-1",
        2,
        {"PATH": os.environ["PATH"]},
        out,
        claude_bin=_fake_claude(tmp_path, exit_code=3),
    )
    err = capsys.readouterr().err
    assert "run failed (rc 3)" in err
    assert "The drain is unaffected" in err


def test_drained_branch_runs_purge_and_agoge_with_the_count(tmp_path, monkeypatch):
    purges, agoges = [], []
    monkeypatch.setattr(loop_mod, "run_purge", lambda repo: purges.append(repo))
    monkeypatch.setattr(
        loop_mod,
        "run_agoge",
        lambda ap_dir, batch, drained, env, out, claude_bin="claude": agoges.append(
            (batch, drained),
        ),
    )
    lp = make_loop(
        tmp_path,
        [terminal_step(batch="b-9", completed_prds=["00001-a.md", "00002-b.md"])],
    )
    write_state(lp._test["ap_dir"], prd="p.md", next_phase="build", batch={"id": "b-9"})
    assert lp.run() == 0
    assert purges == [lp.cwd]
    assert agoges == [("b-9", 2)]
    assert "2 PRDs completed." in lp._test["out"].getvalue()
