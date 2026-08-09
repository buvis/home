"""Behavioural contract for consolidate_findings.py (PRD 00095).

The merge threshold is pinned by these fixtures, not by taste: if
MERGE_THRESHOLD moves, the paraphrase cases below must still merge and the
distinct-defect cases must still stay apart. Change the constant only with
this suite.

The four-reviewer paraphrase fixture reconstructs the engram batch
202608012229 cycle-2 case named in the PRD (one `sys.exit(1)` defect that
four reviewers worded four ways and the bash consolidator scored [1/4]
four times). The original reviewer outputs were GC'd with
`dev/local/reviews/`, so the wordings here are reconstructed from the PRD's
and the batch record's descriptions, not copied from the files.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import consolidate_findings as cf
import pytest

SCRIPT = Path(__file__).with_name("consolidate_findings.py")

# One defect, four reviewers, four wordings.
SYS_EXIT_WORDINGS = [
    "sys.exit(1) called inside a library function instead of raising",
    "library code calls sys.exit(1) rather than raising an exception",
    "calling sys.exit(1) in a library path kills the caller's process",
    "sys.exit(1) in library code should raise instead of exiting",
]


def _write(tmp_path: Path, name: str, lines: list[str]) -> Path:
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _finding(desc: str, file: str = "src/cli.py", severity: str = "🟡") -> cf.Finding:
    return cf.Finding(agent="X", severity=severity, desc=desc, file=file, task="1")


# --- parsing ---------------------------------------------------------------


def test_parses_the_documented_line_format() -> None:
    f = cf.parse_line(
        "[ALICE] 🔴 SQL injection in query builder | File: src/db/query.ts | Task: 3",
        "ALICE",
    )
    assert f is not None
    assert (f.severity, f.desc, f.file, f.task) == (
        "🔴",
        "SQL injection in query builder",
        "src/db/query.ts",
        "3",
    )


@pytest.mark.parametrize(
    "line",
    [
        "",
        "```",
        "[ALICE] ✅ No issues found",
        "some prose the reviewer wrote before the findings",
        "[ALICE] 🔴 missing the file and task suffix",
        "[ALICE] X not a severity | File: a.py | Task: 1",
    ],
)
def test_non_finding_lines_are_ignored(line: str) -> None:
    assert cf.parse_line(line, "ALICE") is None


def test_non_ascii_description_survives_intact() -> None:
    """The defect that killed the bash predecessor: BSD `tr` mangled the
    lead byte of a Latin-1-range character and BSD `sed` then refused the
    line, so normalization silently returned empty."""
    f = cf.parse_line(
        "[BOB] 🟡 café header is mis-encoded | File: src/naïve.py | Task: 2",
        "BOB",
    )
    assert f is not None
    assert f.desc == "café header is mis-encoded"
    assert f.file == "src/naïve.py"


# --- matching --------------------------------------------------------------


def test_paraphrases_of_one_defect_match() -> None:
    base = _finding(SYS_EXIT_WORDINGS[0])
    for wording in SYS_EXIT_WORDINGS[1:]:
        assert cf.match(base, _finding(wording)), wording


@pytest.mark.parametrize(
    "other",
    [
        "argument parser accepts a negative timeout without validation",
        "_run_status returns a bare string instead of a structured result",
        "retry backoff is never applied to the failing request",
        # The closest distinct pair measured, at 0.200 — this one pins the
        # lower edge of the usable threshold band. If it starts merging,
        # MERGE_THRESHOLD went too low and distinct defects are being hidden.
        "the library function has no docstring",
    ],
)
def test_distinct_defects_in_one_file_do_not_match(other: str) -> None:
    assert not cf.match(_finding(SYS_EXIT_WORDINGS[0]), _finding(other))


def test_the_threshold_sits_inside_the_measured_band() -> None:
    """The band both fixture groups leave open. Stated as an assertion so a
    threshold edit that passes by luck on the cases above still fails here."""
    worst_paraphrase = min(
        cf.jaccard(cf.tokens(SYS_EXIT_WORDINGS[0]), cf.tokens(w))
        for w in SYS_EXIT_WORDINGS[1:]
    )
    closest_distinct = cf.jaccard(
        cf.tokens(SYS_EXIT_WORDINGS[0]),
        cf.tokens("the library function has no docstring"),
    )
    assert closest_distinct < cf.MERGE_THRESHOLD <= worst_paraphrase


def test_same_wording_in_different_files_does_not_match() -> None:
    a = _finding(SYS_EXIT_WORDINGS[0], file="src/cli.py")
    b = _finding(SYS_EXIT_WORDINGS[0], file="src/server.py")
    assert not cf.match(a, b)


def test_path_tail_and_line_suffix_resolve_to_the_same_file() -> None:
    assert cf.files_match("src/db/query.ts", "query.ts")
    assert cf.files_match("src/db/query.ts:42", "src/db/query.ts")
    assert cf.files_match("./src/db/query.ts", "src/db/query.ts")


def test_same_basename_in_different_directories_is_not_the_same_file() -> None:
    assert not cf.files_match("pkg_a/__init__.py", "pkg_b/__init__.py")


# --- consolidation --------------------------------------------------------


def test_four_reviewers_wording_one_defect_merge_to_one_row(tmp_path: Path) -> None:
    agents = ["ALICE", "BLAKE", "BOB", "CARL"]
    severities = ["🟡", "🟠", "🔴", "🟡"]
    pairs = []
    for agent, severity, wording in zip(agents, severities, SYS_EXIT_WORDINGS):
        path = _write(
            tmp_path,
            f"{agent.lower()}.txt",
            [f"[{agent}] {severity} {wording} | File: src/cli.py | Task: 4"],
        )
        pairs.append(f"{agent}:{path}")

    result = _run(*pairs)
    assert result.returncode == 0
    rows = [ln for ln in result.stdout.splitlines() if ln.startswith("| [")]
    assert len(rows) == 1, result.stdout
    assert "[4/4]" in rows[0]
    # Most severe severity wins, first-seen description is kept.
    assert "🔴" in rows[0]
    assert SYS_EXIT_WORDINGS[0] in rows[0]
    assert "ALICE, BLAKE, BOB, CARL" in rows[0]


def test_distinct_defects_stay_separate_rows(tmp_path: Path) -> None:
    a = _write(
        tmp_path,
        "alice.txt",
        [
            f"[ALICE] 🟠 {SYS_EXIT_WORDINGS[0]} | File: src/cli.py | Task: 4",
            "[ALICE] 🟡 argument parser accepts a negative timeout without "
            "validation | File: src/cli.py | Task: 4",
        ],
    )
    result = _run(f"ALICE:{a}")
    rows = [ln for ln in result.stdout.splitlines() if ln.startswith("| [")]
    assert len(rows) == 2, result.stdout
    assert all("[1/1]" in row for row in rows)


def test_single_reviewer_output_matches_the_legacy_table_format(tmp_path: Path) -> None:
    a = _write(
        tmp_path,
        "alice.txt",
        ["[ALICE] 🔴 SQL injection in query builder | File: src/db/query.ts | Task: 3"],
    )
    result = _run(f"ALICE:{a}")
    assert result.stdout == (
        "| Consensus | Severity | Issue | File | Task | Found By |\n"
        "|-----------|----------|-------|------|------|----------|\n"
        "| [1/1] | 🔴 | SQL injection in query builder | src/db/query.ts | 3 | ALICE |\n"
    )


def test_rows_sort_by_consensus_then_severity(tmp_path: Path) -> None:
    a = _write(
        tmp_path,
        "alice.txt",
        [
            "[ALICE] 🟡 lonely medium about pagination offsets | File: a.py | Task: 1",
            "[ALICE] 🔴 lonely critical about token leakage | File: b.py | Task: 2",
            "[ALICE] 🟠 shared high about retry backoff | File: c.py | Task: 3",
        ],
    )
    b = _write(
        tmp_path,
        "bob.txt",
        ["[BOB] 🟠 shared high about retry backoff | File: c.py | Task: 3"],
    )
    result = _run(f"ALICE:{a}", f"BOB:{b}")
    rows = [ln for ln in result.stdout.splitlines() if ln.startswith("| [")]
    assert rows[0].startswith("| [2/2] | 🟠")  # consensus first
    assert rows[1].startswith("| [1/2] | 🔴")  # then severity
    assert rows[2].startswith("| [1/2] | 🟡")


def test_no_findings_prints_the_sentinel(tmp_path: Path) -> None:
    a = _write(tmp_path, "alice.txt", ["[ALICE] ✅ No issues found"])
    result = _run(f"ALICE:{a}")
    assert result.stdout.strip() == "✅ No issues found - all agents passed"
    assert result.returncode == 0


def test_a_skipped_reviewers_missing_file_is_not_an_error(tmp_path: Path) -> None:
    a = _write(
        tmp_path,
        "alice.txt",
        ["[ALICE] 🟡 something small | File: a.py | Task: 1"],
    )
    result = _run(f"ALICE:{a}", f"CARL:{tmp_path / 'never-written.txt'}")
    assert result.returncode == 0
    assert "[1/2]" in result.stdout


# --- ledger dismissal ------------------------------------------------------


def _ledger(tmp_path: Path, entries: list[dict]) -> Path:
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def test_blake_reraising_a_settled_deferral_is_auto_dismissed(tmp_path: Path) -> None:
    blake = _write(
        tmp_path,
        "blake.txt",
        [f"[BLAKE] 🟠 {SYS_EXIT_WORDINGS[1]} | File: src/cli.py | Task: 4"],
    )
    ledger = _ledger(
        tmp_path,
        [
            {
                "cycle": 1,
                "disposition": "settled-deferral",
                "severity": "🟠",
                "issue": SYS_EXIT_WORDINGS[0],
                "file": "src/cli.py",
                "reason": "deferred to batch end, out of PRD scope",
            }
        ],
    )
    result = _run(f"BLAKE:{blake}", "--ledger", str(ledger), "--ledger-dismiss", "BLAKE")
    assert result.returncode == 0
    assert "✅ No issues found" in result.stdout
    assert "### Auto-dismissed (ledger)" in result.stdout
    assert "deferred to batch end, out of PRD scope" in result.stdout
    assert not [ln for ln in result.stdout.splitlines() if ln.startswith("| [")]


def test_the_filter_is_blake_only(tmp_path: Path) -> None:
    """An implementation-aware reviewer re-raising despite the prompt feed
    stays visible as signal - only the blind lens is filtered."""
    alice = _write(
        tmp_path,
        "alice.txt",
        [f"[ALICE] 🟠 {SYS_EXIT_WORDINGS[1]} | File: src/cli.py | Task: 4"],
    )
    ledger = _ledger(
        tmp_path,
        [{"issue": SYS_EXIT_WORDINGS[0], "file": "src/cli.py", "reason": "settled"}],
    )
    result = _run(f"ALICE:{alice}", "--ledger", str(ledger), "--ledger-dismiss", "BLAKE")
    assert "[1/1]" in result.stdout
    assert "Auto-dismissed" not in result.stdout


def test_an_unsettled_blake_finding_is_untouched(tmp_path: Path) -> None:
    blake = _write(
        tmp_path,
        "blake.txt",
        ["[BLAKE] 🟠 retry backoff is never applied | File: src/cli.py | Task: 4"],
    )
    ledger = _ledger(
        tmp_path,
        [{"issue": SYS_EXIT_WORDINGS[0], "file": "src/cli.py", "reason": "settled"}],
    )
    result = _run(f"BLAKE:{blake}", "--ledger", str(ledger), "--ledger-dismiss", "BLAKE")
    assert "[1/1]" in result.stdout
    assert "Auto-dismissed" not in result.stdout


def test_malformed_ledger_warns_once_and_drops_no_findings(tmp_path: Path) -> None:
    blake = _write(
        tmp_path,
        "blake.txt",
        [f"[BLAKE] 🟠 {SYS_EXIT_WORDINGS[1]} | File: src/cli.py | Task: 4"],
    )
    ledger = tmp_path / "ledger.json"
    ledger.write_text("{not json at all", encoding="utf-8")
    result = _run(f"BLAKE:{blake}", "--ledger", str(ledger), "--ledger-dismiss", "BLAKE")
    assert result.returncode == 0
    assert "[1/1]" in result.stdout
    assert len(result.stderr.strip().splitlines()) == 1
    assert "ignoring ledger" in result.stderr


def test_ledger_that_is_not_a_list_drops_no_findings(tmp_path: Path) -> None:
    blake = _write(
        tmp_path,
        "blake.txt",
        [f"[BLAKE] 🟠 {SYS_EXIT_WORDINGS[1]} | File: src/cli.py | Task: 4"],
    )
    ledger = tmp_path / "ledger.json"
    ledger.write_text('{"issue": "wrong shape"}', encoding="utf-8")
    result = _run(f"BLAKE:{blake}", "--ledger", str(ledger), "--ledger-dismiss", "BLAKE")
    assert "[1/1]" in result.stdout
    assert "not a list" in result.stderr


def test_a_malformed_pair_is_rejected_rather_than_silently_skipped() -> None:
    result = _run("ALICE-no-colon")
    assert result.returncode != 0
    assert "NAME:FILE" in result.stderr
