"""Tests for slop_metrics.py — completeness requirements.

Covers:
  - acceptance-criteria parsing from PRD markdown fixtures
  - prior `Lines per AC` value extraction across batch reports
  - status labeling at the 1.5x and 2.5x ratio boundaries
  - render_block INSUFFICIENT_DATA branch (< 3 priors)
  - render_block normal branch (>= 3 priors)
  - graceful exit when state.json is absent
  - find_prd_file resolution across wip/done/stalled
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import slop_metrics as sm


class TestCountAcceptanceCriteria(unittest.TestCase):
    def test_counts_tasks_in_implementation_phases(self) -> None:
        text = """# PRD

## Overview

Stuff.

## Implementation Phases

### Phase 0

**Tasks**:
- [ ] Task A
- [ ] Task B
- [ ] Task C

### Phase 1

**Tasks**:
- [ ] Task D

## Test Strategy

- [ ] not counted
"""
        self.assertEqual(sm.count_acceptance_criteria(text), 4)

    def test_returns_zero_when_section_absent(self) -> None:
        text = "# PRD\n\n## Overview\n\nNo phases section."
        self.assertEqual(sm.count_acceptance_criteria(text), 0)

    def test_returns_zero_when_section_empty(self) -> None:
        text = "## Implementation Phases\n\n## Next Section"
        self.assertEqual(sm.count_acceptance_criteria(text), 0)

    def test_indented_checkboxes_count(self) -> None:
        text = """## Implementation Phases
- [ ] Top-level
  - [ ] Indented
    - [ ] Deeply indented
"""
        self.assertEqual(sm.count_acceptance_criteria(text), 3)

    def test_checked_items_do_not_count(self) -> None:
        text = """## Implementation Phases
- [ ] Pending one
- [x] Completed one
- [ ] Another pending
"""
        self.assertEqual(sm.count_acceptance_criteria(text), 2)


class TestStatusLabel(unittest.TestCase):
    def test_low_at_median(self) -> None:
        # Exactly at median → ratio 1.0 → LOW (below 1.5x cutoff is "good")
        self.assertEqual(sm.status_label(40.0, 40.0), "LOW")

    def test_low_below_1_5x_boundary(self) -> None:
        # 40 / 30 ≈ 1.333 < 1.5 → LOW
        self.assertEqual(sm.status_label(40.0, 30.0), "LOW")

    def test_normal_at_1_5x_boundary(self) -> None:
        # 1.5x exactly → NORMAL (LOW boundary is strictly less than 1.5)
        self.assertEqual(sm.status_label(45.0, 30.0), "NORMAL")

    def test_normal_at_2_5x_boundary(self) -> None:
        # 2.5x exactly → NORMAL (HIGH boundary is strictly greater than 2.5)
        self.assertEqual(sm.status_label(75.0, 30.0), "NORMAL")

    def test_high_above_2_5x_boundary(self) -> None:
        # 76 / 30 ≈ 2.533 > 2.5 → HIGH
        self.assertEqual(sm.status_label(76.0, 30.0), "HIGH")

    def test_zero_median_returns_normal(self) -> None:
        self.assertEqual(sm.status_label(40.0, 0.0), "NORMAL")

    def test_negative_median_returns_normal(self) -> None:
        self.assertEqual(sm.status_label(40.0, -5.0), "NORMAL")


class TestRenderBlock(unittest.TestCase):
    def test_insufficient_data_branch(self) -> None:
        # Only 2 priors → INSUFFICIENT_DATA
        block = sm.render_block(120, 6, 20.0, [10.0, 15.0])
        self.assertIn("### Bloat metric", block)
        self.assertIn("- Net lines added: 120", block)
        self.assertIn("- Acceptance criteria items: 6", block)
        self.assertIn("- Lines per AC: 20.0", block)
        self.assertIn("- Median across last 5 PRDs: n/a", block)
        self.assertIn("- Status: INSUFFICIENT_DATA", block)

    def test_normal_branch_renders_ratio(self) -> None:
        # median = 20.0, lines_per_ac = 40.0 → 2.0x median → NORMAL
        block = sm.render_block(200, 5, 40.0, [10.0, 20.0, 30.0, 20.0, 20.0])
        self.assertIn("- Median across last 5 PRDs: 20.0", block)
        self.assertIn("- Status: NORMAL (2.0x median)", block)

    def test_high_branch(self) -> None:
        # median = 20.0, lines_per_ac = 70.0 → 3.5x → HIGH
        block = sm.render_block(350, 5, 70.0, [10.0, 20.0, 30.0, 20.0, 20.0])
        self.assertIn("- Status: HIGH (3.5x median)", block)

    def test_low_branch(self) -> None:
        # median = 40.0, lines_per_ac = 20.0 → 0.5x → LOW
        block = sm.render_block(100, 5, 20.0, [40.0, 40.0, 40.0])
        self.assertIn("- Status: LOW (0.5x median)", block)


class TestCollectPriorLinesPerAc(unittest.TestCase):
    def setUp(self) -> None:
        self._reports_root = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self._reports_root, ignore_errors=True)

    def test_missing_dir_returns_empty(self) -> None:
        result = sm.collect_prior_lines_per_ac(self._reports_root / "nonexistent")
        self.assertEqual(result, [])

    def test_extracts_values_newest_first(self) -> None:
        old_report = self._reports_root / "20260501-report.md"
        old_report.write_text(
            "## prd-1.md\n\n### Bloat metric\n- Lines per AC: 15.0\n"
        )
        new_report = self._reports_root / "20260502-report.md"
        new_report.write_text(
            "## prd-2.md\n\n### Bloat metric\n- Lines per AC: 25.0\n"
        )
        os.utime(old_report, (1_000_000, 1_000_000))
        os.utime(new_report, (2_000_000, 2_000_000))
        result = sm.collect_prior_lines_per_ac(self._reports_root)
        self.assertEqual(result, [25.0, 15.0])

    def test_multiple_prds_per_report_reversed_within_file(self) -> None:
        report = self._reports_root / "20260501-report.md"
        report.write_text(
            "## prd-1.md (first)\n"
            "### Bloat metric\n"
            "- Lines per AC: 10.0\n\n"
            "## prd-2.md (last)\n"
            "### Bloat metric\n"
            "- Lines per AC: 30.0\n"
        )
        result = sm.collect_prior_lines_per_ac(self._reports_root)
        # last PRD in file is most recent → 30.0 first
        self.assertEqual(result, [30.0, 10.0])

    def test_skips_non_matching_lines(self) -> None:
        report = self._reports_root / "20260501-report.md"
        report.write_text("Just some text\n- Other field: 42\n")
        self.assertEqual(sm.collect_prior_lines_per_ac(self._reports_root), [])


class TestFindPrdFile(unittest.TestCase):
    def setUp(self) -> None:
        self._repo_root = Path(tempfile.mkdtemp())
        self._autopilot_dir = self._repo_root / "dev" / "local" / "autopilot"
        self._autopilot_dir.mkdir(parents=True)
        self._prds_dir = self._repo_root / "dev" / "local" / "prds"
        for sub in ("wip", "done", "stalled"):
            (self._prds_dir / sub).mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self._repo_root, ignore_errors=True)

    def test_finds_in_wip(self) -> None:
        target = self._prds_dir / "wip" / "00041-foo.md"
        target.write_text("# PRD")
        result = sm.find_prd_file(self._autopilot_dir, "00041-foo.md")
        self.assertEqual(result, target)

    def test_finds_in_done(self) -> None:
        target = self._prds_dir / "done" / "00041-foo.md"
        target.write_text("# PRD")
        result = sm.find_prd_file(self._autopilot_dir, "00041-foo.md")
        self.assertEqual(result, target)

    def test_finds_in_stalled(self) -> None:
        target = self._prds_dir / "stalled" / "00041-foo.md"
        target.write_text("# PRD")
        result = sm.find_prd_file(self._autopilot_dir, "00041-foo.md")
        self.assertEqual(result, target)

    def test_returns_none_when_absent(self) -> None:
        result = sm.find_prd_file(self._autopilot_dir, "missing.md")
        self.assertIsNone(result)


class TestMainGracefulExits(unittest.TestCase):
    def test_returns_zero_when_no_autopilot_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            saved_cwd = os.getcwd()
            try:
                os.chdir(tmp)
                self.assertEqual(sm.main(), 0)
            finally:
                os.chdir(saved_cwd)

    def test_returns_zero_when_state_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            autopilot = Path(tmp) / "dev" / "local" / "autopilot"
            autopilot.mkdir(parents=True)
            saved_cwd = os.getcwd()
            try:
                os.chdir(autopilot)
                self.assertEqual(sm.main(), 0)
            finally:
                os.chdir(saved_cwd)

    def test_returns_zero_when_prd_field_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            autopilot = Path(tmp) / "dev" / "local" / "autopilot"
            autopilot.mkdir(parents=True)
            (autopilot / "state.json").write_text(json.dumps({"phase": "done"}))
            saved_cwd = os.getcwd()
            try:
                os.chdir(autopilot)
                self.assertEqual(sm.main(), 0)
            finally:
                os.chdir(saved_cwd)


if __name__ == "__main__":
    unittest.main()
