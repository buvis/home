from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from test_adapter import ROOT, successful  # isort: skip
from test_adapter import harness as harness  # isort: skip

from cli import records
from cli import state as store

import adapter
import driver


@pytest.fixture
def cap_stall(harness: tuple) -> tuple:
    instance, ap, _ = harness
    initial = {
        "prd": "00001-demo.md",
        "phase": "review",
        "next_phase": "review",
        "cycle": 2,
        "rework_cap": 2,
        "work_start_sha": "base",
        "batch": {"id": "batch-1", "parks_consecutive": 3},
        "tasks": [
            {
                "id": "1",
                "status": "completed",
                "attempts": [
                    {
                        "attempt": 1,
                        "actual_model": "gpt-6.1-sol",
                        "outcome": "completed",
                    }
                ],
            }
        ],
    }
    store.init(ap / "state.json", initial)
    instance._before = (ap / "state.json").read_bytes()
    instance._before_state = store.load(ap / "state.json")[0]
    reports = ap / "reports"
    reports.mkdir()
    evidence = ap / "implementation.jsonl"
    evidence.write_text('{"model":"gpt-6.1-sol"}\n')
    audit = {
        "snapshot": driver.implementation_snapshot(initial),
        "fingerprint": driver.implementation_fingerprint(initial),
        "evidence": [
            {
                "task": "1",
                "role": "implementation",
                "model": "gpt-6.1-sol",
                "path": str(evidence.relative_to(instance.cwd)),
                "line": 1,
                "sha256": hashlib.sha256(evidence.read_bytes().rstrip(b"\n")).hexdigest(),
            }
        ],
    }
    (reports / "00001-demo-implementation-models.json").write_text(json.dumps(audit))
    parts = ["provider_review_guard: satisfied", "Verdict: 1 findings", "Tests: 1 passed"]
    for lens in ("alice", "blake", "bob"):
        output, raw, receipt = (
            ap / f"{lens}{suffix}" for suffix in (".md", ".jsonl", ".receipt.json")
        )
        output.write_text("\n".join(f"{rule}: pass" for rule in driver.review_rules(lens)))
        raw.write_text(
            json.dumps({"type": "result", "is_error": False, "result": output.read_text()})
        )
        receipt.write_text(
            json.dumps(
                {
                    "provider": "claude",
                    "model": "opus",
                    "lens": lens,
                    "cycle": 2,
                    "prd": initial["prd"],
                    "root": str(instance.cwd),
                    "implementation_fingerprint": audit["fingerprint"],
                    "output": str(output),
                    "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                    "raw": str(raw),
                    "raw_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
                }
            )
        )
        parts += [f"autocodex_{lens}_anthropic_receipt: {receipt}"]
    for lens in ("alice", "blake", "bob"):
        parts += [f"## {lens.title()}", (ap / f"{lens}.md").read_text()]
    review = ap / "review.md"
    review.write_text("\n".join(parts))
    store.transaction(
        ap / "state.json",
        lambda state: {
            **state,
            "review_cycles": [{"cycle": 2, "review_file": str(review)}],
            "doubts_rubric_verdicts": [
                {"rule_id": f"D{n}", "verdict": "pass"} for n in range(1, 6)
            ],
            "deferred_decisions": [
                {
                    "type": "cap-overflow",
                    "issue": "regression",
                    "severity": "high",
                    "reason": "rework cap reached with this finding unresolved",
                }
            ],
        },
    )
    prds = instance.cwd / "docs/dev/project-management/prds"
    (prds / "wip").mkdir(parents=True)
    (prds / "wip" / initial["prd"]).write_text("# Demo\n")
    instance._result = successful(ap / "session.jsonl")
    return instance, ap, prds


def stall_review(cap_stall: tuple) -> Path:
    instance, ap, prds = cap_stall
    snapshot = adapter.capture_stall_review(ROOT, instance.cwd)
    assert (
        records.do_stall(
            ap / "state.json",
            prd="00001-demo.md",
            site="cap_regression",
            detail="R5 abcdef",
            prds_dir=prds,
            autopilot_dir=ap,
        )
        == 0
    )
    return snapshot


def test_real_cap_stall_accepts_review_created_after_launch(cap_stall: tuple) -> None:
    instance, ap, _ = cap_stall
    assert "review_cycles" not in instance._before_state
    stall_review(cap_stall)
    assert instance._decide(ap, 0)["signal"] == "continue"


@pytest.mark.parametrize(
    "change",
    [
        "missing-snapshot",
        "changed-review",
        "changed-raw",
        "changed-audit",
        "wrong-prd",
        "wrong-cycle",
        "wrong-provenance",
        "wrong-batch",
        "missing-hold",
        "wip-remains",
        "missing-deferred",
        "wrong-site",
        "missing-migration",
        "old-stall",
        "partial-reset",
        "changed-cap",
    ],
)
def test_cap_stall_rejects_incomplete_or_wrong_evidence(cap_stall: tuple, change: str) -> None:
    instance, ap, prds = cap_stall
    snapshot = stall_review(cap_stall)
    if change == "missing-snapshot":
        snapshot.unlink()
    elif change in ("changed-review", "changed-raw", "changed-audit"):
        target = {
            "changed-review": ap / "review.md",
            "changed-raw": ap / "alice.jsonl",
            "changed-audit": ap / "reports/00001-demo-implementation-models.json",
        }[change]
        target.write_text("tampered")
    elif change in ("wrong-prd", "wrong-cycle", "wrong-provenance"):
        if change == "wrong-prd":
            instance._before_state["prd"] = "other.md"
        elif change == "wrong-cycle":
            instance._before_state["cycle"] = 3
        else:
            instance._before_state["tasks"][0]["attempts"][0]["actual_model"] = "claude-opus-5"
    elif change == "wrong-batch":
        store.transaction(ap / "state.json", lambda state: {**state, "batch": {"id": "other"}})
    elif change == "missing-hold":
        (prds / "hold/00001-demo.md").unlink()
    elif change == "wip-remains":
        (prds / "wip/00001-demo.md").write_text("# duplicate\n")
    elif change == "changed-cap":
        instance._before_state["rework_cap"] = 1
    elif change == "partial-reset":
        store.transaction(ap / "state.json", lambda state: {**state, "work_start_sha": "base"})
    else:
        path = ap / "deferred/batch-1-deferred.json"
        ledger = json.loads(path.read_text())
        if change == "missing-deferred":
            path.unlink()
        elif change == "wrong-site":
            ledger["items"][0]["site"] = "arbitrary"
            path.write_text(json.dumps(ledger))
        elif change == "missing-migration":
            ledger["items"].pop()
            path.write_text(json.dumps(ledger))
        elif change == "old-stall":
            data = json.loads(snapshot.read_text())
            data["deferred_before"] = ledger
            snapshot.write_text(json.dumps(data))
    assert instance._decide(ap, 0)["signal"] == "paused"


def test_cap_snapshot_is_idempotent_and_refuses_replacement(cap_stall: tuple) -> None:
    instance, ap, _ = cap_stall
    path = adapter.capture_stall_review(ROOT, instance.cwd)
    before = path.read_bytes()
    assert adapter.capture_stall_review(ROOT, instance.cwd) == path
    store.transaction(ap / "state.json", lambda state: {**state, "notes": "different"})
    with pytest.raises(ValueError, match="already exists"):
        adapter.capture_stall_review(ROOT, instance.cwd)
    assert path.read_bytes() == before


def test_canonical_mint_stubs_and_contract_card_are_allowed(cap_stall: tuple) -> None:
    from cli import triage

    instance, ap, prds = cap_stall
    stall_review(cap_stall)
    result = triage.mint_stubs(ap, prds, "batch-1")
    store.transaction(
        ap / "state.json",
        lambda state: {
            **state,
            "batch": {**state["batch"], "minted_stubs": result["minted"]},
            "contract_card": "step: cap_regression stalled; next: fresh build session",
        },
    )
    assert len(result["minted"]) == 2
    assert instance._decide(ap, 0)["signal"] == "continue"
    (prds / "hold" / result["minted"][0]).write_text("forged stub")
    assert instance._decide(ap, 0)["signal"] == "paused"


def test_cap_snapshot_refuses_missing_review_receipt(cap_stall: tuple) -> None:
    instance, ap, _ = cap_stall
    (ap / "alice.receipt.json").unlink()
    with pytest.raises(ValueError, match="review stall snapshot refused"):
        adapter.capture_stall_review(ROOT, instance.cwd)


def test_cap_snapshot_refuses_stale_implementation_audit(cap_stall: tuple) -> None:
    instance, ap, _ = cap_stall
    store.transaction(
        ap / "state.json",
        lambda state: {
            **state,
            "tasks": [{"id": "2", "attempts": [{"actual_model": "gpt-6.1-sol"}]}],
        },
    )
    with pytest.raises(ValueError, match="stale implementation"):
        adapter.capture_stall_review(ROOT, instance.cwd)


def test_cap_stall_cli_prepares_then_validates_canonical_reset(cap_stall: tuple) -> None:
    import subprocess
    import sys

    instance, ap, prds = cap_stall
    captured = subprocess.run(
        [
            sys.executable,
            str(driver.HERE / "driver.py"),
            "--cd",
            str(instance.cwd),
            "review-stall-snapshot",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert Path(captured.stdout.strip()).is_file()
    cli = ROOT / "cli/__main__.py"
    subprocess.run(
        [
            sys.executable,
            str(cli),
            "stall",
            "--state",
            str(ap / "state.json"),
            "--prd",
            "00001-demo.md",
            "--site",
            "cap_regression",
            "--detail",
            "R5 abcdef",
            "--prds",
            str(prds),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(cli),
            "mint-stubs",
            "--state",
            str(ap / "state.json"),
            "--batch",
            "batch-1",
            "--prds",
            str(prds),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert instance._decide(ap, 0)["signal"] == "continue"


def test_snapshot_cli_reports_bad_state_without_traceback(tmp_path: Path) -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            str(driver.HERE / "driver.py"),
            "--cd",
            str(tmp_path),
            "review-stall-snapshot",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "review stall snapshot refused" in result.stderr
    assert "Traceback" not in result.stderr
