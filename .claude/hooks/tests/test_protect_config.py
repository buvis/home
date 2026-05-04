"""Tests for hooks/protect_config.py."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "protect_config.py"


def run_hook(payload: dict | None) -> subprocess.CompletedProcess[str]:
    stdin_text = json.dumps(payload) if payload is not None else ""
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=5,
    )


class TestProtectConfig(unittest.TestCase):
    def test_blocks_eslintrc_js(self) -> None:
        r = run_hook({"tool_input": {"file_path": "/repo/.eslintrc.js"}})
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)
        self.assertIn(".eslintrc.js", r.stderr)

    def test_blocks_prettierrc(self) -> None:
        r = run_hook({"tool_input": {"file_path": "/repo/.prettierrc"}})
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)

    def test_blocks_biome_json(self) -> None:
        r = run_hook({"tool_input": {"file_path": "/repo/biome.json"}})
        self.assertEqual(r.returncode, 2)

    def test_blocks_clippy_toml(self) -> None:
        r = run_hook({"tool_input": {"file_path": "/repo/clippy.toml"}})
        self.assertEqual(r.returncode, 2)

    def test_blocks_dot_clippy_toml(self) -> None:
        r = run_hook({"tool_input": {"file_path": "/repo/sub/.clippy.toml"}})
        self.assertEqual(r.returncode, 2)

    def test_blocks_swiftlint_yaml(self) -> None:
        r = run_hook({"tool_input": {"file_path": "/repo/.swiftlint.yaml"}})
        self.assertEqual(r.returncode, 2)

    def test_blocks_eslint_config_ts(self) -> None:
        r = run_hook({"tool_input": {"file_path": "/repo/eslint.config.ts"}})
        self.assertEqual(r.returncode, 2)

    def test_allows_unrelated_python_file(self) -> None:
        r = run_hook({"tool_input": {"file_path": "/repo/src/foo.py"}})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stderr, "")

    def test_allows_eslintrc_substring_but_not_exact(self) -> None:
        r = run_hook({"tool_input": {"file_path": "/repo/eslintrc-helper.js"}})
        self.assertEqual(r.returncode, 0)

    def test_allows_when_file_path_missing(self) -> None:
        r = run_hook({"tool_input": {}})
        self.assertEqual(r.returncode, 0)

    def test_allows_when_tool_input_missing(self) -> None:
        r = run_hook({})
        self.assertEqual(r.returncode, 0)

    def test_allows_on_empty_stdin(self) -> None:
        r = run_hook(None)
        self.assertEqual(r.returncode, 0)

    def test_allows_on_invalid_json(self) -> None:
        r = subprocess.run(
            [sys.executable, str(HOOK)],
            input="not json",
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
