"""Tests for hooks/enforce_prd_location.py — both file mode and bash mode."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "enforce_prd_location.py"


def run_hook(payload: dict | None) -> subprocess.CompletedProcess[str]:
    stdin_text = json.dumps(payload) if payload is not None else ""
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=10,
    )


def make_repo(parent: str) -> str:
    repo = tempfile.mkdtemp(prefix="prdloc-", dir=parent)
    subprocess.run(
        ["git", "init", "-q", "-b", "main", repo],
        check=True,
        capture_output=True,
    )
    return repo


class TestFileMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.mkdtemp(prefix="prdloc-parent-")
        cls.repo = make_repo(cls._tmp)

    def test_blocks_write_to_repo_root_backlog(self) -> None:
        target = os.path.join(self.repo, "backlog", "foo.md")
        r = run_hook({"tool_name": "Write", "tool_input": {"file_path": target}})
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)
        self.assertIn("backlog/foo.md", r.stderr)

    def test_blocks_edit_to_repo_root_wip(self) -> None:
        target = os.path.join(self.repo, "wip", "bar.md")
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": target}})
        self.assertEqual(r.returncode, 2)

    def test_blocks_edit_to_repo_root_done(self) -> None:
        target = os.path.join(self.repo, "done", "baz.md")
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": target}})
        self.assertEqual(r.returncode, 2)

    def test_allows_write_under_devlocal_prds_wip(self) -> None:
        target = os.path.join(self.repo, "dev", "local", "prds", "wip", "x.md")
        r = run_hook({"tool_name": "Write", "tool_input": {"file_path": target}})
        self.assertEqual(r.returncode, 0)

    def test_allows_when_no_git_repo(self) -> None:
        target = os.path.join(self._tmp, "nonrepo", "backlog", "x.md")
        r = run_hook({"tool_name": "Write", "tool_input": {"file_path": target}})
        self.assertEqual(r.returncode, 0)

    def test_allows_when_lifecycle_substring_not_at_root(self) -> None:
        target = os.path.join(self.repo, "src", "wip-helper.py")
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": target}})
        self.assertEqual(r.returncode, 0)

    def test_allows_empty_file_path(self) -> None:
        r = run_hook({"tool_name": "Edit", "tool_input": {}})
        self.assertEqual(r.returncode, 0)

    def test_blocks_multiedit_when_any_edit_violates(self) -> None:
        ok = os.path.join(self.repo, "src", "x.py")
        bad = os.path.join(self.repo, "wip", "y.md")
        r = run_hook({
            "tool_name": "MultiEdit",
            "tool_input": {"edits": [{"file_path": ok}, {"file_path": bad}]},
        })
        self.assertEqual(r.returncode, 2)

    def test_allows_multiedit_when_all_clean(self) -> None:
        a = os.path.join(self.repo, "src", "a.py")
        b = os.path.join(self.repo, "src", "b.py")
        r = run_hook({
            "tool_name": "MultiEdit",
            "tool_input": {"edits": [{"file_path": a}, {"file_path": b}]},
        })
        self.assertEqual(r.returncode, 0)


class TestRelativePaths(unittest.TestCase):
    """Bash original used `dirname`-walk-to-`.` for relative paths. The Python
    port must do the same via `os.path.abspath` up-front."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.mkdtemp(prefix="prdloc-rel-")
        cls.repo = make_repo(cls._tmp)

    def _run_in_repo(self, payload: dict) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=self.repo,
        )

    def test_blocks_relative_path_to_repo_root_backlog(self) -> None:
        r = self._run_in_repo({"tool_name": "Write", "tool_input": {"file_path": "backlog/new.md"}})
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)

    def test_allows_relative_path_under_devlocal_prds(self) -> None:
        r = self._run_in_repo({
            "tool_name": "Write",
            "tool_input": {"file_path": "dev/local/prds/wip/x.md"},
        })
        self.assertEqual(r.returncode, 0)


class TestBashMode(unittest.TestCase):
    def test_blocks_mkdir_backlog(self) -> None:
        r = run_hook({"tool_name": "Bash", "tool_input": {"command": "mkdir backlog/foo"}})
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)
        self.assertIn("backlog/", r.stderr)

    def test_blocks_mv_into_wip(self) -> None:
        r = run_hook({"tool_name": "Bash", "tool_input": {"command": "mv old wip/new"}})
        self.assertEqual(r.returncode, 2)

    def test_blocks_target_done_after_eq(self) -> None:
        r = run_hook({"tool_name": "Bash", "tool_input": {"command": "rsync --target=./done/x src/"}})
        self.assertEqual(r.returncode, 2)

    def test_allows_mv_within_devlocal_prds(self) -> None:
        r = run_hook({"tool_name": "Bash", "tool_input": {"command": "mv x dev/local/prds/wip/y"}})
        self.assertEqual(r.returncode, 0)

    def test_allows_unrelated_command(self) -> None:
        r = run_hook({"tool_name": "Bash", "tool_input": {"command": "cat README.md"}})
        self.assertEqual(r.returncode, 0)

    def test_allows_empty_command(self) -> None:
        r = run_hook({"tool_name": "Bash", "tool_input": {"command": ""}})
        self.assertEqual(r.returncode, 0)


class TestUnknownTool(unittest.TestCase):
    def test_allows_other_tool(self) -> None:
        r = run_hook({"tool_name": "Read", "tool_input": {"file_path": "/anything/wip/x"}})
        self.assertEqual(r.returncode, 0)

    def test_allows_no_tool_name(self) -> None:
        r = run_hook({})
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
