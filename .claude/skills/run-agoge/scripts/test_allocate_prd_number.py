"""The numbering rule agoge's PRD emission depends on.

    uv run --with pytest pytest test_allocate_prd_number.py

Numbering is deterministic, so it lives in code rather than in a prompt: the
same repo must always yield the same next number, and two writers must never
walk away believing they own the same one.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from allocate_prd_number import claim, claimed_numbers

SCRIPT = Path(__file__).resolve().parent / "allocate_prd_number.py"


def seed(repo: Path, relative: str) -> Path:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# stub\n", encoding="utf-8")
    return path


def test_first_number_in_an_empty_repo_is_one(tmp_path: Path) -> None:
    assert claim(tmp_path, "first-thing").name == "00001-first-thing-v1.md"


def test_scan_covers_every_lifecycle_directory_and_discovery(tmp_path: Path) -> None:
    """A parked PRD keeps its number, so hold/ must count as claimed."""
    seed(tmp_path, "dev/local/prds/backlog/00003-a-v1.md")
    seed(tmp_path, "dev/local/prds/wip/00007-b-v1.md")
    seed(tmp_path, "dev/local/prds/done/00011-c-v1.md")
    seed(tmp_path, "dev/local/prds/hold/00042-d-v1.md")
    seed(tmp_path, "dev/local/discovery/00099-e.md")
    assert claimed_numbers(tmp_path) == {3, 7, 11, 42, 99}
    assert claim(tmp_path, "next-one").name == "00100-next-one-v1.md"


def test_a_taken_filename_pushes_the_claim_to_the_next_number(tmp_path: Path) -> None:
    """The exclusive create is the guard; this is it firing."""
    seed(tmp_path, "dev/local/prds/backlog/00005-taken-v1.md")
    # Same slug, so the scan's max+1 lands on a name that already exists.
    seed(tmp_path, "dev/local/prds/backlog/00006-collide-v1.md")
    assert claim(tmp_path, "collide").name == "00007-collide-v1.md"


def test_two_claims_never_share_a_number(tmp_path: Path) -> None:
    first = claim(tmp_path, "one")
    second = claim(tmp_path, "two")
    assert first != second
    assert first.name == "00001-one-v1.md"
    assert second.name == "00002-two-v1.md"


def test_the_claimed_file_exists_and_is_empty(tmp_path: Path) -> None:
    """The caller writes the body; the claim only reserves the name."""
    claimed = claim(tmp_path, "reserved")
    assert claimed.is_file()
    assert claimed.read_text(encoding="utf-8") == ""


def test_non_prd_filenames_are_ignored(tmp_path: Path) -> None:
    seed(tmp_path, "dev/local/prds/backlog/README.md")
    seed(tmp_path, "dev/local/prds/backlog/FASTTRACK-PLAN-v5.md")
    seed(tmp_path, "dev/local/prds/backlog/0042-too-short-v1.md")
    assert claimed_numbers(tmp_path) == set()


@pytest.mark.parametrize("slug", ["Not Kebab", "trailing-", "UPPER", "under_score", ""])
def test_a_bad_slug_is_refused_rather_than_normalized(tmp_path: Path, slug: str) -> None:
    """Guessing what the caller meant would put a wrong name in the backlog."""
    with pytest.raises(SystemExit):
        claim(tmp_path, slug)


def test_cli_prints_the_path_it_claimed(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path), "from-the-cli"],
        capture_output=True,
        text=True,
        check=True,
    )
    claimed = Path(result.stdout.strip())
    assert claimed.is_file()
    assert claimed.name == "00001-from-the-cli-v1.md"


def test_cli_refuses_wrong_argument_counts(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "usage:" in result.stderr
