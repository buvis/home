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
import io
import json
import re
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from uuid import uuid4

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[1]
SETTINGS_PATH = Path(__file__).resolve().parents[2] / "settings.json"

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
            print(json.dumps({"hookSpecificOutput": {
                "permissionDecision": "deny", "permissionDecisionReason": "FIRST"}}))
            return 0
        """,
    )
    loser = make_route(
        tmp_path,
        "loser",
        """
        import json
        def run(payload):
            print(json.dumps({"hookSpecificOutput": {
                "permissionDecision": "deny", "permissionDecisionReason": "SECOND"}}))
            return 0
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
            print(json.dumps({"hookSpecificOutput": {
                "permissionDecision": "deny", "permissionDecisionReason": "ONLY"}}))
            return 0
        """,
    )
    plain = make_route(
        tmp_path,
        "plain",
        """
        import json
        def run(payload):
            print(json.dumps({"hookSpecificOutput": {"additionalContext": "CTX"}}))
            return 0
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
            print(json.dumps({"hookSpecificOutput": {"additionalContext": "SURVIVED"}}))
            return 0
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
            print(json.dumps({"hookSpecificOutput": {"additionalContext": "AFTERBAD"}}))
            return 0
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
            print("this is raw text, definitely not json")
            return 0
        """,
    )
    envelope = make_route(
        tmp_path,
        "envelope",
        """
        import json
        def run(payload):
            print(json.dumps({"hookSpecificOutput": {"additionalContext": "CLEAN"}}))
            return 0
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
            print("SLOW-FINISHED")
            return 0
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
            return 0
        """,
        timeout=1,
    )
    fast = make_route(
        tmp_path,
        "fast",
        """
        import json
        def run(payload):
            print(json.dumps({"hookSpecificOutput": {"additionalContext": "FAST"}}))
            return 0
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
    quick = make_route(
        tmp_path,
        "quick",
        """
        import time
        def run(payload):
            time.sleep(0.02)
            print("QUICK-DONE")
            return 0
        """,
        timeout=1,
    )
    for _ in range(20):
        code, out, err = dispatch._invoke(quick, {"tool_name": "Bash"})
        assert code == 0
        assert "QUICK-DONE" in out  # completed, never mislabeled timed-out
