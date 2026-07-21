#!/usr/bin/env python3
"""Stop hook: gate session exit on review-file completeness at the done hand-off.

Reads dev/local/autopilot/state.json, determines whether the current phase is a
review handoff, locates the saved review file, and shells out to
check_review_file.py (PRD 00016 — the minimal shape check: reviewer sections,
verdict line, tests line). Returns 0 to allow the session to exit, 2 to block it
so the model can finish the review before the turn ends (exit-2 Stop blocking
works headless — 00014 spike (c)).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _walk_up import find_autopilot_dir

# Liveness valve: block session exit at most this many times per handoff.
# Without it, a review file that stays missing/malformed (reviewer died,
# content lost) blocks every exit until the context cap kills the session.
# On the cap-th+1 block the hook fails loud instead: stderr verdict, a
# `.review-gate-failed` marker for the wrapper/next session, exit 0.
BLOCK_CAP = 3

_PHASE_TO_SURFACE: dict[str, str] = {
    # At session exit `phase` is the NEXT phase, so the surface that JUST
    # finished is the previous one: done → the review-rework loop converged,
    # i.e. a work-completion review cycle just ran. (Phase names are the
    # three-gate set: build|review|done|paused; PRD 00015 folded the blind
    # and doubt legs into the review cycle's lenses.)
    "done": "work-completion",
}


def surface_for_phase(phase: str) -> str | None:
    return _PHASE_TO_SURFACE.get(phase)


def review_file_for(surface: str, prd_base: str, reviews_dir: Path) -> Path | None:
    # work-completion (the only live surface): find highest integer suffix
    pattern = f"{prd_base}-review-*.md"
    best: tuple[int, Path] | None = None
    for candidate in reviews_dir.glob(pattern):
        stem = candidate.stem  # e.g. "P-review-10"
        suffix = stem.rsplit("-", 1)[-1]
        try:
            n = int(suffix)
        except ValueError:
            continue
        if best is None or n > best[0]:
            best = (n, candidate)
    return best[1] if best is not None else None


def run_gate(review_file: Path) -> tuple[int, str]:
    """Delegate to check_review_file.py — the same shape check the review
    skill runs. Reviewer names come from the file's own `reviewers:`
    frontmatter (written by consolidation); no git, no PRD parsing."""
    gate_path = (
        Path(__file__).resolve().parents[2]
        / "review-work-completion"
        / "scripts"
        / "check_review_file.py"
    )
    argv = ["python3", str(gate_path), "--review-file", str(review_file)]
    result = subprocess.run(argv, capture_output=True, text=True)
    return (result.returncode, result.stderr.strip())


def gate_blocks(autopilot_dir: Path, state: dict) -> tuple[bool, str]:
    """Decide whether the review-coverage gate should block the handoff.

    Returns ``(should_block, message)``. ``should_block`` is True only when a
    review surface just completed (the phase is review-gated) AND its saved
    review file is missing or fails the shape check. Returns ``(False, "")``
    when the phase is not review-gated or the gate passes. Infrastructure
    failures fail open INSIDE check_review_file.py (unreadable file → exit 0
    with a loud stderr note), so an infra error never blocks the hand-off.

    This is a PURE decision: no side effects, no exit codes. ``main()`` blocks
    (exit 2) on a True result. (Historically a second Stop hook — the retired
    ``autopilot_stop_hook.py``, PRD 00014 — consulted the same decision to
    avoid racing this one.)
    """
    phase = state.get("phase", "")
    surface = surface_for_phase(phase)
    if surface is None:
        return (False, "")

    prd = state.get("prd", "")
    prd_base = prd[:-3] if prd.endswith(".md") else prd
    repo = autopilot_dir.parents[2]
    reviews_dir = repo / "dev" / "local" / "reviews"

    review_file = review_file_for(surface, prd_base, reviews_dir)
    if review_file is None or not review_file.exists():
        return (
            True,
            f"review coverage: no {surface} review file found for {prd_base}; "
            "blocking session exit",
        )

    code, msg = run_gate(review_file)
    if code != 0:
        return (
            True,
            f"review coverage gap [{surface}]: {msg}; blocking session exit",
        )
    return (False, "")


def main() -> int:
    try:
        sys.stdin.read()
    except OSError:
        pass

    # Only gate review coverage inside the autopilot shell loop. Interactive
    # sessions and manual /run-autopilot runs have no automated review handoff
    # to gate; blocking their exit on a leftover review-phase state.json
    # deadlocks unrelated work that merely shares the cwd tree. Per SKILL.md
    # "Loop Detection", $_AUTOPILOT_LOOP marks a loop-wrapped session.
    if not os.environ.get("_AUTOPILOT_LOOP"):
        return 0

    autopilot_dir = find_autopilot_dir(Path.cwd())
    if autopilot_dir is None:
        return 0

    try:
        state = json.loads((autopilot_dir / "state.json").read_text())
    except (OSError, json.JSONDecodeError):
        return 0

    should_block, message = gate_blocks(autopilot_dir, state)
    counter = autopilot_dir / ".review-gate-blocks"
    if not should_block:
        if message:
            sys.stderr.write(message + "\n")
        # Gate passed: clear the liveness bookkeeping for the next handoff.
        for stale in (counter, autopilot_dir / ".review-gate-failed"):
            try:
                stale.unlink(missing_ok=True)
            except OSError:
                pass
        return 0

    try:
        blocks = int(counter.read_text().strip() or "0")
    except (OSError, ValueError):
        blocks = 0
    blocks += 1
    if blocks > BLOCK_CAP:
        sys.stderr.write(
            message
            + f"; review_gate: failed - giving up after {BLOCK_CAP} blocked "
            "exits to preserve session liveness\n"
        )
        try:
            (autopilot_dir / ".review-gate-failed").write_text(message + "\n")
            counter.unlink(missing_ok=True)
        except OSError:
            pass
        return 0
    try:
        counter.write_text(str(blocks))
    except OSError:
        pass
    sys.stderr.write(message + "\n")
    return 2


def run(payload):
    """Dispatcher entry point (hooks/dispatch.py). dispatch._invoke already wraps
    this in _common.capture_main, which feeds `payload` via stdin and traps the
    exit, so run() is RAW: call main() and return its result. `return` preserves
    an int exit code; `payload` is unused here (main() reads it from the stdin
    capture)."""
    return main()


if __name__ == "__main__":
    sys.exit(main())
