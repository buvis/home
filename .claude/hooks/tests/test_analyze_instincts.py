"""Tests for analyze-instincts.py observation retention (prune_observations)."""

from __future__ import annotations

import importlib.util
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "analyze_instincts", HOOKS_DIR / "analyze-instincts.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def mod(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    m = _load_module()
    monkeypatch.setattr(m, "PROJECTS_DIR", tmp_path)
    monkeypatch.delenv("INSTINCTS_RETENTION_DAYS", raising=False)
    return m


def _ts(days_ago: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_obs(root: Path, rows: list[dict]) -> Path:
    proj = root / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    obs = proj / "observations.jsonl"
    obs.write_text(
        "\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n",
        encoding="utf-8",
    )
    return obs


def _rows(obs: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in obs.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_prunes_analyzed_rows_older_than_retention(mod, tmp_path: Path) -> None:
    obs = _write_obs(
        tmp_path, [{"ts": _ts(30), "tool": "old"}, {"ts": _ts(1), "tool": "fresh"}]
    )
    mod.prune_observations("proj", last_analysis=_ts(0))
    kept = _rows(obs)
    assert [r["tool"] for r in kept] == ["fresh"]


def test_never_prunes_rows_newer_than_last_analysis(mod, tmp_path: Path) -> None:
    # Row is 30 days old (outside retention) but was never analyzed:
    # last_analysis predates it, so it must survive.
    obs = _write_obs(tmp_path, [{"ts": _ts(30), "tool": "unanalyzed"}])
    mod.prune_observations("proj", last_analysis=_ts(60))
    assert [r["tool"] for r in _rows(obs)] == ["unanalyzed"]


def test_no_last_analysis_means_no_prune(mod, tmp_path: Path) -> None:
    obs = _write_obs(tmp_path, [{"ts": _ts(400), "tool": "keep"}])
    mod.prune_observations("proj", last_analysis=None)
    assert [r["tool"] for r in _rows(obs)] == ["keep"]


def test_retention_zero_disables_pruning(
    mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INSTINCTS_RETENTION_DAYS", "0")
    obs = _write_obs(tmp_path, [{"ts": _ts(400), "tool": "keep"}])
    mod.prune_observations("proj", last_analysis=_ts(0))
    assert [r["tool"] for r in _rows(obs)] == ["keep"]


def test_stale_rotated_archive_is_deleted_fresh_kept(mod, tmp_path: Path) -> None:
    _write_obs(tmp_path, [{"ts": _ts(1), "tool": "fresh"}])
    rotated = tmp_path / "proj" / "observations.jsonl.1"
    rotated.write_text("{}\n", encoding="utf-8")

    # Fresh archive survives.
    mod.prune_observations("proj", last_analysis=_ts(0))
    assert rotated.exists()

    # Backdated archive (30 days) is deleted.
    old = time.time() - 30 * 86400
    os.utime(rotated, (old, old))
    mod.prune_observations("proj", last_analysis=_ts(0))
    assert not rotated.exists()


# --- error-fix trigger classification (PRD 00085 R5) -------------------------


def test_classify_error_maps_markers_to_stable_classes(mod) -> None:
    assert mod._classify_error("bash: foo: command not found") == "command_not_found"
    assert mod._classify_error("open x: Permission denied") == "permission_denied"
    assert mod._classify_error("ModuleNotFoundError: No module named 'x'") == "module_not_found"
    assert mod._classify_error("cat: y: No such file or directory") == "file_not_found"
    assert mod._classify_error("process exited with exit code 2") == "non_zero_exit"
    # a matched-but-unrecognized error is a class, never a raw blob
    assert mod._classify_error("something went wrong: error happened") == "generic_error"


def test_error_fix_trigger_is_a_class_not_a_raw_blob(mod) -> None:
    """The trigger names the error CLASS (matchable across sessions), never the
    truncated raw error text that produced the pre-R5 junk instincts."""
    obs: list[dict] = []
    for i in range(3):
        obs.append(
            {"ts": _ts(1), "tool": "Bash", "out": f"bash: tool{i}: command not found",
             "in": "{}", "sid": "s"}
        )
        obs.append(
            {"ts": _ts(1), "tool": "Bash", "in": json.dumps({"command": "mise install"}),
             "out": "ok", "sid": "s"}
        )

    cands = mod.detect_error_fixes(obs)

    assert len(cands) == 1
    c = cands[0]
    assert "command_not_found" in c["id"]
    assert "command_not_found" in c["description"]
    assert "tool0" not in c["description"]  # no raw error text leaks into the trigger
    assert "command_not_found" in mod._build_trigger(c)
