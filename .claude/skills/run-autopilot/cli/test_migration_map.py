#!/usr/bin/env python3
"""Tests for the park/stall migration manifest + map.

migration_manifest.txt is the independent list of behavior IDs that must be
covered (one per line; blank lines and `#` comments ignored).

migration_map.md is a GitHub-flavored markdown pipe table mapping each
behavior ID to a disposition (ported | retired | stays_prose |
behavior_change) and a test_id.

These tests bind the two files together: every manifest ID must appear in
the map exactly once, every map row must be well-formed, every disposition
must be legal, every test_id must have the shape its disposition demands,
and every cited source file must exist on disk.
"""

from __future__ import annotations

import ast
import re
import unittest
from collections import Counter
from pathlib import Path

CLI = Path(__file__).resolve().parent
SKILL_ROOT = CLI.parent

MANIFEST_PATH = CLI / "migration_manifest.txt"
MAP_PATH = CLI / "migration_map.md"
# test_id refs resolve against real test files here, cli/ first then scripts/
# (both hold test_*.py files in this skill).
TEST_ROOTS = (CLI, SKILL_ROOT / "scripts")

COLUMNS = ("behavior_id", "source", "disposition", "test_id")
LEGAL_DISPOSITIONS = frozenset({"ported", "retired", "stays_prose", "behavior_change"})
# every disposition except `retired` must name a real test (retired's test_id
# is free text: the reason it was dropped).
TEST_ID_REQUIRED_DISPOSITIONS = frozenset({"ported", "behavior_change", "stays_prose"})

_SOURCE_PATH_SPLIT_RE = re.compile(r"[\s#(]")


# --- parsing helpers (exercised directly by unit tests, and reused by the
# contract tests against the real files) -----------------------------------


def parse_manifest_lines(text: str) -> list[str]:
    """Return the behavior IDs in a manifest file, in order.

    Blank lines (whitespace-only) and lines whose stripped form starts with
    `#` are comments and are dropped.
    """
    ids = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        ids.append(stripped)
    return ids


def parse_pipe_table(text: str) -> list[list[str]]:
    """Parse a GitHub-flavored markdown pipe table into its data rows.

    Only lines starting with `|` are considered table lines. The first table
    line is the header, the second is the `|---|` delimiter row; both are
    skipped. Each remaining table line becomes a list of stripped cells.
    Rows are returned exactly as found -- a row with the wrong number of
    cells (e.g. a missing column) is NOT padded or rejected here; callers
    validate cell count separately.
    """
    table_lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("|")]
    if len(table_lines) < 2:
        return []
    data_lines = table_lines[2:]
    rows = []
    for line in data_lines:
        cells = line.strip("|").split("|")
        rows.append([c.strip() for c in cells])
    return rows


def find_duplicates(items: list[str]) -> list[str]:
    """Return the items that occur more than once, sorted, each listed once."""
    counts = Counter(items)
    return sorted(item for item, n in counts.items() if n > 1)


def source_file_path(source_cell: str) -> str:
    """Extract the leading file-path token from a `source` cell.

    Assumes the cell is a file path optionally followed by a section
    reference introduced by whitespace, `#`, or `(` (e.g.
    "references/x.md#Heading", "references/x.md (Section)",
    "references/x.md Section name").
    """
    first_chunk = _SOURCE_PATH_SPLIT_RE.split(source_cell.strip(), maxsplit=1)[0]
    return first_chunk.rstrip(",:;")


# --- pure validators (each returns the offending rows/ids; empty = pass) --


def manifest_map_id_diff(
    manifest_ids: list[str], map_ids: list[str]
) -> tuple[list[str], list[str]]:
    """Return (ids missing from the map, ids in the map but not the manifest)."""
    manifest_set = set(manifest_ids)
    map_set = set(map_ids)
    return sorted(manifest_set - map_set), sorted(map_set - manifest_set)


def rows_with_wrong_column_count(rows: list[list[str]]) -> list[tuple[int, list[str]]]:
    return [(i, r) for i, r in enumerate(rows) if len(r) != len(COLUMNS)]


def rows_with_empty_cells(rows: list[list[str]]) -> list[tuple[int, str, str]]:
    """Rows (of the right column count) with a blank cell: (index, behavior_id, column_name)."""
    out = []
    for i, r in enumerate(rows):
        if len(r) != len(COLUMNS):
            continue
        for name, value in zip(COLUMNS, r):
            if not value.strip():
                out.append((i, r[0], name))
    return out


def rows_with_illegal_disposition(rows: list[list[str]]) -> list[tuple[int, str, str]]:
    out = []
    for i, r in enumerate(rows):
        if len(r) != len(COLUMNS):
            continue
        _behavior_id, _source, disposition, _test_id = r
        if disposition not in LEGAL_DISPOSITIONS:
            out.append((i, r[0], disposition))
    return out


def rows_with_missing_source(
    rows: list[list[str]], root: Path
) -> list[tuple[int, str, str, Path]]:
    """Rows whose source file does not exist under `root`: (index, behavior_id, cell, resolved_path)."""
    out = []
    for i, r in enumerate(rows):
        if len(r) != len(COLUMNS):
            continue
        behavior_id, source, _disposition, _test_id = r
        resolved = root / source_file_path(source)
        if not resolved.exists():
            out.append((i, behavior_id, source, resolved))
    return out


def parse_test_id_refs(test_id: str) -> list[str]:
    """Split a test_id cell into its individual test references.

    A cell may hold multiple comma-separated refs (e.g. one behavior proven
    by tests in two different files); each ref is stripped independently.
    """
    return [ref.strip() for ref in test_id.split(",") if ref.strip()]


def _defined_names(tree: ast.Module) -> tuple[set[tuple[str, ...]], set[tuple[str, ...]]]:
    """Every class/function/method defined anywhere in `tree`, as name-path
    tuples: a top-level (or nested) function as `(name,)`, a class as
    `(ClassName,)`, and a method as `(ClassName, method_name)`.

    Returns `(all_names, test_names)`, where `test_names` keeps only the
    test-shaped subset: a function/method whose leaf name is `test_`-
    prefixed, and a class name only when the class has at least one such
    method (so a bare class reference resolves).
    """
    all_names: set[tuple[str, ...]] = set()
    test_names: set[tuple[str, ...]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            all_names.add((node.name,))
            has_test_method = False
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    all_names.add((node.name, child.name))
                    if child.name.startswith("test_"):
                        test_names.add((node.name, child.name))
                        has_test_method = True
            if has_test_method:
                test_names.add((node.name,))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            all_names.add((node.name,))
            if node.name.startswith("test_"):
                test_names.add((node.name,))
    return all_names, test_names


def resolve_test_ref(ref: str, roots: tuple[Path, ...]) -> str | None:
    """Resolve one `<file>.py::<name>` or `<file>.py::<Class>::<name>` test
    reference against real files under `roots` (checked in order, e.g. cli/
    then scripts/; every root's copy of the file is tried before giving up).

    A function/method ref only resolves when its leaf name is `test_`-
    prefixed; a bare `file::ClassName` ref only resolves when the class has
    at least one `test_`-prefixed method.

    Returns None when the ref resolves against some root (found via `ast`,
    not by importing or collecting via pytest); otherwise a human-readable
    reason it does not.
    """
    parts = ref.split("::")
    filename, names = parts[0], tuple(parts[1:])
    if not filename.endswith(".py") or not names:
        return f"malformed test reference: {ref!r}"
    found_file = False
    reason: str | None = None
    for root in roots:
        path = root / filename
        if not path.exists():
            continue
        found_file = True
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as err:
            reason = f"{path}: could not parse as Python: {err}"
            continue
        all_names, test_names = _defined_names(tree)
        if names in test_names:
            return None
        if names in all_names:
            reason = f"{path}: {'::'.join(names)} is not a test (missing test_ prefix)"
        else:
            reason = f"{path}: no class/function/method named {'::'.join(names)}"
    if not found_file:
        return f"test file not found in any root {[str(r) for r in roots]}: {filename}"
    return reason


def rows_with_unresolved_test_id(
    rows: list[list[str]], roots: tuple[Path, ...]
) -> list[tuple[int, str, str, str]]:
    """Rows whose disposition requires a real test but whose test_id contains
    a ref that does not resolve to one: (index, behavior_id, bad_ref, reason).

    Every ref in a comma-separated test_id cell is resolved independently.
    """
    out = []
    for i, r in enumerate(rows):
        if len(r) != len(COLUMNS):
            continue
        behavior_id, _source, disposition, test_id = r
        if disposition not in TEST_ID_REQUIRED_DISPOSITIONS:
            continue
        for ref in parse_test_id_refs(test_id):
            reason = resolve_test_ref(ref, roots)
            if reason is not None:
                out.append((i, behavior_id, ref, reason))
    return out


# --- unit tests for the helpers, using synthetic input only ---------------


class ParseManifestLinesTest(unittest.TestCase):
    def test_returns_empty_list_for_empty_text(self) -> None:
        self.assertEqual(parse_manifest_lines(""), [])

    def test_skips_blank_lines(self) -> None:
        text = "BID-1\n\n   \nBID-2\n"
        self.assertEqual(parse_manifest_lines(text), ["BID-1", "BID-2"])

    def test_skips_comment_lines(self) -> None:
        text = "# heading\nBID-1\n  # indented comment\nBID-2\n"
        self.assertEqual(parse_manifest_lines(text), ["BID-1", "BID-2"])

    def test_returns_empty_list_when_only_comments(self) -> None:
        text = "# nothing here\n# still nothing\n"
        self.assertEqual(parse_manifest_lines(text), [])

    def test_strips_surrounding_whitespace_from_ids(self) -> None:
        self.assertEqual(parse_manifest_lines("  BID-1  \n"), ["BID-1"])


class ParsePipeTableTest(unittest.TestCase):
    def test_returns_empty_list_for_empty_text(self) -> None:
        self.assertEqual(parse_pipe_table(""), [])

    def test_returns_empty_list_for_header_only_table(self) -> None:
        text = "| behavior_id | source | disposition | test_id |\n| --- | --- | --- | --- |\n"
        self.assertEqual(parse_pipe_table(text), [])

    def test_skips_header_and_separator_rows(self) -> None:
        text = (
            "| behavior_id | source | disposition | test_id |\n"
            "| --- | --- | --- | --- |\n"
            "| BID-1 | foo.md | ported | test_x.py::test_thing |\n"
        )
        self.assertEqual(
            parse_pipe_table(text), [["BID-1", "foo.md", "ported", "test_x.py::test_thing"]]
        )

    def test_tolerates_surrounding_whitespace_in_cells(self) -> None:
        text = (
            "| behavior_id | source | disposition | test_id |\n"
            "| --- | --- | --- | --- |\n"
            "|   BID-1   |  foo.md  |  ported  |  test_x.py::test_thing  |\n"
        )
        self.assertEqual(
            parse_pipe_table(text), [["BID-1", "foo.md", "ported", "test_x.py::test_thing"]]
        )

    def test_preserves_row_with_missing_column_instead_of_crashing(self) -> None:
        text = (
            "| behavior_id | source | disposition | test_id |\n"
            "| --- | --- | --- | --- |\n"
            "| BID-2 | bar.md | retired |\n"
        )
        rows = parse_pipe_table(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]), 3, f"expected a 3-cell malformed row, got {rows[0]!r}")

    def test_ignores_non_table_lines_around_the_table(self) -> None:
        text = (
            "Some prose before the table.\n"
            "| behavior_id | source | disposition | test_id |\n"
            "| --- | --- | --- | --- |\n"
            "| BID-1 | foo.md | ported | test_x.py::test_thing |\n"
            "Some prose after.\n"
        )
        self.assertEqual(
            parse_pipe_table(text), [["BID-1", "foo.md", "ported", "test_x.py::test_thing"]]
        )


class FindDuplicatesTest(unittest.TestCase):
    def test_returns_empty_list_when_no_repeats(self) -> None:
        self.assertEqual(find_duplicates(["BID-1", "BID-2"]), [])

    def test_reports_repeated_items_once_each_sorted(self) -> None:
        self.assertEqual(
            find_duplicates(["BID-2", "BID-1", "BID-2", "BID-1", "BID-1"]), ["BID-1", "BID-2"]
        )


class SourceFilePathTest(unittest.TestCase):
    def test_returns_whole_cell_when_no_section_marker(self) -> None:
        self.assertEqual(source_file_path("prompts/de-sloppify.md"), "prompts/de-sloppify.md")

    def test_strips_hash_anchor_section(self) -> None:
        self.assertEqual(
            source_file_path("references/phase-build.md#Phase 0 frontmatter"),
            "references/phase-build.md",
        )

    def test_strips_parenthesized_section(self) -> None:
        self.assertEqual(source_file_path("SKILL.md (Step 3: Catchup)"), "SKILL.md")

    def test_strips_trailing_comma_after_bare_path(self) -> None:
        self.assertEqual(
            source_file_path("references/recovery.md, Recovery section"),
            "references/recovery.md",
        )


class RowValidatorsTest(unittest.TestCase):
    """Unit tests for the pure row validators, against synthetic rows only."""

    def test_manifest_map_id_diff_reports_missing_and_extra_separately(self) -> None:
        missing, extra = manifest_map_id_diff(
            ["BID-1", "BID-2", "BID-3"], ["BID-1", "BID-2", "BID-4"]
        )
        self.assertEqual(missing, ["BID-3"])
        self.assertEqual(extra, ["BID-4"])

    def test_manifest_map_id_diff_empty_when_sets_match(self) -> None:
        missing, extra = manifest_map_id_diff(["BID-1", "BID-2"], ["BID-2", "BID-1"])
        self.assertEqual((missing, extra), ([], []))

    def test_rows_with_wrong_column_count_flags_short_row(self) -> None:
        rows = [
            ["BID-1", "foo.md", "ported", "test_x.py::test_a"],
            ["BID-2", "bar.md", "retired"],
        ]
        offenders = rows_with_wrong_column_count(rows)
        self.assertEqual([i for i, _r in offenders], [1])

    def test_rows_with_empty_cells_flags_blank_column(self) -> None:
        rows = [["BID-1", "foo.md", "", "test_x.py::test_a"]]
        offenders = rows_with_empty_cells(rows)
        self.assertEqual(offenders, [(0, "BID-1", "disposition")])

    def test_rows_with_empty_cells_ignores_wrong_length_rows(self) -> None:
        # a short row is a different failure (column count); it must not
        # also be double-reported as an empty cell.
        rows = [["BID-1", "foo.md", "retired"]]
        self.assertEqual(rows_with_empty_cells(rows), [])

    def test_rows_with_illegal_disposition_flags_unknown_value(self) -> None:
        rows = [["BID-1", "foo.md", "deleted", "some reason"]]
        offenders = rows_with_illegal_disposition(rows)
        self.assertEqual(offenders, [(0, "BID-1", "deleted")])

    def test_rows_with_illegal_disposition_accepts_all_four_legal_values(self) -> None:
        rows = [
            ["BID-1", "foo.md", "ported", "test_x.py::test_a"],
            ["BID-2", "foo.md", "retired", "superseded by BID-1"],
            ["BID-3", "foo.md", "stays_prose", "test_x.py::test_b"],
            ["BID-4", "foo.md", "behavior_change", "test_x.py::test_c"],
        ]
        self.assertEqual(rows_with_illegal_disposition(rows), [])

    def test_rows_with_missing_source_flags_nonexistent_path(self) -> None:
        rows = [["BID-1", "references/does-not-exist.md#Section", "retired", "gone"]]
        offenders = rows_with_missing_source(rows, SKILL_ROOT)
        self.assertEqual(len(offenders), 1)
        self.assertEqual(offenders[0][:3], (0, "BID-1", "references/does-not-exist.md#Section"))

    def test_rows_with_missing_source_accepts_existing_path(self) -> None:
        rows = [["BID-1", "SKILL.md (Step 3)", "retired", "gone"]]
        self.assertEqual(rows_with_missing_source(rows, SKILL_ROOT), [])


class ParseTestIdRefsTest(unittest.TestCase):
    def test_splits_multiple_comma_separated_refs(self) -> None:
        self.assertEqual(
            parse_test_id_refs("test_a.py::test_x, test_b.py::test_y"),
            ["test_a.py::test_x", "test_b.py::test_y"],
        )

    def test_single_ref_returns_one_element_list(self) -> None:
        self.assertEqual(parse_test_id_refs("test_a.py::test_x"), ["test_a.py::test_x"])


class ResolveTestRefTest(unittest.TestCase):
    """Unit tests for resolve_test_ref, resolved against this very file (a
    real, stable fixture: it always exists under CLI)."""

    def test_resolves_existing_method_via_file_class_name(self) -> None:
        self.assertIsNone(
            resolve_test_ref(
                "test_migration_map.py::ParseManifestLinesTest::test_skips_blank_lines",
                TEST_ROOTS,
            )
        )

    def test_resolves_bare_class_reference_with_no_method(self) -> None:
        self.assertIsNone(
            resolve_test_ref("test_migration_map.py::ParseManifestLinesTest", TEST_ROOTS)
        )

    def test_reports_missing_file(self) -> None:
        reason = resolve_test_ref("test_does_not_exist_anywhere.py::test_x", TEST_ROOTS)
        self.assertIsNotNone(reason)
        self.assertIn("not found", reason)

    def test_reports_missing_name_in_existing_file(self) -> None:
        reason = resolve_test_ref(
            "test_migration_map.py::test_this_name_is_not_defined_anywhere", TEST_ROOTS
        )
        self.assertIsNotNone(reason)
        self.assertIn("no class/function/method named", reason)

    def test_reports_malformed_ref_without_double_colon(self) -> None:
        reason = resolve_test_ref("test_migration_map.py", TEST_ROOTS)
        self.assertIsNotNone(reason)
        self.assertIn("malformed", reason)


class RowsWithUnresolvedTestIdTest(unittest.TestCase):
    def test_flags_row_whose_test_id_does_not_resolve(self) -> None:
        rows = [
            ["BID-1", "foo.md", "ported", "test_migration_map.py::test_does_not_exist_here"]
        ]
        offenders = rows_with_unresolved_test_id(rows, TEST_ROOTS)
        self.assertEqual(len(offenders), 1)
        self.assertEqual(offenders[0][:2], (0, "BID-1"))

    def test_accepts_row_whose_test_id_resolves(self) -> None:
        rows = [
            [
                "BID-1",
                "foo.md",
                "ported",
                "test_migration_map.py::ParseManifestLinesTest::test_skips_blank_lines",
            ]
        ]
        self.assertEqual(rows_with_unresolved_test_id(rows, TEST_ROOTS), [])

    def test_resolves_each_comma_separated_ref_independently(self) -> None:
        rows = [
            [
                "BID-1",
                "foo.md",
                "ported",
                "test_migration_map.py::ParseManifestLinesTest::test_skips_blank_lines, "
                "test_migration_map.py::test_missing_entirely",
            ]
        ]
        offenders = rows_with_unresolved_test_id(rows, TEST_ROOTS)
        self.assertEqual(len(offenders), 1)
        self.assertIn("test_missing_entirely", offenders[0][2])

    def test_skips_rows_whose_disposition_does_not_require_a_test(self) -> None:
        rows = [["BID-1", "foo.md", "retired", "not a real test reference at all"]]
        self.assertEqual(rows_with_unresolved_test_id(rows, TEST_ROOTS), [])


# --- contract tests against the real manifest + map files -----------------


class MigrationMapContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(MANIFEST_PATH.exists(), f"missing fixture: {MANIFEST_PATH}")
        self.assertTrue(MAP_PATH.exists(), f"missing fixture: {MAP_PATH}")
        self.manifest_ids = parse_manifest_lines(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.map_rows = parse_pipe_table(MAP_PATH.read_text(encoding="utf-8"))
        self.map_ids = [r[0] for r in self.map_rows if r]

    def test_manifest_and_map_cover_the_same_behavior_ids(self) -> None:
        missing_from_map, extra_in_map = manifest_map_id_diff(self.manifest_ids, self.map_ids)
        self.assertFalse(
            missing_from_map or extra_in_map,
            "manifest and map disagree on behavior IDs: "
            f"missing from map={missing_from_map}, extra in map (not in manifest)={extra_in_map}",
        )

    def test_manifest_has_no_duplicate_ids(self) -> None:
        dupes = find_duplicates(self.manifest_ids)
        self.assertFalse(dupes, f"duplicate behavior IDs in {MANIFEST_PATH.name}: {dupes}")

    def test_map_has_no_duplicate_behavior_ids(self) -> None:
        dupes = find_duplicates(self.map_ids)
        self.assertFalse(dupes, f"duplicate behavior_id rows in {MAP_PATH.name}: {dupes}")

    def test_every_row_has_exactly_four_columns(self) -> None:
        offenders = rows_with_wrong_column_count(self.map_rows)
        self.assertFalse(
            offenders,
            "map rows with the wrong number of columns (expected "
            f"{len(COLUMNS)}: {COLUMNS}): {offenders}",
        )

    def test_every_row_has_no_empty_columns(self) -> None:
        offenders = rows_with_empty_cells(self.map_rows)
        self.assertFalse(
            offenders,
            "map rows with an empty column (row_index, behavior_id, column): "
            f"{offenders}",
        )

    def test_every_row_disposition_is_legal(self) -> None:
        offenders = rows_with_illegal_disposition(self.map_rows)
        self.assertFalse(
            offenders,
            "map rows with an illegal disposition (row_index, behavior_id, disposition); "
            f"legal values are {sorted(LEGAL_DISPOSITIONS)}: {offenders}",
        )

    def test_ported_behavior_change_and_stays_prose_rows_name_a_real_test(self) -> None:
        offenders = rows_with_unresolved_test_id(self.map_rows, TEST_ROOTS)
        self.assertFalse(
            offenders,
            "map rows whose disposition requires a real test reference but whose "
            "test_id does not resolve to an actual class/function/method under "
            f"{[str(r) for r in TEST_ROOTS]} (row_index, behavior_id, bad_ref, reason): "
            f"{offenders}",
        )

    def test_every_source_path_exists_on_disk(self) -> None:
        offenders = rows_with_missing_source(self.map_rows, SKILL_ROOT)
        self.assertFalse(
            offenders,
            "map rows citing a source file that does not exist under "
            f"{SKILL_ROOT} (row_index, behavior_id, source_cell, resolved_path): {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
