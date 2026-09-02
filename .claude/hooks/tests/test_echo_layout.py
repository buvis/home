"""Layout pin for the cartographer-echo family (PRD 00158).

Every file in the family stays at most 800 lines and every function at most
50, measured with `ast` over the family globs, so the split cannot silently
regrow into the 1126-line hook it replaced. The glob-count test guards the
guard: an empty match would otherwise pass vacuously.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
MAX_FILE_LINES = 800
MAX_FUNCTION_LINES = 50

PRODUCT_FILES = sorted([HOOKS / "cartographer-echo.py", *HOOKS.glob("_echo_*.py")])
TEST_FILES = sorted(
    [
        HOOKS / "tests" / "test_cartographer_echo.py",
        *(HOOKS / "tests").glob("test_echo_*.py"),
    ],
)
FAMILY = PRODUCT_FILES + TEST_FILES


def _long_functions(path: Path, limit: int) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        (node.name, node.end_lineno - node.lineno + 1)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.end_lineno - node.lineno + 1 > limit
    ]


def test_family_globs_match_the_split() -> None:
    assert len(PRODUCT_FILES) >= 5, [p.name for p in PRODUCT_FILES]
    assert len(TEST_FILES) >= 5, [p.name for p in TEST_FILES]


@pytest.mark.parametrize("path", FAMILY, ids=lambda p: p.name)
def test_family_file_within_line_limit(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").count("\n")
    assert lines <= MAX_FILE_LINES, f"{path.name}: {lines} lines"


@pytest.mark.parametrize("path", FAMILY, ids=lambda p: p.name)
def test_family_functions_within_line_limit(path: Path) -> None:
    assert _long_functions(path, MAX_FUNCTION_LINES) == []
