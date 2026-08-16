"""Contract for compute_mech_facts.py (PRD 00095).

The point of the script is that a number in the block is RIGHT, so these
tests check counts against hand-countable fixtures rather than checking that
the block merely renders.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import compute_mech_facts as mf

SCRIPT = Path(__file__).with_name("compute_mech_facts.py")

MODULE = """\
def top(a):
    b = a + 1
    return b


class Handler:
    def handle(self, request):
        if request is None:
            return None
        return request.body

    async def close(self):
        return True


def outer():
    def inner():
        return 1

    return inner


@staticmethod
@some_decorator("x")
def decorated(a, b):
    return a + b
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_line_counts_match_the_hand_counted_fixture(tmp_path: Path) -> None:
    status, rows = mf.facts_for_file(_write(tmp_path, "mod.py", MODULE))
    assert status == "ok"
    assert {name: (start, length) for name, start, length in rows} == {
        "top": (1, 3),
        "Handler.handle": (7, 4),
        "Handler.close": (12, 2),
        "outer": (16, 5),
        "outer.inner": (17, 2),
        # The two decorators sit on lines 23-24; the reported start is the
        # `def` on 25 and the length excludes them. The module's own comment
        # claims this; the fixture is what makes the claim checkable.
        "decorated": (25, 2),
    }


def test_a_non_python_file_is_skipped_not_parsed(tmp_path: Path) -> None:
    status, rows = mf.facts_for_file(_write(tmp_path, "notes.md", "# not python"))
    assert status == "skipped (non-python)"
    assert rows == []


def test_an_unparseable_python_file_is_skipped_rather_than_raising(
    tmp_path: Path,
) -> None:
    status, rows = mf.facts_for_file(_write(tmp_path, "broken.py", "def (:\n"))
    assert status == "skipped (parse error)"
    assert rows == []


def test_a_missing_file_is_skipped_rather_than_raising(tmp_path: Path) -> None:
    status, _ = mf.facts_for_file(tmp_path / "never-written.py")
    assert status == "skipped (parse error)"


def test_a_python_file_with_no_functions_says_so(tmp_path: Path) -> None:
    block = mf.render_facts_block([_write(tmp_path, "consts.py", "X = 1\n")])
    assert "no functions" in block


def test_the_cli_prints_the_block_and_exits_zero_even_with_bad_input(
    tmp_path: Path,
) -> None:
    good = _write(tmp_path, "mod.py", MODULE)
    broken = _write(tmp_path, "broken.py", "def (:\n")
    other = _write(tmp_path, "notes.md", "# not python")
    result = _run(str(good), str(broken), str(other))
    assert result.returncode == 0
    assert "## Mechanical facts (computed, do not re-count)" in result.stdout
    assert "`Handler.handle` — line 7, 4 lines" in result.stdout
    assert "skipped (parse error)" in result.stdout
    assert "skipped (non-python)" in result.stdout
