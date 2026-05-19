"""Tests for cartographer-stop.py Stop-event staleness detector (PRD 00011)."""
import importlib.util
import io
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))

_HOOK_PATH = Path.home() / ".claude" / "hooks" / "cartographer-stop.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("cartographer_stop", _HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stop_payload() -> dict:
    """Minimal Stop-event JSON the hook reads from stdin."""
    return {"hook_event_name": "Stop"}


def _make_git_repo(tmp_path: Path) -> Path:
    """Create a real git repo with an initial commit; return the repo path."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@test.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True, capture_output=True)
    return repo


_commit_seq = 0


def _add_commits(repo: Path, count: int) -> str:
    """Add `count` commits on top of current HEAD; return the new HEAD sha.

    Uses a process-global monotonic counter for file names so repeated calls
    on the same repo never re-commit an unchanged file (which git rejects).
    """
    global _commit_seq
    for _ in range(count):
        _commit_seq += 1
        f = repo / f"file_{_commit_seq}.txt"
        f.write_text(f"content {_commit_seq}")
        subprocess.run(["git", "-C", str(repo), "add", str(f)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-m", f"commit {_commit_seq}"], check=True, capture_output=True)
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def _write_atlas(atlas_dir: Path, head_sha: str, surveyed_at: datetime, staleness: dict | None = None) -> None:
    """Write a minimal atlas.json into atlas_dir."""
    atlas_dir.mkdir(parents=True, exist_ok=True)
    data: dict = {
        "head_sha": head_sha,
        "surveyed_at": surveyed_at.isoformat(),
    }
    if staleness is not None:
        data["staleness"] = staleness
    (atlas_dir / "atlas.json").write_text(json.dumps(data))


def _setup_hook(
    tmp_path: Path,
    monkeypatch,
    repo: Path,
    atlas_dir: Path,
) -> tuple:
    """Load hook, wire monkeypatches, return (mod, audit_events)."""
    mod = _load_hook()
    audit_events: list[dict] = []

    monkeypatch.setattr(mod, "project_hash", lambda path: ("testhash", "testrepo", ""))
    monkeypatch.setattr(mod, "atlas_dir", lambda h: atlas_dir)
    monkeypatch.setattr(mod, "append_audit", lambda event: audit_events.append(event))

    import os
    monkeypatch.setattr(os, "getcwd", lambda: str(repo))

    return mod, audit_events


def _run_hook(mod, monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_stop_payload())))
    mod.main()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_flag_set_when_commit_threshold_exceeded(tmp_path, monkeypatch):
    """51 commits since head_sha -> staleness.flag created; audit reason stale-flag-set."""
    repo = _make_git_repo(tmp_path)
    atlas_dir = tmp_path / "atlas"

    base_sha = _add_commits(repo, 1)
    _add_commits(repo, 51)

    recent = datetime.now(timezone.utc) - timedelta(days=1)
    _write_atlas(atlas_dir, base_sha, recent)

    mod, audit_events = _setup_hook(tmp_path, monkeypatch, repo, atlas_dir)
    _run_hook(mod, monkeypatch)

    assert (atlas_dir / "staleness.flag").exists(), "Flag must be created when commit count >= threshold"
    assert audit_events[-1]["reason"] == "stale-flag-set"


def test_no_flag_when_below_commit_threshold(tmp_path, monkeypatch):
    """49 commits since head_sha -> NO staleness.flag; audit reason fresh."""
    repo = _make_git_repo(tmp_path)
    atlas_dir = tmp_path / "atlas"

    base_sha = _add_commits(repo, 1)
    _add_commits(repo, 49)

    recent = datetime.now(timezone.utc) - timedelta(days=1)
    _write_atlas(atlas_dir, base_sha, recent)

    mod, audit_events = _setup_hook(tmp_path, monkeypatch, repo, atlas_dir)
    _run_hook(mod, monkeypatch)

    assert not (atlas_dir / "staleness.flag").exists(), "Flag must NOT be created at 49 commits (below 50 threshold)"
    assert audit_events[-1]["reason"] == "fresh"


def test_flag_set_when_age_threshold_exceeded(tmp_path, monkeypatch):
    """surveyed_at older than 14 days (0 new commits) -> staleness.flag created."""
    repo = _make_git_repo(tmp_path)
    atlas_dir = tmp_path / "atlas"

    head_sha = _add_commits(repo, 1)

    old_date = datetime.now(timezone.utc) - timedelta(days=15)
    _write_atlas(atlas_dir, head_sha, old_date)

    mod, audit_events = _setup_hook(tmp_path, monkeypatch, repo, atlas_dir)
    _run_hook(mod, monkeypatch)

    assert (atlas_dir / "staleness.flag").exists(), "Flag must be created when age >= 14 days"
    assert audit_events[-1]["reason"] == "stale-flag-set"


def test_no_flag_when_fresh(tmp_path, monkeypatch):
    """surveyed_at within 14 days and few commits -> no flag; audit reason fresh."""
    repo = _make_git_repo(tmp_path)
    atlas_dir = tmp_path / "atlas"

    base_sha = _add_commits(repo, 1)
    _add_commits(repo, 5)

    recent = datetime.now(timezone.utc) - timedelta(days=3)
    _write_atlas(atlas_dir, base_sha, recent)

    mod, audit_events = _setup_hook(tmp_path, monkeypatch, repo, atlas_dir)
    _run_hook(mod, monkeypatch)

    assert not (atlas_dir / "staleness.flag").exists()
    assert audit_events[-1]["reason"] == "fresh"


def test_no_flag_and_no_atlas_reason_when_atlas_json_missing(tmp_path, monkeypatch):
    """No atlas.json -> no flag; audit reason no-atlas."""
    repo = _make_git_repo(tmp_path)
    atlas_dir = tmp_path / "atlas"
    atlas_dir.mkdir(parents=True, exist_ok=True)

    mod, audit_events = _setup_hook(tmp_path, monkeypatch, repo, atlas_dir)
    _run_hook(mod, monkeypatch)

    assert not (atlas_dir / "staleness.flag").exists()
    assert audit_events[-1]["reason"] == "no-atlas"


def test_per_repo_override_lowers_commit_threshold(tmp_path, monkeypatch):
    """Per-repo max_commits=10 override; 12 commits since survey -> flag created."""
    repo = _make_git_repo(tmp_path)
    atlas_dir = tmp_path / "atlas"

    base_sha = _add_commits(repo, 1)
    _add_commits(repo, 12)

    recent = datetime.now(timezone.utc) - timedelta(days=1)
    _write_atlas(atlas_dir, base_sha, recent, staleness={"max_commits": 10})

    mod, audit_events = _setup_hook(tmp_path, monkeypatch, repo, atlas_dir)
    _run_hook(mod, monkeypatch)

    assert (atlas_dir / "staleness.flag").exists(), "Override max_commits=10 must trigger at 12 commits"
    assert audit_events[-1]["reason"] == "stale-flag-set"


def test_per_repo_override_does_not_trigger_below_custom_threshold(tmp_path, monkeypatch):
    """Per-repo max_commits=10 override; only 8 commits -> no flag."""
    repo = _make_git_repo(tmp_path)
    atlas_dir = tmp_path / "atlas"

    base_sha = _add_commits(repo, 1)
    _add_commits(repo, 8)

    recent = datetime.now(timezone.utc) - timedelta(days=1)
    _write_atlas(atlas_dir, base_sha, recent, staleness={"max_commits": 10})

    mod, audit_events = _setup_hook(tmp_path, monkeypatch, repo, atlas_dir)
    _run_hook(mod, monkeypatch)

    assert not (atlas_dir / "staleness.flag").exists()
    assert audit_events[-1]["reason"] == "fresh"


def test_exactly_one_audit_event_per_run(tmp_path, monkeypatch):
    """Every run appends exactly one audit event."""
    repo = _make_git_repo(tmp_path)
    atlas_dir = tmp_path / "atlas"

    head_sha = _add_commits(repo, 1)
    recent = datetime.now(timezone.utc) - timedelta(days=1)
    _write_atlas(atlas_dir, head_sha, recent)

    mod, audit_events = _setup_hook(tmp_path, monkeypatch, repo, atlas_dir)

    assert len(audit_events) == 0
    _run_hook(mod, monkeypatch)
    assert len(audit_events) == 1, "Exactly one audit event must be appended per run"


def test_unexpected_error_does_not_propagate(tmp_path, monkeypatch):
    """An unexpected error (project_hash raises) does not propagate out of main()."""
    mod = _load_hook()

    def _raise(path):
        raise RuntimeError("unexpected boom")

    monkeypatch.setattr(mod, "project_hash", _raise)
    import os
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_stop_payload())))

    mod.main()  # must not raise


def test_flag_not_created_at_boundary_below_commit_threshold(tmp_path, monkeypatch):
    """Exactly 49 commits (one below 50 threshold) -> no flag. Guards off-by-one."""
    repo = _make_git_repo(tmp_path)
    atlas_dir = tmp_path / "atlas"

    base_sha = _add_commits(repo, 1)
    _add_commits(repo, 49)

    recent = datetime.now(timezone.utc) - timedelta(days=1)
    _write_atlas(atlas_dir, base_sha, recent)

    mod, audit_events = _setup_hook(tmp_path, monkeypatch, repo, atlas_dir)
    _run_hook(mod, monkeypatch)

    assert not (atlas_dir / "staleness.flag").exists()
    assert audit_events[-1]["reason"] == "fresh"


def test_flag_created_at_exactly_commit_threshold(tmp_path, monkeypatch):
    """Exactly 50 commits -> flag created. The threshold is >=, not >."""
    repo = _make_git_repo(tmp_path)
    atlas_dir = tmp_path / "atlas"

    base_sha = _add_commits(repo, 1)
    _add_commits(repo, 50)

    recent = datetime.now(timezone.utc) - timedelta(days=1)
    _write_atlas(atlas_dir, base_sha, recent)

    mod, audit_events = _setup_hook(tmp_path, monkeypatch, repo, atlas_dir)
    _run_hook(mod, monkeypatch)

    assert (atlas_dir / "staleness.flag").exists(), "Exactly 50 commits must trigger the flag (>= threshold)"
    assert audit_events[-1]["reason"] == "stale-flag-set"


def test_non_git_atlas_missing_head_sha_logs_no_git_reason(tmp_path, monkeypatch):
    """atlas.json without head_sha (non-git atlas) -> audit reason no-git, hook does not crash."""
    repo = _make_git_repo(tmp_path)
    atlas_dir = tmp_path / "atlas"
    atlas_dir.mkdir(parents=True, exist_ok=True)

    # Write atlas.json WITHOUT head_sha to simulate a non-git-directory atlas.
    recent = datetime.now(timezone.utc) - timedelta(days=1)
    (atlas_dir / "atlas.json").write_text(json.dumps({"surveyed_at": recent.isoformat()}))

    mod, audit_events = _setup_hook(tmp_path, monkeypatch, repo, atlas_dir)
    _run_hook(mod, monkeypatch)

    assert len(audit_events) == 1, "Exactly one audit event must be appended"
    assert audit_events[-1]["reason"] == "no-git", (
        f"Expected reason 'no-git' for missing head_sha, got {audit_events[-1]['reason']!r}"
    )


def test_non_git_atlas_does_not_produce_skip_reason(tmp_path, monkeypatch):
    """Missing head_sha must be handled explicitly as no-git, not collapsed into the catch-all skip."""
    repo = _make_git_repo(tmp_path)
    atlas_dir = tmp_path / "atlas"
    atlas_dir.mkdir(parents=True, exist_ok=True)

    recent = datetime.now(timezone.utc) - timedelta(days=1)
    (atlas_dir / "atlas.json").write_text(json.dumps({"surveyed_at": recent.isoformat()}))

    mod, audit_events = _setup_hook(tmp_path, monkeypatch, repo, atlas_dir)
    _run_hook(mod, monkeypatch)

    assert audit_events[-1]["reason"] != "skip", (
        "Missing head_sha must produce reason 'no-git', not the catch-all 'skip'"
    )


def test_invalid_head_sha_logs_git_error_reason(tmp_path, monkeypatch):
    """atlas.json with a bogus head_sha that git rev-list cannot resolve -> audit reason git-error, hook does not crash."""
    repo = _make_git_repo(tmp_path)
    atlas_dir = tmp_path / "atlas"
    atlas_dir.mkdir(parents=True, exist_ok=True)

    # A SHA that does not exist in the repo causes git rev-list to fail.
    bogus_sha = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    recent = datetime.now(timezone.utc) - timedelta(days=1)
    (atlas_dir / "atlas.json").write_text(
        json.dumps({"head_sha": bogus_sha, "surveyed_at": recent.isoformat()})
    )

    mod, audit_events = _setup_hook(tmp_path, monkeypatch, repo, atlas_dir)
    _run_hook(mod, monkeypatch)

    assert len(audit_events) == 1, "Exactly one audit event must be appended"
    assert audit_events[-1]["reason"] == "git-error", (
        f"Expected reason 'git-error' for bad head_sha, got {audit_events[-1]['reason']!r}"
    )


def test_git_error_does_not_produce_skip_reason(tmp_path, monkeypatch):
    """git rev-list failure must be handled explicitly as git-error, not collapsed into the catch-all skip."""
    repo = _make_git_repo(tmp_path)
    atlas_dir = tmp_path / "atlas"
    atlas_dir.mkdir(parents=True, exist_ok=True)

    bogus_sha = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    recent = datetime.now(timezone.utc) - timedelta(days=1)
    (atlas_dir / "atlas.json").write_text(
        json.dumps({"head_sha": bogus_sha, "surveyed_at": recent.isoformat()})
    )

    mod, audit_events = _setup_hook(tmp_path, monkeypatch, repo, atlas_dir)
    _run_hook(mod, monkeypatch)

    assert audit_events[-1]["reason"] != "skip", (
        "git rev-list failure must produce reason 'git-error', not the catch-all 'skip'"
    )
