"""Behavioural contract for check_style_limits.py (PRD 00140).

The script reports only the coding-style limit violations a diff itself
introduces: functions over 50 lines whose line span a diff's new-side hunk
range touches, and files the diff pushed over 800 lines. Pre-existing debt
(an untouched over-limit function, a file already over 800 before the
diff) is deliberately not reported here - that is scope for the review
lens, not this regression check.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).with_name("check_style_limits.py")
_SPEC = importlib.util.spec_from_file_location("check_style_limits", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
csl = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(csl)


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_MODULE_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _long_function(name: str, n_lines: int) -> str:
    """A `def name():` line followed by (n_lines - 1) body lines, so the
    function's total line count is exactly n_lines."""
    body = "\n".join("    x = 1" for _ in range(n_lines - 1))
    return f"def {name}():\n{body}\n"


def _write_over_limit_diff(tmp_path: Path) -> tuple[Path, str]:
    """A 2-line stub expanded by the diff into a 51-line function - the
    whole function is on the diff's new side, so it is fully "touched"."""
    func_text = _long_function("over_limit", 51)
    py_file = _write(tmp_path, "mod.py", func_text)
    diff_text = (
        "diff --git a/mod.py b/mod.py\n"
        "--- a/mod.py\n"
        "+++ b/mod.py\n"
        "@@ -1,2 +1,51 @@\n"
        "-def over_limit():\n"
        "-    pass\n" + "".join(f"+{line}\n" for line in func_text.splitlines())
    )
    return py_file, diff_text


def _write_clean_diff(tmp_path: Path) -> tuple[Path, str]:
    py_file = _write(tmp_path, "mod.py", "def small():\n    return 1\n")
    diff_text = (
        "diff --git a/mod.py b/mod.py\n"
        "--- a/mod.py\n"
        "+++ b/mod.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-def small():\n"
        "-    return 0\n"
        "+def small():\n"
        "+    return 1\n"
    )
    return py_file, diff_text


# --- touched_ranges ---------------------------------------------------------


def test_touched_ranges_strips_the_b_prefix_from_the_diff_path() -> None:
    diff_text = (
        "diff --git a/pkg/mod.py b/pkg/mod.py\n"
        "--- a/pkg/mod.py\n"
        "+++ b/pkg/mod.py\n"
        "@@ -10,3 +10,5 @@ def something():\n"
        " context line\n"
        "+added line\n"
        "+added line\n"
        " context line\n"
        " context line\n"
    )
    ranges = csl.touched_ranges(diff_text)
    assert list(ranges.keys()) == ["pkg/mod.py"]
    assert ranges["pkg/mod.py"] == [(10, 14)]


def test_touched_ranges_header_without_a_count_is_a_single_line() -> None:
    diff_text = (
        "diff --git a/mod.py b/mod.py\n"
        "--- a/mod.py\n"
        "+++ b/mod.py\n"
        "@@ -1,1 +1 @@\n"
        "-old line\n"
        "+new line\n"
    )
    assert csl.touched_ranges(diff_text)["mod.py"] == [(1, 1)]


def test_touched_ranges_pure_deletion_hunk_contributes_no_range() -> None:
    diff_text = (
        "diff --git a/mod.py b/mod.py\n"
        "--- a/mod.py\n"
        "+++ b/mod.py\n"
        "@@ -10,2 +9,0 @@\n"
        "-removed line one\n"
        "-removed line two\n"
    )
    # Key presence for a file whose only hunk is a pure deletion isn't
    # pinned by the contract - only that it contributes no range. `.get`
    # keeps this assertion agnostic to that unstated detail.
    assert csl.touched_ranges(diff_text).get("mod.py", []) == []


# --- function violations -----------------------------------------------------


def test_touched_function_over_fifty_lines_is_reported(tmp_path: Path) -> None:
    py_file, diff_text = _write_over_limit_diff(tmp_path)
    assert csl.violations(diff_text, [py_file]) == [
        f"FUNCTION | {py_file}:1 | over_limit | 51 lines"
    ]


def test_untouched_function_over_fifty_lines_in_same_file_is_not_reported(
    tmp_path: Path,
) -> None:
    edited = ["def edited():", "    x = 1", "    x = 2"]
    gap = [""] * 12
    text = "\n".join(edited + gap) + "\n" + _long_function("never_touched", 51)
    py_file = _write(tmp_path, "mod.py", text)
    diff_text = (
        "diff --git a/mod.py b/mod.py\n"
        "--- a/mod.py\n"
        "+++ b/mod.py\n"
        "@@ -1,3 +1,3 @@\n"
        "-def edited():\n"
        "-    x = 1\n"
        "-    x = 0\n"
        "+def edited():\n"
        "+    x = 1\n"
        "+    x = 2\n"
    )
    assert csl.violations(diff_text, [py_file]) == []


def test_all_deletions_diff_never_reports_a_function_line(tmp_path: Path) -> None:
    py_file = _write(tmp_path, "mod.py", _long_function("survivor", 51))
    diff_text = (
        "diff --git a/mod.py b/mod.py\n"
        "--- a/mod.py\n"
        "+++ b/mod.py\n"
        "@@ -1,5 +1,0 @@\n"
        "-def old_helper():\n"
        "-    x = 1\n"
        "-    x = 2\n"
        "-    x = 3\n"
        "-    x = 4\n"
    )
    assert csl.violations(diff_text, [py_file]) == []


# --- file violations ----------------------------------------------------------


def test_file_crossing_eight_hundred_lines_is_reported(tmp_path: Path) -> None:
    text = "x = 1\n" * 810
    py_file = _write(tmp_path, "mod.py", text)
    added = "".join("+x = 1\n" for _ in range(15))
    diff_text = (
        "diff --git a/mod.py b/mod.py\n"
        "--- a/mod.py\n"
        "+++ b/mod.py\n"
        "@@ -0,0 +1,15 @@\n" + added
    )
    assert csl.violations(diff_text, [py_file]) == [f"FILE | {py_file} | 810 lines"]


def test_file_already_over_eight_hundred_lines_before_the_diff_is_not_reported(
    tmp_path: Path,
) -> None:
    text = "x = 1\n" * 810
    py_file = _write(tmp_path, "mod.py", text)
    diff_text = (
        "diff --git a/mod.py b/mod.py\n"
        "--- a/mod.py\n"
        "+++ b/mod.py\n"
        "@@ -5,2 +5,2 @@\n"
        "-x = 1\n"
        "-x = 1\n"
        "+x = 2\n"
        "+x = 2\n"
    )
    assert csl.violations(diff_text, [py_file]) == []


# --- multi-file diffs / unparseable files --------------------------------------


def test_deleted_file_hunks_do_not_count_against_the_previous_file(
    tmp_path: Path,
) -> None:
    py_file = _write(tmp_path, "mod.py", "x = 1\n" * 805)
    added = "".join("+x = 2\n" for _ in range(10))
    removed = "".join("-old line\n" for _ in range(20))
    diff_text = (
        "diff --git a/mod.py b/mod.py\n"
        "--- a/mod.py\n"
        "+++ b/mod.py\n"
        "@@ -1,0 +1,10 @@\n" + added + "diff --git a/gone.py b/gone.py\n"
        "--- a/gone.py\n"
        "+++ /dev/null\n"
        "@@ -1,20 +0,0 @@\n" + removed
    )
    assert csl.violations(diff_text, [py_file]) == [f"FILE | {py_file} | 805 lines"]


def test_unparseable_file_still_reports_a_file_crossing(tmp_path: Path) -> None:
    text = "def broken(:\n" + "x = 1\n" * 804
    py_file = _write(tmp_path, "broken.py", text)
    added = "".join("+x = 1\n" for _ in range(10))
    diff_text = (
        "diff --git a/broken.py b/broken.py\n"
        "--- a/broken.py\n"
        "+++ b/broken.py\n"
        "@@ -0,0 +1,10 @@\n" + added
    )
    assert csl.violations(diff_text, [py_file]) == [f"FILE | {py_file} | 805 lines"]


# --- non-Python skip -----------------------------------------------------------


def test_non_python_changed_file_is_skipped_silently(tmp_path: Path) -> None:
    md_file = _write(tmp_path, "notes.md", "# notes\n" + "line\n" * 900)
    diff_text = (
        "diff --git a/notes.md b/notes.md\n"
        "--- a/notes.md\n"
        "+++ b/notes.md\n"
        "@@ -0,0 +1,900 @@\n" + "".join("+line\n" for _ in range(900))
    )
    assert csl.violations(diff_text, [md_file]) == []


# --- main / CLI ------------------------------------------------------------


def test_clean_diff_via_main_exits_zero_with_empty_output(tmp_path: Path, capsys) -> None:
    py_file, diff_text = _write_clean_diff(tmp_path)
    diff_file = _write(tmp_path, "changes.diff", diff_text)
    exit_code = csl.main(["--diff", str(diff_file), str(py_file)])
    assert exit_code == 0
    assert capsys.readouterr().out == ""


def test_violating_diff_via_main_exits_one_and_prints_the_lines(
    tmp_path: Path, capsys
) -> None:
    py_file, diff_text = _write_over_limit_diff(tmp_path)
    diff_file = _write(tmp_path, "changes.diff", diff_text)
    exit_code = csl.main(["--diff", str(diff_file), str(py_file)])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert out == f"FUNCTION | {py_file}:1 | over_limit | 51 lines\n"


def test_cli_subprocess_exits_one_and_prints_violation_lines(tmp_path: Path) -> None:
    py_file, diff_text = _write_over_limit_diff(tmp_path)
    diff_file = _write(tmp_path, "changes.diff", diff_text)
    result = _run("--diff", str(diff_file), str(py_file))
    assert result.returncode == 1
    assert result.stdout == f"FUNCTION | {py_file}:1 | over_limit | 51 lines\n"


def test_cli_subprocess_exits_zero_and_prints_nothing_for_a_clean_diff(
    tmp_path: Path,
) -> None:
    py_file, diff_text = _write_clean_diff(tmp_path)
    diff_file = _write(tmp_path, "changes.diff", diff_text)
    result = _run("--diff", str(diff_file), str(py_file))
    assert result.returncode == 0
    assert result.stdout == ""
