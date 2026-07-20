"""Tests for ~/.claude/skills/survey/scripts/run.py — skeleton survey behavior.

Subprocess-driven: run.py is invoked as a child process with HOME redirected to
a tmp dir so atlas.json never touches the real ~/.claude/cartographer/. The
synthetic git repos are created inside tmp_path so project_hash() resolves them
correctly.

Run with: `uvx pytest ~/.claude/hooks/tests/test_survey.py -v`
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

RUN_PY = Path.home() / ".claude" / "skills" / "survey" / "scripts" / "run.py"
# run.py imports `_lib_cartographer` from ~/.claude/hooks via
# `sys.path.insert(0, Path.home()/.claude/hooks)`. _run_survey redirects HOME to
# a tmp dir (so atlas.json never touches the real ~/.claude/cartographer/), which
# makes that insert resolve to an empty tmp hooks dir. PYTHONPATH carries the
# real hooks dir into the subprocess so the library import still resolves.
HOOKS_DIR = Path.home() / ".claude" / "hooks"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )


def _make_git_repo(path: Path) -> None:
    """Initialise a bare git repo with a single empty commit."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "master")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    # Need at least one commit so git rev-parse HEAD works.
    (path / ".gitkeep").touch()
    _git(path, "add", ".gitkeep")
    _git(path, "commit", "-m", "init", "--allow-empty")


def _run_survey(
    repo: Path,
    home: Path,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run run.py as a subprocess with HOME redirected to home."""
    env = {
        **os.environ,
        "HOME": str(home),
        "PYTHONPATH": os.pathsep.join(
            p for p in [str(HOOKS_DIR), os.environ.get("PYTHONPATH", "")] if p
        ),
    }
    cmd = [sys.executable, str(RUN_PY), *(extra_args or [])]
    return subprocess.run(
        cmd,
        cwd=str(repo),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _read_atlas(home: Path, repo: Path) -> dict:
    """Locate and parse atlas.json for the repo rooted at repo under home."""
    import hashlib

    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        top = result.stdout.strip()
        h = hashlib.sha256(top.encode()).hexdigest()[:12]
    else:
        h = "global"

    atlas_path = home / ".claude" / "cartographer" / "projects" / h / "atlas.json"
    assert atlas_path.is_file(), f"atlas.json not found at {atlas_path}"
    return json.loads(atlas_path.read_text(encoding="utf-8"))


def _head_sha(repo: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_run_py_file_exists() -> None:
    """run.py must be present before the skeleton suite makes sense."""
    assert RUN_PY.is_file(), f"run.py not found at {RUN_PY} — create it first"


@pytest.mark.integration
def test_canonical_dirs_map_to_named_layers(tmp_path: Path) -> None:
    """Canonical top-level directory names produce matching layer keys in atlas.json."""
    repo = tmp_path / "repo"
    _make_git_repo(repo)
    for d in ("services", "api", "models"):
        (repo / d).mkdir()
        (repo / d / "placeholder.py").touch()

    proc = _run_survey(repo, home=tmp_path)
    assert proc.returncode == 0, f"run.py exited {proc.returncode}:\n{proc.stderr}"

    atlas = _read_atlas(tmp_path, repo)
    layers = atlas["layers"]
    assert "services" in layers, f"expected 'services' layer, got: {list(layers)}"
    assert "api" in layers, f"expected 'api' layer, got: {list(layers)}"
    assert "models" in layers, f"expected 'models' layer, got: {list(layers)}"


@pytest.mark.integration
def test_opaque_dir_becomes_own_layer(tmp_path: Path) -> None:
    """An unrecognised top-level directory becomes a layer keyed by its own name."""
    repo = tmp_path / "repo"
    _make_git_repo(repo)
    (repo / "weird_thing").mkdir()
    (repo / "weird_thing" / "stuff.py").touch()

    proc = _run_survey(repo, home=tmp_path)
    assert proc.returncode == 0, f"run.py exited {proc.returncode}:\n{proc.stderr}"

    atlas = _read_atlas(tmp_path, repo)
    assert "weird_thing" in atlas["layers"], (
        f"expected opaque dir 'weird_thing' as its own layer, got: {list(atlas['layers'])}"
    )


@pytest.mark.integration
def test_head_sha_matches_git_repo(tmp_path: Path) -> None:
    """head_sha in atlas.json equals `git rev-parse HEAD` of the surveyed repo."""
    repo = tmp_path / "repo"
    _make_git_repo(repo)

    proc = _run_survey(repo, home=tmp_path)
    assert proc.returncode == 0, f"run.py exited {proc.returncode}:\n{proc.stderr}"

    expected_sha = _head_sha(repo)
    atlas = _read_atlas(tmp_path, repo)
    assert atlas["head_sha"] == expected_sha, (
        f"head_sha mismatch: atlas has {atlas.get('head_sha')!r}, git says {expected_sha!r}"
    )


@pytest.mark.integration
def test_surveyed_at_is_iso8601_utc(tmp_path: Path) -> None:
    """surveyed_at parses as a valid ISO-8601 UTC timestamp."""
    repo = tmp_path / "repo"
    _make_git_repo(repo)

    proc = _run_survey(repo, home=tmp_path)
    assert proc.returncode == 0, f"run.py exited {proc.returncode}:\n{proc.stderr}"

    atlas = _read_atlas(tmp_path, repo)
    raw = atlas.get("surveyed_at", "")
    assert raw, "surveyed_at is missing or empty"
    # fromisoformat accepts the Z suffix in Python 3.11+; strip it for compat.
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None, "surveyed_at must include timezone info"


@pytest.mark.integration
def test_placeholder_fields_present_with_empty_defaults(tmp_path: Path) -> None:
    """atlas.json always contains the four empty placeholder fields."""
    repo = tmp_path / "repo"
    _make_git_repo(repo)

    proc = _run_survey(repo, home=tmp_path)
    assert proc.returncode == 0, f"run.py exited {proc.returncode}:\n{proc.stderr}"

    atlas = _read_atlas(tmp_path, repo)
    assert atlas.get("forbidden_imports") == [], (
        f"forbidden_imports should be [], got: {atlas.get('forbidden_imports')!r}"
    )
    # `naming` is no longer an empty placeholder — run.py computes per-layer
    # case-style counts (`{layer: {camelCase, snake_case, PascalCase}}`), all
    # zero for a symbol-less repo. Bind that real contract, not the stale `{}`.
    naming = atlas.get("naming")
    assert isinstance(naming, dict), f"naming should be a dict of per-layer counts, got: {naming!r}"
    for layer, counts in naming.items():
        assert set(counts) == {"camelCase", "snake_case", "PascalCase"}, (
            f"naming[{layer!r}] should carry the three case-style counts, got: {counts!r}"
        )
    assert atlas.get("error_style") == "unknown", (
        f"error_style should be 'unknown', got: {atlas.get('error_style')!r}"
    )
    assert atlas.get("dependency_edges") == [], (
        f"dependency_edges should be [], got: {atlas.get('dependency_edges')!r}"
    )


@pytest.mark.integration
def test_non_git_dir_omits_head_sha(tmp_path: Path) -> None:
    """A non-git directory produces atlas.json with NO head_sha key."""
    plain_dir = tmp_path / "not_a_repo"
    plain_dir.mkdir()
    (plain_dir / "somefile.py").touch()

    proc = _run_survey(plain_dir, home=tmp_path)
    assert proc.returncode == 0, f"run.py exited {proc.returncode}:\n{proc.stderr}"

    # For a non-git dir, project_hash() returns ("global", "global", "").
    atlas_path = tmp_path / ".claude" / "cartographer" / "projects" / "global" / "atlas.json"
    assert atlas_path.is_file(), f"atlas.json not found at {atlas_path}"
    atlas = json.loads(atlas_path.read_text(encoding="utf-8"))
    assert "head_sha" not in atlas, (
        f"head_sha must be omitted for non-git dirs, got: {atlas.get('head_sha')!r}"
    )


@pytest.mark.integration
def test_survey_skips_data_and_build_dirs(tmp_path: Path) -> None:
    """Build/dependency and meta-repo data dirs never become layers, so a survey
    of ~/.claude does not make noise out of projects/, and a JS repo does not out
    of node_modules (PRD 00088 R2)."""
    repo = tmp_path / "repo"
    _make_git_repo(repo)
    (repo / "services").mkdir()
    (repo / "services" / "user_service.py").touch()
    for skip in ("node_modules", "projects", "cache"):
        (repo / skip).mkdir()
        (repo / skip / "junk.py").touch()

    proc = _run_survey(repo, home=tmp_path)
    assert proc.returncode == 0, f"run.py exited {proc.returncode}:\n{proc.stderr}"

    layers = _read_atlas(tmp_path, repo)["layers"]
    assert "services" in layers, "real source dir must be surveyed"
    for skip in ("node_modules", "projects", "cache"):
        assert skip not in layers, f"{skip} must be excluded from survey layers"


@pytest.mark.integration
def test_layers_contains_file_paths_not_just_dir_names(tmp_path: Path) -> None:
    """Each layer value is a list of file paths, not just directory names."""
    repo = tmp_path / "repo"
    _make_git_repo(repo)
    (repo / "services").mkdir()
    (repo / "services" / "user_service.py").touch()
    (repo / "services" / "auth_service.py").touch()

    proc = _run_survey(repo, home=tmp_path)
    assert proc.returncode == 0, f"run.py exited {proc.returncode}:\n{proc.stderr}"

    atlas = _read_atlas(tmp_path, repo)
    service_files = atlas["layers"].get("services", [])
    assert isinstance(service_files, list), "layer value must be a list"
    assert len(service_files) >= 1, "services layer must contain at least one file path"
    # Values should be file paths, not just the directory name.
    assert any("service" in f for f in service_files), (
        f"expected file paths in services layer, got: {service_files}"
    )


@pytest.mark.integration
def test_atlas_json_is_valid_json_after_write(tmp_path: Path) -> None:
    """atlas.json is parseable as JSON after the survey (atomic write succeeded)."""
    repo = tmp_path / "repo"
    _make_git_repo(repo)

    proc = _run_survey(repo, home=tmp_path)
    assert proc.returncode == 0, f"run.py exited {proc.returncode}:\n{proc.stderr}"

    # _read_atlas validates JSON parse; assert top-level structure.
    atlas = _read_atlas(tmp_path, repo)
    assert isinstance(atlas, dict), "atlas.json must be a JSON object"
    assert "layers" in atlas
    assert "surveyed_at" in atlas
