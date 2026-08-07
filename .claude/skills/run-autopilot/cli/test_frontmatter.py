#!/usr/bin/env python3
"""Tests for cli/frontmatter.py - the Phase-0 PRD frontmatter parse.

The three dispositions are the contract, so each gets its own assertions:
an invalid value falls back AND warns, an absent field falls back SILENTLY,
and a malformed or missing block takes every default with exactly ONE warning.
The golden fixture is parsed here too, so the fixture and the parser fail
together if either drifts.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from cli import frontmatter

GOLDEN = Path(__file__).resolve().parent.parent / "scripts" / "golden"


def _block(*lines: str) -> str:
    return "---\n" + "\n".join(lines) + "\n---\n\n# A PRD\n"


class DefaultsTests(unittest.TestCase):
    def test_bare_block_takes_every_default_silently(self) -> None:
        fields, warnings = frontmatter.parse(_block("title: nothing recognized"))
        self.assertEqual(warnings, [], "an unset field is the normal case")
        self.assertEqual(
            fields,
            {
                "catchup_mode": "run",
                "design_mode": "run",
                "doubt_reviewer": "codex",
                "consensus_engine": "legacy",
                "rework_cap": 2,
            },
        )

    def test_optional_markers_stay_absent_rather_than_false(self) -> None:
        # Written as null/False they would survive into state.json and read as
        # "declared off" instead of "not declared".
        fields, _warnings = frontmatter.parse(_block("catchup: skip"))
        self.assertNotIn("design_gate", fields)
        self.assertNotIn("pause_on_ambiguity", fields)


class RecognizedValueTests(unittest.TestCase):
    def test_every_enum_field_parses_its_allowed_values(self) -> None:
        for line, key, value in [
            ("catchup: skip", "catchup_mode", "skip"),
            ("catchup: force", "catchup_mode", "force"),
            ("design: skip", "design_mode", "skip"),
            ("doubt_reviewer: fable", "doubt_reviewer", "fable"),
            ("consensus_engine: workflow", "consensus_engine", "workflow"),
            ("consensus_engine: shadow", "consensus_engine", "shadow"),
        ]:
            with self.subTest(line=line):
                fields, warnings = frontmatter.parse(_block(line))
                self.assertEqual(fields[key], value)
                self.assertEqual(warnings, [])

    def test_rework_cap_parses_as_an_int_not_a_string(self) -> None:
        fields, warnings = frontmatter.parse(_block("rework_cap: 5"))
        self.assertEqual(fields["rework_cap"], 5)
        self.assertIsInstance(fields["rework_cap"], int)
        self.assertEqual(warnings, [])

    def test_design_gate_recognized_only_at_its_exact_value(self) -> None:
        fields, warnings = frontmatter.parse(_block("design_gate: user"))
        self.assertEqual(fields["design_gate"], "user")
        self.assertEqual(warnings, [])

        other, no_warnings = frontmatter.parse(_block("design_gate: auto"))
        self.assertNotIn("design_gate", other)
        self.assertEqual(no_warnings, [], "an unrecognized opt-in is not a warning")

    def test_pause_on_ambiguity_recognized_only_at_true(self) -> None:
        fields, _w = frontmatter.parse(_block("pause_on_ambiguity: true"))
        self.assertIs(fields["pause_on_ambiguity"], True)
        for value in ("false", "True", "yes"):
            with self.subTest(value=value):
                other, _ = frontmatter.parse(_block(f"pause_on_ambiguity: {value}"))
                self.assertNotIn("pause_on_ambiguity", other)

    def test_unknown_keys_are_ignored_without_warning(self) -> None:
        # default_model belongs to /plan-tasks and is re-read at Phase 6;
        # Phase 0 must not claim it.
        fields, warnings = frontmatter.parse(
            _block("prd: 00118", "title: A: colonated title", "default_model: opus"),
        )
        self.assertEqual(warnings, [])
        self.assertNotIn("default_model", fields)
        self.assertEqual(fields["catchup_mode"], "run")


class InvalidValueTests(unittest.TestCase):
    def test_each_invalid_enum_falls_back_and_warns_naming_the_field(self) -> None:
        for line, key, default in [
            ("catchup: sometimes", "catchup_mode", "run"),
            ("design: maybe", "design_mode", "run"),
            ("doubt_reviewer: gemini", "doubt_reviewer", "codex"),
            ("consensus_engine: turbo", "consensus_engine", "legacy"),
        ]:
            with self.subTest(line=line):
                fields, warnings = frontmatter.parse(_block(line))
                self.assertEqual(fields[key], default)
                self.assertEqual(len(warnings), 1)
                self.assertIn(line.split(":")[0], warnings[0])

    def test_non_positive_or_unparseable_rework_cap_falls_back_and_warns(self) -> None:
        for raw in ("0", "-3", "abc", "2.5", ""):
            with self.subTest(raw=raw):
                fields, warnings = frontmatter.parse(_block(f"rework_cap: {raw}"))
                self.assertEqual(fields["rework_cap"], 2)
                self.assertEqual(len(warnings), 1)
                self.assertIn("rework_cap", warnings[0])

    def test_every_field_invalid_takes_every_default_and_does_not_crash(self) -> None:
        fields, warnings = frontmatter.parse(
            _block(
                "catchup: nope",
                "rework_cap: nope",
                "design: nope",
                "doubt_reviewer: nope",
                "consensus_engine: nope",
            ),
        )
        self.assertEqual(fields, frontmatter.defaults())
        self.assertEqual(len(warnings), 5, "one warning per invalid field")


class MalformedBlockTests(unittest.TestCase):
    def test_missing_frontmatter_takes_defaults_with_one_warning(self) -> None:
        fields, warnings = frontmatter.parse("# A PRD\n\nNo frontmatter here.\n")
        self.assertEqual(fields, frontmatter.defaults())
        self.assertEqual(warnings, [frontmatter.MALFORMED_WARNING])

    def test_unterminated_block_is_malformed(self) -> None:
        fields, warnings = frontmatter.parse("---\ncatchup: skip\n\n# A PRD\n")
        self.assertEqual(fields, frontmatter.defaults())
        self.assertEqual(warnings, [frontmatter.MALFORMED_WARNING])
        self.assertEqual(
            fields["catchup_mode"],
            "run",
            "a value inside an unterminated block must not be half-applied",
        )

    def test_block_closing_past_the_head_bound_is_malformed(self) -> None:
        # Only the first 20 lines are read, so a `---` rule deep in the body
        # can never be mistaken for the closing delimiter.
        text = "---\n" + "\n".join(f"pad{i}: x" for i in range(25)) + "\n---\n"
        _fields, warnings = frontmatter.parse(text)
        self.assertEqual(warnings, [frontmatter.MALFORMED_WARNING])

    def test_empty_text_is_malformed_rather_than_a_crash(self) -> None:
        fields, warnings = frontmatter.parse("")
        self.assertEqual(fields, frontmatter.defaults())
        self.assertEqual(warnings, [frontmatter.MALFORMED_WARNING])

    def test_malformed_warning_names_every_default_it_applied(self) -> None:
        for token in (
            "catchup_mode=run",
            "rework_cap=2",
            "design_mode=run",
            "doubt_reviewer=codex",
            "consensus_engine=legacy",
        ):
            self.assertIn(token, frontmatter.MALFORMED_WARNING)


class GoldenFixtureTests(unittest.TestCase):
    def test_golden_prd_frontmatter_parses_clean(self) -> None:
        text = (GOLDEN / "prd-frontmatter.md").read_text(encoding="utf-8")
        fields, warnings = frontmatter.parse(text)
        self.assertEqual(warnings, [], "the known-good fixture must not warn")
        self.assertEqual(
            fields,
            {
                "catchup_mode": "run",
                "design_mode": "run",
                "doubt_reviewer": "codex",
                "consensus_engine": "legacy",
                "rework_cap": 3,
                "design_gate": "user",
                "pause_on_ambiguity": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
