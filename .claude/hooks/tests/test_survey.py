"""Tests for ~/.claude/skills/survey/scripts/run.py — survey brief behavior.

Subprocess-driven: run.py is invoked as a child process with HOME redirected to
a tmp dir, so a survey that wrongly wrote a store would leave it somewhere this
suite can see it. The synthetic git repos are created inside tmp_path so
project_hash() resolves them correctly.

PRD 00138 retired the stored atlas: run.py prints the brief to stdout and
writes nothing, so these tests read stdout.

Run with: `uvx pytest ~/.claude/hooks/tests/test_survey.py -v`
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

RUN_PY = Path.home() / ".claude" / "skills" / "survey" / "scripts" / "run.py"
# run.py imports `_lib_cartographer` from ~/.claude/hooks via
# `sys.path.insert(0, Path.home()/.claude/hooks)`. _run_survey redirects HOME to
# a tmp dir, which makes that insert resolve to an empty tmp hooks dir.
# PYTHONPATH carries the real hooks dir into the subprocess so the library
# import still resolves.
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


def _run_survey(repo: Path, home: Path) -> subprocess.CompletedProcess[str]:
    """Run run.py as a subprocess with HOME redirected to home."""
    env = {
        **os.environ,
        "HOME": str(home),
        "PYTHONPATH": os.pathsep.join(
            p for p in [str(HOOKS_DIR), os.environ.get("PYTHONPATH", "")] if p
        ),
    }
    return subprocess.run(
        [sys.executable, str(RUN_PY)],
        cwd=str(repo),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _brief(repo: Path, home: Path) -> str:
    """Run the survey and return its brief, asserting a clean exit."""
    proc = _run_survey(repo, home=home)
    assert proc.returncode == 0, f"run.py exited {proc.returncode}:\n{proc.stderr}"
    return proc.stdout


def _layer_counts(brief: str) -> dict[str, int]:
    """Parse the 'Where things live' entries into {layer: file count}."""
    return {
        m.group(1): int(m.group(2))
        for m in re.finditer(r"^- \*\*([^*]+)\*\*: (\d+) files$", brief, re.MULTILINE)
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_run_py_file_exists() -> None:
    """run.py must be present before the suite makes sense."""
    assert RUN_PY.is_file(), f"run.py not found at {RUN_PY} — create it first"


@pytest.mark.integration
def test_canonical_dirs_map_to_named_layers(tmp_path: Path) -> None:
    """Canonical top-level directory names produce matching layer entries."""
    repo = tmp_path / "repo"
    _make_git_repo(repo)
    for d in ("services", "api", "models"):
        (repo / d).mkdir()
        (repo / d / "placeholder.py").touch()

    layers = _layer_counts(_brief(repo, home=tmp_path))
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

    layers = _layer_counts(_brief(repo, home=tmp_path))
    assert "weird_thing" in layers, (
        f"expected opaque dir 'weird_thing' as its own layer, got: {list(layers)}"
    )


@pytest.mark.integration
def test_survey_leaves_no_store_behind(tmp_path: Path) -> None:
    """PRD 00138: the brief is ephemeral — a survey creates no cartographer tree.

    HOME is redirected, so an implementation that still wrote an atlas.json,
    an atlas.md, a staleness flag, or an empty `projects/` dir would leave it
    right here.
    """
    repo = tmp_path / "repo"
    _make_git_repo(repo)

    assert _brief(repo, home=tmp_path).strip(), "survey must print the brief to stdout"
    assert not (tmp_path / ".local" / "share" / "agents" / "cartographer").exists(), (
        "survey must not create anything under the cartographer tree"
    )


@pytest.mark.integration
def test_non_git_dir_is_surveyed(tmp_path: Path) -> None:
    """A plain (non-git) directory still produces a brief instead of failing."""
    plain_dir = tmp_path / "not_a_repo"
    plain_dir.mkdir()
    (plain_dir / "somefile.py").touch()

    brief = _brief(plain_dir, home=tmp_path)
    assert "## Where things live" in brief, (
        f"a non-git directory must still yield a brief, got:\n{brief}"
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

    layers = _layer_counts(_brief(repo, home=tmp_path))
    assert "services" in layers, "real source dir must be surveyed"
    for skip in ("node_modules", "projects", "cache"):
        assert skip not in layers, f"{skip} must be excluded from survey layers"


@pytest.mark.integration
def test_brief_indexes_symbols_by_file_path(tmp_path: Path) -> None:
    """Symbols are indexed by their file path, not by a bare layer name."""
    repo = tmp_path / "repo"
    _make_git_repo(repo)
    (repo / "services").mkdir()
    (repo / "services" / "user_service.py").write_text("def create_user():\n    pass\n")
    (repo / "services" / "auth_service.py").write_text("def issue_token():\n    pass\n")

    brief = _brief(repo, home=tmp_path)
    assert "services/user_service.py:1" in brief, (
        f"brief must index symbols by full file path, got:\n{brief}"
    )
    assert _layer_counts(brief).get("services") == 2, (
        f"services layer must report both files, got: {_layer_counts(brief)}"
    )
