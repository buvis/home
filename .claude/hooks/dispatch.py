"""In-process per-event hook dispatcher for ~/.claude/hooks/.

Invoked as `python3 dispatch.py <pre|post|stop>`. Reads one JSON payload on
stdin, selects the matching handlers from the baked ROUTES table (an
equivalence of settings.json), runs each in order with a per-handler SIGALRM
wall-clock cap and crash isolation, then aggregates their outputs into a single
hook response (merged stdout envelope, concatenated stderr, most-restrictive
exit code).

Handler contract: a handler module exposes `run(payload) -> (exit_code, stdout,
stderr)` and owns its own capture. `_invoke` calls it DIRECTLY and surfaces that
triple unchanged; re-capturing around it would map the triple to a bogus 0 and
silently discard every block and every stdout envelope. A return that is not an
(int, str, str) triple is logged as a fault and contributes nothing. A script
with no `run` falls back to a subprocess.

Stdlib only. Python 3.10+.
"""

from __future__ import annotations

import collections
import importlib.util
import json
import re
import signal
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

from _common import HandlerTimeout

EVENTS = {"pre": "PreToolUse", "post": "PostToolUse", "stop": "Stop"}

Route = collections.namedtuple("Route", "event matcher name path timeout")

HOOKS = Path.home() / ".claude" / "hooks"
SCRIPTS = Path.home() / ".claude" / "skills" / "run-autopilot" / "scripts"

# Handlers import their siblings by bare name; make both handler dirs importable.
for _p in (str(SCRIPTS), str(HOOKS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Baked equivalence of settings.json (pre/post/stop scope), in declaration order.
# NOT read back from settings.json at runtime; the test suite cross-checks it.
ROUTES = [
    Route("PreToolUse", "Edit|Write|MultiEdit", "enforce_prd_location",
          HOOKS / "enforce_prd_location.py", 5),
    Route("PreToolUse", "Edit|Write|MultiEdit", "cartographer-echo",
          HOOKS / "cartographer-echo.py", 5),
    Route("PreToolUse", "Edit|Write|MultiEdit", "strunk-ruling-inject",
          HOOKS / "strunk-ruling-inject.py", 5),
    Route("PreToolUse", "Bash", "enforce_prd_location",
          HOOKS / "enforce_prd_location.py", 5),
    Route("PreToolUse", "Bash", "cartographer-echo",
          HOOKS / "cartographer-echo.py", 5),
    Route("PostToolUse", "Bash|Read|Grep|Glob|Agent|WebFetch|WebSearch|mcp__.*",
          "autopilot_context_cap_hook",
          SCRIPTS / "autopilot_context_cap_hook.py", 5),
    Route("PostToolUse", "Edit|Write|MultiEdit", "validate_state_json_hook",
          SCRIPTS / "validate_state_json_hook.py", 5),
    Route("PostToolUse", "Bash|Edit|Write|MultiEdit", "observe_tool",
          HOOKS / "observe_tool.py", 5),
    Route("Stop", None, "notify", HOOKS / "notify.py", 15),
    Route("Stop", None, "review_coverage_hook",
          SCRIPTS / "review_coverage_hook.py", 5),
    Route("Stop", None, "track_cost", HOOKS / "track_cost.py", 10),
    Route("Stop", None, "track_skills", HOOKS / "track_skills.py", 10),
    Route("Stop", None, "analyze-instincts", HOOKS / "analyze-instincts.py", 10),
    Route("Stop", None, "cartographer-stop", HOOKS / "cartographer-stop.py", 5),
]

_RANK = {"allow": 0, "ask": 1, "deny": 2}

_LOG_CAP_BYTES = 1048576  # 1 MiB; one generation of rotation (-> dispatch.log.1)


def log(message: str) -> None:
    """Append one line to ~/.claude/hooks/dispatch.log; never raise.

    The path is resolved at call time so tests that patch Path.home() after
    import land their logs in the sandbox. Capped at 1 MiB with one generation
    of rotation: a file already at or over the cap is moved to dispatch.log.1
    (replacing any previous one) before the new line lands in a fresh file.
    """
    try:
        path = Path.home() / ".claude" / "hooks" / "dispatch.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        # ponytail: unlocked check-then-act; two dispatchers rotating at the
        # same instant can clobber each other's .1. Diagnostic log, never
        # enforcement - add locking only if a lost generation ever costs us.
        try:
            if path.exists() and path.stat().st_size >= _LOG_CAP_BYTES:
                path.replace(path.with_name(path.name + ".1"))
        except Exception:
            pass  # rotation failure must not drop the line being logged below
        stamp = datetime.now().astimezone().isoformat()
        with path.open("a", encoding="utf-8") as fh:
            fh.write(stamp + " " + message.rstrip("\n") + "\n")
    except Exception:
        pass


def _parse_stdin() -> dict:
    """Read stdin as a JSON object. Return {} on any error or non-dict."""
    try:
        data = json.loads(sys.stdin.read())
    except (ValueError, OSError):
        log("[dispatch] malformed stdin payload; treating as empty")
        return {}
    if isinstance(data, dict):
        return data
    log("[dispatch] non-dict stdin payload; treating as empty")
    return {}


def _matches(matcher: str, tool: str) -> bool:
    """Anchored whole-name match, returning a real bool.

    Assumes the harness itself matches tool names with fullmatch (whole-name)
    semantics, not re.search (substring) - unverified against the live
    harness; see test_routing_matches_settings_json_for_observed_tools in
    tests/test_dispatch.py, which models the harness the same way.
    """
    return re.fullmatch(matcher, tool) is not None


def _load_handler(path):
    """Import a handler module from its file path."""
    modname = f"_hook_{Path(path).stem}"
    spec = importlib.util.spec_from_file_location(modname, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(modname, None)
        raise
    return mod


def _subprocess_fallback(path, payload, timeout):
    """Run a run-less handler script as a subprocess -> (rc, stdout, stderr)."""
    try:
        proc = subprocess.run(
            [sys.executable, str(path)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 0, "", f"[dispatch] {Path(path).name}: {exc}\n"


def _raise_timeout(signum, frame):
    raise HandlerTimeout()


def _invoke(route, payload) -> tuple[int, str, str]:
    """Run one handler under a SIGALRM cap with crash/timeout isolation.

    Degrades to NO per-handler wall-clock cap on a platform without
    SIGALRM/alarm (e.g. Windows): the handler still runs and its result still
    surfaces, isolation just loses the timeout half.
    """
    has_alarm = hasattr(signal, "SIGALRM") and hasattr(signal, "alarm")
    prev = signal.signal(signal.SIGALRM, _raise_timeout) if has_alarm else None
    if has_alarm:
        signal.alarm(max(1, int(route.timeout)))
    try:
        mod = _load_handler(route.path)
        if hasattr(mod, "run"):
            result = mod.run(payload)
        else:
            result = _subprocess_fallback(route.path, payload, route.timeout)
        if has_alarm:
            signal.alarm(0)  # handler DONE: cancel immediately
        # This line is observed by test_teardown_race_no_false_timeout via
        # len(result) on the handler's returned triple; keep the check calling
        # len() on the result.
        if not (
            isinstance(result, tuple)
            and len(result) == 3
            and isinstance(result[0], int)
            and not isinstance(result[0], bool)
            and isinstance(result[1], str)
            and isinstance(result[2], str)
        ):
            msg = (f"[dispatch] {route.name}: malformed return {result!r}; "
                   f"expected a (int, str, str) 3-tuple")
            log(msg)
            return 0, "", msg + "\n"
        return result
    except HandlerTimeout:
        log(f"{route.name} timed out after {route.timeout}s")
        return 0, "", f"[dispatch] {route.name}: timed out\n"
    except Exception as exc:
        log(traceback.format_exc())
        return 0, "", f"[dispatch] {route.name}: {exc}\n"
    finally:
        if has_alarm:
            signal.signal(signal.SIGALRM, signal.SIG_IGN)
            signal.alarm(0)
            signal.signal(signal.SIGALRM, prev)


def _warn(msg: str) -> None:
    """Write msg to the real stderr and the dispatch log."""
    sys.stderr.write(msg + "\n")
    log(msg)


def _envelope_of(name, out) -> dict | None:
    """Parse one handler's stdout as a hookSpecificOutput envelope.

    Returns the inner hookSpecificOutput dict, or None if out is not
    parseable JSON, not a JSON object, missing hookSpecificOutput, or
    hookSpecificOutput is not itself an object. Each failure path logs why.
    """
    try:
        obj = json.loads(out)
    except (ValueError, TypeError):
        log(f"[dispatch] non-JSON stdout from {name}")
        return None
    if not isinstance(obj, dict):
        log(f"[dispatch] non-object stdout from {name}")
        return None
    if "hookSpecificOutput" not in obj:
        log(f"[dispatch] missing hookSpecificOutput from {name}")
        return None
    hso = obj["hookSpecificOutput"]
    if not isinstance(hso, dict):
        log(f"[dispatch] non-dict hookSpecificOutput "
            f"({type(hso).__name__}) from {name}")
        return None
    return hso


def _pick_decision(envelopes, blocking) -> tuple:
    """Select the winning permissionDecision from parsed envelopes.

    envelopes is [(name, hso), ...] for handlers whose stdout was a valid
    envelope, in dispatch order. Returns (decision, reason). blocking routes
    the loser warnings to the log (blocking run) or real stderr (non-blocking
    run), same rule as _aggregate's stderr.
    """
    win_decision = None
    win_reason = None
    win_rank = -1
    win_idx = -1
    losers: list[str] = []

    for idx, (name, hso) in enumerate(envelopes):
        if "permissionDecision" not in hso:
            continue
        rank = _RANK.get(hso["permissionDecision"], -1)
        if rank < 0:
            log(f"[dispatch] unrecognized permissionDecision "
                f"{hso['permissionDecision']!r} from {name}")
        # win_idx < 0 registers the FIRST decision even when unranked, so an
        # unrecognized value passes through (as the separate hooks would) and
        # never silently vanishes; a known decision still wins on rank.
        if win_idx < 0 or rank > win_rank:
            if win_idx >= 0:
                losers.append(envelopes[win_idx][0])
            win_decision = hso["permissionDecision"]
            win_reason = hso.get("permissionDecisionReason")
            win_rank = rank
            win_idx = idx
        else:
            losers.append(name)

    for loser in losers:
        msg = (f"[dispatch] permission conflict: dropped permissionDecision "
               f"from {loser}")
        (log if blocking else _warn)(msg)

    return win_decision, win_reason


def _merge_envelopes(named) -> str:
    """Parse each handler's stdout as a hookSpecificOutput envelope and merge
    additionalContext, the most-restrictive permissionDecision, and any other
    keys into one {"hookSpecificOutput": {...}} JSON string ("" if empty).

    named is [(name, code, out, err), ...] - each result already carries its
    own handler name, in dispatch order. Conflict warnings follow the same
    block-reason rule as _aggregate's handler stderr: on a blocking run (some
    handler in named returned 2) they are logged only, never written to real
    stderr, so they cannot pollute the model-visible block reason.
    """
    contexts: list[str] = []
    other: dict = {}
    envelopes: list[tuple[str, dict]] = []
    blocking = any(c == 2 for (_n, c, _o, _e) in named)

    for name, _c, out, _e in named:
        if not out or not out.strip():
            continue
        hso = _envelope_of(name, out)
        if hso is None:
            continue
        envelopes.append((name, hso))
        if "additionalContext" in hso:
            ctx = hso["additionalContext"]
            if isinstance(ctx, str):
                contexts.append(ctx)
            else:
                log(f"[dispatch] non-str additionalContext from {name}")
        for key, value in hso.items():
            if key in ("additionalContext", "permissionDecision",
                       "permissionDecisionReason"):
                continue
            if key in other:
                if other[key] != value:
                    msg = f"[dispatch] key conflict: dropped {key!r} from {name}"
                    (log if blocking else _warn)(msg)
            else:
                other[key] = value

    win_decision, win_reason = _pick_decision(envelopes, blocking)

    inner: dict = {}
    if contexts:
        inner["additionalContext"] = "\n---\n".join(contexts)
    if win_decision is not None:
        inner["permissionDecision"] = win_decision
        if win_reason is not None:
            inner["permissionDecisionReason"] = win_reason
    for key, value in other.items():
        inner[key] = value

    return json.dumps({"hookSpecificOutput": inner}) if inner else ""


def _aggregate(results, names) -> tuple[int, str]:
    """Fold [(code, out, err), ...] into (exit_code, merged_stdout).

    exit_code is 2 if any handler blocked, else 0 (other codes logged as 0).
    Non-empty stderr is concatenated in order and written to the real stderr,
    except that when the run is blocking, a non-blocking handler's stderr is
    logged instead of reaching the real stderr (it must not pollute the
    model-visible block reason).
    Parseable stdout envelopes merge into one {"hookSpecificOutput": {...}}.
    """
    code = 2 if any(c == 2 for (c, _o, _e) in results) else 0
    for (c, _o, _e) in results:
        if c not in (0, 2):
            log(f"[dispatch] ignoring non-0/2 handler exit code {c}")

    named = [
        (names[idx], c, out, err)
        for idx, (c, out, err) in enumerate(results)
    ]

    for name, c, _out, err in named:
        if not err:
            continue
        if code == 2 and c != 2:
            log(f"[dispatch] non-blocking stderr from {name}: {err.rstrip()}")
        else:
            sys.stderr.write(err)

    merged = _merge_envelopes(named)
    return code, merged


def main(event: str) -> None:
    if event not in EVENTS:
        log(f"[dispatch] unknown event {event!r}; exiting non-blocking")
        sys.exit(0)
    payload = _parse_stdin()
    tool = payload.get("tool_name", "")
    if not isinstance(tool, str):
        tool = ""
    selected = [
        r
        for r in ROUTES
        if r.event == EVENTS[event]
        and (r.matcher is None or _matches(r.matcher, tool))
    ]
    results = [_invoke(r, payload) for r in selected]
    code, out = _aggregate(results, [r.name for r in selected])
    if out:
        sys.stdout.write(out)
    sys.exit(code)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        log("[dispatch] missing event argument; exiting non-blocking")
        sys.exit(0)
    main(sys.argv[1])
