"""Tests for hooks/enforce_prd_location.py — both file mode and bash mode."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _common

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

    def test_blocks_symlink_through_devlocal_prds_to_root_backlog(self) -> None:
        backlog_dir = os.path.join(self.repo, "backlog")
        os.makedirs(backlog_dir, exist_ok=True)
        prds_dir = os.path.join(self.repo, "dev", "local", "prds")
        os.makedirs(prds_dir, exist_ok=True)
        sneak = os.path.join(prds_dir, "sneak")
        if not os.path.islink(sneak):
            os.symlink(backlog_dir, sneak)
        target = os.path.join(sneak, "00002-y.md")
        r = run_hook({"tool_name": "Write", "tool_input": {"file_path": target}})
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)
        self.assertIn("backlog/00002-y.md", r.stderr)

    def test_blocks_substring_dev_local_prds_nested_in_root_backlog(self) -> None:
        target = os.path.join(
            self.repo,
            "backlog",
            "dev",
            "local",
            "prds",
            "00003-z.md",
        )
        r = run_hook({"tool_name": "Write", "tool_input": {"file_path": target}})
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)
        self.assertIn("backlog/dev/local/prds/00003-z.md", r.stderr)

    def test_allows_write_under_devlocal_prds_backlog(self) -> None:
        target = os.path.join(self.repo, "dev", "local", "prds", "backlog", "x.md")
        r = run_hook({"tool_name": "Write", "tool_input": {"file_path": target}})
        self.assertEqual(r.returncode, 0)

    def test_allows_empty_file_path(self) -> None:
        r = run_hook({"tool_name": "Edit", "tool_input": {}})
        self.assertEqual(r.returncode, 0)

    def test_blocks_multiedit_when_any_edit_violates(self) -> None:
        ok = os.path.join(self.repo, "src", "x.py")
        bad = os.path.join(self.repo, "wip", "y.md")
        r = run_hook(
            {
                "tool_name": "MultiEdit",
                "tool_input": {"edits": [{"file_path": ok}, {"file_path": bad}]},
            },
        )
        self.assertEqual(r.returncode, 2)

    def test_allows_multiedit_when_all_clean(self) -> None:
        a = os.path.join(self.repo, "src", "a.py")
        b = os.path.join(self.repo, "src", "b.py")
        r = run_hook(
            {
                "tool_name": "MultiEdit",
                "tool_input": {"edits": [{"file_path": a}, {"file_path": b}]},
            },
        )
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
        r = self._run_in_repo(
            {"tool_name": "Write", "tool_input": {"file_path": "backlog/new.md"}},
        )
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)

    def test_allows_relative_path_under_devlocal_prds(self) -> None:
        r = self._run_in_repo(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "dev/local/prds/wip/x.md"},
            },
        )
        self.assertEqual(r.returncode, 0)


class TestBashMode(unittest.TestCase):
    def test_blocks_mkdir_backlog(self) -> None:
        r = run_hook(
            {"tool_name": "Bash", "tool_input": {"command": "mkdir backlog/foo"}},
        )
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)
        self.assertIn("backlog/", r.stderr)

    def test_blocks_mv_into_wip(self) -> None:
        r = run_hook({"tool_name": "Bash", "tool_input": {"command": "mv old wip/new"}})
        self.assertEqual(r.returncode, 2)

    def test_blocks_target_done_after_eq(self) -> None:
        r = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "rsync --target=./done/x src/"},
            },
        )
        self.assertEqual(r.returncode, 2)

    def test_blocks_bash_doublequoted_backlog_path(self) -> None:
        r = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'mv "backlog/00005.md" /tmp/'},
            },
        )
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)
        self.assertIn("backlog/", r.stderr)

    def test_blocks_var_assignment_then_quoted_var_mv(self) -> None:
        r = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'SRC=backlog/00005.md; mv "$SRC" /tmp/'},
            },
        )
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)

    def test_blocks_rsync_log_file_eq_backlog(self) -> None:
        r = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "rsync --log-file=backlog/out.log src dst"},
            },
        )
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)

    def test_allows_mv_within_devlocal_prds(self) -> None:
        r = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "mv x dev/local/prds/wip/y"},
            },
        )
        self.assertEqual(r.returncode, 0)

    def test_allows_unrelated_command(self) -> None:
        r = run_hook({"tool_name": "Bash", "tool_input": {"command": "cat README.md"}})
        self.assertEqual(r.returncode, 0)

    def test_allows_empty_command(self) -> None:
        r = run_hook({"tool_name": "Bash", "tool_input": {"command": ""}})
        self.assertEqual(r.returncode, 0)

    def test_blocks_bare_backlog_token_no_slash_no_child(self) -> None:
        r = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "mv backlog /tmp/exfil"},
            },
        )
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)

    def test_blocks_bare_wip_token_no_slash_no_child(self) -> None:
        r = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "mv wip /tmp/exfil"},
            },
        )
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)

    def test_allows_bare_done_shell_keyword_closing_for_loop(self) -> None:
        r = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "for f in *.md; do echo $f; done"},
            },
        )
        self.assertEqual(r.returncode, 0)

    def test_blocks_bare_backlog_token_with_trailing_slash(self) -> None:
        r = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "mv backlog/ /tmp/exfil"},
            },
        )
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)

    def test_blocks_rm_rf_bare_wip_token(self) -> None:
        r = run_hook({"tool_name": "Bash", "tool_input": {"command": "rm -rf wip"}})
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)

    def test_blocks_mkdir_bare_backlog_token(self) -> None:
        r = run_hook({"tool_name": "Bash", "tool_input": {"command": "mkdir backlog"}})
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)

    def test_allows_git_commit_message_wip(self) -> None:
        r = run_hook(
            {"tool_name": "Bash", "tool_input": {"command": "git commit -m wip"}},
        )
        self.assertEqual(r.returncode, 0)

    def test_allows_git_commit_message_backlog(self) -> None:
        r = run_hook(
            {"tool_name": "Bash", "tool_input": {"command": "git commit -m backlog"}},
        )
        self.assertEqual(r.returncode, 0)

    def test_allows_git_checkout_wip_branch(self) -> None:
        r = run_hook(
            {"tool_name": "Bash", "tool_input": {"command": "git checkout wip"}},
        )
        self.assertEqual(r.returncode, 0)

    def test_allows_git_branch_delete_backlog(self) -> None:
        r = run_hook(
            {"tool_name": "Bash", "tool_input": {"command": "git branch -d backlog"}},
        )
        self.assertEqual(r.returncode, 0)

    def test_allows_echo_done(self) -> None:
        r = run_hook({"tool_name": "Bash", "tool_input": {"command": "echo done"}})
        self.assertEqual(r.returncode, 0)


class TestUnknownTool(unittest.TestCase):
    def test_allows_other_tool(self) -> None:
        r = run_hook(
            {"tool_name": "Read", "tool_input": {"file_path": "/anything/wip/x"}},
        )
        self.assertEqual(r.returncode, 0)

    def test_allows_no_tool_name(self) -> None:
        r = run_hook({})
        self.assertEqual(r.returncode, 0)


class TestResolveToplevel(unittest.TestCase):
    """Tests for _common.resolve_toplevel (PRD 00133 finding 42): the shared,
    per-process memoized `git rev-parse --show-toplevel` resolver that
    enforce_prd_location.py and cartographer-echo.py both route through
    instead of shelling out to `git` independently."""

    def setUp(self) -> None:
        _common._TOPLEVEL_CACHE.clear()

    def tearDown(self) -> None:
        _common._TOPLEVEL_CACHE.clear()

    def test_resolves_toplevel_for_existing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            sub = os.path.join(repo, "src")
            os.makedirs(sub)
            result = _common.resolve_toplevel(sub)
            self.assertIsNotNone(result)
            self.assertEqual(os.path.realpath(result), os.path.realpath(repo))

    def test_resolves_toplevel_for_existing_file(self) -> None:
        """An existing FILE (not a directory) inside a repo must resolve
        too - the removed `os.path.isdir(resolved)` special case only ever
        took the walk-up loop's first step for us; starting the loop at
        `resolved` directly must land on the same toplevel."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            target = os.path.join(repo, "src", "a.py")
            os.makedirs(os.path.dirname(target))
            with open(target, "w", encoding="utf-8") as fh:
                fh.write("# x\n")
            result = _common.resolve_toplevel(target)
            self.assertIsNotNone(result)
            self.assertEqual(os.path.realpath(result), os.path.realpath(repo))

    def test_resolves_the_repo_root_when_handed_the_repo_root_itself(self) -> None:
        """A directory input must resolve from itself, not its parent. The
        parent of a temp repo root sits outside any git repository, so if
        resolve_toplevel walks up from the parent instead of the directory
        it was given, this comes back None instead of the repo root."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            result = _common.resolve_toplevel(repo)
            self.assertIsNotNone(result)
            self.assertEqual(os.path.realpath(result), os.path.realpath(repo))

    def test_resolves_same_toplevel_for_nonexistent_nested_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            target = os.path.join(repo, "newdir", "deeper", "newfile.py")
            self.assertFalse(os.path.exists(os.path.dirname(target)))
            result = _common.resolve_toplevel(target)
            self.assertIsNotNone(result)
            self.assertEqual(os.path.realpath(result), os.path.realpath(repo))

    def test_returns_none_outside_any_git_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outside = tempfile.mkdtemp(prefix="prdloc-nogit-", dir=tmp)
            self.assertIsNone(_common.resolve_toplevel(outside))

    def test_spawns_subprocess_at_most_once_for_same_existing_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            target_a = os.path.join(repo, "src", "a.py")
            target_b = os.path.join(repo, "src", "nested", "b.py")

            calls: list[list[str]] = []
            original_run = subprocess.run

            def counting_run(*args, **kwargs):
                cmd = args[0] if args else kwargs.get("args")
                calls.append(cmd)
                return original_run(*args, **kwargs)

            with patch("subprocess.run", counting_run):
                first = _common.resolve_toplevel(target_a)
                second = _common.resolve_toplevel(target_b)

            self.assertEqual(
                len(calls), 1, f"expected exactly 1 git spawn, got {calls}"
            )
            self.assertIsNotNone(first)
            self.assertEqual(first, second)
            self.assertEqual(os.path.realpath(first), os.path.realpath(repo))


if __name__ == "__main__":
    unittest.main()
