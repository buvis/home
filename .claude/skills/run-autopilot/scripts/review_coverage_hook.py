#!/usr/bin/env python3
"""Stop hook: gate session exit on review coverage when autopilot is in a review phase.

Reads dev/local/autopilot/state.json, determines whether the current phase is a
review handoff, locates the saved review file, and shells out to review_coverage.py.
Returns 0 to allow the session to exit, 2 to block it (and delete the signal so the
loop does not immediately re-trigger).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from _walk_up import find_autopilot_dir

_PHASE_TO_SURFACE: dict[str, str] = {
    # At session exit `phase` is the NEXT phase, so the surface that JUST
    # finished is the previous one: blind-review→work-completion review just
    # ran, doubt-review→blind review just ran, done→doubt review just ran.
    "blind-review": "work-completion",
    "doubt-review": "blindly",
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


def delete_signal(autopilot_dir: Path) -> None:
    try:
        (autopilot_dir / "signal").unlink(missing_ok=True)
    except OSError as exc:
        sys.stderr.write(f"review coverage: warning: failed to delete signal: {exc}\n")


def run_gate(
    review_file: Path,
    surface: str,
    prd_path: Path,
    diff_range: str,
    repo: Path,
) -> tuple[int, str]:
    gate_path = (
        Path(__file__).resolve().parents[2]
        / "review-work-completion"
        / "scripts"
        / "review_coverage.py"
    )
    aggregate_path = repo / "dev" / "local" / "reviews" / ".stop-hook-aggregate.md"
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


def main() -> int:
    try:
        sys.stdin.read()
    except OSError:
        pass

    autopilot_dir = find_autopilot_dir(Path.cwd())
    if autopilot_dir is None:
        return 0

    try:
        state = json.loads((autopilot_dir / "state.json").read_text())
    except (OSError, json.JSONDecodeError):
        return 0

    phase = state.get("phase", "")
    prd = state.get("prd", "")
    work_start_sha = state.get("work_start_sha", "HEAD")

    surface = surface_for_phase(phase)
    if surface is None:
        return 0

    prd_base = prd[:-3] if prd.endswith(".md") else prd
    repo = autopilot_dir.parents[2]
    reviews_dir = repo / "dev" / "local" / "reviews"

    review_file = review_file_for(surface, prd_base, reviews_dir)
    if review_file is None or not review_file.exists():
        sys.stderr.write(
            f"review coverage: no {surface} review file found for {prd_base}; "
            "blocking session exit\n"
        )
        delete_signal(autopilot_dir)
        return 2

    wip_path = repo / "dev" / "local" / "prds" / "wip" / prd
    done_path = repo / "dev" / "local" / "prds" / "done" / prd
    prd_path = wip_path if wip_path.exists() else (done_path if done_path.exists() else wip_path)

    diff_range = f"{work_start_sha}..HEAD"

    code, msg = run_gate(review_file, surface, prd_path, diff_range, repo)
    if code != 0:
        sys.stderr.write(
            f"review coverage gap [{surface}]: {msg}; blocking session exit\n"
        )
        delete_signal(autopilot_dir)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
