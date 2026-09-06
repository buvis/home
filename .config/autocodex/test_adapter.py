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
    instance, ap, _ = harness
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
        ROOT, instance.cwd, None, True, pressure_fn=lambda: 0, notify_fn=lambda *args: None
    )
    assert one.run() == 0
    assert len(launches) == 1
    assert "gpt-5.6-sol" in launches[0]
    assert store.load(ap / "state.json")[0]["next_phase"] == "review"


def test_no_progress_retry_is_bounded(harness: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    instance, ap, _ = harness
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


def test_pause_marker_stops_without_launch(harness: tuple) -> None:
    instance, ap, _ = harness
    (ap / "pause-requested").write_text('{"reason":"operator"}')
    assert instance.run() == 0
    assert instance._launched == 0


def test_existing_paused_batch_is_untouched(harness: tuple) -> None:
    instance, ap, _ = harness
    store.init(ap / "state.json", {"phase": "paused", "next_phase": "paused"})
    before = (ap / "state.json").read_bytes()
    assert instance.run() == 1
    assert instance._launched == 0
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
