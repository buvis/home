"""Tests for the deny surface of hooks/cartographer-echo.py: the two-attempt
key, `build_deny_envelope`, and the rationalization excerpt it renders from
the catalog (path attribution, excerpt shape, trigger reachability).

The hook is loaded by path through `echo_test_helpers`; catalog overrides go
through monkeypatch on `_echo_catalog`, which is imported once per session.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import _echo_catalog
from .echo_test_helpers import import_hook_module

STRONG_MATCH = [
    {"symbol": "formatPrice", "file": "src/util.py", "line": 42, "score": "strong"},
]


@pytest.fixture
def hook():
    return import_hook_module()


def _reason(hook, matches: list[dict]) -> str:
    return hook.build_deny_envelope(matches)["hookSpecificOutput"][
        "permissionDecisionReason"
    ]


# --- two-attempt key ---


def test_deny_key_deterministic(hook) -> None:
    a = hook.deny_key("/a.py", ["foo", "bar"])
    b = hook.deny_key("/a.py", ["bar", "foo"])  # sorted order
    assert a == b
    assert len(a) == 24


# --- deny envelope with rationalization excerpt ---


def test_build_deny_envelope_shape(hook) -> None:
    env = hook.build_deny_envelope(STRONG_MATCH)
    assert env["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert env["hookSpecificOutput"]["permissionDecision"] == "deny"
    reason = env["hookSpecificOutput"]["permissionDecisionReason"]
    assert "formatPrice" in reason
    assert "src/util.py:42" in reason or "`src/util.py:42`" in reason
    assert "retry" in reason.lower()


def test_build_deny_envelope_contains_rationalization_quote(hook) -> None:
    reason = _reason(hook, STRONG_MATCH)
    # Block quote line(s) indicate the rationalization excerpt.
    assert any(line.startswith(">") for line in reason.splitlines()), reason


def test_build_deny_envelope_reason_length_capped(hook) -> None:
    assert len(_reason(hook, STRONG_MATCH)) <= 1500


def test_build_deny_envelope_picks_strong_over_medium(hook) -> None:
    matches = [
        {"symbol": "formatPrice", "file": "src/a.py", "line": 1, "score": "medium"},
        {"symbol": "formatPrice", "file": "src/b.py", "line": 2, "score": "strong"},
    ]
    assert "src/b.py:2" in _reason(hook, matches)


def test_build_deny_envelope_verbs_cite_couldnt_find_helper(hook) -> None:
    """Symbols that contain `format`/`parse`/`validate`/etc cite the 'couldn't find existing helper' rationalization."""
    reason = _reason(hook, STRONG_MATCH)
    assert "couldn't find" in reason.lower() or "didn't grep" in reason.lower()


def test_build_deny_envelope_empty_matches_returns_basic_reason(hook) -> None:
    env = hook.build_deny_envelope([])
    assert env["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert env["hookSpecificOutput"]["permissionDecisionReason"]


# --- Deny payload attribution: pinned to rules-library/ after the catalog move ---


def test_build_deny_envelope_attribution_cites_new_catalog_path(hook) -> None:
    reason = _reason(hook, STRONG_MATCH)
    assert "Rationalization (`rules-library/rationalizations.md`):" in reason
    assert "rules/rationalizations.md" not in reason, (
        f"attribution still cites the old rules/ path: {reason!r}"
    )


def test_build_deny_envelope_excerpt_line_format_pinned(hook) -> None:
    """The quoted excerpt line directly under the attribution keeps its exact
    shape: `> "<excuse>". Why it's wrong: <why> Counter-action: <counter>`."""
    reason = _reason(hook, STRONG_MATCH)
    lines = reason.splitlines()
    attribution_idx = next(
        (
            i
            for i, line in enumerate(lines)
            if line.strip() == "Rationalization (`rules-library/rationalizations.md`):"
        ),
        None,
    )
    assert attribution_idx is not None, f"attribution line not found in: {reason!r}"
    excerpt_line = lines[attribution_idx + 1].strip()
    pattern = r'^> ".+"\. Why it\'s wrong: .+ Counter-action: .+$'
    assert re.match(pattern, excerpt_line), (
        f"excerpt line format changed: {excerpt_line!r}"
    )


def test_build_deny_envelope_surrounding_lines_unchanged_by_catalog_move(hook) -> None:
    """The catalog move only rewords the attribution's path; the leading Echo
    line, the 'Existing implementation' line, and the trailing retry line must
    stay exactly as before."""
    reason = _reason(hook, STRONG_MATCH)
    lines = [line.strip() for line in reason.splitlines() if line.strip()]
    assert lines[0] == "Echo: `formatPrice` likely duplicates `src/util.py:42`."
    assert (
        "Existing implementation is at `src/util.py:42` — import it instead of writing a parallel one."
        in lines
    )
    assert (
        lines[-1] == "If this is genuinely new, retry — the second attempt will pass."
    )


# --- rationalization reachability through the deny message (PRD 00157) ---


def _use_synthetic_catalog(
    monkeypatch: pytest.MonkeyPatch,
    path: Path,
    body: str,
) -> None:
    """Point the catalog module at a one-test synthetic catalog (auto-restored)."""
    path.write_text(body, encoding="utf-8")
    monkeypatch.setattr(_echo_catalog, "_RATIONALIZATIONS_PATH", path)
    monkeypatch.setattr(_echo_catalog, "_RATIONALIZATIONS_CACHE", None)


def test_appended_catalog_entry_is_cited_by_deny_message(
    hook,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An entry appended to the bottom of the catalog must be reachable through
    its own trigger terms, without being moved to the top and with no code
    change. Fails while the selector falls back to the first entry in file
    order."""
    _use_synthetic_catalog(
        monkeypatch,
        tmp_path / "rationalizations.md",
        '### "First entry"\n\n'
        "- **Why it's wrong**: first why.\n"
        "- **Counter-action**: first counter.\n\n"
        '### "Appended entry"\n\n'
        "- **Why it's wrong**: appended why.\n"
        "- **Counter-action**: appended counter.\n"
        "- **Triggers**: frobnicate\n",
    )
    matches = [
        {
            "symbol": "frobnicate_widget",
            "file": "src/w.py",
            "line": 7,
            "score": "strong",
        },
    ]
    reason = _reason(hook, matches)
    assert "Appended entry" in reason, reason
    assert "appended why" in reason, reason


def test_no_trigger_match_renders_deny_without_rationalization(
    hook,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no entry's triggers match, the deny must render with no
    rationalization block at all — an irrelevant excuse is worse than none."""
    _use_synthetic_catalog(
        monkeypatch,
        tmp_path / "rationalizations.md",
        '### "Only entry"\n\n'
        "- **Why it's wrong**: only why.\n"
        "- **Counter-action**: only counter.\n"
        "- **Triggers**: frobnicate\n",
    )
    matches = [
        {"symbol": "load_config", "file": "src/c.py", "line": 3, "score": "strong"},
    ]
    env = hook.build_deny_envelope(matches)
    reason = env["hookSpecificOutput"]["permissionDecisionReason"]
    assert env["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "Rationalization" not in reason, reason
    assert not any(line.startswith(">") for line in reason.splitlines()), reason
    assert "load_config" in reason
    assert reason.splitlines()[-1] == (
        "If this is genuinely new, retry — the second attempt will pass."
    )
