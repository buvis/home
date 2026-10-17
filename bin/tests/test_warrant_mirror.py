"""Drift check: every path ai-agents.sb lets an agent write must count as agent-writable in ~/.config/warrant/config.json.

The broker's refusals ("executable under an agent-writable path", re-hash of
agent-writable file arguments) are only as good as that hand-kept mirror
(PRD 00160). Profile denies do not matter here: a missing mirror entry makes
warrant trust a path agents can write, an extra one only makes it stricter.

Run outside the sandbox (the profile denies reading ~/.config/warrant):
/opt/homebrew/bin/python3 -m unittest discover -s ~/bin/tests -t ~/bin/tests -p 'test_warrant*.py'
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from test_warrant import warrant

HOME = Path.home()
PROFILE = HOME / ".config" / "seatbelt" / "ai-agents.sb"
CONFIG = HOME / ".config" / "warrant" / "config.json"
# Known at session start only, so warrant cannot mirror them; ~/git/src covers the usual project dirs.
RUNTIME_PARAMS = {"_PROJECT_DIR", "_TMPDIR"}
# Every sub-form but the string helpers is a filter; one the patterns below miss is reported, not ignored.
# ponytail: a regex grant counts as unparsed; check it by hand against agent_writable_globs if one returns.
FILTER = re.compile(r"\((?!allow |string-append |param |regex-quote )")
HOME_PATH = re.compile(
    r'\((?:subpath|literal) \(string-append \(param "_HOME"\) "([^"]*)"\)\)',
)
ABS_PATH = re.compile(r'\((?:subpath|literal) "(/[^"]*)"\)')
PARAM_PATH = re.compile(r'\(subpath \(param "(\w+)"\)\)')


def write_allow_forms(profile: str) -> list[str]:
    """Top-level `(allow file-write* ...)` forms, comments dropped and whitespace collapsed."""
    text = re.sub(r";.*", "", profile)
    forms, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        if ch == "(":
            if depth == 0:
                start = i
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                forms.append(" ".join(text[start : i + 1].split()))
    return [form for form in forms if form.startswith("(allow file-write* ")]


def drift(profile: str, config: dict) -> list[str]:
    """Profile write grants the mirror does not cover, plus filters this parser cannot read."""
    site = warrant.Site(Path("/nonexistent"), Path("/nonexistent"), config)
    problems = []
    for form in write_allow_forms(profile):
        paths = [HOME / rel.lstrip("/") for rel in HOME_PATH.findall(form)]
        paths += [Path(p) for p in ABS_PATH.findall(form)]
        params = PARAM_PATH.findall(form)
        if len(paths) + len(params) != len(FILTER.findall(form)):
            problems.append(f"unparsed filter in {form}")
        problems += [
            f"unknown runtime param {p}" for p in params if p not in RUNTIME_PARAMS
        ]
        problems += [
            f"not mirrored: {p}"
            for p in paths
            if not warrant.agent_writable(site, p.resolve())
        ]
    return problems


class MirrorCase(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = PROFILE.read_text()
        try:
            self.config = warrant.load_config(CONFIG)
        except PermissionError:
            self.skipTest(
                f"{CONFIG} is unreadable here (sandboxed session); run outside run-agent",
            )

    def test_profile_write_roots_are_mirrored(self) -> None:
        self.assertEqual(drift(self.profile, self.config), [])

    def test_dropping_a_root_from_the_mirror_is_reported(self) -> None:
        roots = [r for r in self.config["agent_writable_roots"] if r != "~/.codex"]
        self.assertEqual(
            drift(self.profile, {**self.config, "agent_writable_roots": roots}),
            [f"not mirrored: {HOME / '.codex'}"],
        )

    def test_an_unreadable_filter_is_reported(self) -> None:
        profile = self.profile + '\n(allow file-write* (prefix "/opt"))\n'
        self.assertNotEqual(drift(profile, self.config), [])

    def test_a_regex_grant_is_reported_for_a_hand_check(self) -> None:
        grant = r'(regex (string-append "^" (regex-quote (param "_HOME")) "/\\.local/bin/claude[^/]*$"))'
        profile = self.profile + f"\n(allow file-write* {grant})\n"
        self.assertNotEqual(drift(profile, self.config), [])


if __name__ == "__main__":
    unittest.main()
