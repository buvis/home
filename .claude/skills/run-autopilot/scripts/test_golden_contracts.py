"""Golden record-replay for machine-parsed contracts (PRD 00087 R2).

One known-good fixture per contract; a test asserts the deterministic
validator(s) accept it, so the fixture fails when either side of the contract
changes without the other. No model in the loop.

Fully-bound pairs (producer validator AND consumer parser, both Python):
- state.json  <->  statectl.read_and_parse  +  resume_target.resume_target
- review file <->  check_review_file.check

Producer-side pins (the consumer is parsed model-side — no Python parser to
bind — so only the producing shape is checked; documented limitation):
- create-prd frontmatter -> the run-autopilot Phase 0 recognized field set
- work FILES_TOUCHED footer -> its documented format
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
GOLDEN = SCRIPTS / "golden"
REVIEW_SCRIPTS = SCRIPTS.parent.parent / "review-work-completion" / "scripts"


def _load(name: str, path: Path):
    """Import a hyphen-free helper module by file path (no sys.path surgery)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


statectl = _load("statectl", SCRIPTS / "statectl.py")
resume_target = _load("resume_target", SCRIPTS / "resume_target.py")
check_review_file = _load("check_review_file", REVIEW_SCRIPTS / "check_review_file.py")


# --- state.json <-> statectl (validator) + resume_target (consumer parser) ---

STATE_CASES = [
    ("state-build-pending.json", "/work continues at first non-completed task task-2"),
    ("state-review-cycle2.json", "run review loop at cycle 2"),
    ("state-review-converged.json", "skip review -> done"),
]


@pytest.mark.parametrize("fixture, expected_target", STATE_CASES)
def test_golden_state_accepted_by_statectl_and_resume_target(
    fixture: str, expected_target: str
) -> None:
    # statectl (the sole state.json writer/validator) parses the fixture as valid.
    _raw, parsed = statectl.read_and_parse(GOLDEN / fixture)
    assert isinstance(parsed, dict)
    # resume_target (the consumer parser) resolves the documented next action.
    assert resume_target.resume_target(parsed) == expected_target


# --- review file <-> check_review_file.check ---


def test_golden_review_file_passes_check_review_file() -> None:
    text = (GOLDEN / "review-converged.md").read_text(encoding="utf-8")
    match = check_review_file.FRONTMATTER_REVIEWERS_RE.search(text)
    reviewers = [r.strip() for r in match.group(1).split(",")] if match else []
    assert reviewers, "fixture must name its reviewers in frontmatter"
    assert check_review_file.check(text, reviewers) is None


# --- create-prd frontmatter -> run-autopilot Phase 0 recognized fields (producer pin) ---

# Mirrors run-autopilot references/phase-build.md Phase 0 "Frontmatter parse
# table". No Python consumer parser exists (the Phase 0 parse is model-driven),
# so this binds the producing side only — a documented limitation of R2.
_RECOGNIZED_FRONTMATTER = frozenset({
    "catchup", "rework_cap", "design", "design_gate",
    "doubt_reviewer", "consensus_engine", "pause_on_ambiguity", "default_model",
})


def test_golden_prd_frontmatter_fields_are_recognized() -> None:
    text = (GOLDEN / "prd-frontmatter.md").read_text(encoding="utf-8")
    fm = re.search(r"^---\n(.*?)\n---", text, re.DOTALL)
    assert fm, "fixture must have a frontmatter block"
    keys = {
        line.split(":", 1)[0].strip()
        for line in fm.group(1).splitlines()
        if ":" in line
    }
    unknown = keys - _RECOGNIZED_FRONTMATTER
    assert not unknown, f"frontmatter fields not in the Phase 0 parse table: {unknown}"


# --- work FILES_TOUCHED footer -> documented format (producer pin) ---


def test_golden_work_footer_matches_format() -> None:
    text = (GOLDEN / "work-footer.txt").read_text(encoding="utf-8")
    if re.search(r"^FILES_TOUCHED:\s*none\s*$", text, re.MULTILINE):
        return  # the `FILES_TOUCHED: none` form is valid
    header = re.search(r"^FILES_TOUCHED:\s*$", text, re.MULTILINE)
    assert header, "footer must start with a 'FILES_TOUCHED:' line (or 'FILES_TOUCHED: none')"
    paths = [ln for ln in text[header.end():].splitlines() if ln.strip()]
    assert paths, "footer must list at least one path"
