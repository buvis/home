"""Regression tests for collect.py's local parsers. Run: python3 -m pytest test_collect.py -q"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from collect import collect_brush, collect_claude_maintenance


def write_report(tmp_path: Path, body: str) -> None:
    report = tmp_path / "dev/local/audit-results/brush-report.md"
    report.parent.mkdir(parents=True)
    report.write_text(body)


def test_reads_generated_date_from_brush_report(tmp_path):
    write_report(tmp_path, "# Brush report - x\n\n"
                 "- generated: 2026-07-13 14:02 | mode: quick | HEAD: abc123 | branch: master | unpushed: 0\n")
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
