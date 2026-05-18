"""
End-to-end behavioral tests for the survey atlas generator (run.py).

All tests operate on real tmp-dir (git) repos and assert on the written
atlas.json / atlas.md.  No internal helpers are imported or patched.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "survey" / "scripts"))

import run


# ---------------------------------------------------------------------------
# PRD-pinned constants — do NOT alter these strings
# ---------------------------------------------------------------------------

PRD_REQUIRED_KEYS = {
    "surveyed_at", "layers", "forbidden_imports",
    "naming", "error_style", "dependency_edges",
}
PRD_OPTIONAL_KEYS = {"head_sha", "staleness", "[manual]", "truncated", "degraded"}
PRD_ALLOWED_KEYS = PRD_REQUIRED_KEYS | PRD_OPTIONAL_KEYS

PRD_LEGACY_KEYS = {"generated_at", "project_hash", "symbols", "naming_conventions", "error_handling"}

PRD_VALID_ERROR_STYLES = {"result", "exceptions", "mixed", "unknown"}

PRD_MD_SECTIONS = [
    "Where things live",
    "Naming conventions",
    "Error-handling style",
    "Existing implementations index",
    "Extension points",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_git_repo(path: Path) -> str:
    """Init a git repo with one commit; return HEAD sha."""
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, check=True, capture_output=True)
    (path / "main.py").write_text("def hello():\n    return 'hello'\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _locate_atlas_json(home: Path) -> Path:
    paths = list((home / ".claude" / "cartographer" / "projects").glob("*/atlas.json"))
    assert len(paths) == 1, f"Expected exactly 1 atlas.json under {home}, found: {paths}"
    return paths[0]


def _locate_atlas_md(home: Path) -> Path:
    paths = list((home / ".claude" / "cartographer" / "projects").glob("*/atlas.md"))
    assert len(paths) == 1, f"Expected exactly 1 atlas.md under {home}, found: {paths}"
    return paths[0]


def _survey(repo: Path, home: Path, *, refresh: bool = False, if_missing: bool = False) -> None:
    prev = os.getcwd()
    try:
        os.chdir(repo)
        run.main(
            _args=argparse.Namespace(refresh=refresh, if_missing=if_missing),
            _home=home,
        )
    finally:
        os.chdir(prev)


@pytest.fixture()
def git_repo(tmp_path):
    """(repo_path, head_sha, home_path) for a fresh git repo."""
    repo = tmp_path / "repo"
    repo.mkdir()
    sha = _init_git_repo(repo)
    home = tmp_path / "home"
    home.mkdir()
    return repo, sha, home


# ---------------------------------------------------------------------------
# atlas.json: correct key set
# ---------------------------------------------------------------------------

def test_atlas_json_has_exact_prd_required_keys(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)

    data = json.loads(_locate_atlas_json(home).read_text())
    actual = set(data.keys())
    assert PRD_REQUIRED_KEYS <= actual, f"Missing keys: {PRD_REQUIRED_KEYS - actual}"
    assert actual <= PRD_ALLOWED_KEYS, f"Unexpected keys: {actual - PRD_ALLOWED_KEYS}"


def test_atlas_json_contains_no_legacy_keys(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)

    data = json.loads(_locate_atlas_json(home).read_text())
    found = set(data.keys()) & PRD_LEGACY_KEYS
    assert not found, f"Legacy keys present: {found}"


# ---------------------------------------------------------------------------
# atlas.json: surveyed_at
# ---------------------------------------------------------------------------

def test_surveyed_at_is_utc_iso8601_string(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)

    ts = json.loads(_locate_atlas_json(home).read_text())["surveyed_at"]
    assert isinstance(ts, str)
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert dt.tzinfo is not None, "surveyed_at must include UTC timezone info"


# ---------------------------------------------------------------------------
# atlas.json: head_sha
# ---------------------------------------------------------------------------

def test_head_sha_equals_git_rev_parse_head(git_repo):
    repo, expected_sha, home = git_repo
    _survey(repo, home)

    data = json.loads(_locate_atlas_json(home).read_text())
    assert "head_sha" in data, "head_sha must be present for a git repo"
    assert data["head_sha"] == expected_sha


def test_head_sha_absent_for_non_git_directory(tmp_path):
    repo = tmp_path / "plain"
    repo.mkdir()
    (repo / "app.py").write_text("x = 1\n")
    home = tmp_path / "home"
    home.mkdir()
    _survey(repo, home)

    data = json.loads(_locate_atlas_json(home).read_text())
    assert "head_sha" not in data, "head_sha must be omitted for non-git directories"


# ---------------------------------------------------------------------------
# atlas.json: error_style enum
# ---------------------------------------------------------------------------

def test_error_style_value_is_in_allowed_enum(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)

    style = json.loads(_locate_atlas_json(home).read_text())["error_style"]
    assert style in PRD_VALID_ERROR_STYLES, \
        f"error_style {style!r} must be one of {PRD_VALID_ERROR_STYLES}"


# ---------------------------------------------------------------------------
# atlas.json: naming structure
# ---------------------------------------------------------------------------

def test_naming_maps_layer_to_case_counts(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)

    naming = json.loads(_locate_atlas_json(home).read_text())["naming"]
    assert isinstance(naming, dict)
    for layer, counts in naming.items():
        assert set(counts.keys()) == {"camelCase", "snake_case", "PascalCase"}, \
            f"naming[{layer!r}] must have exactly camelCase, snake_case, PascalCase"
        for k, v in counts.items():
            assert isinstance(v, int), f"naming[{layer!r}][{k!r}] must be int"


# ---------------------------------------------------------------------------
# atlas.md: both files created
# ---------------------------------------------------------------------------

def test_atlas_md_written_alongside_json(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)
    assert _locate_atlas_md(home).exists()


# ---------------------------------------------------------------------------
# atlas.md: size and sections
# ---------------------------------------------------------------------------

def test_atlas_md_within_5120_byte_limit(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)
    size = _locate_atlas_md(home).stat().st_size
    assert size <= 5120, f"atlas.md is {size} bytes, limit is 5120"


def test_atlas_md_sections_present_in_correct_order(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)
    content = _locate_atlas_md(home).read_text()
    positions = []
    for heading in PRD_MD_SECTIONS:
        pos = content.find(heading)
        assert pos != -1, f"Required section {heading!r} missing from atlas.md"
        positions.append(pos)
    assert positions == sorted(positions), "atlas.md sections are not in the required order"


def test_atlas_md_contains_real_surveyed_content(tmp_path):
    """Guard against atlas.md being rendered from an empty/default dict."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    (repo / "utils.py").write_text("def format_date(d):\n    return str(d)\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add utils"], cwd=repo, check=True, capture_output=True)
    home = tmp_path / "home"
    home.mkdir()
    _survey(repo, home)
    content = _locate_atlas_md(home).read_text()
    assert len(content) > 300, \
        f"atlas.md is suspiciously short ({len(content)} chars); likely rendered from empty data"


# ---------------------------------------------------------------------------
# Atomic write: re-survey leaves a valid JSON file
# ---------------------------------------------------------------------------

def test_resurvey_produces_valid_json(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)
    _survey(repo, home, refresh=True)
    data = json.loads(_locate_atlas_json(home).read_text())
    assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# [manual] block preserved across --refresh
# ---------------------------------------------------------------------------

def test_manual_block_preserved_on_resurvey(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)

    atlas_path = _locate_atlas_json(home)
    data = json.loads(atlas_path.read_text())
    manual_payload = {"note": "keep this", "author": "bob"}
    data["[manual]"] = manual_payload
    atlas_path.write_text(json.dumps(data))

    _survey(repo, home, refresh=True)

    data2 = json.loads(_locate_atlas_json(home).read_text())
    assert "[manual]" in data2, "[manual] key must survive a --refresh re-survey"
    assert data2["[manual]"] == manual_payload, \
        f"[manual] content was altered: {data2['[manual]']!r}"


# ---------------------------------------------------------------------------
# --if-missing: no-op when atlas exists without staleness.flag
# ---------------------------------------------------------------------------

def test_if_missing_skips_existing_fresh_atlas(git_repo, capsys):
    repo, _sha, home = git_repo
    _survey(repo, home)
    atlas_path = _locate_atlas_json(home)
    mtime_before = atlas_path.stat().st_mtime

    _survey(repo, home, if_missing=True)

    assert atlas_path.stat().st_mtime == mtime_before, \
        "--if-missing must not rewrite atlas.json when it is fresh"
    out = capsys.readouterr().out
    assert out.strip(), "--if-missing skip must print an explicit skip reason to stdout"


def test_if_missing_surveys_when_atlas_absent(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    home = tmp_path / "home"
    home.mkdir()
    # No prior survey — atlas is absent
    _survey(repo, home, if_missing=True)
    assert _locate_atlas_json(home).exists(), \
        "--if-missing must create atlas.json when it does not yet exist"


# ---------------------------------------------------------------------------
# --if-missing: rebuilds when staleness.flag file is present on disk
# ---------------------------------------------------------------------------

def test_if_missing_rebuilds_when_staleness_flag_file_present(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)
    atlas_path = _locate_atlas_json(home)
    flag_path = atlas_path.parent / "staleness.flag"

    # Create the empty marker file that signals the atlas is stale
    flag_path.touch()
    mtime_before = atlas_path.stat().st_mtime

    _survey(repo, home, if_missing=True)

    assert atlas_path.stat().st_mtime != mtime_before, \
        "--if-missing must rebuild atlas.json when staleness.flag is present"
    assert not flag_path.exists(), \
        "--if-missing must remove staleness.flag after a successful rebuild"


# ---------------------------------------------------------------------------
# --refresh: removes staleness.flag file on disk
# ---------------------------------------------------------------------------

def test_refresh_removes_staleness_flag_file(git_repo):
    repo, _sha, home = git_repo
    _survey(repo, home)
    atlas_path = _locate_atlas_json(home)
    flag_path = atlas_path.parent / "staleness.flag"

    flag_path.touch()

    _survey(repo, home, refresh=True)

    assert not flag_path.exists(), \
        "--refresh must remove staleness.flag after a successful rebuild"


# ---------------------------------------------------------------------------
# Status line printed to stdout
# ---------------------------------------------------------------------------

def test_survey_prints_status_to_stdout(git_repo, capsys):
    repo, _sha, home = git_repo
    _survey(repo, home)
    out = capsys.readouterr().out
    assert out.strip(), "survey must print a status line to stdout"


# ---------------------------------------------------------------------------
# Truncation: >50 files per layer
# ---------------------------------------------------------------------------

def test_truncated_flag_set_and_footer_visible_when_cap_hit(tmp_path):
    """Repo with >50 Python files: truncated:true in JSON, *atlas truncated* visible in MD."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)

    for i in range(60):
        (repo / f"mod_{i:03d}.py").write_text(f"def fn_{i}():\n    return {i}\n")

    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "many files"], cwd=repo, check=True, capture_output=True)

    home = tmp_path / "home"
    home.mkdir()
    _survey(repo, home)

    data = json.loads(_locate_atlas_json(home).read_text())
    assert data.get("truncated") is True, \
        "atlas.json must have truncated:true when 50-file-per-layer cap is reached"

    md = _locate_atlas_md(home).read_text()
    assert "*atlas truncated*" in md, \
        "atlas.md must contain the visible literal '*atlas truncated*' when truncated"

    # Must not be hidden inside an HTML comment
    for segment in md.split("<!--"):
        if "-->" in segment:
            comment_body = segment.split("-->")[0]
            assert "*atlas truncated*" not in comment_body, \
                "*atlas truncated* must not appear only inside an HTML comment"

    assert len(md.encode()) <= 5120, \
        f"atlas.md must still be <=5120 bytes when truncated; got {len(md.encode())}"
