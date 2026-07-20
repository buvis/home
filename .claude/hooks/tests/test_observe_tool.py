"""Tests for hooks/observe_tool.py.

Covers structural input shaping, error/ok output classification, git-credential
stripping, automated-session detection, and end-to-end JSONL row + registry
emission. Subprocess-based end-to-end tests override HOME and run from a
non-git cwd so detect_project falls through to ('global', 'global', '').
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import observe_tool

HOOK = Path(__file__).resolve().parents[1] / "observe_tool.py"


def run_hook(payload: dict, home: Path, cwd: Path, env_extra: dict | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "HOME": str(home)}
    env.pop("CLAUDE_SESSION_NAME", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
        cwd=str(cwd),
    )


def read_observations(home: Path, proj_hash: str) -> list[dict]:
    f = home / ".claude" / "instincts" / "projects" / proj_hash / "observations.jsonl"
    if not f.is_file():
        return []
    return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]


class TestIsAutomatedSession(unittest.TestCase):
    def test_autopilot_match(self) -> None:
        with patch.dict("os.environ", {"CLAUDE_SESSION_NAME": "autopilot-run-001"}, clear=False):
            self.assertTrue(observe_tool.is_automated_session())

    def test_de_sloppify_match(self) -> None:
        with patch.dict("os.environ", {"CLAUDE_SESSION_NAME": "de-sloppify-2025"}, clear=False):
            self.assertTrue(observe_tool.is_automated_session())

    def test_human_session(self) -> None:
        with patch.dict("os.environ", {"CLAUDE_SESSION_NAME": "manual-debug"}, clear=False):
            self.assertFalse(observe_tool.is_automated_session())

    def test_unset(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_SESSION_NAME"}
        with patch.dict("os.environ", env, clear=True):
            self.assertFalse(observe_tool.is_automated_session())


class TestBuildToolIn(unittest.TestCase):
    def test_keeps_file_path(self) -> None:
        result = observe_tool.build_tool_in({"file_path": "/x/y.py"})
        self.assertEqual(json.loads(result), {"file_path": "/x/y.py"})

    def test_command_keeps_only_binary(self) -> None:
        result = observe_tool.build_tool_in({"command": "git status -sb"})
        self.assertEqual(json.loads(result), {"command": "git"})

    def test_drops_empty_values(self) -> None:
        result = observe_tool.build_tool_in({"file_path": "", "pattern": None})
        self.assertEqual(json.loads(result), {})

    def test_keeps_pattern_and_path(self) -> None:
        result = observe_tool.build_tool_in({"pattern": "TODO", "path": "/repo"})
        self.assertEqual(json.loads(result), {"pattern": "TODO", "path": "/repo"})

    def test_ignores_unknown_keys(self) -> None:
        result = observe_tool.build_tool_in({"file_path": "/x", "secret": "leak"})
        self.assertEqual(json.loads(result), {"file_path": "/x"})

    def test_compact_separators(self) -> None:
        result = observe_tool.build_tool_in({"file_path": "/x", "pattern": "y"})
        self.assertNotIn(", ", result)
        self.assertNotIn(": ", result)


class TestBuildToolOut(unittest.TestCase):
    def test_ok_when_no_error(self) -> None:
        self.assertEqual(observe_tool.build_tool_out("Files changed: 3"), "ok")

    def test_truncates_error_to_500(self) -> None:
        text = "ERROR: " + ("x" * 1000)
        result = observe_tool.build_tool_out(text)
        self.assertEqual(len(result), 500)

    def test_detects_lowercase_error(self) -> None:
        result = observe_tool.build_tool_out("error: bad input")
        self.assertNotEqual(result, "ok")

    def test_detects_exception(self) -> None:
        self.assertNotEqual(observe_tool.build_tool_out("Exception thrown"), "ok")

    def test_detects_permission_denied(self) -> None:
        self.assertNotEqual(observe_tool.build_tool_out("Permission denied"), "ok")

    def test_none_returns_ok(self) -> None:
        self.assertEqual(observe_tool.build_tool_out(None), "ok")

    def test_non_string_coerced(self) -> None:
        self.assertEqual(observe_tool.build_tool_out({"status": "fine"}), "ok")


class TestStripGitCredentials(unittest.TestCase):
    def test_strips_user_pass(self) -> None:
        self.assertEqual(
            observe_tool.strip_git_credentials("https://user:token@github.com/o/r.git"),
            "https://github.com/o/r.git",
        )

    def test_leaves_clean_url(self) -> None:
        self.assertEqual(
            observe_tool.strip_git_credentials("https://github.com/o/r.git"),
            "https://github.com/o/r.git",
        )

    def test_leaves_ssh_url(self) -> None:
        self.assertEqual(
            observe_tool.strip_git_credentials("git@github.com:o/r.git"),
            "git@github.com:o/r.git",
        )


class TestEndToEnd(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        self.cwd = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.home)
        shutil.rmtree(self.cwd)

    def test_writes_observation_row(self) -> None:
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "tool_response": "ok",
            "session_id": "sess-1",
        }
        proc = run_hook(payload, self.home, self.cwd)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        rows = read_observations(self.home, "global")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["tool"], "Bash")
        self.assertEqual(row["sid"], "sess-1")
        self.assertEqual(row["pid"], "global")
        self.assertEqual(row["out"], "ok")
        self.assertEqual(json.loads(row["in"]), {"command": "ls"})
        self.assertTrue(row["ts"].endswith("Z"))

    def test_skips_when_session_is_automated(self) -> None:
        payload = {"tool_name": "Bash", "tool_input": {}, "session_id": "s"}
        proc = run_hook(payload, self.home, self.cwd, env_extra={"CLAUDE_SESSION_NAME": "autopilot"})
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(read_observations(self.home, "global"), [])

    def test_skips_when_tool_name_missing(self) -> None:
        proc = run_hook({"session_id": "s"}, self.home, self.cwd)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(read_observations(self.home, "global"), [])

    def test_updates_registry(self) -> None:
        payload = {"tool_name": "Read", "tool_input": {"file_path": "/x"}, "session_id": "s"}
        run_hook(payload, self.home, self.cwd)
        registry_file = self.home / ".claude" / "instincts" / "projects.json"
        self.assertTrue(registry_file.is_file())
        registry = json.loads(registry_file.read_text(encoding="utf-8"))
        self.assertIn("global", registry)
        self.assertEqual(registry["global"]["name"], "global")
        self.assertEqual(registry["global"]["remote"], "")
        self.assertRegex(registry["global"]["last_seen"], r"^\d{4}-\d{2}-\d{2}$")

    def test_error_response_recorded(self) -> None:
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_response": "ERROR: command failed",
            "session_id": "s",
        }
        run_hook(payload, self.home, self.cwd)
        rows = read_observations(self.home, "global")
        self.assertEqual(rows[0]["out"], "ERROR: command failed")


class TestCwdCache(unittest.TestCase):
    """Cross-process cwd->identity cache skips the per-tool-call git spawn (R5)."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_cache_hit_skips_detect_on_repeat_cwd(self) -> None:
        calls: list[int] = []

        def fake_detect() -> tuple[str, str, str]:
            calls.append(1)
            return ("abc123def456", "repo", "https://github.com/o/repo.git")

        with patch.object(observe_tool, "INSTINCTS_DIR", self.tmp), \
             patch.object(observe_tool, "CWD_CACHE_FILE", self.tmp / ".cwd-cache.json"), \
             patch.object(observe_tool, "detect_project", fake_detect):
            r1 = observe_tool.detect_project_cached("/some/cwd")
            r2 = observe_tool.detect_project_cached("/some/cwd")

        self.assertEqual(r1, ("abc123def456", "repo", "https://github.com/o/repo.git"))
        self.assertEqual(r2, r1)
        self.assertEqual(len(calls), 1)  # git-backed detect ran once, not per call

    def test_different_cwd_detects_again(self) -> None:
        calls: list[int] = []

        def fake_detect() -> tuple[str, str, str]:
            calls.append(1)
            return ("h", "n", "")

        with patch.object(observe_tool, "INSTINCTS_DIR", self.tmp), \
             patch.object(observe_tool, "CWD_CACHE_FILE", self.tmp / ".cwd-cache.json"), \
             patch.object(observe_tool, "detect_project", fake_detect):
            observe_tool.detect_project_cached("/a")
            observe_tool.detect_project_cached("/b")

        self.assertEqual(len(calls), 2)


class TestRegistryPruning(unittest.TestCase):
    """update_registry drops entries older than INSTINCTS_RETENTION_DAYS (R5)."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_prunes_stale_keeps_current_and_recent(self) -> None:
        old = (datetime.now(timezone.utc) - timedelta(days=40)).strftime("%Y-%m-%d")
        recent = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")
        registry_file = self.tmp / "projects.json"
        registry_file.write_text(json.dumps({
            "stalehash": {"name": "old", "remote": "", "last_seen": old},
            "recenthash": {"name": "rec", "remote": "", "last_seen": recent},
        }))

        with patch.object(observe_tool, "INSTINCTS_DIR", self.tmp), \
             patch.object(observe_tool, "REGISTRY_FILE", registry_file), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("INSTINCTS_RETENTION_DAYS", None)
            observe_tool.update_registry("newhash", "new", "")

        result = json.loads(registry_file.read_text())
        self.assertIn("newhash", result)       # current project always kept
        self.assertIn("recenthash", result)    # within the 14d window, kept
        self.assertNotIn("stalehash", result)  # 40d > 14d, pruned


if __name__ == "__main__":
    unittest.main()
