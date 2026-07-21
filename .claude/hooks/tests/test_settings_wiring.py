"""Contract test: the live settings.json must still wire hooks/dispatch.py.

PRD 00071 collapsed the per-handler PreToolUse/PostToolUse/Stop registrations
in settings.json into one dispatcher entry per event, moving the real routing
table into hooks/dispatch.py's ROUTES. Before that swap,
skills/run-autopilot/scripts/test_review_coverage_hook_registration.py's
settings.json branch was the guardrail proving a Stop hook was actually wired;
after the swap that branch is permanently dead (it now passes purely on
dispatch.ROUTES) and nothing asserts that settings.json still wires
dispatch.py at all. This file is that guardrail: it binds to the live
settings.json (not a frozen fixture) so a future edit that drops or narrows
the dispatcher entries fails loud instead of silently turning off every
personal hook.

Matcher coverage (last test) compares the '|'-joined alternatives in each
settings.json matcher against the '|'-joined alternatives in dispatch.ROUTES's
matchers for the same event, as a set. All matchers in both places are simple
alternations (e.g. "Edit|Write|MultiEdit", "mcp__.*"); token-set comparison is
exact for that shape and avoids implementing general regex-containment.

Stdlib-only unittest.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

_CLAUDE_DIR = Path(__file__).resolve().parents[2]
_SETTINGS_PATH = _CLAUDE_DIR / "settings.json"
_HOOKS_DIR = _CLAUDE_DIR / "hooks"

_EVENT_ARG = {"PreToolUse": "pre", "PostToolUse": "post", "Stop": "stop"}


def _load_dispatch():
    """Import hooks/dispatch.py by absolute path so dispatch.ROUTES can be
    inspected without relying on hooks/ already being on sys.path."""
    if "dispatch" in sys.modules:
        return sys.modules["dispatch"]
    if str(_HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_DIR))  # dispatch.py does `from _common import ...`
    spec = importlib.util.spec_from_file_location("dispatch", str(_HOOKS_DIR / "dispatch.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["dispatch"] = mod
    spec.loader.exec_module(mod)
    return mod


def _settings() -> dict:
    return json.loads(_SETTINGS_PATH.read_text())


def _entries(event: str) -> list[dict]:
    return _settings().get("hooks", {}).get(event, [])


def _route_tokens(event: str) -> set[str]:
    """Tool-name tokens dispatch.ROUTES matches for one event, derived by
    splitting each route's matcher on '|'. Stop routes carry matcher=None
    (they run unconditionally) and contribute nothing."""
    dispatch = _load_dispatch()
    tokens: set[str] = set()
    for route in dispatch.ROUTES:
        if route.event == event and route.matcher:
            tokens.update(route.matcher.split("|"))
    return tokens


def _worst_case_sequential_timeout(event: str) -> int:
    """Worst-case sequential wall-clock sum, in seconds, of the
    dispatch.ROUTES handlers dispatch.py can select for one event.

    dispatch.py runs the selected handlers for an event one after another
    under a single outer command timeout, so that timeout must cover the
    worst tool name: the one whose matching routes sum to the largest
    total. matcher=None routes (e.g. all Stop routes) run unconditionally
    for every tool and are added to every candidate's sum.
    """
    dispatch = _load_dispatch()
    routes = [r for r in dispatch.ROUTES if r.event == event]
    always = [r for r in routes if r.matcher is None]
    conditional = [r for r in routes if r.matcher is not None]
    base = sum(r.timeout for r in always)
    if not conditional:
        return base
    candidates: set[str] = set()
    for r in conditional:
        candidates.update(r.matcher.split("|"))
    worst_conditional = max(
        sum(r.timeout for r in conditional if dispatch._matches(r.matcher, tool))
        for tool in candidates
    )
    return base + worst_conditional


class SettingsWiringTests(unittest.TestCase):
    def test_settings_json_is_valid(self) -> None:
        # Must parse — a malformed settings.json breaks the harness.
        json.loads(_SETTINGS_PATH.read_text())

    def test_each_dispatched_event_has_exactly_one_entry(self) -> None:
        for event in _EVENT_ARG:
            entries = _entries(event)
            self.assertEqual(
                len(entries), 1,
                f"hooks.{event} must carry exactly one dispatcher entry, "
                f"found {len(entries)}",
            )

    def test_each_dispatched_event_invokes_dispatch_with_its_event_arg(self) -> None:
        for event, arg in _EVENT_ARG.items():
            hooks = _entries(event)[0]["hooks"]
            self.assertEqual(
                len(hooks), 1,
                f"hooks.{event}[0].hooks must carry exactly one hook entry",
            )
            command = hooks[0]["command"]
            self.assertIn("hooks/dispatch.py", command)
            self.assertTrue(
                command.rstrip().endswith(f" {arg}"),
                f"hooks.{event} command {command!r} must invoke dispatch.py "
                f"with the {arg!r} event argument",
            )

    def test_each_dispatched_event_timeout_covers_worst_case_sequential_sum(self) -> None:
        # Handlers for one event run SEQUENTIALLY inside dispatch.py under a
        # single outer command timeout, so that timeout must cover the worst
        # case (over every tool name the event can route for) of the SUMMED
        # per-handler timeouts dispatch.ROUTES selects for that tool. A bare
        # `> 0` check would pass with e.g. Stop: 1, silently reintroducing the
        # truncation this sizing exists to prevent.
        for event in _EVENT_ARG:
            timeout = _entries(event)[0]["hooks"][0].get("timeout")
            self.assertIsInstance(timeout, (int, float))
            minimum = _worst_case_sequential_timeout(event)
            self.assertGreaterEqual(
                timeout, minimum,
                f"hooks.{event}[0].hooks[0].timeout ({timeout}) is less than "
                f"the worst-case sequential sum of dispatch.ROUTES handler "
                f"timeouts for {event} ({minimum})",
            )

    def test_pre_and_post_matchers_are_not_narrower_than_routes(self) -> None:
        for event in ("PreToolUse", "PostToolUse"):
            matcher = _entries(event)[0].get("matcher")
            self.assertTrue(
                matcher,
                f"hooks.{event}[0].matcher must be present and non-empty",
            )
            settings_tokens = set(matcher.split("|"))
            route_tokens = _route_tokens(event)
            missing = route_tokens - settings_tokens
            self.assertFalse(
                missing,
                f"hooks.{event} settings matcher {matcher!r} is narrower "
                f"than dispatch.ROUTES: missing tokens {sorted(missing)}",
            )


if __name__ == "__main__":
    unittest.main()
