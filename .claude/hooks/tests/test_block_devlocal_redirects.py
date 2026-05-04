"""Tests for hooks/block_devlocal_redirects.py."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "block_devlocal_redirects.py"


def run_hook(cmd: str | None) -> subprocess.CompletedProcess[str]:
    if cmd is None:
        payload = ""
    else:
        payload = json.dumps({"tool_input": {"command": cmd}})
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=5,
    )


class TestBlocks(unittest.TestCase):
    def test_blocks_single_gt_redirect(self) -> None:
        r = run_hook("echo foo > dev/local/x.md")
        self.assertEqual(r.returncode, 2)
        self.assertIn("shell redirect", r.stderr)

    def test_blocks_double_gt_redirect(self) -> None:
        r = run_hook("echo foo >> dev/local/x.md")
        self.assertEqual(r.returncode, 2)
        self.assertIn("shell redirect", r.stderr)

    def test_blocks_amp_gt_redirect(self) -> None:
        r = run_hook("echo foo &> dev/local/x.md")
        self.assertEqual(r.returncode, 2)

    def test_blocks_redirect_with_spaces(self) -> None:
        r = run_hook("cat README.md   >   dev/local/foo.md")
        self.assertEqual(r.returncode, 2)

    def test_blocks_tee_to_devlocal(self) -> None:
        r = run_hook("echo foo | tee dev/local/x.md")
        self.assertEqual(r.returncode, 2)
        self.assertIn("tee", r.stderr)

    def test_blocks_tee_a_flag(self) -> None:
        r = run_hook("echo foo | tee -a dev/local/x.md")
        self.assertEqual(r.returncode, 2)

    def test_blocks_redirect_into_nested_devlocal(self) -> None:
        r = run_hook("echo foo > dev/local/prds/wip/note.md")
        self.assertEqual(r.returncode, 2)


class TestAllows(unittest.TestCase):
    def test_allows_redirect_to_tmp(self) -> None:
        r = run_hook("echo foo > /tmp/x.md")
        self.assertEqual(r.returncode, 0)

    def test_allows_read_of_devlocal(self) -> None:
        r = run_hook("cat dev/local/foo.md")
        self.assertEqual(r.returncode, 0)

    def test_allows_grep_in_devlocal(self) -> None:
        r = run_hook("grep -r foo dev/local/")
        self.assertEqual(r.returncode, 0)

    def test_allows_empty_command(self) -> None:
        r = run_hook("")
        self.assertEqual(r.returncode, 0)

    def test_allows_missing_command_field(self) -> None:
        r = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps({"tool_input": {}}),
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(r.returncode, 0)

    def test_allows_empty_stdin(self) -> None:
        r = run_hook(None)
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
