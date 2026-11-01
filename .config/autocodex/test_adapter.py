from __future__ import annotations

import copy
import hashlib
import io
import json
import sys
from pathlib import Path

import pytest

import driver

ROOT = driver.skill_root()
sys.path.insert(0, str(ROOT))
from cli import loop as legacy_loop
from cli import state as store
from cli import transitions

import adapter


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple:
    repo = tmp_path / "repo"
    ap = repo / "docs/dev/project-management/autopilot"
    ap.mkdir(parents=True)
    monkeypatch.setenv("_AUTOPILOT_LOOPS_DIR", str(tmp_path / "registry"))
    monkeypatch.setenv("AUTOCODEX_RETRY_DELAY", "0")
    monkeypatch.setattr(legacy_loop.Loop, "_cleanup_orphans", lambda self: None)
    out = io.StringIO()
    instance = adapter.CodexLoop(
        ROOT,
        repo,
        None,
        False,
        pressure_fn=lambda: 0,
        notify_fn=lambda *args: None,
        out=out,
        err=out,
    )
    return instance, ap, out


def successful(log: Path) -> driver.Result:
    log.write_text('{"type":"turn.completed"}\n')
    events = driver.Events("codex", success=True)
    return driver.Result(0, log, events, False)


def test_unchanged_terminal_state_is_not_completion(harness: tuple) -> None:
    instance, ap, _ = harness
    store.init(ap / "state.json", {"phase": "done", "next_phase": ""})
    instance._before = (ap / "state.json").read_bytes()
    instance._result = successful(ap / "raw.jsonl")
    decision = instance._decide(ap, 0)
    assert decision["signal"] != "done"


def test_false_completion_persists_pause(harness: tuple) -> None:
    instance, ap, _ = harness
    store.init(ap / "state.json", {"phase": "build", "next_phase": "build"})
    instance._before = (ap / "state.json").read_bytes()
    store.transaction(ap / "state.json", lambda state: transitions.apply(state, "tasks_done"))
    instance._result = driver.Result(0, ap / "raw.jsonl", driver.Events("codex"), False)
    decision = instance._decide(ap, 0)
    assert decision["signal"] == "paused"
    instance._act_paused(decision, ap / "state.json")
    assert instance._schema_gate(ap) == 1
    assert store.load(ap / "state.json")[0]["phase"] == "paused"


def test_missing_review_evidence_blocks_finalize(harness: tuple) -> None:
    instance, ap, _ = harness
    store.init(ap / "state.json", {"phase": "review", "next_phase": "review"})
    instance._before = (ap / "state.json").read_bytes()
    instance._before_state = store.load(ap / "state.json")[0]
    store.transaction(ap / "state.json", lambda state: transitions.apply(state, "converged"))
    instance._result = successful(ap / "raw.jsonl")
    decision = instance._decide(ap, 0)
    assert decision["signal"] == "paused"
    assert "review" in decision["detail"]


def test_duplicate_loop_lock_refuses(harness: tuple) -> None:
    instance, ap, _ = harness
    second = adapter.CodexLoop(
        ROOT, instance.cwd, None, False, pressure_fn=lambda: 0, notify_fn=lambda *args: None
    )
    try:
        assert instance._register(ap) is None
        assert second._register(ap) == 1
    finally:
        second._teardown()
        instance._teardown()


def test_once_really_runs_only_one_phase(harness: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    instance, ap, out = harness
    store.init(ap / "state.json", {"phase": "build", "next_phase": "build"})
    launches = []

    def fake(
        argv: list, prompt: str, cwd: Path, env: dict, stem: Path, cap: int, **kwargs: object
    ) -> driver.Result:
        launches.append(argv)
        store.transaction(ap / "state.json", lambda state: transitions.apply(state, "tasks_done"))
        return successful(stem.with_suffix(".jsonl"))

    monkeypatch.setattr(driver, "run_process", fake)
    one = adapter.CodexLoop(
        ROOT,
        instance.cwd,
        None,
        True,
        pressure_fn=lambda: 0,
        notify_fn=lambda *args: None,
        out=out,
        err=out,
    )
    assert one.run() == 0
    assert len(launches) == 1
    assert "gpt-6.1-sol" in launches[0]
    assert "gpt-6.1-sol/low" in out.getvalue()
    assert "claude-sonnet" not in out.getvalue()
    assert out.getvalue().splitlines()[-1] == (
        "autocodex: stopping because --once is active; workflow state advanced, "
        "but no new session will start. Next phase queued: review. "
        "Run plain 'autocodex' to continue."
    )
    assert store.load(ap / "state.json")[0]["next_phase"] == "review"


def test_inherited_routes_are_translated_before_display(tmp_path: Path) -> None:
    ap = tmp_path / "docs/dev/project-management/autopilot"
    ap.mkdir(parents=True)
    env = {"_AUTOPILOT_MODEL_BUILD": "claude-opus-5[1m]"}

    route = adapter.codex_route("build", ap, env)

    assert route.model == "gpt-6.1-sol"
    assert route.effort == "low"


def test_no_progress_retry_is_bounded(harness: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    instance, ap, out = harness
    store.init(ap / "state.json", {"phase": "build", "next_phase": "build"})
    launches = []

    def fake(
        argv: list, prompt: str, cwd: Path, env: dict, stem: Path, cap: int, **kwargs: object
    ) -> driver.Result:
        launches.append(argv)
        return successful(stem.with_suffix(".jsonl"))

    monkeypatch.setattr(driver, "run_process", fake)
    assert instance.run() == 1
    assert len(launches) == 2
    assert "autocodex: session died" in out.getvalue()
    assert "autoclaude:" not in out.getvalue()


@pytest.mark.parametrize(
    "launch_args, expected_prd",
    [
        (("00001-launched.md",), "00001-launched.md"),
        (("",), "00002-current.md"),
        ((), "00002-current.md"),
    ],
    ids=["state-advanced", "bootstrap", "legacy-caller"],
)
def test_metrics_attribute_session_to_launched_prd(
    harness: tuple, launch_args: tuple[str, ...], expected_prd: str
) -> None:
    instance, ap, _ = harness
    decision = {
        "phase_end": "build",
        "signal": "continue",
        "prd": "00002-current.md",
        "batch": "test-batch",
    }

    instance._append_metrics(ap, 10, 20, decision, "done", "gpt-6.1-sol", "low", *launch_args)

    metrics = json.loads((ap / "autocodex-metrics.jsonl").read_text())
    assert metrics["prd"] == expected_prd
    assert metrics["prd_end"] == "00002-current.md"


@pytest.mark.parametrize("entrypoint, exit_code", [("run", 1), ("run_once", 0)])
@pytest.mark.parametrize("effort", ["xhigh", "medium"])
def test_review_pause_records_metrics_before_exit(
    harness: tuple,
    monkeypatch: pytest.MonkeyPatch,
    entrypoint: str,
    exit_code: int,
    effort: str,
) -> None:
    instance, ap, _ = harness
    instance.env["AUTOCODEX_COORDINATOR_EFFORT"] = effort
    store.init(ap / "state.json", {"phase": "review", "next_phase": "review"})

    def fake(
        argv: list, prompt: str, cwd: Path, env: dict, stem: Path, cap: int, **kwargs: object
    ) -> driver.Result:
        store.transaction(
            ap / "state.json",
            lambda state: {
                **state,
                "phase": "paused",
                "next_phase": "paused",
                "pause_reason": {"site": "data_loss_risk", "detail": "durability gap"},
            },
        )
        return successful(stem.with_suffix(".jsonl"))

    monkeypatch.setattr(driver, "run_process", fake)

    assert getattr(instance, entrypoint)() == exit_code

    [metrics] = [
        json.loads(line) for line in (ap / "autocodex-metrics.jsonl").read_text().splitlines()
    ]
    assert metrics["effort"] == effort
    assert metrics["model"] == "gpt-6.1-sol"
    assert metrics["phase_launched"] == "review"
    assert metrics["phase_end"] == "paused"
    assert metrics["signal"] == "paused"
    assert Path(metrics["raw"]).read_text() == '{"type":"turn.completed"}\n'
    assert instance._launched == 1
    paused = (ap / "state.json").read_bytes()
    assert instance._schema_gate(ap) == 1
    assert (ap / "state.json").read_bytes() == paused
    assert store.load(ap / "state.json")[0]["pause_reason"]["site"] == "data_loss_risk"


def test_pause_marker_stops_without_launch(harness: tuple) -> None:
    instance, ap, out = harness
    (ap / "pause-requested").write_text('{"reason":"operator"}')
    assert instance.run() == 0
    assert instance._launched == 0
    assert "Resume unattended: autocodex" in out.getvalue()
    assert "To take over first: codex" in out.getvalue()
    assert "~/.config/autocodex/host.md" in out.getvalue()
    assert "claude" not in out.getvalue()
    assert "/autopilot:run-autopilot" not in out.getvalue()


def test_existing_paused_batch_is_untouched(harness: tuple) -> None:
    instance, ap, out = harness
    store.init(ap / "state.json", {"phase": "paused", "next_phase": "paused"})
    before = (ap / "state.json").read_bytes()
    assert instance.run() == 1
    assert instance._launched == 0
    assert (ap / "state.json").read_bytes() == before
    assert "autocodex status" in out.getvalue()
    assert "  codex\n" in out.getvalue()
    assert "~/.config/autocodex/host.md" in out.getvalue()
    assert "interactive recovery" in out.getvalue()
    assert "claude" not in out.getvalue()
    assert "/autopilot:run-autopilot" not in out.getvalue()


def test_current_cap_pause_prints_findings_and_resume_runbook(harness: tuple) -> None:
    instance, ap, out = harness
    prd = "00004-current.md"
    wip = instance.cwd / "docs/dev/project-management/prds/wip"
    wip.mkdir(parents=True)
    (wip / prd).write_text("# Current\n")
    store.init(
        ap / "state.json",
        {
            "prd": prd,
            "phase": "paused",
            "next_phase": "paused",
            "cycle": 2,
            "rework_cap": 2,
            "cap_pause_reason": {
                "cycle": 2,
                "cap": 2,
                "unresolved_findings": [
                    {"severity": "high", "consensus": "3/3", "issue": "lost update"}
                ],
            },
        },
    )
    before = (ap / "state.json").read_bytes()

    assert instance.run() == 1

    rendered = out.getvalue()
    assert "[high; 3/3] lost update" in rendered
    assert "Choose Resume" in rendered
    assert "1. codex" in rendered
    assert "~/.config/autocodex/host.md" in rendered
    assert "interactive recovery" in rendered
    assert "Exit Codex" in rendered
    assert "claude" not in rendered.lower()
    assert "/autopilot:run-autopilot" not in rendered
    assert "autocodex again" in rendered
    assert instance._launched == 0
    assert (ap / "state.json").read_bytes() == before


def test_completed_prd_pause_prints_detach_runbook(harness: tuple) -> None:
    instance, ap, out = harness
    prd = "00003-complete.md"
    done = instance.cwd / "docs/dev/project-management/prds/done"
    done.mkdir(parents=True)
    (done / prd).write_text("# Complete\n")
    store.init(
        ap / "state.json",
        {
            "prd": prd,
            "phase": "paused",
            "next_phase": "paused",
            "cycle": 2,
            "rework_cap": 2,
            "cap_pause_reason": {
                "cycle": 2,
                "cap": 2,
                "unresolved_findings": [{"severity": "high", "issue": "historical"}],
            },
        },
    )
    before = (ap / "state.json").read_bytes()

    assert instance.run() == 1

    rendered = out.getvalue()
    assert "belongs to completed PRD 00003-complete.md" in rendered
    assert "do not resume" in rendered
    assert (
        "mv docs/dev/project-management/autopilot docs/dev/project-management/autopilot-00003-complete-paused-preserved"
        in rendered
    )
    assert "autocodex --once --scope <handoff.md>" in rendered
    assert (ap / "state.json").read_bytes() == before


def test_build_cannot_skip_fresh_review(harness: tuple) -> None:
    instance, ap, _ = harness
    store.init(ap / "state.json", {"prd": "00001-demo.md", "phase": "build", "next_phase": "build"})
    instance._before = (ap / "state.json").read_bytes()
    instance._before_state = store.load(ap / "state.json")[0]
    store.transaction(ap / "state.json", lambda state: {**state, "phase": "done", "next_phase": ""})
    instance._result = successful(ap / "raw.jsonl")
    assert instance._decide(ap, 0)["signal"] == "paused"


def test_build_drains_after_parking_its_prd(harness: tuple) -> None:
    """oversized_task parked the PRD in hold/ and selection found nothing else:
    the build session's ("build", "drained") transition is a batch end, not a
    skipped review (AP 00012, 2026-10-26)."""
    instance, ap, _ = harness
    hold = instance.cwd / "docs/dev/project-management/prds/hold"
    hold.mkdir(parents=True)
    (hold / "00001-demo.md").write_text("# parked\n")
    store.init(ap / "state.json", {"prd": "00001-demo.md", "phase": "build", "next_phase": "build"})
    instance._before = (ap / "state.json").read_bytes()
    instance._before_state = store.load(ap / "state.json")[0]
    store.transaction(ap / "state.json", lambda state: {**state, "phase": "done", "next_phase": ""})
    instance._result = successful(ap / "raw.jsonl")
    assert instance._decide(ap, 0)["signal"] == "done"


def test_failed_session_can_resume_partial_work(harness: tuple) -> None:
    instance, ap, _ = harness
    store.init(ap / "state.json", {"phase": "build", "next_phase": "build"})
    instance._before = (ap / "state.json").read_bytes()
    instance._before_state = store.load(ap / "state.json")[0]
    store.transaction(ap / "state.json", lambda state: {**state, "notes": "partial work survives"})
    instance._result = driver.Result(1, ap / "raw.jsonl", driver.Events("codex"), False)
    assert instance._decide(ap, 0)["signal"] == "continue"


def test_malformed_state_after_session_fails_closed(harness: tuple) -> None:
    instance, ap, _ = harness
    (ap / "state.json").write_text('["bad-root"]')
    instance._result = successful(ap / "raw.jsonl")
    assert instance._decide(ap, 0)["signal"] == "state_write_failed"


def test_quota_waits_without_burning_crash_budget(harness: tuple) -> None:
    instance, ap, _ = harness
    events = driver.Events("codex", error="usage limit reached")
    instance._result = driver.Result(1, ap / "raw.jsonl", events, False)
    decision = instance._decide(ap, 0)
    assert decision["signal"] == "continue"
    assert decision["limit_wait"] == 300
    assert instance._died_retries == 0


def test_quota_wait_is_bounded(harness: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    instance, ap, _ = harness
    instance._limit_started = 1
    instance._died_retries = 1
    monkeypatch.setattr(adapter.time, "monotonic", lambda: 30000)
    instance._result = driver.Result(
        1, ap / "raw.jsonl", driver.Events("codex", error="quota"), False
    )
    assert instance._decide(ap, 0)["signal"] == "died"


@pytest.fixture
def bob_receipt(tmp_path: Path) -> tuple[Path, str]:
    output = tmp_path / "bob.md"
    output.write_text("\n".join(f"D{n}: pass" for n in range(1, 6)))
    raw = tmp_path / "raw.jsonl"
    raw.write_text(json.dumps({"type": "result", "is_error": False, "result": output.read_text()}))
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "provider": "claude",
                "cycle": 2,
                "prd": "00001-demo.md",
                "root": str(tmp_path),
                "started": 1,
                "output": str(output),
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "raw": str(raw),
                "raw_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
            }
        )
    )
    return tmp_path, f"autocodex_bob_receipt: {receipt}\n"


def test_same_cycle_receipt_survives_session_restart(bob_receipt: tuple) -> None:
    cwd, text = bob_receipt
    assert adapter.bob_gap(text, cwd, 2, "00001-demo.md") is None


def test_previous_cycle_receipt_is_refused(bob_receipt: tuple) -> None:
    cwd, text = bob_receipt
    assert adapter.bob_gap(text, cwd, 3, "00001-demo.md") is not None


def test_tampered_raw_review_is_refused(bob_receipt: tuple) -> None:
    cwd, text = bob_receipt
    (cwd / "raw.jsonl").write_text("replaced")
    assert "raw evidence changed" in adapter.bob_gap(text, cwd, 2, "00001-demo.md")


def test_same_provider_receipt_cannot_satisfy_opposite_roster(bob_receipt: tuple) -> None:
    cwd, _ = bob_receipt
    path = cwd / "receipt.json"
    receipt = json.loads(path.read_text())
    receipt.update(lens="bob", model="opus")
    path.write_text(json.dumps(receipt))
    text = f"autocodex_bob_openai_receipt: {path}\n"
    assert adapter.bob_gap(text, cwd, 2, "00001-demo.md", "bob", "openai") is not None


def test_changed_implementation_invalidates_receipt(bob_receipt: tuple) -> None:
    cwd, text = bob_receipt
    assert "implementation snapshot" in adapter.bob_gap(
        text, cwd, 2, "00001-demo.md", fingerprint="new"
    )


@pytest.fixture
def tail_sweep(tmp_path: Path) -> tuple:
    attempt = {
        "attempt": 1,
        "actual_model": "gpt-6.1-sol",
        "actual_provider": "openai",
        "implementor": "codex",
        "outcome": "completed",
        "review_cycle": 2,
    }
    state = {
        "prd": "00001-demo.md",
        "cycle": 2,
        "work_start_sha": "base",
        "phase": "done",
        "tasks": [
            {"id": "1", "status": "completed", "attempts": [copy.deepcopy(attempt)]}
        ],
    }
    snapshot = driver.implementation_snapshot(state)
    review = tmp_path / "review.md"
    state["applied_review_batches"] = [
        f"{review}::decision-gate",
        f"{review}::tail-sweep",
    ]
    state["tasks"].append(
        {
            "id": "2",
            "name": "[D2] Tail sweep: fixture readability",
            "status": "completed",
            "attempts": [copy.deepcopy(attempt)],
        }
    )
    reports = tmp_path / "docs/dev/project-management/autopilot/reports"
    reports.mkdir(parents=True)
    evidence = tmp_path / "model.jsonl"
    evidence.write_text('{"model":"gpt-6.1-sol"}\n')
    audit = reports / "00001-demo-tail-sweep-models.json"
    audit.write_text(
        json.dumps(
            {
                "snapshot": driver.implementation_snapshot(state),
                "fingerprint": driver.implementation_fingerprint(state),
                "evidence": [
                    {
                        "task": task_id,
                        "role": "implementation",
                        "model": "gpt-6.1-sol",
                        "path": "model.jsonl",
                        "line": 1,
                        "sha256": hashlib.sha256(
                            evidence.read_bytes().rstrip(b"\n")
                        ).hexdigest(),
                    }
                    for task_id in ("1", "2")
                ],
            }
        )
    )
    return state, snapshot, tmp_path, review


def test_completed_tail_sweep_preserves_review_snapshot(tail_sweep: tuple) -> None:
    state, snapshot, cwd, review = tail_sweep
    before = copy.deepcopy(snapshot)
    assert adapter.convergence_gap(state, snapshot, cwd, review) is None
    assert snapshot == before


@pytest.mark.parametrize(
    "change",
    [
        "ordinary-task",
        "unfinished",
        "failed-attempt",
        "wrong-cycle",
        "missing-attempt",
        "changed-original",
        "removed-original",
        "duplicate-id",
        "missing-batch",
        "old-batch",
        "changed-cycle",
        "changed-prd",
        "changed-base",
        "missing-audit",
        "tampered-evidence",
        "unknown-model",
        "conflicting-provider",
    ],
)
def test_tail_sweep_does_not_waive_provenance(tail_sweep: tuple, change: str) -> None:
    state, snapshot, cwd, review = tail_sweep
    tail = state["tasks"][-1]
    if change == "ordinary-task":
        tail["name"] = "[D2] ordinary rework"
    elif change == "unfinished":
        tail["status"] = "in_progress"
    elif change == "failed-attempt":
        tail["attempts"][-1]["outcome"] = "failed"
    elif change == "wrong-cycle":
        tail["attempts"][-1]["review_cycle"] = 1
    elif change == "missing-attempt":
        tail["attempts"] = []
    elif change == "changed-original":
        state["tasks"][0]["attempts"].append(copy.deepcopy(tail["attempts"][0]))
    elif change == "removed-original":
        state["tasks"].pop(0)
    elif change == "duplicate-id":
        state["tasks"].append(copy.deepcopy(tail))
    elif change == "missing-batch":
        state["applied_review_batches"].pop()
    elif change == "old-batch":
        state["applied_review_batches"] = [f"{cwd}/old.md::tail-sweep"]
    elif change == "changed-cycle":
        state["cycle"] = 3
    elif change == "changed-prd":
        state["prd"] = "another.md"
    elif change == "changed-base":
        state["work_start_sha"] = "another"
    elif change == "missing-audit":
        (
            cwd
            / "docs/dev/project-management/autopilot/reports/00001-demo-tail-sweep-models.json"
        ).unlink()
    elif change == "tampered-evidence":
        (cwd / "model.jsonl").write_text("changed")
    elif change == "unknown-model":
        tail["attempts"][-1]["actual_model"] = "auto"
    elif change == "conflicting-provider":
        tail["attempts"][-1]["actual_provider"] = "anthropic"
    assert adapter.convergence_gap(state, snapshot, cwd, review) is not None


def test_unchanged_convergence_needs_no_tail_audit(tail_sweep: tuple) -> None:
    state, _, cwd, review = tail_sweep
    snapshot = driver.implementation_snapshot(state)
    assert adapter.convergence_gap(state, snapshot, cwd, review) is None
