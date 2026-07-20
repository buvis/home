"""Tests for hooks/reinject_contract_card.py — compaction re-anchor (PRD 00087 R1)."""

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "reinject_contract_card.py"


def _run(payload: dict, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(cwd),
    )


def _write_card(root: Path, *, scratch: str | None = None, state_card: str | None = None) -> None:
    base = root / "dev" / "local" / "autopilot"
    base.mkdir(parents=True, exist_ok=True)
    if scratch is not None:
        (base / "contract-card.md").write_text(scratch, encoding="utf-8")
    if state_card is not None:
        (base / "state.json").write_text(
            json.dumps({"contract_card": state_card}), encoding="utf-8"
        )


def test_emits_scratch_card_on_compact(tmp_path: Path) -> None:
    _write_card(tmp_path, scratch="STEP 3 | invariant X | next gate review")
    proc = _run({"source": "compact", "cwd": str(tmp_path)}, tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "STEP 3 | invariant X | next gate review" in out["hookSpecificOutput"]["additionalContext"]


def test_state_card_preferred_over_scratch(tmp_path: Path) -> None:
    _write_card(tmp_path, scratch="SCRATCH", state_card="FROM STATE")
    proc = _run({"source": "compact", "cwd": str(tmp_path)}, tmp_path)
    ctx = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "FROM STATE" in ctx
    assert "SCRATCH" not in ctx


def test_silent_on_startup(tmp_path: Path) -> None:
    _write_card(tmp_path, scratch="CARD")
    proc = _run({"source": "startup", "cwd": str(tmp_path)}, tmp_path)
    assert proc.returncode == 0
    assert proc.stdout.strip() == "", "must stay silent on startup (no standing token cost)"


def test_silent_on_resume(tmp_path: Path) -> None:
    _write_card(tmp_path, scratch="CARD")
    proc = _run({"source": "resume", "cwd": str(tmp_path)}, tmp_path)
    assert proc.stdout.strip() == ""


def test_silent_when_no_card(tmp_path: Path) -> None:
    proc = _run({"source": "compact", "cwd": str(tmp_path)}, tmp_path)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""
