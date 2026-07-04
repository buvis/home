"""Contract test: Phase 8 of run-autopilot must invoke review_coverage.py with
--surface doubt and --write-aggregate, and must name the output file
<prd>-doubt-review.md.

Also validates a canonical doubt coverage block against the real parser and
asserts the rubric section exactly matches doubt-review-rubric.md.

This covers a DIFFERENT concern from test_doubt_review_prompt_contract.py,
which tests the PROMPT's emitted block shape. Here we test the CONSUMPTION
side: the gate-call contract and output filename pinned in SKILL.md.

Stdlib-only; run with: python3 .../test_phase8_doubt_review_file_contract.py
"""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_SKILLS = Path(__file__).resolve().parents[2]
_SKILL_PATH = _SKILLS / "run-autopilot" / "SKILL.md"
_RC_PATH = _SKILLS / "review-work-completion" / "scripts" / "review_coverage.py"
_RUBRIC_PATH = Path(__file__).resolve().parent.parent / "references" / "doubt-review-rubric.md"
_STATE_SCHEMA_PATH = _SKILLS / "run-autopilot" / "references" / "state-schema.md"
_BATCH_REPORT_PATH = _SKILLS / "run-autopilot" / "references" / "batch-report-format.md"

_spec = importlib.util.spec_from_file_location("review_coverage", _RC_PATH)
rc = importlib.util.module_from_spec(_spec)
# Register before exec: review_coverage.py uses `from __future__ import
# annotations`, so its @dataclass fields are stringized. Python 3.14's
# dataclasses._is_type resolves them via sys.modules[cls.__module__]; without
# this registration that lookup returns None and class creation raises
# AttributeError. (Running review_coverage.py as a script is unaffected —
# __module__ is then "__main__", which is always registered.)
sys.modules["review_coverage"] = rc
_spec.loader.exec_module(rc)

CANONICAL_BLOCK = """\
---review-coverage---
files:
  src/foo.py: reviewed
  gen/bar.py: n/a:generated file
tests:
  pending: filled by consolidation
features:
  widget rendering: reviewed
rubric:
  R1: pass
  R2: pass
  R3: pass
  R4: pass
  R5: pass
---end-review-coverage---
"""


class Phase8DoubtReviewFileContractTests(unittest.TestCase):
    def test_phase8_invokes_doubt_gate(self) -> None:
        """SKILL.md Phase 8 must call review_coverage.py with --surface doubt and --write-aggregate."""
        skill_text = _SKILL_PATH.read_text()
        self.assertIn(
            "review_coverage.py",
            skill_text,
            "SKILL.md must reference review_coverage.py in Phase 8",
        )
        self.assertIn(
            "--surface doubt",
            skill_text,
            "SKILL.md must pass --surface doubt to the gate",
        )
        self.assertIn(
            "--write-aggregate",
            skill_text,
            "SKILL.md must pass --write-aggregate to the gate",
        )

    def test_phase8_names_doubt_review_file(self) -> None:
        """SKILL.md must pin the output filename <prd>-doubt-review.md."""
        skill_text = _SKILL_PATH.read_text()
        self.assertIn(
            "<prd>-doubt-review.md",
            skill_text,
            "SKILL.md must name the doubt review output file as <prd>-doubt-review.md",
        )

    def test_canonical_doubt_block_parses_and_validates(self) -> None:
        """The canonical doubt coverage block must parse to all four sections and pass verdict validation."""
        inner = rc._extract_block_text(CANONICAL_BLOCK)
        self.assertIsNotNone(inner, "Canonical block delimiters not found")
        sections = rc._parse_block(inner)
        self.assertEqual(
            set(sections),
            {"files", "tests", "features", "rubric"},
            "Canonical block must yield exactly the four required sections",
        )
        # Must not raise:
        rc._validate_verdicts(sections)

    def test_block_rubric_ids_match_doubt_rubric(self) -> None:
        """Canonical block's rubric keys must equal the rule IDs in doubt-review-rubric.md."""
        rules = set(rc._rubric_rules(_RUBRIC_PATH))
        inner = rc._extract_block_text(CANONICAL_BLOCK)
        block_rules = set(rc._parse_block(inner)["rubric"].keys())
        self.assertEqual(
            block_rules,
            rules,
            f"Canonical block rubric keys {block_rules} must equal rubric file rules {rules}",
        )

    def test_parser_rejects_bad_files_verdict(self) -> None:
        """Parser must raise ValueError when a files verdict is not 'reviewed' or 'n/a:...'."""
        bad = CANONICAL_BLOCK.replace(
            "src/foo.py: reviewed", "src/foo.py: looked-ok"
        )
        inner = rc._extract_block_text(bad)
        self.assertIsNotNone(inner)
        sections = rc._parse_block(inner)
        with self.assertRaises(ValueError):
            rc._validate_verdicts(sections)


# ---------------------------------------------------------------------------
# PRD 00038: dual-reviewer (codex + Eve/fable) sequencing & merge contract.
# EXTENDS the file — all assertions above are unchanged.
# ---------------------------------------------------------------------------


def _phase8_section() -> str:
    """Return SKILL.md's Phase 8 section text (## Phase 8 .. ## Phase 9)."""
    text = _SKILL_PATH.read_text()
    start = text.index("## Phase 8:")
    end = text.index("## Phase 9:", start)
    return text[start:end]


# Two Eve/codex-shaped coverage blocks whose rubric verdicts differ on R3, so
# _merge_blocks's "pass wins" rule is exercised (codex pass + Eve fail -> pass).
_CODEX_BLOCK = """\
---review-coverage---
files:
  skills/run-autopilot/SKILL.md: reviewed
tests:
  pending: filled by consolidation
features:
  Doubt-Review Sequencing & Merge: reviewed
rubric:
  R1: pass
  R2: pass
  R3: pass
  R4: pass
  R5: pass
---end-review-coverage---
"""

_EVE_BLOCK = """\
---review-coverage---
files:
  skills/run-autopilot/SKILL.md: reviewed
tests:
  pending: filled by consolidation
features:
  Doubt-Review Sequencing & Merge: reviewed
rubric:
  R1: pass
  R2: pass
  R3: fail
  R4: pass
  R5: pass
---end-review-coverage---
"""

# A synthesized dual-reviewer durable <prd>-doubt-review.md: two labeled
# per-reviewer sections (bare R lines, NO raw coverage block) followed by the
# single tests-filled aggregate block. Encodes the single-coverage-block
# invariant (design §5).
_DUAL_DURABLE_FILE = """\
## codex

FIX:
- (none)
VERIFY:
- (none)
KNOWN:
- (none)
R1: pass
R2: pass
R3: pass
R4: pass
R5: pass

## fable (Eve)

FIX:
- SKILL.md Phase 8 omits the sequencing precondition
VERIFY:
- (none)
KNOWN:
- (none)
R1: pass
R2: pass
R3: fail
R4: pass
R5: pass

---review-coverage---
files:
  skills/run-autopilot/SKILL.md: reviewed
tests:
  pytest: pass=9 fail=0 skip=0
features:
  Doubt-Review Sequencing & Merge: reviewed
rubric:
  R1: pass
  R2: pass
  R3: pass
  R4: pass
  R5: pass
---end-review-coverage---
"""


# NEGATIVE fixture: a MALFORMED durable file that VIOLATES the single-coverage-
# block invariant — the codex per-reviewer section kept its OWN raw
# ---review-coverage--- block (tests: pending sentinel) instead of being
# stripped, so it precedes the tests-filled aggregate. This is the exact failure
# the invariant guards against: _extract_block_text returns the FIRST block, so
# the done-phase Stop-hook re-parse sees the pending sentinel and fires
# EMPTY_TESTS, stalling the loop drain. (Contrast _DUAL_DURABLE_FILE, which
# strips the per-reviewer blocks and holds exactly one aggregate.)
_LEAKED_DURABLE_FILE = """\
## codex

FIX:
- (none)
VERIFY:
- (none)
KNOWN:
- (none)
R1: pass
R2: pass
R3: pass
R4: pass
R5: pass

---review-coverage---
files:
  skills/run-autopilot/SKILL.md: reviewed
tests:
  pending: filled by consolidation
features:
  Doubt-Review Sequencing & Merge: reviewed
rubric:
  R1: pass
  R2: pass
  R3: pass
  R4: pass
  R5: pass
---end-review-coverage---

## fable (Eve)

FIX:
- (none)
VERIFY:
- (none)
KNOWN:
- (none)
R1: pass
R2: pass
R3: fail
R4: pass
R5: pass

---review-coverage---
files:
  skills/run-autopilot/SKILL.md: reviewed
tests:
  pytest: pass=9 fail=0 skip=0
features:
  Doubt-Review Sequencing & Merge: reviewed
rubric:
  R1: pass
  R2: pass
  R3: pass
  R4: pass
  R5: pass
---end-review-coverage---
"""


class Phase8EveDualReviewerContractTests(unittest.TestCase):
    # --- SKILL.md Phase 8 wording (the model-executed procedure contract) ---

    def test_phase8_documents_eve_sequential_gate(self) -> None:
        """Phase 8 documents the doubt_reviewer==fable sequential Eve gate."""
        s = _phase8_section()
        self.assertIn('state.doubt_reviewer == "fable"', s)
        self.assertIn("never runs in parallel with codex", s)
        self.assertIn(".doubt-eve-block.md", s)
        self.assertIn("source", s)

    def test_phase8_sequencing_keys_on_first_reviewer_completed(self) -> None:
        """Sequencing keys on 'first reviewer COMPLETED', not file-exists / 'codex ran'."""
        s = _phase8_section()
        self.assertIn("the first reviewer has COMPLETED", s)

    def test_phase8_documents_eve_failure_degradation(self) -> None:
        """A failed Eve degrades to the single-reviewer path with a warning, no PAUSE."""
        s = _phase8_section()
        self.assertIn(
            "── AUTOPILOT ── Eve (fable) doubt reviewer failed; "
            "proceeding with codex/fallback alone ──",
            s,
        )
        self.assertIn("single-reviewer", s)

    def test_phase8_documents_per_reviewer_rubric_verdicts(self) -> None:
        """doubts_rubric_verdicts carries one entry per rule per reviewer (10 dual)."""
        s = _phase8_section()
        self.assertIn("one entry per rule per reviewer", s)
        self.assertIn("10 entries", s)

    def test_phase8_documents_single_coverage_block_invariant(self) -> None:
        """The durable file must hold EXACTLY ONE aggregate coverage block."""
        s = _phase8_section()
        self.assertIn("EXACTLY ONE", s)
        self.assertIn("---review-coverage---", s)

    def test_phase8_no_flag_path_stays_byte_identical(self) -> None:
        """The no-flag path still uses a single --reviewer-block and is byte-identical."""
        s = _phase8_section()
        self.assertIn("--reviewer-block", s)
        self.assertIn("byte-identical", s)

    # --- merge machinery (reuses review_coverage.py; NO new gate code) ---

    def test_dual_reviewer_merge_yields_four_sections_pass_wins(self) -> None:
        """Merging codex + Eve blocks yields the four sections; rubric pass wins."""
        codex = rc._parse_block(rc._extract_block_text(_CODEX_BLOCK))
        eve = rc._parse_block(rc._extract_block_text(_EVE_BLOCK))
        merged = rc._merge_blocks([codex, eve])
        self.assertEqual(set(merged), {"files", "tests", "features", "rubric"})
        # codex R3 pass + Eve R3 fail -> pass wins
        self.assertEqual(merged["rubric"]["R3"], "pass")
        rc._validate_verdicts(merged)

    def test_dual_durable_file_has_exactly_one_coverage_block(self) -> None:
        """The dual durable file holds exactly one ---review-coverage--- pair."""
        self.assertEqual(_DUAL_DURABLE_FILE.count(rc.OPEN_DELIM), 1)
        self.assertEqual(_DUAL_DURABLE_FILE.count(rc.CLOSE_DELIM), 1)

    def test_dual_durable_file_extracts_tests_filled_aggregate(self) -> None:
        """_extract_block_text on the dual durable file returns the tests-filled aggregate."""
        inner = rc._extract_block_text(_DUAL_DURABLE_FILE)
        self.assertIsNotNone(inner)
        sections = rc._parse_block(inner)
        # The extracted block is the aggregate: real pytest counts, NOT the
        # 'pending' sentinel a per-reviewer raw block would carry.
        self.assertIn("pytest", sections["tests"])
        self.assertNotIn("pending", sections["tests"])

    def test_leaked_per_reviewer_block_fires_empty_tests_guard(self) -> None:
        """NEGATIVE: a leaked per-reviewer raw block (tests: pending) placed
        before the aggregate is what _extract_block_text returns first, and that
        pending-first block makes _check_empty_tests fire EMPTY_TESTS — proving
        the single-coverage-block invariant guards a real loop-drain failure."""
        # Invariant violated: the durable file holds TWO coverage blocks, not one.
        self.assertEqual(_LEAKED_DURABLE_FILE.count(rc.OPEN_DELIM), 2)
        self.assertEqual(_LEAKED_DURABLE_FILE.count(rc.CLOSE_DELIM), 2)
        # _extract_block_text returns the FIRST (leaked) block: unfilled
        # 'pending' sentinel, no real pytest counts — unlike _DUAL_DURABLE_FILE.
        sections = rc._parse_block(rc._extract_block_text(_LEAKED_DURABLE_FILE))
        self.assertIn("pending", sections["tests"])
        self.assertNotIn("pytest", sections["tests"])
        # The done-phase re-parse over that pending-first block hard-fails
        # EMPTY_TESTS (SystemExit via _fail), which is what stalls the drain.
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(SystemExit):
                rc._check_empty_tests(
                    sections, ["skills/run-autopilot/SKILL.md"], Path(td)
                )

    # --- cross-file contract: the source tag is documented in the schema and
    #     batch-report references, not only in SKILL.md prose ---

    def test_state_schema_documents_source_tag_on_doubts_and_verdicts(self) -> None:
        """state-schema.md documents the optional codex|fable source tag on both
        doubts[] and doubts_rubric_verdicts[], with the dual per-rule-per-reviewer
        cardinality — so enum drift there fails a test, not just SKILL.md drift."""
        text = _STATE_SCHEMA_PATH.read_text()
        self.assertIn("doubts_rubric_verdicts", text)
        self.assertIn('"source?"', text)
        # both enum members and the codex-slot semantics (codex OR fallback)
        self.assertIn('"codex"', text)
        self.assertIn('"fable"', text)
        self.assertIn("codex slot", text)
        # dual-run cardinality: one verdict entry per rule per reviewer
        self.assertIn("one entry per rule per reviewer", text)

    def test_batch_report_documents_source_tagged_verdict_rendering(self) -> None:
        """batch-report-format.md documents the PRD 00038 source-tagged rubric
        rendering (combined row per rule, per-reviewer fail surfaced) — binding
        the render contract to that file, not only SKILL.md Phase 9 prose."""
        text = _BATCH_REPORT_PATH.read_text()
        self.assertIn("Source-tagged rendering", text)
        # the combined-row format with a surfaced per-reviewer fail (R3)
        self.assertIn("pass (codex) / fail (fable)", text)


if __name__ == "__main__":
    unittest.main()
