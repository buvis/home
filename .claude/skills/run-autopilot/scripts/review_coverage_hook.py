#!/usr/bin/env python3
"""Stop hook: gate session exit on review coverage when autopilot is in a review phase.

Reads dev/local/autopilot/state.json, determines whether the current phase is a
review handoff, locates the saved review file, and shells out to review_coverage.py.
Returns 0 to allow the session to exit, 2 to block it so the model can finish the
review before the turn ends (exit-2 Stop blocking works headless — 00014 spike (c)).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _walk_up import find_autopilot_dir

_PHASE_TO_SURFACE: dict[str, str] = {
    # At session exit `phase` is the NEXT phase, so the surface that JUST
    # finished is the previous one: blind→work-completion review just ran,
    # doubt→blind review just ran, done→doubt review just ran. (Phase names
    # are the five-gate set: build|review|blind|doubt|done|paused.)
    "blind": "work-completion",
    "doubt": "blindly",
    "done": "doubt",
}


def surface_for_phase(phase: str) -> str | None:
    return _PHASE_TO_SURFACE.get(phase)


def review_file_for(surface: str, prd_base: str, reviews_dir: Path) -> Path | None:
    if surface == "blindly":
        return reviews_dir / f"{prd_base}-blind-review.md"
    if surface == "doubt":
        return reviews_dir / f"{prd_base}-doubt-review.md"
    # work-completion: find highest integer suffix
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


def run_gate(
    review_file: Path,
    surface: str,
    prd_path: Path,
    diff_range: str,
    repo: Path,
    project_root: Path | None = None,
) -> tuple[int, str]:
    """`repo` is the git repo the diff range lives in; `project_root` is where
    the dev/local artifacts live. They coincide except when a PRD targets a
    nested repo (e.g. ~/.claude/skills/run-autopilot under non-git ~/.claude)."""
    if project_root is None:
        project_root = repo
    gate_path = (
        Path(__file__).resolve().parents[2]
        / "review-work-completion"
        / "scripts"
        / "review_coverage.py"
    )
    aggregate_path = project_root / "dev" / "local" / "reviews" / ".stop-hook-aggregate.md"
    argv = [
        "python3",
        str(gate_path),
        "--surface", surface,
        "--prd", str(prd_path),
        "--diff-range", diff_range,
        "--reviewer-block", str(review_file),
        "--write-aggregate", str(aggregate_path),
        "--repo", str(repo),
    ]
    result = subprocess.run(argv, capture_output=True, text=True)
    return (result.returncode, result.stderr.strip())


def gate_blocks(autopilot_dir: Path, state: dict) -> tuple[bool, str]:
    """Decide whether the review-coverage gate should block the handoff.

    Returns ``(should_block, message)``. ``should_block`` is True only when a
    review surface just completed (the phase is review-gated) AND its saved
    review file is missing, or its coverage block is incomplete. Returns
    ``(False, "")`` when the phase is not review-gated or the gate passes, and
    ``(False, <warning>)`` on DIFF_ERROR — the gate could not compute the diff
    at all, so coverage is unknown (not incomplete) and the handoff is allowed
    with a warning.

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
    work_start_sha = state.get("work_start_sha", "HEAD")
    prd_base = prd[:-3] if prd.endswith(".md") else prd
    repo = autopilot_dir.parents[2]
    # The git repo holding the work commits. Usually the project root, but a
    # PRD can target a nested repo while dev/local stays at the project root;
    # Phase 3 records the nested repo in state.repo_root.
    repo_root = state.get("repo_root", "")
    git_repo = Path(repo_root) if repo_root else repo
    reviews_dir = repo / "dev" / "local" / "reviews"

    review_file = review_file_for(surface, prd_base, reviews_dir)
    if review_file is None or not review_file.exists():
        return (
            True,
            f"review coverage: no {surface} review file found for {prd_base}; "
            "blocking session exit",
        )

    wip_path = repo / "dev" / "local" / "prds" / "wip" / prd
    done_path = repo / "dev" / "local" / "prds" / "done" / prd
    # Neither location exists -> pass wip_path; the gate fires a clean MISSING_PRD.
    prd_path = wip_path if wip_path.exists() else (done_path if done_path.exists() else wip_path)

    diff_range = f"{work_start_sha}..HEAD"

    code, msg = run_gate(review_file, surface, prd_path, diff_range, git_repo, repo)
    if code != 0:
        if msg.startswith("DIFF_ERROR"):
            # The gate could not compute the diff at all (infra failure), so
            # coverage is unknown, not incomplete — the in-session gate
            # already ran; allow the handoff and warn loudly. (A 2026-06-11
            # false block here once masked a killed handoff as drained.)
            return (
                False,
                f"review coverage: cannot compute diff [{surface}]: {msg}; "
                "allowing handoff (coverage was gated in-session)",
            )
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
    if not should_block:
        # A non-empty message on a non-blocking result is the DIFF_ERROR
        # warning: surface the infra failure but allow the handoff.
        if message:
            sys.stderr.write(message + "\n")
        return 0

    sys.stderr.write(message + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
