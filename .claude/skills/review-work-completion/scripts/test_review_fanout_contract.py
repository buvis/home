"""Contract test for the review-fanout workflow script.

Pins the invariants of `workflows/review-fanout.workflow.js` that the
Workflow tool and downstream consumers rely on: the `meta` export, the
findings schema's severity enum and `maxItems` cap, the two size/constant
guards, the three fail-closed `INVALID_ARGS` throws in `validateArgs`, and
the `// ---- pure region (start/end) ----` markers.

Text-pinning only: this test reads the .js file as TEXT and asserts on its
source. It does NOT execute JavaScript. Runtime semantics (dedup, demotion,
verification, rendering) are covered by the sibling behavioral test
`workflows/test_review_fanout.mjs`, which extracts the region between the
pure-region markers and runs it in node:vm -- that is exactly why the
marker test here matters: deleting or renaming a marker must fail LOUDLY
in this file rather than making the behavioral test silently extract
nothing.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

CLAUDE_DIR = Path(__file__).resolve().parents[3]
WORKFLOW_JS = CLAUDE_DIR / "workflows" / "review-fanout.workflow.js"

PURE_START = "// ---- pure region (start) ----"
PURE_END = "// ---- pure region (end) ----"


def _between(text: str, start_marker: str, end_marker: str) -> str:
    """Return the slice from `start_marker` up to (not including) `end_marker`."""
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


class ReviewFanoutContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.js = WORKFLOW_JS.read_text(encoding="utf-8")
        cls.findings_schema = _between(cls.js, "const FINDINGS_SCHEMA = {", "const RUBRIC_SCHEMA = {")
        cls.validate_args = _between(cls.js, "function validateArgs(a) {", "function securityish(text)")

    def test_meta_export_is_present(self) -> None:
        # The Workflow tool requires the meta block to register the workflow.
        self.assertRegex(self.js, r"(?m)^export const meta\b")

    def test_findings_schema_severity_enum_has_exactly_four_values(self) -> None:
        # No more, no fewer than CRITICAL/HIGH/MEDIUM/LOW -- downstream ranking
        # (SEVERITY_RANK, SEVERITY_EMOJI) is keyed to exactly these four.
        match = re.search(
            r'severity:\s*\{\s*type:\s*"string",\s*enum:\s*\[([^\]]*)\]',
            self.findings_schema,
        )
        self.assertIsNotNone(match, "could not locate the findings.severity enum in FINDINGS_SCHEMA")
        values = [v.strip().strip('"') for v in match.group(1).split(",")]
        self.assertEqual(len(values), 4, f"expected exactly 4 severities, got {values}")
        self.assertEqual(set(values), {"CRITICAL", "HIGH", "MEDIUM", "LOW"})

    def test_findings_array_has_maxitems_cap(self) -> None:
        # Bounds fan-out downstream (verify budget, table rendering).
        self.assertRegex(self.findings_schema, r"maxItems:\s*\d+")

    def test_verify_cap_and_max_diff_bytes_are_constants(self) -> None:
        self.assertRegex(self.js, r"(?m)^const MAX_DIFF_BYTES\s*=\s*\d+;")
        self.assertRegex(self.js, r"(?m)^const VERIFY_CAP\s*=\s*\d+;")

    def test_invalid_args_rejects_blank_diff(self) -> None:
        self.assertIn('a.diff.trim() === "") bad(', self.validate_args)

    def test_invalid_args_rejects_blank_rubric_text(self) -> None:
        self.assertIn('a.rubric_text.trim() === "") bad(', self.validate_args)

    def test_invalid_args_rejects_oversized_diff_without_diff_path(self) -> None:
        self.assertIn("a.diff_bytes > MAX_DIFF_BYTES && !a.diff_path) bad(", self.validate_args)

    def test_pure_region_markers_present_and_ordered(self) -> None:
        start = self.js.find(PURE_START)
        end = self.js.find(PURE_END)
        self.assertNotEqual(start, -1, "pure region start marker missing")
        self.assertNotEqual(end, -1, "pure region end marker missing")
        self.assertLess(start, end, "pure region start marker must precede end marker")
        region = self.js[start + len(PURE_START) : end]
        self.assertTrue(region.strip(), "pure region between markers must be non-empty")


if __name__ == "__main__":
    unittest.main()
