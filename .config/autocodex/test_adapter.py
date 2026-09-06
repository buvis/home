from __future__ import annotations

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
    ap = repo / "dev/local/autopilot"
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
    assert "gpt-5.6-sol" in launches[0]
    assert "gpt-5.6-sol/high" in out.getvalue()
    assert "claude-sonnet" not in out.getvalue()
    assert store.load(ap / "state.json")[0]["next_phase"] == "review"


def test_inherited_routes_are_translated_before_display(tmp_path: Path) -> None:
    ap = tmp_path / "dev/local/autopilot"
    ap.mkdir(parents=True)
    env = {"_AUTOPILOT_MODEL_BUILD": "claude-opus-5[1m]"}

    route = adapter.codex_route("build", ap, env)

    assert route.model == "gpt-6-astra"
    assert route.effort == "xhigh"


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


def test_pause_marker_stops_without_launch(harness: tuple) -> None:
    instance, ap, _ = harness
    (ap / "pause-requested").write_text('{"reason":"operator"}')
    assert instance.run() == 0
    assert instance._launched == 0


def test_existing_paused_batch_is_untouched(harness: tuple) -> None:
    instance, ap, out = harness
    store.init(ap / "state.json", {"phase": "paused", "next_phase": "paused"})
    before = (ap / "state.json").read_bytes()
    assert instance.run() == 1
    assert instance._launched == 0
    assert (ap / "state.json").read_bytes() == before
    assert "autocodex status" in out.getvalue()
    assert "/autopilot:run-autopilot" in out.getvalue()


def test_current_cap_pause_prints_findings_and_resume_runbook(harness: tuple) -> None:
    instance, ap, out = harness
    prd = "00004-current.md"
    wip = instance.cwd / "dev/local/prds/wip"
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
    assert "claude" in rendered
    assert "autocodex again" in rendered
    assert (ap / "state.json").read_bytes() == before


def test_completed_prd_pause_prints_detach_runbook(harness: tuple) -> None:
    instance, ap, out = harness
    prd = "00003-complete.md"
    done = instance.cwd / "dev/local/prds/done"
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
    assert "mv dev/local/autopilot dev/local/autopilot-00003-complete-paused-preserved" in rendered
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
