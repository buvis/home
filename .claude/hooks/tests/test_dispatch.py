"""Contract tests for the in-process hook dispatcher (hooks/dispatch.py) and the
shared `capture_main` / `HandlerTimeout` helpers added to hooks/_common.py.

TDD: neither `dispatch.py` nor the new `_common` symbols exist yet, so this file
is expected to be RED until they are built. Tests bind to the observable contract
only (routing, aggregation, isolation, timeout), never to an implementation.

Conventions
-----------
- Bare pytest functions, `tmp_path` + `monkeypatch` for sandboxing (no TestCase).
- All filesystem writes are redirected to `tmp_path` via `monkeypatch.setattr(
  Path, "home", ...)`. The dispatcher's log (~/.claude/hooks/dispatch.log) is
  assumed to resolve at call time (e.g. via `_common.log_path`), so patching
  home AFTER import lands it in tmp. See ASSUMPTIONS in the task report.
- `dispatch` is imported once at REAL home so its module-level `ROUTES` capture
  the real absolute handler paths; home is patched to tmp only afterwards.
- Routing tests derive the expected handler set by parsing the live
  settings.json in the test (not a hardcoded snapshot) and assert the real
  `dispatch.ROUTES` (driven through `main` with a recording `_invoke`) matches
  it by handler basename and order.
- Aggregation / isolation / timeout tests monkeypatch `dispatch.ROUTES` (or call
  `dispatch._invoke` / `dispatch._aggregate` directly) against tiny stub handler
  files written into `tmp_path`, so the 12 real handlers are never executed.
"""

from __future__ import annotations

import collections
import contextlib
import functools
import io
import json
import os
import re
import signal
import subprocess
import sys
import textwrap
import time
import types
from pathlib import Path
from uuid import uuid4

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[1]
# PRD 00071 consolidated the per-handler PreToolUse/PostToolUse/Stop matchers
# out of settings.json and into dispatch.ROUTES; settings.json now carries one
# dispatcher entry per event. This fixture is the frozen pre-swap wiring ROUTES
# must keep reproducing - comparing ROUTES against the post-swap settings.json
# would be a tautology (both would just say "one dispatch.py entry").
SETTINGS_PATH = Path(__file__).resolve().parent / "fixtures" / "settings-preswap-hooks.json"

if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

EVENTS_MAP = {"pre": "PreToolUse", "post": "PostToolUse", "stop": "Stop"}

SETTINGS = json.loads(SETTINGS_PATH.read_text())

# A local Route shape. `main`/`_invoke` read routes purely by attribute
# (`row.event`, `row.matcher`, `row.name`, `row.path`, `row.timeout`), so a
# namedtuple with matching fields works for stub ROUTES regardless of the
# internal Route type used by dispatch.py.
Route = collections.namedtuple("Route", "event matcher name path timeout")

_HAS_SIGALRM = hasattr(signal, "SIGALRM")


# --------------------------------------------------------------------------- #
# Loaders / fixtures
# --------------------------------------------------------------------------- #
def _load_common():
    if "_common" in sys.modules:
        return sys.modules["_common"]
    import _common

    return _common


def _load_dispatch():
    # First import happens at the REAL home so module-level ROUTES capture the
    # real handler paths. Subsequent calls reuse the cached module.
    if "dispatch" in sys.modules:
        return sys.modules["dispatch"]
    import dispatch

    return dispatch


@pytest.fixture
def common(monkeypatch, tmp_path):
    mod = _load_common()
    home = tmp_path / "home"
    (home / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    return mod


@pytest.fixture
def dispatch(monkeypatch, tmp_path):
    mod = _load_dispatch()  # import at real home BEFORE patching
    home = tmp_path / "home"
    (home / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    return mod


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _uid() -> str:
    return uuid4().hex[:8]


def make_route(tmp_path, label, src, *, event="PreToolUse", matcher=None, timeout=5):
    """Write a stub handler file and return a Route pointing at it."""
    path = tmp_path / f"{label}_{_uid()}.py"
    path.write_text(textwrap.dedent(src))
    return Route(event, matcher, label.upper(), str(path), timeout)


def env(**inner) -> str:
    """A hookSpecificOutput envelope as a handler would print it on stdout."""
    return json.dumps({"hookSpecificOutput": inner})


def route_basename(route) -> str:
    path = getattr(route, "path", None)
    if path is None:
        path = route[3]
    return Path(str(path)).name


def expected_handlers(event_full: str, tool_name: str) -> list[str]:
    """Ordered handler basenames settings.json declares for (event, tool)."""
    out: list[str] = []
    for entry in SETTINGS["hooks"].get(event_full, []):
        matcher = entry.get("matcher")
        if matcher is None or re.fullmatch(matcher, tool_name):
            for hook in entry["hooks"]:
                script = hook["command"].split()[-1]
                out.append(Path(script).name)
    return out


def run_main(dispatch_mod, event: str, payload: dict, capsys):
    """Feed payload on stdin, run main(event), return (code, stdout, stderr)."""
    old_stdin = sys.stdin
    sys.stdin = io.StringIO(json.dumps(payload))
    try:
        try:
            dispatch_mod.main(event)
            code = 0
        except SystemExit as exc:
            if isinstance(exc.code, int):
                code = exc.code
            elif exc.code is None:
                code = 0
            else:
                code = 1
    finally:
        sys.stdin = old_stdin
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def dispatch_log_text() -> str:
    p = Path.home() / ".claude" / "hooks" / "dispatch.log"
    return p.read_text() if p.exists() else ""


# Match-all matcher variants collapse to one canonical form: the runtime treats
# them identically (they all fire for every tool / for tool-less Stop), so a
# faithful ROUTES may spell a match-all route as any of them. Specific matchers
# ("Bash", "Edit|Write|MultiEdit", ...) are NOT in this set and compare exactly.
_MATCH_ALL_MATCHERS = frozenset({None, "", ".*", "*"})


def _norm_matcher(m):
    return None if m in _MATCH_ALL_MATCHERS else m


def _route_event_full(route) -> str:
    """Full settings.json event name for a Route; accepts short ('pre') or full
    ('PreToolUse') form, and returns any out-of-scope event unchanged."""
    return EVENTS_MAP.get(route.event, route.event)


def settings_routes(event_full: str) -> list[tuple]:
    """Flattened (norm-matcher, basename) rows settings.json declares for an
    event, in declaration order across all its matcher groups."""
    rows: list[tuple] = []
    for entry in SETTINGS["hooks"].get(event_full, []):
        matcher = _norm_matcher(entry.get("matcher"))
        for hook in entry["hooks"]:
            script = hook["command"].split()[-1]
            rows.append((matcher, Path(script).name))
    return rows


def dispatch_routes(routes, event_full: str) -> list[tuple]:
    """Flattened (norm-matcher, basename) rows dispatch.ROUTES carries for an
    event, in ROUTES order. Routes for other events are ignored."""
    rows: list[tuple] = []
    for r in routes:
        if _route_event_full(r) == event_full:
            rows.append((_norm_matcher(r.matcher), route_basename(r)))
    return rows


# Broad conflict-context detector: a line that mentions `name` together with a
# conflict/drop/losing marker. Used to assert NO such line exists on a run with
# no real permission conflict (task-named markers: conflict / dropped / losing;
# stems catch dropped/dropping and losing).
_CONFLICT_MARKERS = ("conflict", "drop", "losing")


def conflict_context_lines(surface: str, name: str) -> list[str]:
    low_name = name.lower()
    out: list[str] = []
    for line in surface.splitlines():
        low = line.lower()
        if low_name in low and any(m in low for m in _CONFLICT_MARKERS):
            out.append(line)
    return out


def named_as_dropped(surface: str, name: str) -> bool:
    """True when `name` is flagged as the dropped/losing handler - it follows a
    drop verb within a few non-word chars. Distinguishes 'dropping LOSER'
    (flagged) from 'keeping WINNER, dropping LOSER' (WINNER not flagged)."""
    pat = re.compile(
        r"(?:drop\w*|losing|discard\w*|supersed\w*|overrid\w*|ignor\w*)"
        r"[^\w]{1,4}(?:the |handler ){0,2}" + re.escape(name),
        re.IGNORECASE,
    )
    return bool(pat.search(surface))


# --------------------------------------------------------------------------- #
# capture_main + HandlerTimeout (contract 14)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_handlertimeout_is_baseexception_not_exception(common):
    assert issubclass(common.HandlerTimeout, BaseException)
    assert not issubclass(common.HandlerTimeout, Exception)


@pytest.mark.unit
def test_capture_main_feeds_stdin_and_maps_int_return(common):
    def fn():
        data = json.load(sys.stdin)
        print(data["msg"])
        return data["code"]

    code, out, err = common.capture_main(fn, {"msg": "hi", "code": 7})
    assert code == 7
    assert out == "hi\n"
    assert err == ""


@pytest.mark.unit
def test_capture_main_captures_stderr(common):
    def fn():
        print("to-err", file=sys.stderr)
        return 0

    code, out, err = common.capture_main(fn, {})
    assert code == 0
    assert err == "to-err\n"


@pytest.mark.unit
def test_capture_main_non_int_return_is_zero(common):
    assert common.capture_main(lambda: None, {})[0] == 0
    assert common.capture_main(lambda: "not-an-int", {})[0] == 0


@pytest.mark.unit
def test_capture_main_systemexit_int_code(common):
    def fn():
        sys.exit(2)

    assert common.capture_main(fn, {})[0] == 2


@pytest.mark.unit
def test_capture_main_systemexit_none_is_zero(common):
    def fn():
        sys.exit()

    assert common.capture_main(fn, {})[0] == 0


@pytest.mark.unit
def test_capture_main_systemexit_non_int_is_one(common):
    def fn():
        sys.exit("boom")

    assert common.capture_main(fn, {})[0] == 1


@pytest.mark.unit
def test_capture_main_isolates_exception_to_zero_with_traceback(common):
    def fn():
        print("before-crash")
        raise ValueError("kaboom")

    code, out, err = common.capture_main(fn, {})
    assert code == 0
    assert "before-crash" in out
    assert "Traceback" in err
    assert "ValueError" in err
    assert "kaboom" in err


@pytest.mark.unit
def test_capture_main_does_not_swallow_handlertimeout(common):
    def fn():
        raise common.HandlerTimeout()

    with pytest.raises(common.HandlerTimeout):
        common.capture_main(fn, {})


@pytest.mark.unit
def test_capture_main_reduces_argv_and_restores(common, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["orig-argv0", "--flag", "value"])
    seen = {}

    def fn():
        seen["argv"] = list(sys.argv)
        return 0

    common.capture_main(fn, {})
    assert seen["argv"] == ["orig-argv0"]
    assert sys.argv == ["orig-argv0", "--flag", "value"]  # restored


@pytest.mark.unit
def test_capture_main_restores_streams(common):
    orig_out, orig_err, orig_in = sys.stdout, sys.stderr, sys.stdin
    common.capture_main(lambda: 0, {})
    assert sys.stdout is orig_out
    assert sys.stderr is orig_err
    assert sys.stdin is orig_in


@pytest.mark.unit
def test_capture_main_restores_streams_after_exception(common):
    orig_out, orig_err, orig_in = sys.stdout, sys.stderr, sys.stdin

    def fn():
        raise RuntimeError("x")

    common.capture_main(fn, {})  # swallows the non-timeout exception
    # ALL THREE streams must be restored, not just stdout - a leaked stderr or
    # stdin swap corrupts every later handler in the same dispatch.
    assert sys.stdout is orig_out
    assert sys.stderr is orig_err
    assert sys.stdin is orig_in


# --------------------------------------------------------------------------- #
# Constants (EVENTS)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_events_constant(dispatch):
    assert dispatch.EVENTS == {"pre": "PreToolUse", "post": "PostToolUse", "stop": "Stop"}


# --------------------------------------------------------------------------- #
# _matches: anchored whole-name (contract + acceptance 2)
# --------------------------------------------------------------------------- #
_ALL_POST = "Bash|Read|Grep|Glob|Agent|WebFetch|WebSearch|mcp__.*"


@pytest.mark.unit
@pytest.mark.parametrize(
    "matcher,tool,expected",
    [
        ("Edit|Write|MultiEdit", "Edit", True),
        ("Edit|Write|MultiEdit", "Write", True),
        ("Edit|Write|MultiEdit", "MultiEdit", True),
        ("Edit|Write|MultiEdit", "TodoWrite", False),
        ("Edit|Write|MultiEdit", "NotebookEdit", False),
        ("Edit|Write|MultiEdit", "Editor", False),
        ("mcp__.*", "mcp__foo", True),
        ("mcp__.*", "mcp__foo__bar", True),
        ("mcp__.*", "notmcp__foo", False),
        (_ALL_POST, "Bash", True),
        (_ALL_POST, "Task", False),
        ("Bash", "Bash", True),
        ("Bash", "bash", False),
    ],
)
def test_matches_is_fullmatch(dispatch, matcher, tool, expected):
    assert dispatch._matches(matcher, tool) is expected


# The REAL settings.json matchers (non-None, pre/post/stop scope), read via the
# same `settings_routes` helper the routing tests use. Stop routes normalize to
# None and drop out; what remains are the harness matchers the dispatcher must
# honour. Crossed with tool names DELIBERATELY OUTSIDE the finite 13-case
# `test_matches_is_fullmatch` table above, so an impl that memorizes only those
# 13 pairs (correct there, wrong everywhere else) is caught.
_REAL_MATCHERS = sorted(
    {
        matcher
        for event_full in ("PreToolUse", "PostToolUse", "Stop")
        for (matcher, _basename) in settings_routes(event_full)
        if matcher is not None
    }
)
_OUTSIDE_TOOLS = [
    "Read",
    "Glob",
    "Grep",
    "Agent",
    "WebFetch",
    "mcp__zzz",
    "mcp__a__b",
    "WriteFile",
    "MultiEditor",
    "Bashful",
    "Editor",
    "",
]
_REAL_MATCHER_OUTSIDE_PAIRS = [(m, t) for m in _REAL_MATCHERS for t in _OUTSIDE_TOOLS]


@pytest.mark.unit
@pytest.mark.parametrize("matcher,tool", _REAL_MATCHER_OUTSIDE_PAIRS)
def test_matches_equals_fullmatch_for_real_matchers_outside_table(dispatch, matcher, tool):
    """`_matches` must equal `bool(re.fullmatch(matcher, tool))` for the real
    settings.json matchers crossed with tool names OUTSIDE the finite 13-case
    parametrize - both matching (e.g. "Read" vs the mcp__.* group) and
    non-matching cases. A `_matches` that hardcodes a lookup of exactly the 13
    parametrized pairs answers these wrong and FAILS. The boolean TYPE is
    asserted too via `is` (fullmatch returns a truthy Match, not a bool)."""
    expected = bool(re.fullmatch(matcher, tool))
    assert dispatch._matches(matcher, tool) is expected


# --------------------------------------------------------------------------- #
# _parse_stdin: robust to malformed / non-dict (contract + acceptance 3)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    ["", "   ", "not json {{{", "[1, 2, 3]", "null", '"a string"', "123", "3.14"],
)
def test_parse_stdin_returns_empty_for_bad_or_non_dict(dispatch, monkeypatch, raw):
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    assert dispatch._parse_stdin() == {}


@pytest.mark.unit
def test_parse_stdin_returns_dict_payload(dispatch, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"tool_name": "Bash", "n": 1}'))
    assert dispatch._parse_stdin() == {"tool_name": "Bash", "n": 1}


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["", "not json {{{", "[1,2]", "null"])
def test_main_survives_malformed_stdin(dispatch, monkeypatch, raw):
    calls = []
    monkeypatch.setattr(dispatch, "_invoke", lambda r, p: (calls.append(r), (0, "", ""))[1])
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    with pytest.raises(SystemExit) as ei:
        dispatch.main("pre")  # tool_name "" -> no pre matcher fires
    assert ei.value.code == 0
    assert calls == []


# --------------------------------------------------------------------------- #
# Routing: real ROUTES vs settings.json (acceptance 1 + 2 negatives)
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.parametrize(
    "event_short,tool_name",
    [
        ("pre", "Bash"),
        ("pre", "Edit"),
        ("pre", "Read"),  # no Read PreToolUse matcher -> ZERO handlers
        ("pre", "TodoWrite"),  # anchoring negative -> ZERO
        ("pre", "NotebookEdit"),  # anchoring negative -> ZERO
        ("pre", "Task"),  # ZERO
        ("post", "Bash"),
        ("post", "Edit"),
        ("post", "Read"),
        ("stop", ""),
    ],
)
def test_routing_matches_settings_json(dispatch, monkeypatch, event_short, tool_name):
    expected = expected_handlers(EVENTS_MAP[event_short], tool_name)

    recorded = []
    monkeypatch.setattr(
        dispatch, "_invoke", lambda r, p: (recorded.append(r), (0, "", ""))[1]
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_name": tool_name})))
    with pytest.raises(SystemExit):
        dispatch.main(event_short)

    assert [route_basename(r) for r in recorded] == expected


@pytest.mark.integration
def test_routing_bash_pre_runs_exactly_two(dispatch, monkeypatch):
    recorded = []
    monkeypatch.setattr(
        dispatch, "_invoke", lambda r, p: (recorded.append(r), (0, "", ""))[1]
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_name": "Bash"})))
    with pytest.raises(SystemExit):
        dispatch.main("pre")
    names = [route_basename(r) for r in recorded]
    assert names == ["enforce_prd_location.py", "cartographer-echo.py"]


@pytest.mark.integration
def test_routing_stop_runs_all_six_in_order(dispatch, monkeypatch):
    recorded = []
    monkeypatch.setattr(
        dispatch, "_invoke", lambda r, p: (recorded.append(r), (0, "", ""))[1]
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({})))
    with pytest.raises(SystemExit):
        dispatch.main("stop")
    names = [route_basename(r) for r in recorded]
    assert names == expected_handlers("Stop", "")
    assert len(names) == 6


@pytest.mark.integration
def test_routes_bidirectionally_equal_settings_for_pre_post_stop(dispatch):
    """dispatch.ROUTES must reproduce EXACTLY the pre/post/stop routes that
    settings.json declares - identical (event, matcher, handler basename, order)
    per event, with no route dropped, added, or frozen into the wrong slot.

    ROUTES is intentionally a baked literal in dispatch.py (NOT read from
    settings.json at runtime), so this is an equivalence check between two
    independent sources, not a derivation test. It compares the FULL set of
    pre/post/stop routes, so a route frozen in a slot the routing params never
    exercise is caught too. Only these three events are in scope;
    SessionStart / UserPromptSubmit / Notification are ignored, never required.
    """
    for event_full in ("PreToolUse", "PostToolUse", "Stop"):
        expected = settings_routes(event_full)
        actual = dispatch_routes(dispatch.ROUTES, event_full)
        assert actual == expected, (
            f"{event_full}: ROUTES {actual!r} != settings.json {expected!r}"
        )


@pytest.mark.integration
def test_main_routes_through_module_level_matches(dispatch, monkeypatch):
    """`main` must select handlers by consulting the MODULE-LEVEL
    `dispatch._matches`, not a private inline matcher of its own. Patching
    `_matches` to always return False must collapse a normally-matching run
    (event "pre" + tool "Bash", where BOTH PreToolUse routes carry non-None
    matchers) to ZERO invoked handlers. An impl with its own inline matcher
    ignores the patch and still records handlers - exactly the fraud this kills.
    Not a Stop event on purpose: Stop routes have matcher None and run
    regardless of `_matches`, so they could never collapse to zero."""
    monkeypatch.setattr(dispatch, "_matches", lambda *_: False)
    recorded = []
    monkeypatch.setattr(
        dispatch, "_invoke", lambda r, p: (recorded.append(r), (0, "", ""))[1]
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_name": "Bash"})))
    with pytest.raises(SystemExit):
        dispatch.main("pre")

    assert recorded == []


@pytest.mark.integration
def test_routes_point_at_real_files_with_settings_timeouts(dispatch):
    """ROUTES must be FAITHFUL to settings.json beyond the routing graph: every
    route's per-handler timeout must equal the settings.json timeout, and every
    handler path must resolve to a real, absolute, existing file. The bidirectional
    equivalence test above compares only (matcher, basename, order); a ROUTES table
    with fake paths or bogus timeouts would pass it while the dispatcher silently
    invoked ZERO real hooks (a silent enforcement bypass). This pins the fidelity
    the graph check omits."""

    def settings_rows_with_timeout(event_full):
        rows = []
        for entry in SETTINGS["hooks"].get(event_full, []):
            matcher = _norm_matcher(entry.get("matcher"))
            for hook in entry["hooks"]:
                script = hook["command"].split()[-1]
                rows.append((matcher, Path(script).name, hook.get("timeout")))
        return rows

    for event_full in ("PreToolUse", "PostToolUse", "Stop"):
        expected = settings_rows_with_timeout(event_full)
        actual = [
            (_norm_matcher(r.matcher), route_basename(r), r.timeout)
            for r in dispatch.ROUTES
            if _route_event_full(r) == event_full
        ]
        assert actual == expected, f"{event_full}: {actual!r} != {expected!r}"

    for r in dispatch.ROUTES:
        p = Path(r.path)
        assert p.is_absolute(), f"ROUTES path not absolute: {r.path!r}"
        assert p.exists(), f"ROUTES path missing: {r.path!r}"


# --------------------------------------------------------------------------- #
# _aggregate: exit code, err passthrough, JSON merge (acceptance 4,5,9,10)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_aggregate_block_propagates_and_preserves_stderr(dispatch, capsys):
    code, out = dispatch._aggregate([(0, "", ""), (2, "", "BLOCK-REASON"), (0, "", "")])
    assert code == 2
    assert "BLOCK-REASON" in capsys.readouterr().err


@pytest.mark.unit
def test_aggregate_all_zero_is_zero(dispatch, capsys):
    assert dispatch._aggregate([(0, "", ""), (0, "", "")])[0] == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    "codes,expected",
    [([1, 3], 0), ([0, 1], 0), ([3], 0), ([2, 1], 2), ([0, 2], 2), ([1, 2, 3], 2)],
)
def test_aggregate_normalizes_non_0_2_codes(dispatch, capsys, codes, expected):
    results = [(c, "", "") for c in codes]
    assert dispatch._aggregate(results)[0] == expected


@pytest.mark.unit
def test_aggregate_concatenates_additional_context(dispatch, capsys):
    results = [(0, env(additionalContext="AAA"), ""), (0, env(additionalContext="BBB"), "")]
    code, out = dispatch._aggregate(results)
    assert code == 0
    merged = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert merged == "AAA\n---\nBBB"


@pytest.mark.unit
def test_aggregate_keeps_context_when_blocked(dispatch, capsys):
    results = [
        (2, env(additionalContext="AAA"), "blocked"),
        (0, env(additionalContext="BBB"), ""),
    ]
    code, out = dispatch._aggregate(results)
    assert code == 2
    assert json.loads(out)["hookSpecificOutput"]["additionalContext"] == "AAA\n---\nBBB"


@pytest.mark.unit
def test_aggregate_drops_non_json_stdout(dispatch, capsys):
    results = [(0, "raw non-JSON noise", ""), (0, env(additionalContext="ENV"), "")]
    code, out = dispatch._aggregate(results)
    obj = json.loads(out)  # must be a single valid JSON object
    assert obj["hookSpecificOutput"]["additionalContext"] == "ENV"
    assert "raw non-JSON noise" not in out


@pytest.mark.unit
def test_aggregate_all_non_json_yields_empty_stdout(dispatch, capsys):
    code, out = dispatch._aggregate([(0, "foo", ""), (0, "bar baz", "")])
    assert out.strip() == ""


@pytest.mark.unit
def test_aggregate_logs_dict_stdout_with_no_hookspecificoutput_key(dispatch, capsys):
    """PRD 00071: a handler emitting valid JSON that IS a dict but carries no
    hookSpecificOutput key must not vanish with zero trace. The two adjacent
    failure paths just above it - non-JSON stdout, non-object stdout - both
    call log(...); today this third path (dict, but no hookSpecificOutput key)
    falls through `if not isinstance(hso, dict): continue` with no log call at
    all. Its stdout must still contribute nothing to the merged envelope."""
    results = [
        (0, json.dumps({"decision": "block", "reason": "no envelope here"}), ""),
        (0, env(additionalContext="OK"), ""),
    ]
    names = ["NOENV", "PLAIN"]
    code, out = dispatch._aggregate(results, names)

    hso = json.loads(out)["hookSpecificOutput"]
    assert hso == {"additionalContext": "OK"}  # NOENV's payload contributes nothing

    log_text = dispatch_log_text()
    assert "noenv" in log_text.lower(), log_text


@pytest.mark.unit
def test_aggregate_well_formed_envelope_logs_nothing(dispatch, capsys):
    """NEGATIVE CONTROL for the missing-hookSpecificOutput log line above,
    sharing its detection surface. A handler whose stdout IS a well-formed
    hookSpecificOutput envelope must not be reported as dropped/faulty.
    Without this, an impl that logs unconditionally for every dict stdout
    (well-formed envelopes included) would pass the test above for the wrong
    reason."""
    results = [(0, env(additionalContext="FINE"), "")]
    names = ["FINE"]
    code, out = dispatch._aggregate(results, names)
    hso = json.loads(out)["hookSpecificOutput"]
    assert hso["additionalContext"] == "FINE"

    log_text = dispatch_log_text()
    assert "fine" not in log_text.lower(), log_text


@pytest.mark.unit
def test_aggregate_unknown_permission_decision_survives(dispatch, capsys):
    """An unrecognized permissionDecision must NOT silently vanish - it passes
    through (parity with the separate hooks) instead of being dropped with no
    trace, which in a hook-enforcement system would be a silent bypass."""
    results = [(0, env(permissionDecision="block", permissionDecisionReason="RB"), "")]
    code, out = dispatch._aggregate(results)
    hso = json.loads(out)["hookSpecificOutput"]
    assert hso["permissionDecision"] == "block"
    assert hso["permissionDecisionReason"] == "RB"


@pytest.mark.unit
@pytest.mark.parametrize("order", [["deny", "block"], ["block", "deny"]])
def test_aggregate_known_deny_beats_unknown_decision(dispatch, capsys, order):
    """A known most-restrictive decision still wins over an unranked unknown,
    regardless of order."""
    results = [
        (0, env(permissionDecision=d, permissionDecisionReason=d.upper()), "")
        for d in order
    ]
    hso = json.loads(dispatch._aggregate(results)[1])["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"


@pytest.mark.unit
def test_aggregate_non_str_additional_context_is_isolated(dispatch, capsys):
    """A handler emitting a non-str additionalContext must not crash the whole
    aggregation (per-handler isolation) - it is skipped while a co-running valid
    envelope still merges."""
    results = [
        (0, json.dumps({"hookSpecificOutput": {"additionalContext": 123}}), ""),
        (0, env(additionalContext="OK"), ""),
    ]
    code, out = dispatch._aggregate(results)  # must not raise
    hso = json.loads(out)["hookSpecificOutput"]
    assert hso["additionalContext"] == "OK"


@pytest.mark.unit
@pytest.mark.parametrize(
    "order,winner,winner_reason",
    [
        (["deny", "allow"], "deny", "RD"),
        (["allow", "deny"], "deny", "RD"),
        (["ask", "allow"], "ask", "RK"),
        (["allow", "ask"], "ask", "RK"),
        (["deny", "ask"], "deny", "RD"),
        (["ask", "deny"], "deny", "RD"),
    ],
)
def test_aggregate_permission_most_restrictive(dispatch, capsys, order, winner, winner_reason):
    reasons = {"deny": "RD", "ask": "RK", "allow": "RA"}
    results = [
        (0, env(permissionDecision=d, permissionDecisionReason=reasons[d]), "") for d in order
    ]
    hso = json.loads(dispatch._aggregate(results)[1])["hookSpecificOutput"]
    assert hso["permissionDecision"] == winner
    assert hso["permissionDecisionReason"] == winner_reason  # atomic pair


@pytest.mark.unit
def test_aggregate_merges_context_and_permission_into_one_envelope(dispatch, capsys):
    results = [
        (0, env(additionalContext="A", permissionDecision="allow", permissionDecisionReason="ra"), ""),
        (0, env(additionalContext="B", permissionDecision="deny", permissionDecisionReason="rd"), ""),
    ]
    hso = json.loads(dispatch._aggregate(results)[1])["hookSpecificOutput"]
    assert hso["additionalContext"] == "A\n---\nB"
    assert hso["permissionDecision"] == "deny"
    assert hso["permissionDecisionReason"] == "rd"


# --------------------------------------------------------------------------- #
# _aggregate: non-blocking handler stderr excluded from the block reason
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_non_blocking_stderr_excluded_from_block_reason(dispatch, capsys):
    """When the aggregate exit code is 2, only the stderr of handlers that
    themselves returned 2 may reach the real stderr - a non-blocking sibling's
    stderr must not be concatenated into the model-visible block reason. This
    MUST fail against the current implementation, which writes every handler's
    stderr to real stderr regardless of that handler's own exit code."""
    results = [
        (2, "", "BLOCKED: dangerous command\n"),
        (0, "", "[some-hook] non-blocking note\n"),
    ]
    names = ["BLOCKER", "NOTER"]
    code, out = dispatch._aggregate(results, names)
    assert code == 2
    err = capsys.readouterr().err
    assert "BLOCKED: dangerous command" in err
    assert "non-blocking note" not in err


@pytest.mark.unit
def test_non_blocking_stderr_recorded_in_dispatch_log(dispatch, capsys):
    """A non-blocking handler's stderr, suppressed from real stderr on a
    blocking run, must not vanish silently - it lands in the dispatch log."""
    results = [
        (2, "", "BLOCKED: dangerous command\n"),
        (0, "", "[some-hook] non-blocking note\n"),
    ]
    names = ["BLOCKER", "NOTER"]
    dispatch._aggregate(results, names)
    capsys.readouterr()  # drain; real-stderr content is not under test here
    assert "non-blocking note" in dispatch_log_text()


@pytest.mark.unit
def test_stderr_not_suppressed_when_no_handler_blocks(dispatch, capsys):
    """When the aggregate exit code is 0, current behavior is preserved: every
    handler's stderr still reaches real stderr. Locks in that the block-reason
    fix does not over-suppress a non-blocking run."""
    results = [
        (0, "", "[hook-a] note-a\n"),
        (0, "", "[hook-b] note-b\n"),
    ]
    names = ["A", "B"]
    code, out = dispatch._aggregate(results, names)
    assert code == 0
    err = capsys.readouterr().err
    assert "note-a" in err
    assert "note-b" in err


@pytest.mark.unit
def test_blocking_stderr_order_preserved_across_handlers(dispatch, capsys):
    """When multiple handlers block, their stderr must reach real stderr in
    handler order."""
    results = [
        (2, "", "FIRST-BLOCK\n"),
        (2, "", "SECOND-BLOCK\n"),
    ]
    names = ["FIRST", "SECOND"]
    code, out = dispatch._aggregate(results, names)
    assert code == 2
    err = capsys.readouterr().err
    assert err.index("FIRST-BLOCK") < err.index("SECOND-BLOCK")


# --------------------------------------------------------------------------- #
# Merge-conflict warning names the losing handler (acceptance 6)
# --------------------------------------------------------------------------- #
@pytest.mark.integration
def test_merge_conflict_warns_naming_losing_handler(dispatch, monkeypatch, tmp_path, capsys):
    winner = make_route(
        tmp_path,
        "winner",
        """
        import json
        def run(payload):
            return (0, json.dumps({"hookSpecificOutput": {
                "permissionDecision": "deny", "permissionDecisionReason": "FIRST"}}), "")
        """,
    )
    loser = make_route(
        tmp_path,
        "loser",
        """
        import json
        def run(payload):
            return (0, json.dumps({"hookSpecificOutput": {
                "permissionDecision": "deny", "permissionDecisionReason": "SECOND"}}), "")
        """,
    )
    monkeypatch.setattr(dispatch, "ROUTES", [winner, loser])
    code, out, err = run_main(dispatch, "pre", {"tool_name": "Bash"}, capsys)

    hso = json.loads(out)["hookSpecificOutput"]
    assert hso["permissionDecisionReason"] == "FIRST"  # earlier wins the tie

    surface = err + dispatch_log_text()
    assert "LOSER" in surface  # names the losing handler
    assert "permissionDecision" in surface  # names the dropped key
    # A real conflict names only the LOSER as dropped, never the WINNER. This
    # kills the "dump every handler name as dropped" impl that never actually
    # detects which one lost.
    assert not named_as_dropped(surface, "WINNER"), surface


@pytest.mark.integration
def test_no_conflict_emits_no_conflict_warning(dispatch, monkeypatch, tmp_path, capsys):
    """When only ONE handler sets permissionDecision there is no real conflict,
    so the dispatcher must emit no conflict/dropped/losing warning naming any
    handler. Guards against an impl that warns unconditionally on every run
    (dumping handler names, winner included) and so passed the conflict test by
    accident. Two handlers run; only SOLO decides, PLAIN just adds context.
    """
    solo = make_route(
        tmp_path,
        "solo",
        """
        import json
        def run(payload):
            return (0, json.dumps({"hookSpecificOutput": {
                "permissionDecision": "deny", "permissionDecisionReason": "ONLY"}}), "")
        """,
    )
    plain = make_route(
        tmp_path,
        "plain",
        """
        import json
        def run(payload):
            return (0, json.dumps({"hookSpecificOutput": {"additionalContext": "CTX"}}), "")
        """,
    )
    monkeypatch.setattr(dispatch, "ROUTES", [solo, plain])
    code, out, err = run_main(dispatch, "pre", {"tool_name": "Bash"}, capsys)

    hso = json.loads(out)["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"  # sole decision survives intact
    assert hso["permissionDecisionReason"] == "ONLY"

    surface = err + dispatch_log_text()
    # Neither handler may surface in a conflict/dropped/losing line - there was
    # no conflict to warn about.
    assert conflict_context_lines(surface, "SOLO") == [], surface
    assert conflict_context_lines(surface, "PLAIN") == [], surface


@pytest.mark.integration
def test_merge_conflict_names_true_losers_when_winner_route_is_last(
    dispatch, monkeypatch, tmp_path, capsys
):
    """Three routes ranked [allow, allow, deny] in route order: the highest-
    ranked decision (deny) belongs to the LAST route, not the first. Guards
    against a "loser = last route name" hardcode - that shape would instead
    name the true winner (THIRD_DENY) as dropped and miss both real losers
    (FIRST_ALLOW, SECOND_ALLOW), so it cannot pass this test."""
    first_allow = make_route(
        tmp_path,
        "first_allow",
        """
        import json
        def run(payload):
            return (0, json.dumps({"hookSpecificOutput": {
                "permissionDecision": "allow", "permissionDecisionReason": "FIRST"}}), "")
        """,
    )
    second_allow = make_route(
        tmp_path,
        "second_allow",
        """
        import json
        def run(payload):
            return (0, json.dumps({"hookSpecificOutput": {
                "permissionDecision": "allow", "permissionDecisionReason": "SECOND"}}), "")
        """,
    )
    third_deny = make_route(
        tmp_path,
        "third_deny",
        """
        import json
        def run(payload):
            return (0, json.dumps({"hookSpecificOutput": {
                "permissionDecision": "deny", "permissionDecisionReason": "THIRD"}}), "")
        """,
    )
    monkeypatch.setattr(dispatch, "ROUTES", [first_allow, second_allow, third_deny])
    code, out, err = run_main(dispatch, "pre", {"tool_name": "Bash"}, capsys)

    hso = json.loads(out)["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"  # highest rank wins even though last
    assert hso["permissionDecisionReason"] == "THIRD"  # winner's own reason survives

    surface = err + dispatch_log_text()
    # Both allow handlers are real losers - they never won the rank comparison.
    assert conflict_context_lines(surface, "FIRST_ALLOW") != [], surface
    assert conflict_context_lines(surface, "SECOND_ALLOW") != [], surface
    # The deny handler won; it must never be named as dropped/losing.
    assert conflict_context_lines(surface, "THIRD_DENY") == [], surface


# --------------------------------------------------------------------------- #
# Merge-conflict warning generalizes beyond permissionDecision (PRD 00071)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_aggregate_non_special_key_conflict_earlier_wins_and_warns(dispatch, capsys):
    """PRD 00071: on ANY hookSpecificOutput key conflict - not just
    permissionDecision - the earlier handler's value wins AND a warning names
    both the losing handler and the dropped key. Today's
    `other.setdefault(key, value)` keeps the earlier value (right) but never
    reports the drop (wrong): SECOND's "customField" value vanishes with no
    stderr line and no dispatch.log entry."""
    results = [
        (0, env(customField="FIRST"), ""),
        (0, env(customField="SECOND"), ""),
    ]
    names = ["WINNER", "LOSER"]
    code, out = dispatch._aggregate(results, names)

    hso = json.loads(out)["hookSpecificOutput"]
    assert hso["customField"] == "FIRST"  # earlier handler's value still wins

    surface = capsys.readouterr().err + dispatch_log_text()
    loser_lines = conflict_context_lines(surface, "LOSER")
    assert loser_lines, surface  # names the losing handler
    assert any("customField" in ln for ln in loser_lines), surface  # names the dropped key
    assert conflict_context_lines(surface, "WINNER") == [], surface


@pytest.mark.unit
def test_aggregate_same_key_same_value_no_conflict_warning(dispatch, capsys):
    """NEGATIVE CONTROL for the key-conflict warning above: two handlers
    agreeing on the same non-special key's value is not a conflict, so no
    drop/conflict line may name either. Without this, an impl that warns on
    every repeated key - agreement included - would pass the conflict test
    above for the wrong reason."""
    results = [
        (0, env(customField="SAME"), ""),
        (0, env(customField="SAME"), ""),
    ]
    names = ["FIRST", "SECOND"]
    code, out = dispatch._aggregate(results, names)
    hso = json.loads(out)["hookSpecificOutput"]
    assert hso["customField"] == "SAME"

    surface = capsys.readouterr().err + dispatch_log_text()
    assert conflict_context_lines(surface, "FIRST") == [], surface
    assert conflict_context_lines(surface, "SECOND") == [], surface


@pytest.mark.unit
def test_aggregate_single_handler_setting_key_no_conflict_warning(dispatch, capsys):
    """NEGATIVE CONTROL: only ONE handler sets a given non-special key (the
    other only sets additionalContext) - there is no second value to drop, so
    no conflict/drop line may name either handler."""
    results = [
        (0, env(customField="ONLY"), ""),
        (0, env(additionalContext="CTX"), ""),
    ]
    names = ["SOLO", "PLAIN"]
    code, out = dispatch._aggregate(results, names)
    hso = json.loads(out)["hookSpecificOutput"]
    assert hso["customField"] == "ONLY"

    surface = capsys.readouterr().err + dispatch_log_text()
    assert conflict_context_lines(surface, "SOLO") == [], surface
    assert conflict_context_lines(surface, "PLAIN") == [], surface


# --------------------------------------------------------------------------- #
# Crash / broken-import isolation (acceptance 7, 8)
# --------------------------------------------------------------------------- #
@pytest.mark.integration
def test_raising_handler_is_isolated_siblings_run(dispatch, monkeypatch, tmp_path, capsys):
    raiser = make_route(
        tmp_path,
        "raiser",
        """
        def run(payload):
            raise RuntimeError("BOOM-HANDLER")
        """,
    )
    ok = make_route(
        tmp_path,
        "survivor",
        """
        import json
        def run(payload):
            return (0, json.dumps({"hookSpecificOutput": {"additionalContext": "SURVIVED"}}), "")
        """,
    )
    monkeypatch.setattr(dispatch, "ROUTES", [raiser, ok])
    code, out, err = run_main(dispatch, "pre", {"tool_name": "Bash"}, capsys)

    assert code == 0  # final exit reflects only surviving (0) handlers
    assert json.loads(out)["hookSpecificOutput"]["additionalContext"] == "SURVIVED"
    surface = err + dispatch_log_text()
    assert "BOOM-HANDLER" in surface or "RuntimeError" in surface


@pytest.mark.integration
def test_import_error_handler_is_isolated_siblings_run(dispatch, monkeypatch, tmp_path, capsys):
    bad = make_route(
        tmp_path,
        "badimport",
        """
        raise RuntimeError("IMPORT-BOOM")
        """,
    )
    ok = make_route(
        tmp_path,
        "afterbad",
        """
        import json
        def run(payload):
            return (0, json.dumps({"hookSpecificOutput": {"additionalContext": "AFTERBAD"}}), "")
        """,
    )
    monkeypatch.setattr(dispatch, "ROUTES", [bad, ok])
    code, out, err = run_main(dispatch, "pre", {"tool_name": "Bash"}, capsys)

    assert code == 0
    assert json.loads(out)["hookSpecificOutput"]["additionalContext"] == "AFTERBAD"
    surface = err + dispatch_log_text()
    assert "IMPORT-BOOM" in surface or "RuntimeError" in surface


# --------------------------------------------------------------------------- #
# Noisy non-JSON stdout co-running with an envelope (acceptance 9, pipeline)
# --------------------------------------------------------------------------- #
@pytest.mark.integration
def test_noisy_stdout_does_not_corrupt_merged_json(dispatch, monkeypatch, tmp_path, capsys):
    noisy = make_route(
        tmp_path,
        "noisy",
        """
        def run(payload):
            return (0, "this is raw text, definitely not json\\n", "")
        """,
    )
    envelope = make_route(
        tmp_path,
        "envelope",
        """
        import json
        def run(payload):
            return (0, json.dumps({"hookSpecificOutput": {"additionalContext": "CLEAN"}}), "")
        """,
    )
    monkeypatch.setattr(dispatch, "ROUTES", [noisy, envelope])
    code, out, err = run_main(dispatch, "pre", {"tool_name": "Bash"}, capsys)

    obj = json.loads(out)  # single valid JSON object
    assert obj["hookSpecificOutput"]["additionalContext"] == "CLEAN"
    assert "raw text" not in out


# --------------------------------------------------------------------------- #
# Subprocess fallback for a run-less script (acceptance 11)
# --------------------------------------------------------------------------- #
@pytest.mark.integration
def test_subprocess_fallback_matches_direct_run(dispatch, tmp_path):
    route = make_route(
        tmp_path,
        "norun",
        """
        import sys
        if __name__ == "__main__":
            sys.stdin.read()
            sys.stdout.write("SUBPROC-RAN")
            sys.exit(0)
        """,
    )
    payload = {"tool_name": "Bash", "n": 1}
    code, out, err = dispatch._invoke(route, payload)

    direct = subprocess.run(
        [sys.executable, route.path],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert code == direct.returncode == 0
    assert out == direct.stdout == "SUBPROC-RAN"


# --------------------------------------------------------------------------- #
# SIGALRM per-handler cap (acceptance 12) + teardown-race (acceptance 13)
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.skipif(not _HAS_SIGALRM, reason="SIGALRM unavailable on this platform")
def test_sigalrm_caps_slow_handler(dispatch, tmp_path):
    slow = make_route(
        tmp_path,
        "slow",
        """
        import time
        def run(payload):
            try:
                time.sleep(3)
            except Exception:
                pass
            return (0, "SLOW-FINISHED", "")
        """,
        timeout=1,
    )
    start = time.monotonic()
    code, out, err = dispatch._invoke(slow, {"tool_name": "Bash"})
    elapsed = time.monotonic() - start

    assert elapsed < 2.5  # capped at ~1s, did not sleep the full 3s
    assert code == 0
    assert "SLOW-FINISHED" not in out
    assert out == ""
    assert err != ""  # a timeout note is returned on stderr


@pytest.mark.integration
@pytest.mark.skipif(not _HAS_SIGALRM, reason="SIGALRM unavailable on this platform")
def test_sigalrm_next_handler_still_runs(dispatch, monkeypatch, tmp_path, capsys):
    slow = make_route(
        tmp_path,
        "slow",
        """
        import time
        def run(payload):
            try:
                time.sleep(3)
            except Exception:
                pass
            return (0, "", "")
        """,
        timeout=1,
    )
    fast = make_route(
        tmp_path,
        "fast",
        """
        import json
        def run(payload):
            return (0, json.dumps({"hookSpecificOutput": {"additionalContext": "FAST"}}), "")
        """,
    )
    monkeypatch.setattr(dispatch, "ROUTES", [slow, fast])
    start = time.monotonic()
    code, out, err = run_main(dispatch, "pre", {"tool_name": "Bash"}, capsys)
    elapsed = time.monotonic() - start

    assert elapsed < 2.5
    assert code == 0
    assert json.loads(out)["hookSpecificOutput"]["additionalContext"] == "FAST"


@pytest.mark.integration
@pytest.mark.skipif(not _HAS_SIGALRM, reason="SIGALRM unavailable on this platform")
def test_teardown_race_no_false_timeout(dispatch, tmp_path):
    """The marked `signal.alarm(0)` in `_invoke` must cancel the per-handler
    cap the INSTANT the handler returns - not merely "eventually" in
    `finally`, after the malformed-return validation has already run. A
    handler that COMPLETED must never be killed by its own alarm firing
    during that validation-and-return path.

    A stub that sleeps close to its cap cannot expose this: measurement
    showed the actual gap between the fixed cancellation point and
    finally's fallback cancellation is tens to ~1500 nanoseconds - far
    below the resolution of any real wall-clock SIGALRM/setitimer (0 false
    timeouts observed in 2000 trials of a handler-armed 1-microsecond
    timer, and 0 in 30 trials sleeping to within 5ms of a 1s cap). A
    sleep-based race for this specific invariant is a coin flip that never
    lands - it would just be a differently-shaped dead test.

    So instead of racing wall-clock luck, the stub's returned triple probes
    the cap's actual state DETERMINISTICALLY: `signal.alarm(0)` atomically
    cancels whatever is pending and reports how many seconds were left on
    it (0 if nothing was pending). The triple is a `tuple` subclass whose
    `__len__` - invoked by `_invoke`'s own `len(result) == 3` check, which
    runs immediately after the marked line when it is present - records
    that probe's result. Fixed code has already cancelled the cap by then,
    so the probe reports 0 every time. With the marked line removed, the
    1s cap armed at `_invoke`'s entry is still pending when validation (and
    the probe) runs, so it reports the true remaining time (non-zero) -
    exactly the condition under which a completed handler could still be
    killed by its own alarm.
    """
    quick = make_route(
        tmp_path,
        "quick",
        """
        import signal

        _observed = []

        class _RaceTuple(tuple):
            def __len__(self):
                _observed.append(signal.alarm(0))
                return tuple.__len__(self)

        def run(payload):
            return _RaceTuple((0, "QUICK-DONE", ""))
        """,
        timeout=1,
    )
    for _ in range(20):
        code, out, err = dispatch._invoke(quick, {"tool_name": "Bash"})
        assert code == 0
        assert "QUICK-DONE" in out  # completed, never mislabeled timed-out

    observed = dispatch._load_handler(quick.path)._observed
    assert observed == [0] * 20, (
        f"the cap must already be cancelled by the time _invoke validates "
        f"the handler's return; leftover armed seconds per call: {observed!r}"
    )


# --------------------------------------------------------------------------- #
# run(payload) -> tuple[int, str, str]: the DOCUMENTED handler contract
# (PRD 00071, feature "run() interface").
#
# The handler OWNS its capture and RETURNS (exit_code, stdout, stderr).
# `_invoke` calls `mod.run(payload)` directly and surfaces that triple as-is.
#
# The failure mode these tests exist to make unshippable: if `_invoke` keeps an
# OUTER `capture_main(lambda: mod.run(payload), payload)` around a handler that
# now returns a real triple, `capture_main` maps the non-int return to code 0
# with empty captured streams - every block (exit 2) and every stdout envelope
# vanishes silently, with no error and no log line.
# --------------------------------------------------------------------------- #
SCRIPTS_DIR = HOOKS_DIR.parent / "skills" / "run-autopilot" / "scripts"

# Handlers whose benign path is hermetic (no fs writes, no git, no network) and
# so is safe to exercise in-process here. Broad per-handler behavior parity for
# all twelve lives in test_handler_run_parity.py.
_ENFORCE_PRD_LOCATION = HOOKS_DIR / "enforce_prd_location.py"
_OBSERVE_TOOL = HOOKS_DIR / "observe_tool.py"
_REVIEW_COVERAGE_HOOK = SCRIPTS_DIR / "review_coverage_hook.py"

# Markers that flip autopilot/nested handlers off their benign early-return
# path; cleared so these runs observe quiescent state whatever pytest inherited.
_QUIESCENT_ENV = ("_AUTOPILOT_LOOP", "CLAUDE_NESTED", "CLAUDE_SESSION_NAME")


@contextlib.contextmanager
def require_in_process_work(mod, who: str):
    """Witness that `mod.run(payload)` did the handler's real work IN THIS PROCESS.

    PRD 00071 exists to REMOVE the per-hook fork/exec, so `run(payload)` must do
    its work IN-PROCESS. A `run()` that just re-execs its own script -
    `subprocess.run([sys.executable, __file__], input=json.dumps(payload), ...)`
    - reproduces the exit code, stdout, stderr and every side-effect file BY
    CONSTRUCTION (it is literally the same program), so it satisfies every
    parity and side-effect assertion in this suite while paying the fork/exec
    twice. No output-based oracle can tell it apart from a real implementation.

    Denying spawns BY NAME cannot tell it apart either: a one-line `/bin/sh` shim
    (or a renamed interpreter) hides the interpreter inside the file body, where
    argv inspection cannot see it. So this oracle is POSITIVE instead - the
    handler module's own entry point is wrapped with a recorder, and `run()` must
    make it fire. A child process cannot see a patch applied to the parent's
    module object, so EVERY subprocess-shaped run() leaves the recorder unfired
    however the child is launched; so does a no-op `return (0, "", "")`.

    Because it witnesses work instead of policing spawns, a handler's own
    legitimate child processes still run: review_coverage_hook delegates to
    check_review_file.py via `python3`, enforce_prd_location shells out to
    `git rev-parse`. That is pre-existing handler work, not the dispatcher
    overhead this PRD removes.
    """
    own = {
        name: obj
        for name, obj in vars(mod).items()
        if isinstance(obj, types.FunctionType) and name != "run"
    }
    # `main` is the documented entry point of every handler script; when a module
    # has one, only IT counts as the work witness (a trivial helper must not
    # stand in for the handler's real work). Otherwise fall back to any of the
    # module's own functions.
    targets = {"main": own["main"]} if "main" in own else own
    assert targets, f"{who}: module exposes no work function to witness"
    fired: list[str] = []

    def recorder(name, real):
        @functools.wraps(real)
        def wrapper(*args, **kwargs):
            fired.append(name)
            return real(*args, **kwargs)

        return wrapper

    for name, real in targets.items():
        setattr(mod, name, recorder(name, real))
    try:
        yield fired
    finally:
        for name, real in targets.items():
            setattr(mod, name, real)


def direct_run(mod, payload):
    """Call `mod.run(payload)` with NO outer capture_main - the real contract.

    A handler that EXITS or RAISES instead of RETURNING is a contract violation;
    reporting it as a plain failure (not a stray SystemExit/OSError error) keeps
    the red message pointed at the missing contract. The call is witnessed so a
    `run()` that re-execs its own script (or does nothing at all) fails instead
    of faking the contract.
    """
    try:
        with require_in_process_work(mod, f"{mod.__name__}.run(payload)") as fired:
            result = mod.run(payload)
    except SystemExit as exc:
        pytest.fail(
            f"{mod.__name__}.run(payload) exited (SystemExit {exc.code!r}) instead of "
            f"returning (exit_code, stdout, stderr)"
        )
    except Exception as exc:
        pytest.fail(
            f"{mod.__name__}.run(payload) raised {type(exc).__name__}: {exc}; it must "
            f"return (exit_code, stdout, stderr)"
        )
    assert fired, (
        f"{mod.__name__}.run(payload) returned without ever entering the module's "
        f"own work function IN THIS PROCESS. A re-exec (any shape: "
        f"[sys.executable, __file__], a renamed interpreter, a /bin/sh shim, "
        f"os.posix_spawn) runs the work in a CHILD, which cannot touch this module "
        f"object; a no-op never enters it at all."
    )
    return result


def assert_triple(result, who: str):
    """Assert `result` is a real (int, str, str) triple and unpack it."""
    assert isinstance(result, tuple), (
        f"{who}: run(payload) must return a tuple, got "
        f"{type(result).__name__} ({result!r})"
    )
    assert len(result) == 3, f"{who}: run(payload) must return 3 items, got {result!r}"
    code, out, err = result
    assert isinstance(code, int) and not isinstance(code, bool), (
        f"{who}: exit code must be an int, got {type(code).__name__} ({code!r})"
    )
    assert isinstance(out, str), f"{who}: stdout must be a str, got {type(out).__name__}"
    assert isinstance(err, str), f"{who}: stderr must be a str, got {type(err).__name__}"
    return code, out, err


@pytest.mark.integration
@pytest.mark.parametrize(
    "handler,payload",
    [
        pytest.param(
            _ENFORCE_PRD_LOCATION,
            {"tool_name": "Bash", "tool_input": {"command": "ls /tmp"}},
            id="enforce_prd_location",
        ),
        pytest.param(_OBSERVE_TOOL, {"tool_name": ""}, id="observe_tool"),
        pytest.param(_REVIEW_COVERAGE_HOOK, {"session_id": "s"}, id="review_coverage_hook"),
    ],
)
def test_handler_run_returns_triple_when_called_directly(
    dispatch, monkeypatch, handler, payload
):
    """A real handler's `run(payload)` must RETURN (int, str, str) on its own -
    no outer capture_main, no SystemExit, no reliance on the dispatcher to
    manufacture the triple. Each payload rides a benign, hermetic path, so the
    only thing under test is the shape of the return value."""
    for name in _QUIESCENT_ENV:
        monkeypatch.delenv(name, raising=False)
    mod = dispatch._load_handler(str(handler))
    code, out, err = assert_triple(direct_run(mod, payload), handler.name)
    assert code == 0, f"{handler.name}: benign payload must not block (got {code})"
    assert out == "", f"{handler.name}: benign payload must emit no envelope ({out!r})"


@pytest.mark.integration
def test_blocking_handler_run_returns_exit_2_and_reason_when_called_directly(
    dispatch, monkeypatch
):
    """A BLOCK must survive a direct `run(payload)` call: exit code 2 in the
    returned triple and the BLOCKED reason in the returned stderr. Today the
    handler exits (SystemExit 2) and only `capture_main` turns that into a
    triple; with the contract in place the block is the handler's own return
    value, so the dispatcher cannot silently downgrade it to 0."""
    for name in _QUIESCENT_ENV:
        monkeypatch.delenv(name, raising=False)
    payload = {"tool_name": "Bash", "tool_input": {"command": "ls backlog/"}}
    mod = dispatch._load_handler(str(_ENFORCE_PRD_LOCATION))
    code, out, err = assert_triple(direct_run(mod, payload), "enforce_prd_location.py")
    assert code == 2, "a repo-root lifecycle path must block (exit 2) from run() itself"
    assert "BLOCKED" in err, f"the block reason must ride the returned stderr: {err!r}"
    assert out == ""


@pytest.mark.integration
def test_invoke_surfaces_handler_triple_unchanged(dispatch, tmp_path):
    """THE regression guard for the double-wrap. `_invoke` must return the
    handler's own (2, stdout, stderr) byte-for-byte. Wrapped in an outer
    capture_main this collapses to (0, "", "") - block lost, envelope lost, no
    error, no log line."""
    route = make_route(
        tmp_path,
        "triple",
        """
        import json
        def run(payload):
            return (
                2,
                json.dumps({"hookSpecificOutput": {"additionalContext": "TRIPLE-CTX"}}),
                "TRIPLE-STDERR\\n",
            )
        """,
    )
    result = dispatch._invoke(route, {"tool_name": "Bash"})
    assert result == (2, env(additionalContext="TRIPLE-CTX"), "TRIPLE-STDERR\n"), (
        f"_invoke must surface the handler's triple unchanged, got {result!r}"
    )


@pytest.mark.integration
def test_main_propagates_tuple_handler_block_and_envelope(
    dispatch, monkeypatch, tmp_path, capsys
):
    """End to end: a triple-returning handler's block reaches the process exit
    code, its reason reaches real stderr, and its envelope reaches real stdout."""
    blocker = make_route(
        tmp_path,
        "tupleblock",
        """
        import json
        def run(payload):
            return (
                2,
                json.dumps({"hookSpecificOutput": {"additionalContext": "BLOCK-CTX"}}),
                "TUPLE-BLOCKED: dangerous command\\n",
            )
        """,
    )
    monkeypatch.setattr(dispatch, "ROUTES", [blocker])
    code, out, err = run_main(dispatch, "pre", {"tool_name": "Bash"}, capsys)

    assert code == 2, "a handler returning exit 2 must block the tool call"
    assert "TUPLE-BLOCKED: dangerous command" in err
    assert json.loads(out)["hookSpecificOutput"]["additionalContext"] == "BLOCK-CTX"


# Vocabulary that identifies the FAULT in a malformed-return report. A line that
# merely names the handler ("[dispatch] JUNK returned NoneType") carries no
# detection: an impl can print it on EVERY invocation, success included, and
# never check anything. Requiring fault vocabulary forces the line to be the
# CONSEQUENCE of a check. Deliberately excludes the bare type name and the bare
# repr - "NoneType" contains "None", so accepting the offending repr would wave
# that same unconditional spam through for the `none` case.
_MALFORMED_MARKERS = (
    "malformed",
    "invalid",
    "bad return",
    "not a tuple",
    "not a 3-tuple",
    "3-tuple",
    "three-tuple",
    "int, str, str",
    "must return",
    "expected",
)


def malformed_report_lines(surface: str, name: str) -> list[str]:
    """Lines of `surface` that name handler `name` AND identify the fault."""
    low_name = name.lower()
    out: list[str] = []
    for line in surface.splitlines():
        low = line.lower()
        if low_name in low and any(m in low for m in _MALFORMED_MARKERS):
            out.append(line)
    return out


@pytest.mark.integration
@pytest.mark.parametrize(
    "returned",
    [
        "0",
        "None",
        "(2, 'x')",
        "'nope'",
        "(0, 'a', 'b', 'c')",
        "(2, None, 3)",
        '("0", "", "")',
    ],
    ids=[
        "bare-int",
        "none",
        "two-tuple",
        "string",
        "four-tuple",
        "right-arity-wrong-members",
        "str-exit-code",
    ],
)
def test_invoke_logs_malformed_handler_return_instead_of_reporting_success(
    dispatch, tmp_path, returned
):
    """A handler that returns anything but a real (int, str, str) is a bug, and
    the dispatcher must say so: no crash, no envelope built from the junk, and a
    dispatch.log entry NAMING THE FAULT. Silently mapping it to a clean
    (0, "", "") - what an outer capture_main does - is one forbidden failure;
    surfacing the junk unchanged is the other. The last two params carry the
    right ARITY with wrong MEMBER TYPES: `(2, None, 3)` and `("0", "", "")` are
    3-tuples, so an `_invoke` that only counts members lets them reach
    `_aggregate`, which writes the int 3 to stderr (TypeError, killing the whole
    dispatch) and reads the str "0" as an unknown exit code."""
    # Label "junk", NOT "malformed": the handler's own name must not hand the
    # implementation a fault word for free, or `[dispatch] JUNK returned
    # NoneType` would satisfy the fault check while detecting nothing.
    route = make_route(
        tmp_path,
        "junk",
        f"""
        def run(payload):
            return {returned}
        """,
    )
    result = dispatch._invoke(route, {"tool_name": "Bash"})  # must not raise
    # A real (int, str, str) even here: whatever the handler did, _invoke's own
    # return value must stay inside the contract its caller (_aggregate) reads.
    code, out, err = assert_triple(result, "_invoke")
    assert out == "", f"a malformed return must contribute no stdout, got {out!r}"

    log_text = dispatch_log_text()
    assert log_text.strip(), (
        f"a malformed handler return ({returned}) must be logged, not silently "
        f"accepted as success"
    )
    surface = err + log_text
    assert route.name.lower() in surface.lower(), (
        f"the malformed return must name the handler {route.name!r}; "
        f"stderr={err!r} log={log_text!r}"
    )
    assert malformed_report_lines(surface, route.name), (
        f"the report for {returned} must NAME THE FAULT on the line that names "
        f"{route.name!r}, not merely announce that the handler returned "
        f"something: expected one of {_MALFORMED_MARKERS}. An unconditional "
        f"per-invocation debug line detects nothing. stderr={err!r} "
        f"log={log_text!r}"
    )


@pytest.mark.integration
def test_invoke_reports_no_fault_for_well_formed_handler_return(dispatch, tmp_path):
    """NEGATIVE CONTROL for the malformed-return test above, sharing its exact
    matcher. A handler returning a proper (int, str, str) must produce NO fault
    report. Without this, an `_invoke` that logs a fault-flavoured line on EVERY
    invocation - success included - passes the malformed test with zero
    detection logic; here that same spam names the handler alongside the fault
    vocabulary and FAILS."""
    route = make_route(
        tmp_path,
        "clean",
        """
        def run(payload):
            return (0, "", "")
        """,
    )
    result = dispatch._invoke(route, {"tool_name": "Bash"})
    assert result == (0, "", ""), f"_invoke must surface the triple, got {result!r}"

    surface = result[2] + dispatch_log_text()
    assert malformed_report_lines(surface, route.name) == [], (
        f"a well-formed (int, str, str) return must NOT be reported as a fault; "
        f"got {malformed_report_lines(surface, route.name)!r}"
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "command,expected_code,expect_blocked",
    [
        ("ls backlog/", 2, True),
        ("ls /tmp", 0, False),
    ],
    ids=["blocks", "allows"],
)
def test_handler_script_standalone_behavior_unchanged(
    tmp_path, command, expected_code, expect_blocked
):
    """The `__main__` path must keep working exactly as before: run the script
    with a payload on stdin and it still exits 2 with a BLOCKED reason (or 0
    with silence). Growing a triple-returning `run()` must not disturb it."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(_ENFORCE_PRD_LOCATION)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(home)},
        cwd=str(tmp_path),
        timeout=30,
    )
    assert proc.returncode == expected_code, f"{command!r}: stderr={proc.stderr!r}"
    assert proc.stdout == ""
    assert ("BLOCKED" in proc.stderr) is expect_blocked
