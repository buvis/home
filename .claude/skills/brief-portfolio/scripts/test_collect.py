"""Regression tests for collect.py's local parsers. Run: python3 -m pytest test_collect.py -q"""

import json
import pytest
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import collect
from collect import (
    ROTATE_MIN_AGE,
    collect_brush,
    collect_claude_maintenance,
    collect_claude_skill_adherence,
    collect_repo,
    main,
    should_rotate,
    stub_from_path,
)


def write_report(tmp_path: Path, body: str) -> None:
    report = tmp_path / "dev/local/audit-results/brush-report.md"
    report.parent.mkdir(parents=True)
    report.write_text(body)


def test_reads_generated_date_from_brush_report(tmp_path):
    write_report(
        tmp_path,
        "# Brush report - x\n\n"
        "- generated: 2026-07-13 14:02 | mode: quick | HEAD: abc123 | branch: master | unpushed: 0\n",
    )
    assert collect_brush(tmp_path) == "2026-07-13"


def test_never_brushed_repo_returns_none(tmp_path):
    assert collect_brush(tmp_path) is None


def test_report_without_generated_line_returns_none(tmp_path):
    write_report(tmp_path, "# Brush report - x\n")
    assert collect_brush(tmp_path) is None


def test_maintenance_none_when_dir_absent_or_empty(tmp_path):
    assert collect_claude_maintenance(tmp_path / "missing") is None
    (tmp_path / "audit-results").mkdir()
    assert collect_claude_maintenance(tmp_path / "audit-results") is None


def test_maintenance_returns_newest_mtime_day(tmp_path):
    import os
    import time

    d = tmp_path / "audit-results"
    d.mkdir()
    old = d / "old.md"
    new = d / "new.md"
    old.write_text("x")
    new.write_text("y")
    newest = time.time()
    os.utime(old, (newest - 5 * 86400, newest - 5 * 86400))
    os.utime(new, (newest, newest))
    expected = datetime.fromtimestamp(newest, timezone.utc).strftime("%Y-%m-%d")
    assert collect_claude_maintenance(d) == expected


def test_skill_adherence_none_when_no_file(tmp_path):
    assert collect_claude_skill_adherence(tmp_path / "skills.jsonl") is None


def test_skill_adherence_counts_last_30d_and_ranks_top(tmp_path):
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    recent = now.isoformat()
    old = (now - timedelta(days=45)).isoformat()
    f = tmp_path / "skills.jsonl"
    f.write_text(
        "\n".join(
            json.dumps(r)
            for r in [
                {"skill": "work", "ts": recent},
                {"skill": "work", "ts": recent},
                {"skill": "brush", "ts": recent},
                {"skill": "survey", "ts": old},  # outside the 30d window
                "not json",
            ]
        )
        + "\n"
    )
    got = collect_claude_skill_adherence(f)
    assert got["count"] == 3
    assert got["distinct"] == 2
    assert got["top"][0] == {"skill": "work", "n": 2}
    assert not any(t["skill"] == "survey" for t in got["top"])


def test_skill_adherence_empty_when_all_stale(tmp_path):
    from datetime import timedelta

    old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    f = tmp_path / "skills.jsonl"
    f.write_text(json.dumps({"skill": "work", "ts": old}) + "\n")
    assert collect_claude_skill_adherence(f) == {"count": 0, "distinct": 0, "top": []}


def test_stub_from_path_builds_owner_name_org_and_reason_from_path():
    result = stub_from_path("/repos/acme/widget", "not a github remote: bad-url")
    assert result == {
        "owner": "acme",
        "name": "widget",
        "org": "acme",
        "path": "/repos/acme/widget",
        "skipped": "not a github remote: bad-url",
    }


def test_collect_repo_returns_skip_stub_when_remote_unresolvable(monkeypatch):
    def fake_run(cmd, cwd=None, timeout=120):
        if cmd[0] == "git" and cmd[1] == "remote":
            raise RuntimeError("not a github remote: bad-url")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(collect, "run", fake_run)
    result = collect_repo("/repos/acme/widget", 60, False)
    assert result == {
        "owner": "acme",
        "name": "widget",
        "org": "acme",
        "path": "/repos/acme/widget",
        "skipped": "not a github remote: bad-url",
    }


def test_collect_repo_records_fetch_timeout_without_raising(monkeypatch):
    fetch_cmd = ["git", "fetch", "--quiet", "origin"]
    timeout_exc = subprocess.TimeoutExpired(fetch_cmd, 180)

    def fake_run(cmd, cwd=None, timeout=120):
        if cmd[0] == "git" and cmd[1] == "remote":
            return "git@github.com:acme/widget.git\n"
        if cmd[0] == "git" and cmd[1] == "fetch":
            raise timeout_exc
        if cmd[0] == "gh":
            raise RuntimeError("gh: not authenticated")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(collect, "run", fake_run)
    result = collect_repo("/repos/acme/widget", 60, True)
    assert result is not None
    assert "skipped" not in result
    assert f"fetch: {timeout_exc}" in result["errors"]


def make_registry(tmp_path: Path, names) -> list:
    """Create a fake gita registry: one directory with a .git marker per name."""
    root = tmp_path / "repos"
    paths = []
    for name in names:
        d = root / name
        (d / ".git").mkdir(parents=True)
        paths.append(str(d))
    return paths


def write_registry_csv(tmp_path: Path, paths) -> Path:
    csv_path = tmp_path / "repos.csv"
    csv_path.write_text("\n".join(paths) + "\n")
    return csv_path


def make_fake_run(skip_cwds):
    """collect.run replacement: resolvable repos get a valid github remote,
    skip_cwds fail repo_slug, and every gh call fails (unauthenticated)."""

    def fake_run(cmd, cwd=None, timeout=120):
        if cmd[0] == "git" and cmd[1] == "remote":
            if str(cwd) in skip_cwds:
                raise RuntimeError("not a github remote: bad-url")
            return f"git@github.com:acme/{Path(cwd).name}.git\n"
        if cmd[0] == "gh":
            raise RuntimeError("gh: not authenticated")
        raise AssertionError(f"unexpected command: {cmd}")

    return fake_run


def run_collector(tmp_path, monkeypatch, resolvable_names, skip_names):
    paths = make_registry(tmp_path, resolvable_names + skip_names)
    skip_paths = {str(tmp_path / "repos" / name) for name in skip_names}
    monkeypatch.setattr(collect, "run", make_fake_run(skip_paths))
    monkeypatch.setattr(collect, "GITA_CSV", write_registry_csv(tmp_path, paths))
    out_dir = tmp_path / "out"
    monkeypatch.setattr(
        sys, "argv", ["collect.py", "--no-git-fetch", "--out", str(out_dir)]
    )
    main()
    return paths, out_dir


def test_main_partition_invariant_covers_every_registry_path(tmp_path, monkeypatch):
    paths, out_dir = run_collector(tmp_path, monkeypatch, ["alpha", "beta"], ["broken"])
    data = json.loads((out_dir / "data.json").read_text())
    assert len(paths) == len(data["repos"]) + len(data["skipped"])
    assert len(data["skipped"]) == 1
    assert data["skipped"][0]["skipped"]


def test_main_history_entry_counts_skipped_repos(tmp_path, monkeypatch):
    _, out_dir = run_collector(tmp_path, monkeypatch, ["alpha", "beta"], ["broken"])
    lines = (out_dir / "history.jsonl").read_text().strip().splitlines()
    last = json.loads(lines[-1])
    assert last["skipped"] == 1


def test_main_summary_line_reports_paths_and_skipped_counts(
    tmp_path, monkeypatch, capsys
):
    paths, _ = run_collector(tmp_path, monkeypatch, ["alpha", "beta"], ["broken"])
    captured = capsys.readouterr()
    assert f"{len(paths)} repos, 1 skipped" in captured.out


def test_main_external_section_reports_error_when_gh_unauthenticated(
    tmp_path, monkeypatch
):
    _, out_dir = run_collector(tmp_path, monkeypatch, ["alpha"], [])
    data = json.loads((out_dir / "data.json").read_text())
    assert data["external"]["review_requested"] == []
    assert data["external"]["authored"] == []
    assert data["external"]["error"]


def test_rotate_min_age_is_four_hours():
    from datetime import timedelta

    assert ROTATE_MIN_AGE == timedelta(hours=4)


def test_should_rotate_false_for_snapshot_48_seconds_old():
    from datetime import timedelta

    now = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
    existing_at = (now - timedelta(seconds=48)).isoformat()
    assert should_rotate(existing_at, now) is False


def test_should_rotate_true_for_snapshot_5_hours_old():
    from datetime import timedelta

    now = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
    existing_at = (now - timedelta(hours=5)).isoformat()
    assert should_rotate(existing_at, now) is True


def test_should_rotate_boundary_is_inclusive_at_exactly_four_hours():
    from datetime import timedelta

    now = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
    just_under = now - (ROTATE_MIN_AGE - timedelta(seconds=1))
    exactly = now - ROTATE_MIN_AGE
    assert should_rotate(just_under.isoformat(), now) is False
    assert should_rotate(exactly.isoformat(), now) is True


def write_snapshot(path: Path, generated_at: str, marker: str) -> str:
    """Write a minimal data.json-shaped fixture and return its exact text,
    so callers can assert byte-for-byte preservation later."""
    content = json.dumps({"generated_at": generated_at, "marker": marker}, indent=1)
    path.write_text(content)
    return content


def test_main_leaves_older_baseline_untouched_when_existing_snapshot_is_recent(
    tmp_path, monkeypatch
):
    from datetime import timedelta

    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True)
    baseline_content = write_snapshot(
        out_dir / "data-prev.json", "2026-08-01T00:00:00+00:00", "real-baseline"
    )
    recent_at = (datetime.now(timezone.utc) - timedelta(seconds=48)).isoformat(
        timespec="seconds"
    )
    write_snapshot(out_dir / "data.json", recent_at, "48-seconds-old")

    run_collector(tmp_path, monkeypatch, ["alpha"], [])

    assert (out_dir / "data-prev.json").read_text() == baseline_content
    new_data = json.loads((out_dir / "data.json").read_text())
    assert new_data["generated_at"] != recent_at
    assert len(new_data["repos"]) == 1


def test_main_publishes_old_snapshot_as_data_prev_when_stale(tmp_path, monkeypatch):
    from datetime import timedelta

    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True)
    stale_at = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat(
        timespec="seconds"
    )
    old_content = write_snapshot(out_dir / "data.json", stale_at, "5-hours-old")

    run_collector(tmp_path, monkeypatch, ["alpha"], [])

    assert (out_dir / "data-prev.json").read_text() == old_content
    new_data = json.loads((out_dir / "data.json").read_text())
    assert new_data["generated_at"] != stale_at
    assert len(new_data["repos"]) == 1


def test_main_leaves_data_json_unchanged_when_prev_tmp_write_fails(
    tmp_path, monkeypatch
):
    from datetime import timedelta

    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True)
    stale_at = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat(
        timespec="seconds"
    )
    old_content = write_snapshot(out_dir / "data.json", stale_at, "5-hours-old")

    original_write_text = Path.write_text

    def failing_write_text(self, *args, **kwargs):
        if str(self).endswith("data-prev.json.tmp"):
            raise OSError("disk full")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing_write_text)

    with pytest.raises(OSError):
        run_collector(tmp_path, monkeypatch, ["alpha"], [])

    assert (out_dir / "data.json").read_text() == old_content


def test_offline_makes_zero_subprocess_calls(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True)
    write_snapshot(out_dir / "data.json", "2026-08-20T00:00:00+00:00", "cached")

    def explode(*args, **kwargs):
        raise AssertionError(f"subprocess.run should not be called: {args!r} {kwargs!r}")

    monkeypatch.setattr(collect.subprocess, "run", explode)
    monkeypatch.setattr(
        sys, "argv", ["collect.py", "--offline", "--out", str(out_dir)]
    )
    main()


def test_offline_leaves_cached_data_json_byte_for_byte_unchanged(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True)
    content = write_snapshot(out_dir / "data.json", "2026-08-20T00:00:00+00:00", "cached")

    monkeypatch.setattr(
        sys, "argv", ["collect.py", "--offline", "--out", str(out_dir)]
    )
    main()

    assert (out_dir / "data.json").read_text() == content


def test_offline_without_cached_data_json_exits_with_error(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    monkeypatch.setattr(
        sys, "argv", ["collect.py", "--offline", "--out", str(out_dir)]
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    message = str(exc_info.value.code)
    assert message
    assert str(out_dir / "data.json") in message
    assert "collect.py" in message


def test_offline_does_not_write_history_digest_or_prev_snapshot(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True)
    write_snapshot(out_dir / "data.json", "2026-08-20T00:00:00+00:00", "cached")

    monkeypatch.setattr(
        sys, "argv", ["collect.py", "--offline", "--out", str(out_dir)]
    )
    main()

    assert not (out_dir / "history.jsonl").exists()
    assert not (out_dir / "commits-digest.md").exists()
    assert not (out_dir / "data-prev.json").exists()


def test_no_git_fetch_flag_passes_fetch_false_to_collect_repo(tmp_path, monkeypatch):
    paths = make_registry(tmp_path, ["alpha"])
    monkeypatch.setattr(collect, "GITA_CSV", write_registry_csv(tmp_path, paths))
    monkeypatch.setattr(collect, "run", make_fake_run(set()))
    fetch_values = []

    def fake_collect_repo(path, days, fetch):
        fetch_values.append(fetch)
        return {"owner": "acme", "name": Path(path).name, "errors": []}

    monkeypatch.setattr(collect, "collect_repo", fake_collect_repo)
    out_dir = tmp_path / "out"
    monkeypatch.setattr(
        sys, "argv", ["collect.py", "--no-git-fetch", "--out", str(out_dir)]
    )
    main()

    assert fetch_values == [False]


def test_no_fetch_old_spelling_is_rejected_by_argparse(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["collect.py", "--no-fetch", "--out", str(tmp_path / "out")]
    )

    with pytest.raises(SystemExit):
        main()
