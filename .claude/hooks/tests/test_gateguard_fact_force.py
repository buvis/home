"""Tests for hooks/gateguard-fact-force.py."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "gateguard-fact-force.py"


def run_hook(
    payload: dict,
    state_dir: str,
    session_id: str = "test-session",
) -> subprocess.CompletedProcess[str]:
    body = {**payload, "session_id": session_id}
    env = {**os.environ, "GATEGUARD_STATE_DIR": state_dir}
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(body),
        capture_output=True,
        text=True,
        timeout=5,
        env=env,
    )


def is_deny(r: subprocess.CompletedProcess[str]) -> bool:
    if r.returncode != 0 or not r.stdout.strip():
        return False
    try:
        out = json.loads(r.stdout)
    except json.JSONDecodeError:
        return False
    return out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


class GateguardCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.state_dir = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()


class TestEditGateBaseline(GateguardCase):
    def test_first_edit_on_source_denies(self) -> None:
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/repo/src/foo.py"}}, self.state_dir)
        self.assertTrue(is_deny(r))

    def test_second_edit_on_same_source_allows(self) -> None:
        run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/repo/src/foo.py"}}, self.state_dir)
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/repo/src/foo.py"}}, self.state_dir)
        self.assertFalse(is_deny(r))

    def test_first_write_on_source_denies(self) -> None:
        r = run_hook({"tool_name": "Write", "tool_input": {"file_path": "/repo/src/new.py"}}, self.state_dir)
        self.assertTrue(is_deny(r))

    def test_write_then_edit_same_source_allows(self) -> None:
        # Write marks the path checked; subsequent Edit in same session passes.
        run_hook({"tool_name": "Write", "tool_input": {"file_path": "/repo/src/new.py"}}, self.state_dir)
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/repo/src/new.py"}}, self.state_dir)
        self.assertFalse(is_deny(r))


class TestWorkingDocExemption(GateguardCase):
    """Edits to working-doc paths should not be gated."""

    def test_devlocal_dir_exempt(self) -> None:
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/repo/dev/local/scratch.py"}}, self.state_dir)
        self.assertFalse(is_deny(r))

    def test_devlocal_nested_exempt(self) -> None:
        r = run_hook(
            {"tool_name": "Write", "tool_input": {"file_path": "/repo/dev/local/notes/today.py"}},
            self.state_dir,
        )
        self.assertFalse(is_deny(r))

    def test_prd_backlog_exempt(self) -> None:
        r = run_hook(
            {"tool_name": "Edit", "tool_input": {"file_path": "/repo/dev/local/prds/backlog/00001-foo.md"}},
            self.state_dir,
        )
        self.assertFalse(is_deny(r))

    def test_prd_wip_exempt(self) -> None:
        r = run_hook(
            {"tool_name": "Edit", "tool_input": {"file_path": "/repo/dev/local/prds/wip/00002-bar.md"}},
            self.state_dir,
        )
        self.assertFalse(is_deny(r))

    def test_claude_plans_exempt(self) -> None:
        path = str(Path.home() / ".claude" / "plans" / "foo.json")
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": path}}, self.state_dir)
        self.assertFalse(is_deny(r))

    def test_claude_projects_memory_exempt(self) -> None:
        path = str(Path.home() / ".claude" / "projects" / "-Users-bob--claude" / "memory" / "MEMORY.md")
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": path}}, self.state_dir)
        self.assertFalse(is_deny(r))

    def test_markdown_extension_exempt_anywhere(self) -> None:
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/repo/docs/architecture.md"}}, self.state_dir)
        self.assertFalse(is_deny(r))

    def test_changelog_md_exempt(self) -> None:
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/repo/CHANGELOG.md"}}, self.state_dir)
        self.assertFalse(is_deny(r))

    def test_txt_extension_exempt(self) -> None:
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/repo/notes.txt"}}, self.state_dir)
        self.assertFalse(is_deny(r))

    def test_rst_extension_exempt(self) -> None:
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/repo/docs/index.rst"}}, self.state_dir)
        self.assertFalse(is_deny(r))

    def test_gitignore_exempt(self) -> None:
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/repo/.gitignore"}}, self.state_dir)
        self.assertFalse(is_deny(r))

    def test_env_example_exempt(self) -> None:
        r = run_hook({"tool_name": "Write", "tool_input": {"file_path": "/repo/.env.example"}}, self.state_dir)
        self.assertFalse(is_deny(r))


class TestScratchDirExemption(GateguardCase):
    """Temp/scratch paths are throwaway; gating them only causes retry storms
    (regression: 14 consecutive Write denials on session-scratchpad files)."""

    def test_session_scratchpad_write_exempt(self) -> None:
        r = run_hook(
            {"tool_name": "Write", "tool_input": {"file_path": "/private/tmp/claude-501/-Users-bob--claude/abc123/scratchpad/driver.py"}},
            self.state_dir,
        )
        self.assertFalse(is_deny(r))

    def test_tmp_dir_code_exempt(self) -> None:
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/tmp/probe/main.py"}}, self.state_dir)
        self.assertFalse(is_deny(r))

    def test_var_folders_exempt(self) -> None:
        r = run_hook(
            {"tool_name": "Write", "tool_input": {"file_path": "/private/var/folders/m6/x/T/tmp.abc/script.sh"}},
            self.state_dir,
        )
        self.assertFalse(is_deny(r))

    def test_relative_tmp_dir_exempt(self) -> None:
        r = run_hook({"tool_name": "Write", "tool_input": {"file_path": "/repo/tmp/fixture_gen.py"}}, self.state_dir)
        self.assertFalse(is_deny(r))


class TestExemptionDoesNotLeak(GateguardCase):
    """Substring-only matches must not be exempt."""

    def test_tmp_substring_not_exempt(self) -> None:
        # "tmpfile.py" and "mytmp/" must not match the "/tmp/" segment.
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/repo/src/tmpfile.py"}}, self.state_dir)
        self.assertTrue(is_deny(r))
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/repo/mytmp/helper.py"}}, self.state_dir)
        self.assertTrue(is_deny(r))

    def test_devlocal_substring_not_exempt(self) -> None:
        # "dev_local" inside a filename is not a working-doc path.
        r = run_hook(
            {"tool_name": "Edit", "tool_input": {"file_path": "/repo/src/dev_local_helper.py"}},
            self.state_dir,
        )
        self.assertTrue(is_deny(r))

    def test_devlocalbackup_dir_not_exempt(self) -> None:
        # "dev/local.backup/" must not match "/dev/local/".
        r = run_hook(
            {"tool_name": "Edit", "tool_input": {"file_path": "/repo/dev/local.backup/foo.py"}},
            self.state_dir,
        )
        self.assertTrue(is_deny(r))

    def test_md_substring_not_exempt(self) -> None:
        # File ending in something that contains "md" but not the extension.
        r = run_hook(
            {"tool_name": "Edit", "tool_input": {"file_path": "/repo/src/cmd.py"}},
            self.state_dir,
        )
        self.assertTrue(is_deny(r))

    def test_python_source_still_gated(self) -> None:
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/repo/src/foo.py"}}, self.state_dir)
        self.assertTrue(is_deny(r))

    def test_yaml_config_still_gated(self) -> None:
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/repo/config.yaml"}}, self.state_dir)
        self.assertTrue(is_deny(r))


class TestMultiEditExemption(GateguardCase):
    def test_multiedit_skips_exempt_files(self) -> None:
        # Mixed batch: exempt md + gated py. Gate fires on the py only.
        r = run_hook(
            {
                "tool_name": "MultiEdit",
                "tool_input": {
                    "edits": [
                        {"file_path": "/repo/notes.md"},
                        {"file_path": "/repo/src/main.py"},
                    ]
                },
            },
            self.state_dir,
        )
        self.assertTrue(is_deny(r))
        self.assertIn("main.py", r.stdout)

    def test_multiedit_all_exempt_allows(self) -> None:
        r = run_hook(
            {
                "tool_name": "MultiEdit",
                "tool_input": {
                    "edits": [
                        {"file_path": "/repo/notes.md"},
                        {"file_path": "/repo/dev/local/foo.py"},
                    ]
                },
            },
            self.state_dir,
        )
        self.assertFalse(is_deny(r))


class TestBashGate(GateguardCase):
    """Bash gating: only destructive commands are gated; routine bash passes."""

    def test_first_nondestructive_bash_allows(self) -> None:
        r = run_hook({"tool_name": "Bash", "tool_input": {"command": "ls"}}, self.state_dir)
        self.assertFalse(is_deny(r))

    def test_repeated_nondestructive_bash_allows(self) -> None:
        run_hook({"tool_name": "Bash", "tool_input": {"command": "ls"}}, self.state_dir)
        r = run_hook({"tool_name": "Bash", "tool_input": {"command": "pwd"}}, self.state_dir)
        self.assertFalse(is_deny(r))

    def test_destructive_rm_rf_denies(self) -> None:
        r = run_hook({"tool_name": "Bash", "tool_input": {"command": "rm -rf /tmp/x"}}, self.state_dir)
        self.assertTrue(is_deny(r))

    def test_destructive_rm_rf_second_attempt_allows(self) -> None:
        run_hook({"tool_name": "Bash", "tool_input": {"command": "rm -rf /tmp/x"}}, self.state_dir)
        r = run_hook({"tool_name": "Bash", "tool_input": {"command": "rm -rf /tmp/x"}}, self.state_dir)
        self.assertFalse(is_deny(r))

    def test_readonly_git_status_allows(self) -> None:
        r = run_hook({"tool_name": "Bash", "tool_input": {"command": "git status --porcelain"}}, self.state_dir)
        self.assertFalse(is_deny(r))


class TestGateMessagesHaveNoVerbatimQuote(GateguardCase):
    """The "Quote the user's current instruction verbatim" line is pure
    compliance theater - the instruction is already in conversation context.
    No gate message should include it."""

    _VERBATIM = "verbatim"

    def test_edit_message_omits_verbatim(self) -> None:
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/repo/src/foo.py"}}, self.state_dir)
        self.assertTrue(is_deny(r))
        self.assertNotIn(self._VERBATIM, r.stdout.lower())

    def test_write_message_omits_verbatim(self) -> None:
        r = run_hook({"tool_name": "Write", "tool_input": {"file_path": "/repo/src/new.py"}}, self.state_dir)
        self.assertTrue(is_deny(r))
        self.assertNotIn(self._VERBATIM, r.stdout.lower())

    def test_destructive_bash_message_omits_verbatim(self) -> None:
        r = run_hook({"tool_name": "Bash", "tool_input": {"command": "rm -rf /tmp/x"}}, self.state_dir)
        self.assertTrue(is_deny(r))
        self.assertNotIn(self._VERBATIM, r.stdout.lower())


class TestMultiEditCoalesce(GateguardCase):
    """A single MultiEdit batch should produce one denial covering all its
    unchecked files, not N denials requiring N retries."""

    def test_single_denial_lists_all_unchecked_files(self) -> None:
        r = run_hook(
            {
                "tool_name": "MultiEdit",
                "tool_input": {
                    "edits": [
                        {"file_path": "/repo/src/a.py"},
                        {"file_path": "/repo/src/b.py"},
                        {"file_path": "/repo/src/c.py"},
                    ]
                },
            },
            self.state_dir,
        )
        self.assertTrue(is_deny(r))
        self.assertIn("a.py", r.stdout)
        self.assertIn("b.py", r.stdout)
        self.assertIn("c.py", r.stdout)

    def test_retry_same_multiedit_allows(self) -> None:
        payload = {
            "tool_name": "MultiEdit",
            "tool_input": {
                "edits": [
                    {"file_path": "/repo/src/a.py"},
                    {"file_path": "/repo/src/b.py"},
                ]
            },
        }
        run_hook(payload, self.state_dir)
        r = run_hook(payload, self.state_dir)
        self.assertFalse(is_deny(r))

    def test_retry_individual_edit_after_multiedit_allows(self) -> None:
        run_hook(
            {
                "tool_name": "MultiEdit",
                "tool_input": {
                    "edits": [
                        {"file_path": "/repo/src/a.py"},
                        {"file_path": "/repo/src/b.py"},
                    ]
                },
            },
            self.state_dir,
        )
        r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/repo/src/b.py"}}, self.state_dir)
        self.assertFalse(is_deny(r))

    def test_mixed_batch_only_lists_new_unchecked(self) -> None:
        # Pre-check one file so it shouldn't appear in the denial message.
        run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/repo/src/already.py"}}, self.state_dir)
        run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/repo/src/already.py"}}, self.state_dir)

        r = run_hook(
            {
                "tool_name": "MultiEdit",
                "tool_input": {
                    "edits": [
                        {"file_path": "/repo/notes.md"},        # exempt
                        {"file_path": "/repo/src/already.py"},  # already checked
                        {"file_path": "/repo/src/fresh.py"},    # new
                    ]
                },
            },
            self.state_dir,
        )
        self.assertTrue(is_deny(r))
        self.assertIn("fresh.py", r.stdout)
        self.assertNotIn("already.py", r.stdout)
        self.assertNotIn("notes.md", r.stdout)


class TestFactListTailoredByExtension(GateguardCase):
    """Code files get the "public functions/classes" question; config/data
    files get a "consumers + expected fields" question instead."""

    _CODE_PHRASE = "public functions"
    _CONFIG_PHRASE = "consumes this file"

    def _msg_for(self, file_path: str, tool: str = "Edit") -> str:
        r = run_hook({"tool_name": tool, "tool_input": {"file_path": file_path}}, self.state_dir)
        self.assertTrue(is_deny(r), f"expected deny for {file_path}")
        return r.stdout

    # Code → code-style prompt
    def test_python_uses_code_prompt(self) -> None:
        body = self._msg_for("/repo/src/foo.py")
        self.assertIn(self._CODE_PHRASE, body)

    def test_typescript_uses_code_prompt(self) -> None:
        body = self._msg_for("/repo/src/foo.ts")
        self.assertIn(self._CODE_PHRASE, body)

    def test_rust_uses_code_prompt(self) -> None:
        body = self._msg_for("/repo/src/lib.rs")
        self.assertIn(self._CODE_PHRASE, body)

    def test_svelte_uses_code_prompt(self) -> None:
        body = self._msg_for("/repo/src/Foo.svelte")
        self.assertIn(self._CODE_PHRASE, body)

    # Non-code → config/data prompt
    def test_yaml_uses_config_prompt(self) -> None:
        body = self._msg_for("/repo/config.yaml")
        self.assertNotIn(self._CODE_PHRASE, body)
        self.assertIn(self._CONFIG_PHRASE, body)

    def test_json_uses_config_prompt(self) -> None:
        body = self._msg_for("/repo/package.config.json")
        self.assertNotIn(self._CODE_PHRASE, body)
        self.assertIn(self._CONFIG_PHRASE, body)

    def test_css_uses_config_prompt(self) -> None:
        body = self._msg_for("/repo/styles.css")
        self.assertNotIn(self._CODE_PHRASE, body)
        self.assertIn(self._CONFIG_PHRASE, body)

    def test_toml_uses_config_prompt(self) -> None:
        body = self._msg_for("/repo/pyproject.toml")
        self.assertNotIn(self._CODE_PHRASE, body)
        self.assertIn(self._CONFIG_PHRASE, body)

    def test_sql_uses_config_prompt(self) -> None:
        body = self._msg_for("/repo/schema.sql")
        self.assertNotIn(self._CODE_PHRASE, body)
        self.assertIn(self._CONFIG_PHRASE, body)


class TestTranscriptAwareSkip(GateguardCase):
    """If a file was already Read earlier in the conversation, the gate's
    investigation questions are redundant - skip the gate."""

    def _write_transcript(self, entries: list[dict]) -> str:
        """Write JSONL transcript and return its path."""
        path = Path(self.state_dir) / "transcript.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        return str(path)

    def _read_event(self, file_path: str) -> dict:
        """Build an assistant-side JSONL entry containing a Read tool_use."""
        return {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_test",
                        "name": "Read",
                        "input": {"file_path": file_path},
                    }
                ],
            },
        }

    def _run_with_transcript(self, payload: dict, transcript_path: str) -> subprocess.CompletedProcess[str]:
        body = {**payload, "session_id": "test-session", "transcript_path": transcript_path}
        env = {**os.environ, "GATEGUARD_STATE_DIR": self.state_dir}
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(body),
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
        )

    def test_edit_skipped_when_file_previously_read(self) -> None:
        target = "/repo/src/foo.py"
        transcript = self._write_transcript([self._read_event(target)])
        r = self._run_with_transcript(
            {"tool_name": "Edit", "tool_input": {"file_path": target}},
            transcript,
        )
        self.assertFalse(is_deny(r))

    def test_edit_still_gated_when_other_file_was_read(self) -> None:
        transcript = self._write_transcript([self._read_event("/repo/src/other.py")])
        r = self._run_with_transcript(
            {"tool_name": "Edit", "tool_input": {"file_path": "/repo/src/foo.py"}},
            transcript,
        )
        self.assertTrue(is_deny(r))

    def test_multiedit_filters_out_previously_read_files(self) -> None:
        transcript = self._write_transcript([
            self._read_event("/repo/src/seen.py"),
        ])
        r = self._run_with_transcript(
            {
                "tool_name": "MultiEdit",
                "tool_input": {
                    "edits": [
                        {"file_path": "/repo/src/seen.py"},    # filtered out
                        {"file_path": "/repo/src/unseen.py"},  # still gated
                    ]
                },
            },
            transcript,
        )
        self.assertTrue(is_deny(r))
        self.assertIn("/repo/src/unseen.py", r.stdout)
        self.assertNotIn("/repo/src/seen.py", r.stdout)

    def test_multiedit_all_previously_read_allows(self) -> None:
        transcript = self._write_transcript([
            self._read_event("/repo/src/a.py"),
            self._read_event("/repo/src/b.py"),
        ])
        r = self._run_with_transcript(
            {
                "tool_name": "MultiEdit",
                "tool_input": {
                    "edits": [
                        {"file_path": "/repo/src/a.py"},
                        {"file_path": "/repo/src/b.py"},
                    ]
                },
            },
            transcript,
        )
        self.assertFalse(is_deny(r))

    def test_write_not_skipped_by_prior_read(self) -> None:
        # Write means new file; "previously read" cannot apply, gate stays.
        target = "/repo/src/new.py"
        transcript = self._write_transcript([self._read_event(target)])
        r = self._run_with_transcript(
            {"tool_name": "Write", "tool_input": {"file_path": target}},
            transcript,
        )
        self.assertTrue(is_deny(r))

    def test_missing_transcript_file_does_not_crash(self) -> None:
        r = self._run_with_transcript(
            {"tool_name": "Edit", "tool_input": {"file_path": "/repo/src/foo.py"}},
            "/nonexistent/transcript.jsonl",
        )
        self.assertTrue(is_deny(r))  # no transcript = no skip = normal gate

    def test_grep_does_not_count_as_read(self) -> None:
        transcript = self._write_transcript([
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_x",
                            "name": "Grep",
                            "input": {"pattern": "foo", "path": "/repo/src/foo.py"},
                        }
                    ],
                },
            }
        ])
        r = self._run_with_transcript(
            {"tool_name": "Edit", "tool_input": {"file_path": "/repo/src/foo.py"}},
            transcript,
        )
        self.assertTrue(is_deny(r))


if __name__ == "__main__":
    unittest.main()
