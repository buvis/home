"""cli/routing.py - per-phase model/effort/cap routing (PRD 00106).

Ports the wrapper's launch-model case table and
`_autopilot_build_model`/`_autopilot_build_target` verbatim
(development.plugin.bash; contract pinned by
test_autoclaude_build_model.sh, re-expressed in cli/test_routing.py).

Build routes per-PRD (PRD 00076): Sonnet unless a promotion signal
fires. The absent phase is a BUILD launch (a fresh batch has no
state.json and resumes at the build gate). A genuinely unknown
non-empty phase falls to Opus xhigh: fail expensive, never fail dumb.
Review stays on Opus at xhigh (the decision gate classifies findings);
finalize (done) is mechanical rendering - Sonnet at medium.

The `[1m]` suffix is load-bearing: autopilot_context_cap_hook.USAGE_CAP
(500K) is sized for a 1M window, so every launch model here must carry
it.

Promotion decay (PRD 00111): recomputed from scratch on EVERY relaunch,
no stored latch, so a signal that clears stops promoting by
construction. The loop-metrics tail is deliberately NOT an input -
00111 retired signal 6 (repeat build session), and restoring that read
in any form is the decay regression.

`default_model` is parsed with the wrapper's own line grammar, NOT
cli/frontmatter.py: that module's Phase-0 contract deliberately excludes
the key (it belongs to /plan-tasks), caps at 20 head lines and strips
delimiter whitespace, none of which this signal ever did.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

OPUS = "claude-opus-5[1m]"
SONNET = "claude-sonnet-5[1m]"

_DEFAULT_MODEL_OPUS = re.compile(
    r"^[ \t]*default_model[ \t]*:[ \t]*(\"opus\"|'opus'|opus)[ \t]*$",
)
_TRAILING_COMMENT = re.compile(r"[ \t]+#.*$")
_PRD_GLOB = "[0-9][0-9][0-9][0-9][0-9]-*"


@dataclass(frozen=True)
class Route:
    model: str
    effort: str
    cap_secs: int


def _env_int(env: dict, key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def build_target(prds_dir: Path) -> Path | None:
    """The lowest 00XXX- PRD file in wip/, else in backlog/, else None.

    NEVER state.prd, which between PRDs still names the one that just
    finished. done/ and hold/ are not candidates.
    """
    for sub in ("wip", "backlog"):
        try:
            candidates = sorted((prds_dir / sub).glob(_PRD_GLOB))
        except OSError:
            candidates = []
        for path in candidates:
            if path.is_file():
                return path
    return None


def _frontmatter_pins_opus(prd_path: Path) -> bool:
    """Signal 1: a real (uncommented) `default_model: opus` key in the
    LEADING frontmatter block only.

    The wrapper's awk grammar verbatim: line 1 must be exactly `---` (no
    whitespace tolerance), the scan stops at the next exact `---`, a
    trailing comment needs whitespace before its `#` (YAML semantics:
    `opus#suffix` is the scalar value, `opus  # rationale` is opus), and
    the value must be exactly opus, bare or matched-quoted.
    """
    try:
        lines = prd_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False
    if not lines or lines[0] != "---":
        return False
    for line in lines[1:]:
        if line == "---":
            return False
        if _DEFAULT_MODEL_OPUS.match(_TRAILING_COMMENT.sub("", line)):
            return True
    return False


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _state_signals_fire(state_path: Path, target: str) -> bool:
    """Signals 2/3a/4, all guarded on state.prd being the target: a
    replan, a live stall, or a fired cap rotation. Signals 2 and 4 are
    cleared by Phase 9 step 10 at PRD completion; 3a clears when
    /run-autopilot resolves the stall."""
    state = _load_json(state_path)
    if not isinstance(state, dict) or state.get("prd") != target:
        return False
    replan = state.get("replan_count") or 0
    rotations = state.get("cap_rotations") or []
    return (
        (isinstance(replan, int) and replan > 0)
        or state.get("stall_reason") is not None
        or (isinstance(rotations, list) and len(rotations) > 0)
    )


def _ledger_has_key(ledger_path: Path, target: str) -> bool:
    """Signal 5: a rescue-ledger KEY for the target, any status. Sticky
    by design (a human approved that rescue). A key lookup, never a
    substring scan - the target appearing as a VALUE in another PRD's
    entry must not fire."""
    ledger = _load_json(ledger_path)
    return isinstance(ledger, dict) and target in ledger


def _deferred_stall_fires(deferred_dir: Path, target: str) -> bool:
    """Signal 3b: a type:"stall" item naming the target in the 2 NEWEST
    *-deferred.json files BY FILENAME (batch ids are minted in order;
    mtimes are not - a .bak restore or late append rewrites them). The
    type and the prd must match on the SAME item."""
    try:
        files = sorted(
            path for path in deferred_dir.glob("*-deferred.json") if path.is_file()
        )
    except OSError:
        return False
    for path in files[max(0, len(files) - 2) :]:
        record = _load_json(path)
        if not isinstance(record, dict):
            continue
        items = record.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if (
                isinstance(item, dict)
                and item.get("type") == "stall"
                and item.get("prd") == target
            ):
                return True
    return False


def build_model(
    state_path: Path,
    prds_dir: Path,
    ledger_path: Path,
    deferred_dir: Path,
) -> str:
    """The build-phase launch model: OPUS when the target PRD carries
    difficulty evidence, else SONNET. Never raises and never writes -
    the wrapper ran this on every launch with its stderr as the
    operator's log, so a missing state.json, ledger or metrics file and
    an empty deferred dir are all normal."""
    target_path = build_target(prds_dir)
    if target_path is None:
        return SONNET
    if _frontmatter_pins_opus(target_path):
        return OPUS
    target = target_path.name
    if _state_signals_fire(state_path, target) or _ledger_has_key(
        ledger_path,
        target,
    ):
        return OPUS
    if _deferred_stall_fires(deferred_dir, target):
        return OPUS
    return SONNET


def route(phase: str, autopilot_dir: Path, env: dict | None = None) -> Route:
    """Model, effort and wall-clock cap for the next spawn.

    `phase` is state.next_phase as launched (empty string for a fresh
    batch with no state.json). Env overrides mirror the wrapper's knobs;
    the unknown-phase branch deliberately has none.
    """
    if env is None:
        env = dict(os.environ)
    if phase in ("build", ""):
        model = env.get("_AUTOPILOT_MODEL_BUILD") or build_model(
            autopilot_dir / "state.json",
            autopilot_dir.parent / "prds",
            autopilot_dir / "ledger" / "fable-requests.json",
            autopilot_dir / "deferred",
        )
        return Route(
            model=model,
            effort=env.get("_AUTOPILOT_EFFORT_BUILD") or "xhigh",
            cap_secs=_env_int(env, "_AUTOPILOT_SESSION_MAX", 7200),
        )
    if phase == "review":
        return Route(
            model=env.get("_AUTOPILOT_MODEL_REVIEW") or OPUS,
            effort=env.get("_AUTOPILOT_EFFORT_REVIEW") or "xhigh",
            cap_secs=_env_int(env, "_AUTOPILOT_SESSION_MAX_REVIEW", 10800),
        )
    if phase == "done":
        return Route(
            model=env.get("_AUTOPILOT_MODEL_DONE") or SONNET,
            effort=env.get("_AUTOPILOT_EFFORT_DONE") or "medium",
            cap_secs=_env_int(env, "_AUTOPILOT_SESSION_MAX", 7200),
        )
    return Route(
        model=OPUS,
        effort="xhigh",
        cap_secs=_env_int(env, "_AUTOPILOT_SESSION_MAX", 7200),
    )
