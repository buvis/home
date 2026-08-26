"""Binds HARNESS_CONTRACT.md to the live hooks/_common.py.

The contract is only worth reading if it stays true, so the module - not the
document, and not a hardcoded list - is the source of truth for what must be
documented.
"""

import ast
import importlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_common = importlib.import_module("_common")

COMMON = Path(_common.__file__)
CONTRACT = Path(__file__).parent / "HARNESS_CONTRACT.md"


def _public_names(source: str) -> list[str]:
    """Top-level names defined in `source` that don't start with `_`.

    Parsed rather than introspected so imported names (`Path`, `json`) never
    count as public API of the module.
    """
    names: list[str] = []
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            names.extend(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
    return sorted(n for n in names if not n.startswith("_"))


class TestContractCompleteness(unittest.TestCase):
    def test_every_public_helper_is_documented(self) -> None:
        contract = CONTRACT.read_text(encoding="utf-8")
        headings = {
            line.removeprefix("### `").split("(")[0].split("`")[0]
            for line in contract.splitlines()
            if line.startswith("### `")
        }
        missing = [
            n
            for n in _public_names(COMMON.read_text(encoding="utf-8"))
            if n not in headings
        ]
        self.assertEqual(
            missing,
            [],
            f"undocumented public names in _common.py: {missing}. "
            f"Add a '### `<name>`' entry to {CONTRACT.name}.",
        )


class TestDocumentedBehavior(unittest.TestCase):
    """One test per load-bearing claim the contract makes."""

    def test_capture_main_replaces_stdin(self) -> None:
        seen = {}

        def handler() -> None:
            seen["payload"] = _common.read_input()

        with patch("sys.stdin", io.StringIO('{"tool_name": "ignored"}')):
            code, out, err = _common.capture_main(handler, {"tool_name": "Edit"})
            # capture_main won, and it handed the streams back.
            self.assertEqual(sys.stdin.read(), '{"tool_name": "ignored"}')
        self.assertEqual(seen["payload"], {"tool_name": "Edit"})
        self.assertEqual((code, out, err), (0, "", ""))

    def test_read_input_returns_empty_dict_on_malformed_input(self) -> None:
        for raw in ("", "   \n", "not json {", '["array"]'):
            with self.subTest(raw=raw), patch("sys.stdin", io.StringIO(raw)):
                self.assertEqual(_common.read_input(), {})

    def test_block_exits_two_with_reason_on_stderr(self) -> None:
        with patch("sys.stderr", io.StringIO()) as err:
            with self.assertRaises(SystemExit) as ctx:
                _common.block("because")
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("because", err.getvalue())


if __name__ == "__main__":
    unittest.main()
