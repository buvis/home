"""Lifecycle guard tests for the autopilot PRD artifact lifecycle (PRD 00045).

Two kinds of tests live here:

1. Behavioral fixtures (stable green) — reproduce the warden-00011 failure mode:
   a bare ``mv`` into a destination directory that does not exist silently
   misplaces or loses the PRD. These encode *why* the Loud Moves guard is
   needed and demonstrate the verified-move contract on real filesystem ops.

2. Doc-contract tests (RED before this PRD's Phase 1 edits land, GREEN after) —
   assert the SKILL.md / recovery.md prose actually encodes the guards: a
   Phase 0 ``mkdir -p`` covering every lifecycle dir, and an existence-check +
   loud PAUSE after each of the three lifecycle ``mv`` sites (backlog->wip,
   wip->done, wip->stalled).

The contract tests bind to intent (verify-destination-exists + PAUSE on
failure), not to incidental wording, so they fail loud when a move site is left
unguarded. Stdlib + pytest only.
"""

import re
import shutil
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]  # skills/run-autopilot/
SKILL = (_ROOT / "SKILL.md").read_text()
RECOVERY = (_ROOT / "references" / "recovery.md").read_text()

# Every directory a run moves files into; Phase 0 must `mkdir -p` all of them.
LIFECYCLE_DIRS = [
    "prds/backlog",
    "prds/wip",
    "prds/done",
    "prds/stalled",
    "reviews",
    "tmp",
    "autopilot/reports",
    "autopilot/deferred",
]

# A guarded move site verifies the destination exists and PAUSEs loudly when it
# does not. "verify/confirm ... exist" within one clause expresses the check.
_VERIFY_RE = re.compile(r"(verif|confirm)\w*[^.\n]{0,80}exist", re.I)


def _phase_section(text: str, header_prefix: str) -> str:
    """Return the lines from a ``## <header_prefix>...`` heading up to (but not
    including) the next top-level ``## `` heading, or end of file."""
    lines = text.splitlines()
    start = next(
        (i for i, ln in enumerate(lines) if ln.strip().startswith(header_prefix)),
        None,
    )
    if start is None:
        return ""
    end = next(
        (j for j in range(start + 1, len(lines)) if lines[j].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _guarded_windows(text: str, anchor: re.Pattern, window: int = 600) -> list[bool]:
    """For each match of ``anchor``, report whether the following ``window``
    characters contain both an existence-check and a loud PAUSE."""
    return [
        bool(_VERIFY_RE.search(region)) and "PAUSE" in region
        for m in anchor.finditer(text)
        for region in (text[m.start() : m.start() + window],)
    ]


# --------------------------------------------------------------------------- #
# Behavioral fixtures — the warden-00011 missing-dir failure, on real ops.
# --------------------------------------------------------------------------- #


def test_bare_move_into_missing_done_dir_misplaces_prd(tmp_path: Path) -> None:
    """Unguarded `mv wip/x done` with `done/` absent renames the PRD to a stray
    file `done` — it never lands in done/ and is gone from wip/ (warden 00011)."""
    wip = tmp_path / "prds" / "wip"
    wip.mkdir(parents=True)
    prd = wip / "00011-harden.md"
    prd.write_text("# PRD\n")
    done = tmp_path / "prds" / "done"  # intentionally NOT created

    shutil.move(str(prd), str(done))  # no mkdir, no verify — current behavior

    assert not (done / "00011-harden.md").exists()  # never reached the folder
    assert not prd.exists()  # silently gone from wip/
    assert (tmp_path / "prds" / "done").is_file()  # became a stray file instead


def test_move_with_trailing_target_into_missing_dir_errors(tmp_path: Path) -> None:
    """Targeting a path inside a missing dir (shell `mv x done/`) raises rather
    than silently losing the file — the other half of the missing-dir hazard."""
    wip = tmp_path / "prds" / "wip"
    wip.mkdir(parents=True)
    prd = wip / "00011-harden.md"
    prd.write_text("# PRD\n")
    done = tmp_path / "prds" / "done"  # missing

    with pytest.raises((FileNotFoundError, NotADirectoryError)):
        shutil.move(str(prd), str(done / prd.name))

    assert prd.exists()  # source untouched on the error path


def test_verified_move_after_mkdir_lands_prd(tmp_path: Path) -> None:
    """The fix contract: `mkdir -p` the destination, move, then the destination
    file exists and the source is gone."""
    wip = tmp_path / "prds" / "wip"
    wip.mkdir(parents=True)
    prd = wip / "00011-harden.md"
    prd.write_text("# PRD\n")
    done = tmp_path / "prds" / "done"
    done.mkdir(parents=True, exist_ok=True)  # the Phase 0 mkdir -p guard
    target = done / prd.name

    shutil.move(str(prd), str(target))

    assert target.exists()
    assert not prd.exists()


def test_verification_detects_failed_move(tmp_path: Path) -> None:
    """The Loud Moves check: after a move, a missing destination file means the
    move failed and the run must PAUSE — the guard catches the warden case."""
    wip = tmp_path / "prds" / "wip"
    wip.mkdir(parents=True)
    prd = wip / "00011-harden.md"
    prd.write_text("# PRD\n")
    done = tmp_path / "prds" / "done"  # missing → move misplaces
    target = done / prd.name

    try:
        shutil.move(str(prd), str(done))  # unguarded
    except (FileNotFoundError, NotADirectoryError):
        pass

    move_succeeded = target.exists()
    assert move_succeeded is False  # guard would PAUSE here, not continue


# --------------------------------------------------------------------------- #
# Doc-contract tests — RED until Phase 1 (task 3) adds the guards, then GREEN.
# --------------------------------------------------------------------------- #


def test_phase0_ensures_lifecycle_dirs_with_mkdir_p() -> None:
    """Phase 0 must `mkdir -p` every lifecycle dir before any move runs."""
    phase0 = _phase_section(SKILL, "## Phase 0")
    assert phase0, "Phase 0 section not found in SKILL.md"
    assert "mkdir -p" in phase0, (
        "Phase 0 must create lifecycle dirs with `mkdir -p` before the first move"
    )
    missing = [d for d in LIFECYCLE_DIRS if d not in phase0]
    assert not missing, f"Phase 0 mkdir must cover all lifecycle dirs; missing: {missing}"


def test_backlog_to_wip_move_is_verified() -> None:
    """The Phase 0 backlog->wip `mv` must be followed by a verify + PAUSE."""
    phase0 = _phase_section(SKILL, "## Phase 0")
    guards = _guarded_windows(phase0, re.compile(r"mv[^\n]*wip/"))
    assert guards, "no backlog->wip `mv` instruction found in Phase 0"
    assert any(guards), (
        "the backlog->wip `mv` must be followed by an existence check and a "
        "PAUSE on failure"
    )


def test_wip_to_done_move_is_verified() -> None:
    """The Phase 9 wip->done `mv` must be followed by a verify + PAUSE."""
    phase9 = _phase_section(SKILL, "## Phase 9")
    # tolerate markdown backticks/spacing between the paths, e.g. `wip/` to `done/`
    guards = _guarded_windows(phase9, re.compile(r"wip/[^\n]{0,10}done/"))
    assert guards, "no wip->done `mv` instruction found in Phase 9"
    assert all(guards), (
        "the wip->done `mv` must be followed by an existence check and a PAUSE "
        "on failure"
    )


def test_stalled_moves_are_verified() -> None:
    """Every wip->stalled `mv` in recovery.md must verify + PAUSE on failure."""
    anchor = re.compile(r"the PRD from[^\n]*wip/[^\n]*stalled/")
    guards = _guarded_windows(RECOVERY, anchor)
    assert len(guards) >= 2, (
        f"expected >=2 wip->stalled move sites in recovery.md, found {len(guards)}"
    )
    assert all(guards), (
        "every wip->stalled `mv` in recovery.md must be followed by an "
        "existence check and a PAUSE on failure"
    )


# --------------------------------------------------------------------------- #
# Retention contract — durable artifacts survive batch end; only transients go.
# --------------------------------------------------------------------------- #

# Affirmative deletion verbs vs. negations/contract language that must NOT count
# as "an instruction to delete" (the Retention prose names durables to retain).
_DEL_RE = re.compile(r"\b(delete|deletes|rm)\b", re.I)
_NEG_RE = re.compile(
    r"(do not|don'?t|does not|doesn'?t|never|must not|\bnot\b|preserve|retain|durable|intact)",
    re.I,
)
# Durable-artifact references that must never be the target of an affirmative
# delete. Disposables (signal, tmp/, state.json, replan-context.md) may be deleted.
_DURABLE_ARTIFACTS = [
    "deferred JSON",
    "-deferred.json",
    "prds/done",
    "/reviews/",
    "autopilot/reports",
    "project-capsule.md",
]


def _retention_section() -> str:
    """Return the body of the SKILL.md Retention section, or '' if absent."""
    m = re.search(r"^#{2,3}\s+Retention\b", SKILL, re.M)
    if not m:
        return ""
    rest = SKILL[m.end() :]
    nxt = re.search(r"^#{1,3}\s", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def test_skill_documents_a_retention_contract() -> None:
    """SKILL.md must carry a Retention section naming every durable and every
    disposable artifact, so cleanup never guesses what 'temp' means."""
    section = _retention_section()
    assert section, "SKILL.md must contain a Retention section"
    durable = [
        "prds/done",
        "reviews/",
        "autopilot/reports",
        "autopilot/deferred",
        "project-capsule.md",
    ]
    disposable = ["signal", "tmp/", "state.json", "replan-context.md"]
    missing_d = [t for t in durable if t not in section]
    missing_x = [t for t in disposable if t not in section]
    assert not missing_d, f"Retention section must list durable artifacts; missing: {missing_d}"
    assert not missing_x, (
        f"Retention section must list disposable artifacts; missing: {missing_x}"
    )


def test_no_affirmative_delete_of_a_durable_artifact() -> None:
    """No SKILL.md instruction may delete a durable artifact (reviews/, done/,
    reports/, the deferred JSON, the capsule). This is the acceptance for the
    Retention rewrite: enumerate disposables, never directory-level durable rm."""
    offenders = []
    for line in SKILL.splitlines():
        if not _DEL_RE.search(line) or _NEG_RE.search(line):
            continue  # not a delete, or a negation/contract statement
        if any(tok in line for tok in _DURABLE_ARTIFACTS):
            offenders.append(line.strip())
    assert not offenders, f"SKILL.md affirmatively deletes durable artifacts: {offenders}"


# --------------------------------------------------------------------------- #
# Batch identity rollover — one report file per batch; fresh id per batch.
# --------------------------------------------------------------------------- #

_REPORT_SUFFIX = "-report.md"


def _report_filename(batch_id: str) -> str:
    """The report file is keyed by batch id — the checkable invariant."""
    return f"{batch_id}{_REPORT_SUFFIX}"


def _id_from_report_filename(name: str) -> str:
    assert name.endswith(_REPORT_SUFFIX), f"not a report filename: {name}"
    return name[: -len(_REPORT_SUFFIX)]


def test_report_filename_id_equals_batch_id_invariant() -> None:
    """The report filename's embedded id must round-trip to the batch id — the
    invariant Phase 9 verifies at append time."""
    for bid in ("202606092228", "202605181149"):
        assert _id_from_report_filename(_report_filename(bid)) == bid


def test_two_consecutive_batches_get_distinct_report_files(tmp_path: Path) -> None:
    """A fresh batch id (minted after batch end deletes state) keys a distinct
    report file — reports never append across batches."""
    reports = tmp_path / "reports"
    reports.mkdir()
    b1 = "202606120001"
    b2 = "202606130002"  # next batch mints a fresh id
    assert b1 != b2
    (reports / _report_filename(b1)).write_text(f"# Autopilot Batch Report {b1}\n")
    (reports / _report_filename(b2)).write_text(f"# Autopilot Batch Report {b2}\n")
    files = sorted(p.name for p in reports.glob(f"*{_REPORT_SUFFIX}"))
    assert files == [_report_filename(b1), _report_filename(b2)]
    assert len({_id_from_report_filename(f) for f in files}) == 2


def test_phase0_mints_fresh_id_for_a_closed_surviving_batch() -> None:
    """Phase 0 must mint a fresh batch.id when a closed batch's state.json
    survives (phase == done) — the stale-id reuse the forensics found."""
    phase0 = _phase_section(SKILL, "## Phase 0")
    assert re.search(r"fresh\s+`?batch\.id`?", phase0, re.I), (
        "Phase 0 must mint a fresh batch.id for a surviving closed batch"
    )
    assert re.search(r'phase[^\n]{0,40}"done"', phase0), (
        "Phase 0 fresh-id guard must key on a closed (phase == done) surviving batch"
    )


def test_report_append_pins_filename_to_batch_id() -> None:
    """Phase 9 report append must build the filename from the current
    state.batch.id and verify the match — never glob an old report file."""
    phase9 = _phase_section(SKILL, "## Phase 9")
    assert "state.batch.id" in phase9, (
        "Phase 9 report append must reference state.batch.id explicitly"
    )
    assert re.search(r"(verif|confirm|match|equal)[^.\n]{0,70}batch\.id", phase9, re.I) or (
        re.search(r"batch\.id[^.\n]{0,70}(verif|confirm|match|equal)", phase9, re.I)
    ), "Phase 9 must verify the report filename's id equals state.batch.id"
