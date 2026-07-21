"""In-process per-event hook dispatcher for ~/.claude/hooks/.

Invoked as `python3 dispatch.py <pre|post|stop>`. Reads one JSON payload on
stdin, selects the matching handlers from the baked ROUTES table (an
equivalence of settings.json), runs each in order with a per-handler SIGALRM
wall-clock cap and crash isolation, then aggregates their outputs into a single
hook response (merged stdout envelope, concatenated stderr, most-restrictive
exit code).

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
from pathlib import Path

from _common import HandlerTimeout, capture_main

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

_HANDLER_CACHE: dict[str, object] = {}

_RANK = {"allow": 0, "ask": 1, "deny": 2}


def log(message: str) -> None:
    """Append one line to ~/.claude/hooks/dispatch.log; never raise.

    The path is resolved at call time so tests that patch Path.home() after
    import land their logs in the sandbox.
    """
    try:
        path = Path.home() / ".claude" / "hooks" / "dispatch.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(message.rstrip("\n") + "\n")
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
    """Anchored whole-name match, returning a real bool."""
    return re.fullmatch(matcher, tool) is not None


def _load_handler(path):
    """Import a handler module from its file path, caching only on success."""
    key = str(path)
    if key in _HANDLER_CACHE:
        return _HANDLER_CACHE[key]
    modname = f"_hook_{Path(path).stem}"
    spec = importlib.util.spec_from_file_location(modname, key)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(modname, None)
        raise
    _HANDLER_CACHE[key] = mod
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
    """Run one handler under a SIGALRM cap with crash/timeout isolation."""
    prev = signal.signal(signal.SIGALRM, _raise_timeout)
    signal.alarm(max(1, int(route.timeout)))
    try:
        mod = _load_handler(route.path)
        if hasattr(mod, "run"):
            result = capture_main(lambda: mod.run(payload), payload)
        else:
            result = _subprocess_fallback(route.path, payload, route.timeout)
        signal.alarm(0)  # handler DONE: cancel immediately
        return result
    except HandlerTimeout:
        log(f"{route.name} timed out after {route.timeout}s")
        return 0, "", f"[dispatch] {route.name}: timed out\n"
    except Exception as exc:
        log(traceback.format_exc())
        return 0, "", f"[dispatch] {route.name}: {exc}\n"
    finally:
        signal.signal(signal.SIGALRM, signal.SIG_IGN)
        signal.alarm(0)
        signal.signal(signal.SIGALRM, prev)


def _name_at(names, idx) -> str:
    if names and idx < len(names):
        return names[idx]
    return f"handler[{idx}]"


def _aggregate(results, names=None) -> tuple[int, str]:
    """Fold [(code, out, err), ...] into (exit_code, merged_stdout).

    exit_code is 2 if any handler blocked, else 0 (other codes logged as 0).
    Non-empty stderr is concatenated in order and written to the real stderr.
    Parseable stdout envelopes merge into one {"hookSpecificOutput": {...}}.
    """
    code = 2 if any(c == 2 for (c, _o, _e) in results) else 0
    for (c, _o, _e) in results:
        if c not in (0, 2):
            log(f"[dispatch] ignoring non-0/2 handler exit code {c}")

    for (_c, _o, err) in results:
        if err:
            sys.stderr.write(err)

    contexts: list[str] = []
    other: dict = {}
    win_decision = None
    win_reason = None
    win_rank = -1
    win_idx = -1
    decision_count = 0
    losers: list[str] = []

    for idx, (_c, out, _e) in enumerate(results):
        if not out or not out.strip():
            continue
        try:
            obj = json.loads(out)
        except (ValueError, TypeError):
            log(f"[dispatch] non-JSON stdout from {_name_at(names, idx)}")
            continue
        if not isinstance(obj, dict):
            log(f"[dispatch] non-object stdout from {_name_at(names, idx)}")
            continue
        hso = obj.get("hookSpecificOutput")
        if not isinstance(hso, dict):
            continue
        if "additionalContext" in hso:
            ctx = hso["additionalContext"]
            if isinstance(ctx, str):
                contexts.append(ctx)
            else:
                log(f"[dispatch] non-str additionalContext from {_name_at(names, idx)}")
        if "permissionDecision" in hso:
            decision_count += 1
            rank = _RANK.get(hso["permissionDecision"], -1)
            if rank < 0:
                log(f"[dispatch] unrecognized permissionDecision "
                    f"{hso['permissionDecision']!r} from {_name_at(names, idx)}")
            # win_idx < 0 registers the FIRST decision even when unranked, so an
            # unrecognized value passes through (as the separate hooks would) and
            # never silently vanishes; a known decision still wins on rank.
            if win_idx < 0 or rank > win_rank:
                if win_idx >= 0:
                    losers.append(_name_at(names, win_idx))
                win_decision = hso["permissionDecision"]
                win_reason = hso.get("permissionDecisionReason")
                win_rank = rank
                win_idx = idx
            else:
                losers.append(_name_at(names, idx))
        for key, value in hso.items():
            if key in ("additionalContext", "permissionDecision",
                       "permissionDecisionReason"):
                continue
            other.setdefault(key, value)

    if decision_count >= 2 and losers:
        for loser in losers:
            msg = (f"[dispatch] permission conflict: dropped permissionDecision "
                   f"from {loser}")
            sys.stderr.write(msg + "\n")
            log(msg)

    inner: dict = {}
    if contexts:
        inner["additionalContext"] = "\n---\n".join(contexts)
    if win_decision is not None:
        inner["permissionDecision"] = win_decision
        if win_reason is not None:
            inner["permissionDecisionReason"] = win_reason
    for key, value in other.items():
        inner[key] = value

    merged = json.dumps({"hookSpecificOutput": inner}) if inner else ""
    return code, merged


def main(event: str) -> None:
    payload = _parse_stdin()
    tool = payload.get("tool_name", "")
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
    main(sys.argv[1])
