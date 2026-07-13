"""Contract test for the review-fanout workflow script.

Pins the invariants of `workflows/review-fanout.workflow.js` that the
Workflow tool and downstream consumers rely on: the `meta` export, the
findings schema's severity enum and `maxItems` cap, the two size/constant
guards, the three fail-closed `INVALID_ARGS` throws in `validateArgs`, the
`// ---- pure region (start/end) ----` markers, and -- the reason this file
carries teeth rather than trivia -- the CALL SITE that hands the engine's
shipped verdict to the pure `decideVerdict` function.

Text-pinning only: this test reads the .js file as TEXT and asserts on its
source. It does NOT execute JavaScript. Runtime semantics (dedup, demotion,
verification, rendering) are covered by the sibling behavioral test
`workflows/test_review_fanout.mjs`, which extracts the region between the
pure-region markers and runs it in node:vm -- that is exactly why the
marker test here matters: deleting or renaming a marker must fail LOUDLY
in this file rather than making the behavioral test silently extract
nothing.

That same split is the behavioral suite's blind spot, and the reason for
the verdict tests below. The .mjs harness can only reach the PURE region;
the impure region, where the engine builds the object it actually returns,
is unreachable by construction. So "a correct decideVerdict exists in the
pure region" is a claim the behavioral suite can prove, while "the engine's
verdict IS that function's result" is not: an implementation can ship a
correct, fully tested, never-called decideVerdict and hardcode
`verdict: "APPROVE"` two hundred lines below it, and all 53 behavioral
tests still pass. Only the call site binds the two together.

Source-text assertions are a weak instrument, so the verdict tests are
narrow and specific. They resolve the expression the engine returns under
its `verdict` key, require it to be a `decideVerdict(...)` call fed the
engine's live state, and forbid the verdict vocabulary from appearing in
the impure region at all -- the one place no test can observe it.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

CLAUDE_DIR = Path(__file__).resolve().parents[3]
WORKFLOW_JS = CLAUDE_DIR / "workflows" / "review-fanout.workflow.js"

PURE_START = "// ---- pure region (start) ----"
PURE_END = "// ---- pure region (end) ----"

IDENT_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
OPENERS = "([{"
CLOSERS = ")]}"

# The engine's whole verdict vocabulary. Both strings must be produced inside the
# pure region, where a test can prove WHICH state produces them.
VERDICT_LITERALS = ('"APPROVE"', '"CHANGES_REQUESTED"')

# The inline ternary this contract replaces, quoted in full so its reappearance is
# caught even if the code around it is reshuffled.
LEGACY_INLINE_TERNARY = 'verified.blocking.length > 0 || incomplete ? "CHANGES_REQUESTED" : "APPROVE"'


def _between(text: str, start_marker: str, end_marker: str) -> str:
    """Return the slice from `start_marker` up to (not including) `end_marker`."""
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def _balanced_slice(text: str, stop: str) -> str:
    """Read `text` until a char in `stop` (or an unmatched closer) at bracket depth 0.

    Just enough of a JS expression reader to lift one object-literal property value
    or one `const` right-hand side out of the source, nested calls and objects
    included. Not a parser: a stop char inside a string literal would cut the
    expression short, which fails the assertion loudly rather than passing it.
    """
    depth = 0
    out = []
    for ch in text:
        if ch in OPENERS:
            depth += 1
        elif ch in CLOSERS:
            if depth == 0:
                break
            depth -= 1
        elif ch in stop and depth == 0:
            break
        out.append(ch)
    return "".join(out).strip()


def _top_level_return_block(js: str) -> str:
    """The script's top-level `return { ... }` -- the object the Workflow tool ships."""
    match = re.search(r"(?m)^return\s*\{", js)
    return js[match.start() :] if match else ""


def _property_expression(block: str, key: str) -> str | None:
    """The expression a `key:` is set to, or the key itself when written ES6-shorthand."""
    match = re.search(rf"(?m)^\s*{re.escape(key)}\b\s*(:?)", block)
    if match is None:
        return None
    if match.group(1) != ":":
        return key  # `return { verdict, ... }` -- shorthand for the binding of that name
    return _balanced_slice(block[match.end() :], ",")


def _const_expression(js: str, name: str) -> str | None:
    """The right-hand side of a `const`/`let`/`var <name> = ...;` binding."""
    match = re.search(rf"(?m)^\s*(?:const|let|var)\s+{re.escape(name)}\s*=\s*", js)
    if match is None:
        return None
    return _balanced_slice(js[match.end() :], ";")


def _returned_verdict_expression(js: str, impure: str) -> tuple[str | None, str]:
    """Resolve the expression whose value the engine ships as its `verdict`.

    Follows one level of indirection, so `const verdict = decideVerdict(...)` +
    `return { verdict, ... }` resolves to the call, exactly like the inline
    `verdict: decideVerdict(...)` form does. Returns (expression, provenance): the
    expression is None when it cannot be located, and the provenance says why, so a
    failure names the shape it was looking for instead of dying on a None.
    """
    block = _top_level_return_block(js)
    if not block:
        return None, "the script has no top-level `return { ... }`, so it ships nothing"
    expr = _property_expression(block, "verdict")
    if expr is None:
        return None, "the returned object carries no `verdict` key"
    if IDENT_RE.match(expr):
        resolved = _const_expression(impure, expr)
        if resolved is None:
            return None, f"the returned verdict `{expr}` is bound nowhere in the impure region"
        return resolved, f"`return {{ {expr} }}` resolves to `{resolved}`"
    return expr, "the verdict is written inline in the returned object"


class ReviewFanoutContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.js = WORKFLOW_JS.read_text(encoding="utf-8")
        cls.findings_schema = _between(cls.js, "const FINDINGS_SCHEMA = {", "const RUBRIC_SCHEMA = {")
        cls.validate_args = _between(cls.js, "function validateArgs(a) {", "function securityish(text)")
        # Marker lookups are non-fatal here (`find`, not `index`): a missing marker
        # must fail its own test loudly, not error out every other test in the class.
        start = cls.js.find(PURE_START)
        end = cls.js.find(PURE_END)
        cls.pure_region = cls.js[start:end] if start != -1 and end > start else ""
        cls.impure = cls.js[end:] if end != -1 else ""

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

    def test_schema_requires_proof_on_critical_and_high(self) -> None:
        # The PRD's actual mechanism: an if/then in the SCHEMA itself rejects an
        # unproven CRITICAL/HIGH finding at the tool layer, forcing a retry.
        # demote() stays as the app-level fail-safe for anything that still slips
        # through -- this test pins the primary gate, not a replacement for it.
        if_match = re.search(
            r"if:\s*\{\s*properties:\s*\{\s*severity:\s*\{\s*enum:\s*\[([^\]]*)\]",
            self.findings_schema,
        )
        self.assertIsNotNone(
            if_match,
            "FINDINGS_SCHEMA has no if/properties/severity/enum trigger for the proof requirement",
        )
        triggers = [v.strip().strip('"') for v in if_match.group(1).split(",")]
        self.assertEqual(
            set(triggers),
            {"CRITICAL", "HIGH"},
            f"the if/then must trigger on exactly CRITICAL and HIGH, got {triggers}",
        )

        then_match = re.search(r"then:\s*\{\s*required:\s*\[([^\]]*)\]", self.findings_schema)
        self.assertIsNotNone(
            then_match,
            "FINDINGS_SCHEMA has no then/required clause following the severity if",
        )
        required = [v.strip().strip('"') for v in then_match.group(1).split(",")]
        self.assertIn(
            "proof",
            required,
            f"the then clause must require `proof`, got {required}",
        )

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

    # ---- the verdict call site: the one contract no behavioral test can reach ----

    def test_decide_verdict_is_defined_inside_the_pure_region(self) -> None:
        # The behavioral suite proves decideVerdict's LOGIC by slicing the pure
        # region into a vm. A decideVerdict defined below the end marker is a
        # different function than the one those tests exercise, and nothing would
        # bind the two. So the definition must live between the markers.
        # assertTrue, not assertRegex: a failing assertRegex dumps the entire pure
        # region into the report and buries the sentence that says what to do.
        self.assertTrue(
            re.search(
                r"(?m)^\s*(?:function\s+decideVerdict\s*\(|(?:const|let)\s+decideVerdict\s*=)",
                self.pure_region,
            ),
            "decideVerdict must be DEFINED between the pure-region markers, or the function "
            "the engine calls is not the function test_review_fanout.mjs proves correct",
        )

    def test_engine_verdict_comes_from_decide_verdict_not_an_inline_ternary(self) -> None:
        # THE exploit this file exists to close: a correct decideVerdict in the pure
        # region satisfies every behavioral test even when the engine never calls it
        # and hardcodes its own answer. The contract is not "a correct function
        # exists" -- it is "the shipped verdict is that function's return value".
        expr, provenance = _returned_verdict_expression(self.js, self.impure)
        self.assertIsNotNone(
            expr,
            f"cannot find the verdict the engine returns: {provenance}",
        )
        self.assertRegex(
            expr,
            r"^decideVerdict\s*\(",
            "the returned verdict must BE the result of a decideVerdict(...) call "
            f"({provenance}); any other expression is computed in the impure region, "
            "where no behavioral test can observe whether it fails closed",
        )
        self.assertNotIn(
            "?",
            expr,
            f"the verdict must not be decided by a ternary at the call site: {expr}",
        )
        self.assertNotIn(
            LEGACY_INLINE_TERNARY,
            expr,
            "the legacy inline verdict ternary must be GONE, not merely shadowed by a "
            "decideVerdict call somewhere else",
        )
        self.assertTrue(
            LEGACY_INLINE_TERNARY not in self.js,
            f"the legacy inline verdict ternary is still in the script: {LEGACY_INLINE_TERNARY}",
        )

    def test_no_bare_verdict_string_is_assigned_to_the_returned_verdict_key(self) -> None:
        block = _top_level_return_block(self.js)
        self.assertTrue(block, "the script must end in a top-level `return { ... }`")
        hardcoded = re.search(r"(?m)^\s*verdict\s*:\s*[\"'`].*$", block)
        self.assertIsNone(
            hardcoded,
            "the engine must never hardcode its own verdict (found: "
            f"{hardcoded.group(0).strip() if hardcoded else ''}). A constant verdict passes "
            "every behavioral test, because those tests only reach the pure region",
        )
        for literal in VERDICT_LITERALS:
            self.assertTrue(
                literal not in self.impure,
                f"the literal {literal} appears below the pure-region end marker. The verdict "
                "vocabulary may only be produced INSIDE the pure region, where a test can prove "
                "which state produces which word; in the impure region nothing can observe it",
            )

    def test_decide_verdict_is_called_with_the_engines_live_state_not_a_clean_constant(self) -> None:
        # Binding the call site is not enough on its own: `decideVerdict({blocking: [],
        # incomplete: false, unverified: 0})` calls the right function and still always
        # approves. The three gates must arrive from the engine's own computed state.
        expr, provenance = _returned_verdict_expression(self.js, self.impure)
        self.assertIsNotNone(expr, f"cannot find the verdict the engine returns: {provenance}")
        call = re.match(r"^decideVerdict\s*\((?P<args>.*)\)\s*$", expr, re.S)
        self.assertIsNotNone(
            call,
            f"the verdict must come from a decideVerdict(...) call, got: {expr}",
        )
        args = call.group("args")

        for gate in ("blocking", "incomplete", "unverified"):
            self.assertIn(
                gate,
                args,
                f"decideVerdict must be handed the engine's `{gate}` state; a call that omits a "
                f"gate cannot fail closed on it. Call site: decideVerdict({args})",
            )
        for gate, hardcoded in (
            (r"blocking", r"\[\s*\]"),
            (r"incomplete", r"(?:true|false)"),
            (r"unverified", r"\d+"),
        ):
            self.assertNotRegex(
                args,
                rf"{gate}\s*:\s*{hardcoded}",
                f"`{gate}` must be passed from the engine's computed state, never as a literal: "
                f"a constant argument makes decideVerdict correct and useless. Call site: "
                f"decideVerdict({args})",
            )


if __name__ == "__main__":
    unittest.main()
