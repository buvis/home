#!/usr/bin/env python3
"""Tests for schema.validate's handling of legacy `batch.completed_prds` entries.

A sibling of `cli/test_schema.py` rather than more of it: that file sits at 737
lines against this project's 800-line ceiling. `cli/test_schema_task_entries.py`
is the same split for the `tasks[]` rules, and this file follows its shape —
self-contained, importing only `cli.schema`, building each state inline.

Scope: the bare-string tolerance decision. A legacy bare-string element stays
valid (it is what archived batch states hold, and `render_report.batch_summary`,
`cli/status.py` and `scripts/tracon/model.py` all read the list with a bare
`len()`), but it must not validate in total silence.
"""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cli import schema


def _well_formed_entry() -> dict:
    return {
        "filename": "00001-x.md",
        "cycles": 2,
        "autonomous_decisions": 3,
        "escalated_decisions": 1,
        "tasks_completed": 4,
        "tasks_total": 4,
    }


def _capture_validate_warning(state: dict) -> tuple[str, str]:
    """Return (warning text, stdout text) from one `schema.validate` call.

    stdout is captured so the tests can assert it stayed empty: `mutate()`
    validates on every write, and statectl plus several autopilot subcommands
    emit machine-read output there, so a notice on stdout would corrupt a
    caller's parse.
    """
    stdout_buf = io.StringIO()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with contextlib.redirect_stdout(stdout_buf):
            schema.validate(state)
    return "\n".join(str(w.message) for w in caught), stdout_buf.getvalue()


class ValidateBatchCompletedPrdsBareStringWarningTest(unittest.TestCase):
    """A bare-string `completed_prds` entry stays tolerated (see
    test_schema.py's test_bare_string_entry_passes_legacy_tolerance, unmodified)
    but must no longer validate in total silence: a warning must reach the
    operator, off stdout, naming the field path and the offending value."""

    def test_bare_string_entry_warns_naming_the_field_path(self) -> None:
        state = {"batch": {"completed_prds": ["00001-x.md"]}}
        notice, _stdout = _capture_validate_warning(state)
        self.assertIn("batch.completed_prds[0]", notice)

    def test_bare_string_entry_warns_naming_the_offending_value(self) -> None:
        state = {"batch": {"completed_prds": ["00001-x.md"]}}
        notice, _stdout = _capture_validate_warning(state)
        self.assertIn("00001-x.md", notice)

    def test_bare_string_on_second_element_warns_naming_index_one(self) -> None:
        # The index must come from the loop, not a hardcoded 0 - mirrors
        # test_schema.py's test_bad_field_on_second_element_names_index_one.
        state = {"batch": {"completed_prds": [_well_formed_entry(), "00002-y.md"]}}
        notice, _stdout = _capture_validate_warning(state)
        self.assertIn("batch.completed_prds[1]", notice)
        self.assertIn("00002-y.md", notice)

    def test_well_formed_dict_entries_emit_no_warning(self) -> None:
        state = {"batch": {"completed_prds": [_well_formed_entry()]}}
        notice, _stdout = _capture_validate_warning(state)
        self.assertEqual(notice.strip(), "")

    def test_warning_never_goes_to_stdout(self) -> None:
        # statectl and several autopilot subcommands emit machine-read JSON on
        # stdout, and validate() runs on every write - a notice there would
        # corrupt a caller's parse.
        for entries in (["00001-x.md"], [_well_formed_entry()]):
            with self.subTest(entries=entries):
                state = {"batch": {"completed_prds": entries}}
                _notice, stdout_text = _capture_validate_warning(state)
                self.assertEqual(stdout_text, "")


if __name__ == "__main__":
    unittest.main()
