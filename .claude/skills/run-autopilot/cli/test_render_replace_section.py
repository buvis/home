#!/usr/bin/env python3
"""Tests for render_report._replace_section and the `render report` CLI
behavior it backs: collapsing an already-duplicated PRD section down to
exactly one occurrence.

Split out as a new sibling of test_render.py to keep both files under the
project's 800-line ceiling; test_render.py's own module docstring still
covers the full render-surface test map this file's classes pin into.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

CLI_DIR = Path(__file__).resolve().parent
CLI_MAIN = CLI_DIR / "__main__.py"
GOLDEN = CLI_DIR / "golden"

sys.path.insert(0, str(CLI_DIR.parent))

from cli import render_report

NOW = "2026-08-09T12:00:00Z"


class ReplaceSectionTests(unittest.TestCase):
    """render_report._replace_section: drop the section starting at the
    exact line `heading` (up to the next `## `-prefixed line or EOF) from
    `existing`; a no-op when `heading` is not present as an exact line."""

    def test_drops_middle_section_leaving_earlier_and_later_sections_intact(
        self,
    ) -> None:
        existing = (
            "# Header\n"
            "\n"
            "## PRD-A\n"
            "\n"
            "Content A\n"
            "\n"
            "## PRD-B\n"
            "\n"
            "Content B\n"
            "\n"
            "## PRD-C\n"
            "\n"
            "Content C\n"
        )
        result = render_report._replace_section(existing, "## PRD-B")
        self.assertEqual(
            result,
            ("# Header\n\n## PRD-A\n\nContent A\n\n## PRD-C\n\nContent C\n"),
        )

    def test_noop_when_heading_is_not_present(self) -> None:
        existing = "# Header\n\n## PRD-A\n\nContent A\n"
        self.assertEqual(render_report._replace_section(existing, "## PRD-Z"), existing)

    def test_noop_when_heading_is_prefix_of_a_longer_heading_line(self) -> None:
        # "## PRD-Alpha" is not the exact line "## PRD-A" - a substring
        # match here would wrongly drop the whole section.
        existing = "## PRD-Alpha\n\nContent\n"
        self.assertEqual(render_report._replace_section(existing, "## PRD-A"), existing)

    def test_noop_when_line_has_trailing_whitespace_before_the_newline(self) -> None:
        # Only the trailing "\n" is stripped before comparison, so trailing
        # spaces before it must still break the match.
        existing = "## PRD-A \n\nContent\n"
        self.assertEqual(render_report._replace_section(existing, "## PRD-A"), existing)

    def test_drops_a_section_that_runs_to_end_of_file(self) -> None:
        existing = "# Header\n\n## PRD-A\n\nContent A\n"
        result = render_report._replace_section(existing, "## PRD-A")
        self.assertEqual(result, "# Header\n\n")

    def test_drops_section_immediately_adjacent_to_the_next_heading(self) -> None:
        # No blank-line separator between the dropped section's last content
        # line and the next "## " heading.
        existing = "## PRD-A\ncontent line\n## PRD-B\nmore\n"
        result = render_report._replace_section(existing, "## PRD-A")
        self.assertEqual(result, "## PRD-B\nmore\n")

    def test_does_not_stop_at_a_level_3_subheading_inside_the_dropped_section(
        self,
    ) -> None:
        # prd_section() bodies contain "### " subheadings (Assumptions Made,
        # Autonomous Decisions, ...); those must not be mistaken for the
        # next top-level "## " boundary and truncate the drop early.
        existing = "## PRD-A\n\n### Sub Heading\n\nSub content\n\n## PRD-B\n\ncontent\n"
        result = render_report._replace_section(existing, "## PRD-A")
        self.assertEqual(result, "## PRD-B\n\ncontent\n")

    def test_drops_every_occurrence_when_the_heading_is_duplicated(self) -> None:
        # A report file in the wild can already carry the SAME heading
        # twice (the bug this PRD fixed used to append a duplicate PRD
        # section on every render-report rerun). One call must remove every
        # occurrence, not just the first one found, or the file never
        # converges to a single section.
        existing = (
            "# Header\n"
            "\n"
            "## PRD-A\n"
            "\n"
            "Content A first\n"
            "\n"
            "## PRD-B\n"
            "\n"
            "Content B\n"
            "\n"
            "## PRD-A\n"
            "\n"
            "Content A second\n"
        )
        result = render_report._replace_section(existing, "## PRD-A")
        self.assertEqual(result.count("## PRD-A"), 0)
        self.assertIn("## PRD-B", result)
        self.assertIn("Content B", result)


class CliWiringTests(unittest.TestCase):
    """`autopilot render report`'s duplicate-section collapse, as real
    subprocesses against a constructed <repo>/dev/local/autopilot tree."""

    def setUp(self) -> None:
        import tempfile

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        self.ap_dir = self.repo / "dev" / "local" / "autopilot"
        self.ap_dir.mkdir(parents=True)
        self.state_path = self.ap_dir / "state.json"
        self.state_path.write_text(
            (GOLDEN / "state-render.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (self.ap_dir / "loop-metrics.jsonl").write_text(
            (GOLDEN / "metrics-render.jsonl").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CLI_MAIN), *args, "--state", str(self.state_path)],
            capture_output=True,
            text=True,
        )

    def test_render_report_rerun_produces_exactly_one_prd_section(self) -> None:
        first = self._run(["render", "report", "--now", NOW])
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self._run(["render", "report", "--now", NOW])
        self.assertEqual(second.returncode, 0, second.stderr)
        report = self.ap_dir / "reports" / "202607202320-report.md"
        text = report.read_text(encoding="utf-8")
        self.assertEqual(text.count("## 00040-feature-x-v1.md"), 1)
        self.assertEqual(text.count("# Autopilot Batch Report 202607202320"), 1)

    def test_render_report_seeded_with_a_duplicate_section_collapses_to_one(
        self,
    ) -> None:
        # A report file can already be on disk with the SAME PRD section
        # twice (the pre-fix bug: append a duplicate on every rerun). A
        # SINGLE render-report run against such a file must collapse it to
        # exactly one occurrence, not merely stop it growing further.
        first = self._run(["render", "report", "--now", NOW])
        self.assertEqual(first.returncode, 0, first.stderr)
        report = self.ap_dir / "reports" / "202607202320-report.md"
        text = report.read_text(encoding="utf-8")
        section_start = text.index("## 00040-feature-x-v1.md")
        section = text[section_start:]
        report.write_text(text + section, encoding="utf-8")
        self.assertEqual(
            report.read_text(encoding="utf-8").count("## 00040-feature-x-v1.md"),
            2,
        )

        second = self._run(["render", "report", "--now", NOW])

        self.assertEqual(second.returncode, 0, second.stderr)
        rerendered = report.read_text(encoding="utf-8")
        self.assertEqual(rerendered.count("## 00040-feature-x-v1.md"), 1)

    def test_render_report_stays_idempotent_across_three_runs(self) -> None:
        for _ in range(3):
            proc = self._run(["render", "report", "--now", NOW])
            self.assertEqual(proc.returncode, 0, proc.stderr)
        report = self.ap_dir / "reports" / "202607202320-report.md"
        text = report.read_text(encoding="utf-8")
        self.assertEqual(text.count("## 00040-feature-x-v1.md"), 1)

    def test_render_report_rerun_preserves_other_prds_section_and_header(self) -> None:
        first = self._run(["render", "report", "--now", NOW])
        self.assertEqual(first.returncode, 0, first.stderr)

        other_state = json.loads(self.state_path.read_text(encoding="utf-8"))
        other_state["prd"] = "00041-feature-y-v1.md"
        self.state_path.write_text(json.dumps(other_state), encoding="utf-8")
        second = self._run(["render", "report", "--now", NOW])
        self.assertEqual(second.returncode, 0, second.stderr)

        # Switch back to the original PRD: its rerun must replace only its
        # own section, not the other PRD's section or the file header.
        self.state_path.write_text(
            (GOLDEN / "state-render.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        third = self._run(["render", "report", "--now", NOW])
        self.assertEqual(third.returncode, 0, third.stderr)

        report = self.ap_dir / "reports" / "202607202320-report.md"
        text = report.read_text(encoding="utf-8")
        self.assertEqual(text.count("## 00040-feature-x-v1.md"), 1)
        self.assertEqual(text.count("## 00041-feature-y-v1.md"), 1)
        self.assertEqual(text.count("# Autopilot Batch Report 202607202320"), 1)


if __name__ == "__main__":
    unittest.main()
