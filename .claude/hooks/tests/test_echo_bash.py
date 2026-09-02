"""Tests for hooks/_echo_bash.py — Bash bypass pattern detection for the Echo
gate, plus the `.claude/settings*.json` predicate that lives beside it.

`hooks/` is on sys.path via the tests package (`tests/__init__.py`), so the
module imports by bare name.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import _echo_bash as bash

# --- settings path predicate ---


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/Users/x/.claude/settings.json", True),
        ("/Users/x/.claude/settings.local.json", True),
        ("C:\\Users\\x\\.claude\\settings.json", True),
        ("/Users/x/.claude/settings.json.bak", False),
        ("/Users/x/project/settings.json", False),
        ("", False),
    ],
)
def test_is_claude_settings_path(path: str, expected: bool) -> None:
    assert bash.is_claude_settings_path(path) is expected


# --- Bash bypass pattern detection ---


@pytest.mark.parametrize(
    "command, expected_pattern",
    [
        (
            "cat > src/util/format.ts <<EOF\nexport function formatPrice(){}\nEOF\n",
            "cat-redirect",
        ),
        ("tee src/lib.py", "tee"),
        ("python3 -c \"open('src/x.py', 'w').write('...')\"", "python-open-write"),
        ("sed -i 's/foo/bar/' src/main.rs", "sed-inplace"),
        ("echo hello > out.md", "redirect-source"),
        ("echo x >> notes.md", "redirect-source"),
    ],
)
def test_detect_bash_bypass_positive(
    tmp_path: Path,
    command: str,
    expected_pattern: str,
) -> None:
    # Create the dirs referenced so resolve() works inside cwd.
    (tmp_path / "src" / "util").mkdir(parents=True, exist_ok=True)
    detected = bash.detect_bash_bypass(command, tmp_path)
    assert detected is not None, (
        f"expected {expected_pattern}, got None for {command!r}"
    )
    assert detected[0] == expected_pattern, detected


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "cat /etc/passwd",
        "grep -r foo .",
        "git status",
        "python3 script.py --flag",
        # Outside cwd
        "cat > /tmp/scratch.py <<EOF\nx\nEOF",
        # Literal > inside quoted args must not read as a redirect (audit FPs
        # 2026-06-28 and 2026-07-21).
        'git commit -m "defer to <prd>-review-<n>.md"',
        'rg ">\\s*\\S+\\.py" hooks/',
        'echo "a -> result.rs"',
        # fd redirect, not a source write
        "python3 script.py 2> err.md",
    ],
)
def test_detect_bash_bypass_negative(tmp_path: Path, command: str) -> None:
    detected = bash.detect_bash_bypass(command, tmp_path)
    assert detected is None, f"false-positive on {command!r}: {detected}"


def test_detect_bash_bypass_settings_json_skipped(tmp_path: Path) -> None:
    """Edits to ~/.claude/settings.json must not be flagged (gateguard owns it)."""
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text("{}")
    cmd = f"echo {{}} > {settings}"
    detected = bash.detect_bash_bypass(cmd, tmp_path)
    assert detected is None


def test_detect_bash_bypass_non_source_extension_ignored(tmp_path: Path) -> None:
    """A redirect to a non-source extension (a log, a binary) is not a bypass."""
    assert bash.detect_bash_bypass("echo x > run.log", tmp_path) is None
    assert bash.detect_bash_bypass("cat > image.png <<EOF\nx\nEOF", tmp_path) is None


def test_find_redirect_targets_fails_open_on_unbalanced_quotes() -> None:
    """An unparseable command line yields no redirect targets, never an exception."""
    assert bash._find_redirect_targets("echo 'unterminated > x.py") == []
