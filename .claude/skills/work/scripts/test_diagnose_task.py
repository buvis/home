"""Tests for diagnose_task.py — spec-gap diagnosis for a planned task."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).with_name("diagnose_task.py")


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _write_task(tmp_path: Path, body: str, name: str = "task.md") -> Path:
    task_file = tmp_path / name
    task_file.write_text(body)
    return task_file


def _good_preamble() -> str:
    return (
        "Contract (verbatim - do not deviate):\n"
        "  Implement exactly as specified below.\n"
        "\n"
        "Acceptance criteria:\n"
        "  - The feature behaves as described.\n"
    )


# --- missing_contract ---------------------------------------------------


def test_flags_missing_contract(tmp_path: Path) -> None:
    body = (
        "Implement the widget as described.\n"
        "\n"
        "Acceptance criteria:\n"
        "  - The widget renders.\n"
    )
    task_file = _write_task(tmp_path, body)

    result = _run([str(task_file), "--repo-root", str(tmp_path)], cwd=tmp_path)

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["verdict"] == "spec_gap"
    assert "missing_contract" in data["gaps"]


def test_mid_sentence_contract_mention_still_flagged(tmp_path: Path) -> None:
    body = (
        "This task defines the contract for the widget informally.\n"
        "\n"
        "Acceptance criteria:\n"
        "  - The widget renders.\n"
    )
    task_file = _write_task(tmp_path, body)

    result = _run([str(task_file), "--repo-root", str(tmp_path)], cwd=tmp_path)

    data = json.loads(result.stdout)
    assert "missing_contract" in data["gaps"]


def test_indented_contract_line_satisfies_requirement(tmp_path: Path) -> None:
    body = (
        "   Contract (verbatim - do not deviate):\n"
        "     Implement exactly as specified below.\n"
        "\n"
        "Acceptance criteria:\n"
        "  - The widget renders.\n"
    )
    task_file = _write_task(tmp_path, body)

    result = _run([str(task_file), "--repo-root", str(tmp_path)], cwd=tmp_path)

    data = json.loads(result.stdout)
    assert "missing_contract" not in data["gaps"]


# --- missing_acceptance ---------------------------------------------------


def test_flags_missing_acceptance_criteria(tmp_path: Path) -> None:
    body = (
        "Contract (verbatim - do not deviate):\n"
        "  Implement exactly as specified below.\n"
        "\n"
        "No criteria section is present here.\n"
    )
    task_file = _write_task(tmp_path, body)

    result = _run([str(task_file), "--repo-root", str(tmp_path)], cwd=tmp_path)

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["verdict"] == "spec_gap"
    assert "missing_acceptance" in data["gaps"]


def test_acceptance_criteria_satisfied_as_substring_mid_line(tmp_path: Path) -> None:
    body = (
        "Contract (verbatim - do not deviate):\n"
        "  Implement exactly as specified below.\n"
        "\n"
        "See the Acceptance criteria noted in the linked doc for details.\n"
    )
    task_file = _write_task(tmp_path, body)

    result = _run([str(task_file), "--repo-root", str(tmp_path)], cwd=tmp_path)

    data = json.loads(result.stdout)
    assert "missing_acceptance" not in data["gaps"]


# --- dangling_file ---------------------------------------------------


def test_flags_dangling_referenced_file(tmp_path: Path) -> None:
    body = _good_preamble() + (
        "\n"
        "See `skills/work/ghost.py` for prior art.\n"
    )
    task_file = _write_task(tmp_path, body)

    result = _run([str(task_file), "--repo-root", str(tmp_path)], cwd=tmp_path)

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["verdict"] == "spec_gap"
    assert "dangling_file:skills/work/ghost.py" in data["gaps"]


def test_pass_when_all_present_and_files_exist(tmp_path: Path) -> None:
    existing = tmp_path / "skills" / "work" / "existing.py"
    existing.parent.mkdir(parents=True)
    existing.write_text("# already here\n")

    body = _good_preamble() + (
        "\n"
        "See `skills/work/existing.py` for prior art.\n"
    )
    task_file = _write_task(tmp_path, body)

    result = _run([str(task_file), "--repo-root", str(tmp_path)], cwd=tmp_path)

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["verdict"] == "pass"
    assert data["gaps"] == []


def test_existing_skills_path_resolved_against_repo_root_not_flagged(
    tmp_path: Path,
) -> None:
    # Regression guard: paths must resolve against --repo-root, never against
    # the process cwd or the task file's own directory.
    repo_root = tmp_path / "reporoot"
    existing = repo_root / "skills" / "work" / "thing.py"
    existing.parent.mkdir(parents=True)
    existing.write_text("# already here\n")

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    body = _good_preamble() + (
        "\n"
        "See `skills/work/thing.py` for prior art.\n"
    )
    task_file = _write_task(elsewhere, body)

    result = _run(
        [str(task_file), "--repo-root", str(repo_root)], cwd=elsewhere
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "dangling_file:skills/work/thing.py" not in data["gaps"]


# --- creation-target exclusion ---------------------------------------------------


def test_location_line_creation_target_not_flagged(tmp_path: Path) -> None:
    body = _good_preamble() + (
        "\n"
        "Location: `skills/work/scripts/diagnose_task.py`\n"
    )
    task_file = _write_task(tmp_path, body)

    result = _run([str(task_file), "--repo-root", str(tmp_path)], cwd=tmp_path)

    data = json.loads(result.stdout)
    assert "dangling_file:skills/work/scripts/diagnose_task.py" not in data["gaps"]


def test_markdown_table_new_row_creation_target_not_flagged(tmp_path: Path) -> None:
    body = _good_preamble() + (
        "\n"
        "| Path | Status | Notes |\n"
        "|------|--------|-------|\n"
        "| `skills/work/scripts/new_thing.py` | NEW | Handles the widget |\n"
    )
    task_file = _write_task(tmp_path, body)

    result = _run([str(task_file), "--repo-root", str(tmp_path)], cwd=tmp_path)

    data = json.loads(result.stdout)
    assert "dangling_file:skills/work/scripts/new_thing.py" not in data["gaps"]


def test_creation_verb_proximity_target_not_flagged(tmp_path: Path) -> None:
    body = _good_preamble() + (
        "\n"
        "Please create `skills/work/scripts/new_thing.py` next.\n"
    )
    task_file = _write_task(tmp_path, body)

    result = _run([str(task_file), "--repo-root", str(tmp_path)], cwd=tmp_path)

    data = json.loads(result.stdout)
    assert "dangling_file:skills/work/scripts/new_thing.py" not in data["gaps"]


def test_location_creation_target_deep_in_file_not_flagged(tmp_path: Path) -> None:
    # Regression (precision invariant): a token must map to its OWN line, not to a
    # line found by char-offset arithmetic over newline-stripped splitlines(). A
    # Location: creation-target token placed past line 40 was falsely flagged
    # dangling_file because the offset drifted and defeated is_creation_target. A
    # false spec_gap forces a wasted task-description repair on a good task, which
    # the design forbids ("false positives unacceptable").
    filler = "".join(f"Note line {i} with some context text here.\n" for i in range(60))
    body = _good_preamble() + "\n" + filler + (
        "Location: `skills/work/scripts/deep_target.py`\n"
    )
    task_file = _write_task(tmp_path, body)

    result = _run([str(task_file), "--repo-root", str(tmp_path)], cwd=tmp_path)

    data = json.loads(result.stdout)
    assert "dangling_file:skills/work/scripts/deep_target.py" not in data["gaps"]


def test_creation_verb_target_deep_in_file_not_flagged(tmp_path: Path) -> None:
    # Same precision regression via the creation-verb proximity exclusion, deep
    # in the file (past line 40) where the old offset drift misfired.
    filler = "".join(
        f"Background paragraph {i} describing prior context.\n" for i in range(60)
    )
    body = _good_preamble() + "\n" + filler + (
        "Please create `skills/work/scripts/deep_new.py` for this.\n"
    )
    task_file = _write_task(tmp_path, body)

    result = _run([str(task_file), "--repo-root", str(tmp_path)], cwd=tmp_path)

    data = json.loads(result.stdout)
    assert "dangling_file:skills/work/scripts/deep_new.py" not in data["gaps"]


# --- extension / glob exclusions ---------------------------------------------------


def test_markdown_doc_extension_not_flagged(tmp_path: Path) -> None:
    body = _good_preamble() + (
        "\n"
        "See `skills/work/notes.md` for background.\n"
    )
    task_file = _write_task(tmp_path, body)

    result = _run([str(task_file), "--repo-root", str(tmp_path)], cwd=tmp_path)

    data = json.loads(result.stdout)
    assert "dangling_file:skills/work/notes.md" not in data["gaps"]


def test_json_config_extension_not_flagged(tmp_path: Path) -> None:
    body = _good_preamble() + (
        "\n"
        "See `skills/work/config.json` for settings.\n"
    )
    task_file = _write_task(tmp_path, body)

    result = _run([str(task_file), "--repo-root", str(tmp_path)], cwd=tmp_path)

    data = json.loads(result.stdout)
    assert "dangling_file:skills/work/config.json" not in data["gaps"]


def test_glob_pattern_path_not_flagged(tmp_path: Path) -> None:
    body = _good_preamble() + (
        "\n"
        "Applies to all of `skills/*.py` in this area.\n"
    )
    task_file = _write_task(tmp_path, body)

    result = _run([str(task_file), "--repo-root", str(tmp_path)], cwd=tmp_path)

    data = json.loads(result.stdout)
    assert not any(gap.startswith("dangling_file:skills/*.py") for gap in data["gaps"])


# --- verdict / exit-code contract ---------------------------------------------------


def test_verdict_is_spec_gap_when_multiple_gaps_present(tmp_path: Path) -> None:
    body = (
        "Implement the widget as described, referencing "
        "`skills/work/ghost.py` for prior art.\n"
        "\n"
        "No criteria section is present here.\n"
    )
    task_file = _write_task(tmp_path, body)

    result = _run([str(task_file), "--repo-root", str(tmp_path)], cwd=tmp_path)

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["verdict"] == "spec_gap"
    assert {
        "missing_contract",
        "missing_acceptance",
        "dangling_file:skills/work/ghost.py",
    } <= set(data["gaps"])


def test_returncode_zero_even_with_gaps(tmp_path: Path) -> None:
    body = "No contract, no acceptance criteria, nothing referenced.\n"
    task_file = _write_task(tmp_path, body)

    result = _run([str(task_file), "--repo-root", str(tmp_path)], cwd=tmp_path)

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert len(data["gaps"]) > 0
    assert data["verdict"] == "spec_gap"


def test_missing_task_file_exits_2_with_stderr_error(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.md"

    result = _run([str(missing), "--repo-root", str(tmp_path)], cwd=tmp_path)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.strip() != ""
    error_payload = json.loads(result.stderr)
    assert "error" in error_payload
