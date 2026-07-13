#!/usr/bin/env python3
"""Regression net for brush helper scripts: classification, vetoes, moves."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

import collect_facts as cf
import trash_untracked as tu

OLD = time.time() - 10 * 86400


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q", "-b", "master")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    (r / "tracked.log").write_text("x")
    _git(r, "add", "tracked.log")
    _git(r, "commit", "-qm", "init")
    return r


@pytest.mark.parametrize("rel,expected", [
    ("dev/local/tmp/x.bin", "devlocal"),
    (".env.local", "secret"),
    ("a/__pycache__/m.pyc", "junk-dir"),
    (".DS_Store", "os-junk"),
    ("docs/guide.pdf", "doc"),
    ("README", "doc"),
    ("node_modules/x.js", "heavy"),
    ("foo.log", "junk"),
    ("scratch_bench.py", "scratch"),
    ("src/module.py", "other"),
])
def test_classify_path_rules(rel: str, expected: str) -> None:
    assert cf.classify_path(rel) == expected


def test_default_branch_prefers_master(repo: Path) -> None:
    assert cf.detect_default_branch(repo) == "master"


def test_ctx_flags_in_progress_merge(repo: Path) -> None:
    (repo / ".git/MERGE_HEAD").write_text("x")
    assert cf.gather_repo_ctx(repo)["in_progress_op"] == ["MERGE_HEAD"]


def test_ctx_refuses_non_repo(tmp_path: Path) -> None:
    d = tmp_path / "nogit"
    d.mkdir()
    assert cf.gather_repo_ctx(d)["refusals"]


def test_branch_drift_counts(repo: Path) -> None:
    _git(repo, "branch", "feat")
    (repo / "f2").write_text("y")
    _git(repo, "add", "f2")
    _git(repo, "commit", "-qm", "second")
    feat = [b for b in cf.gather_branches(repo, "master", fast=True)
            if b["name"] == "feat"][0]
    assert (feat["behind"], feat["ahead"]) == (1, 0)
    assert feat["merged"] is True


def _veto(repo: Path, rel: str) -> str | None:
    return tu.veto_reason(rel, repo / rel, tu.load_tracked(repo), 3)


def test_veto_tracked_file(repo: Path) -> None:
    assert "tracked" in _veto(repo, "tracked.log")


def test_veto_doc_suffix(repo: Path) -> None:
    p = repo / "notes.md"
    p.write_text("d")
    os.utime(p, (OLD, OLD))
    assert "documentation" in _veto(repo, "notes.md")


def test_veto_devlocal_protected(repo: Path) -> None:
    p = repo / "dev/local/keep.bin"
    p.parent.mkdir(parents=True)
    p.write_text("k")
    os.utime(p, (OLD, OLD))
    assert "protected" in _veto(repo, "dev/local/keep.bin")


def test_veto_fresh_file(repo: Path) -> None:
    (repo / "fresh.tmp").write_text("f")
    assert "fresh" in _veto(repo, "fresh.tmp")


def test_old_junk_passes_veto(repo: Path) -> None:
    p = repo / "old_junk.log"
    p.write_text("j")
    os.utime(p, (OLD, OLD))
    assert _veto(repo, "old_junk.log") is None


def test_relocate_writes_manifest_row(repo: Path) -> None:
    (repo / "old_junk.log").write_text("j")
    date = "2026-07-13"
    trash_rel = tu.relocate(repo, "old_junk.log", date)
    tu.note_manifest(repo, date, "brush-junk", "old_junk.log", trash_rel)
    assert (repo / trash_rel).is_file()
    row = (repo / "dev/local/.trash/manifest.tsv").read_text().strip().split("\t")
    assert row == [date, "brush-junk", "old_junk.log", trash_rel]


def test_tracked_junk_pathspec_finds_nested(repo: Path) -> None:
    p = repo / "charts/sub/.DS_Store"
    p.parent.mkdir(parents=True)
    p.write_text("x")
    _git(repo, "add", "-f", "charts/sub/.DS_Store")
    _git(repo, "commit", "-qm", "junk")
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z", "--",
         ".DS_Store", "**/.DS_Store", "Thumbs.db", "**/Thumbs.db", "*.pyc"],
        capture_output=True, text=True, check=True).stdout
    assert "charts/sub/.DS_Store" in out.split("\0")
