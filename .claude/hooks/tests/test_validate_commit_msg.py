"""Tests for hooks/validate_commit_msg.py."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "validate_commit_msg.py"


def run_hook(cmd: str) -> subprocess.CompletedProcess[str]:
    payload = json.dumps({"tool_input": {"command": cmd}})
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=5,
    )


class TestAllows(unittest.TestCase):
    def test_allows_valid_with_scope(self) -> None:
        r = run_hook('git commit -m "fix(scope): some change"')
        self.assertEqual(r.returncode, 0)

    def test_allows_valid_no_scope(self) -> None:
        r = run_hook('git commit -m "feat: add new thing"')
        self.assertEqual(r.returncode, 0)

    def test_allows_breaking_marker(self) -> None:
        r = run_hook('git commit -m "fix!: breaking change"')
        self.assertEqual(r.returncode, 0)

    def test_allows_breaking_with_scope(self) -> None:
        r = run_hook('git commit -m "feat(api)!: drop legacy endpoint"')
        self.assertEqual(r.returncode, 0)

    def test_allows_single_quoted(self) -> None:
        r = run_hook("git commit -m 'docs: clarify readme'")
        self.assertEqual(r.returncode, 0)

    def test_allows_amend_without_m(self) -> None:
        r = run_hook("git commit --amend")
        self.assertEqual(r.returncode, 0)

    def test_allows_non_git_commit(self) -> None:
        r = run_hook("git status")
        self.assertEqual(r.returncode, 0)

    def test_allows_unrelated_command(self) -> None:
        r = run_hook("ls -la")
        self.assertEqual(r.returncode, 0)

    def test_allows_heredoc_with_valid_message(self) -> None:
        cmd = "git commit -m \"$(cat <<'EOF'\nfix: handle edge case\nEOF\n)\""
        r = run_hook(cmd)
        self.assertEqual(r.returncode, 0)

    def test_allows_heredoc_unquoted_eof(self) -> None:
        cmd = "git commit -m \"$(cat <<EOF\nfeat: new thing\nEOF\n)\""
        r = run_hook(cmd)
        self.assertEqual(r.returncode, 0)

    def test_allows_heredoc_with_non_eof_delimiter(self) -> None:
        # Bash original returned empty msg → allowed. Python must do the same
        # rather than falling through to the double-quote regex.
        cmd = "git commit -m \"$(cat <<COMMIT_MSG\nfix: ok\nCOMMIT_MSG\n)\""
        r = run_hook(cmd)
        self.assertEqual(r.returncode, 0)

    def test_allows_message_containing_cat_substring_when_valid(self) -> None:
        # The literal string "cat <<" inside a quoted message must NOT trigger
        # the heredoc branch (it's not a real command-substitution).
        r = run_hook('git commit -m "fix: cat << is fine in body"')
        self.assertEqual(r.returncode, 0)

    def test_allows_heredoc_with_whitespace_after_dollar_paren(self) -> None:
        # `$( cat <<EOF ... EOF )` (whitespace after `$(`) should still be
        # detected as a heredoc construction.
        cmd = "git commit -m \"$( cat <<EOF\nfix: spaced heredoc\nEOF\n)\""
        r = run_hook(cmd)
        self.assertEqual(r.returncode, 0)

    def test_allows_empty_stdin(self) -> None:
        r = subprocess.run(
            [sys.executable, str(HOOK)],
            input="",
            capture_output=True,
            text=True,
            timeout=5,
        )
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


class TestBlocks(unittest.TestCase):
    def test_blocks_capitalized_subject(self) -> None:
        r = run_hook('git commit -m "Fix typo"')
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)
        self.assertIn("conventional commit format", r.stderr)

    def test_validates_message_containing_cat_substring(self) -> None:
        # Literal "cat <<" in message body must still go through conventional
        # commit validation (capital F should block).
        r = run_hook('git commit -m "Fix: cat << broken"')
        self.assertEqual(r.returncode, 2)
        self.assertIn("conventional commit format", r.stderr)

    def test_blocks_trailing_period(self) -> None:
        r = run_hook('git commit -m "fix: ends with period."')
        self.assertEqual(r.returncode, 2)
        self.assertIn("must not end with a period", r.stderr)

    def test_blocks_unknown_type(self) -> None:
        r = run_hook('git commit -m "wrong-type: foo"')
        self.assertEqual(r.returncode, 2)
        self.assertIn("conventional commit format", r.stderr)

    def test_blocks_co_authored_by_in_heredoc(self) -> None:
        cmd = (
            "git commit -m \"$(cat <<'EOF'\n"
            "fix: do thing\n\n"
            "Co-Authored-By: someone <s@example.com>\n"
            "EOF\n)\""
        )
        r = run_hook(cmd)
        self.assertEqual(r.returncode, 2)
        self.assertIn("forbidden boilerplate", r.stderr)

    def test_blocks_signed_off_by(self) -> None:
        cmd = 'git commit -m "fix: something\n\nSigned-Off-By: someone"'
        r = run_hook(cmd)
        self.assertEqual(r.returncode, 2)
        self.assertIn("forbidden boilerplate", r.stderr)

    def test_blocks_generated_with(self) -> None:
        cmd = 'git commit -m "fix: thing\n\nGenerated with Some-Tool"'
        r = run_hook(cmd)
        self.assertEqual(r.returncode, 2)
        self.assertIn("forbidden boilerplate", r.stderr)

    def test_blocks_co_authored_in_inline_message(self) -> None:
        cmd = 'git commit -m "fix: thing\n\nCo-authored-by: alice"'
        r = run_hook(cmd)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
