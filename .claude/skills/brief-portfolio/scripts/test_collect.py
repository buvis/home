"""Regression tests for collect.py's local parsers. Run: python3 -m pytest test_collect.py -q"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from collect import collect_brush


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
