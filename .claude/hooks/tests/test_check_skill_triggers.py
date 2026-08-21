"""Tests for hooks/check_skill_triggers.py.

The motivating regression is a fixture here: commit `76feb4475`'s before/after
`manage-agents-md` descriptions must yield exactly the two phrases that edit
silently dropped. Everything else guards the silence contract - this hook is
advisory and must print nothing at all unless a phrase really went missing or
two skills really claim the same one.

Integration tests build real git repos under tmp_path; one binds to the live
~/.buvis bare repo to prove the absolute-pathspec mitigation actually resolves.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[1]
HOOK = HOOKS_DIR / "check_skill_triggers.py"

if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

import check_skill_triggers as cst

# Verbatim from `git show 76feb4475 -- .claude/skills/manage-agents-md/SKILL.md`.
BEFORE_76FEB4475 = (
    "Use when creating, auditing, or improving an AGENTS.md file for AI coding "
    "agents (progressive disclosure, context window budgeting). Triggers on "
    '"agents.md", "AGENTS.md", "create AGENTS.md", "audit AGENTS.md", '
    '"improve AGENTS.md".'
)
AFTER_76FEB4475 = (
    "Use when creating, auditing, or improving an AGENTS.md file, or promoting "
    "project memories into it (progressive disclosure, context budgeting). "
    'Triggers on "AGENTS.md", "audit AGENTS.md", "promote memories", '
    '"memories to AGENTS.md".'
)


def skill_md(name: str, description: str, body: str = "Body.") -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\n{body}\n"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def make_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "master")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    return root


def commit_skill(repo: Path, rel: str, description: str) -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(skill_md(path.parent.name, description), encoding="utf-8")
    git(repo, "add", str(path))
    git(repo, "commit", "-q", "-m", "add skill")
    return path


def run_hook(
    payload: dict,
    home: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Drive the hook as the harness does. `home` overrides $HOME so the
    collision scan sees a sandbox instead of the operator's real skills -
    without it a fixture phrase collides with whatever is actually installed."""
    env = dict(os.environ)
    if home is not None:
        env["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
    )


def sandbox_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point Path.home() at an empty sandbox so the collision scan sees only
    what a test puts there, never the operator's real skills."""
    home = tmp_path / "home"
    (home / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    return home


def sandbox_cache_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the on-disk trigger-index cache at a sandbox file so tests never
    read or write the operator's real
    ~/.claude/hooks/.trigger-index-cache.json. `_INDEX_CACHE_FILE` is a
    module-level constant bound at import time, so `sandbox_home` (which only
    patches `Path.home()` for later calls) does not redirect it - this needs
    its own patch. The file lives directly under `tmp_path` so its parent
    directory always exists, matching the real `hooks/` directory."""
    cache_file = tmp_path / ".trigger-index-cache.json"
    monkeypatch.setattr(cst, "_INDEX_CACHE_FILE", cache_file)
    return cache_file


def count_skill_md_reads(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Wrap `Path.read_text` with a counter scoped to files named SKILL.md, so
    a warm-cache assertion can't be fooled by a legitimate read of the cache
    file itself (whose name and read method are not part of the contract)."""
    reads: list[Path] = []
    real_read_text = Path.read_text

    def counting_read_text(self, *args, **kwargs):
        if self.name == "SKILL.md":
            reads.append(self)
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)
    return reads


@pytest.fixture(autouse=True)
def block_real_trigger_index_cache_access(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """No test in this module may read or modify the operator's real
    ~/.claude/hooks/.trigger-index-cache.json. The write-side check binds to
    the rule, not to `Path.write_text`: it snapshots the real file's
    existence, content and mtime before the test and asserts none of them
    changed after, so a write through ANY mechanism - including an atomic
    write-to-tempfile-then-rename - still fails the guard. Autouse, so a test
    that forgets to call `sandbox_cache_file` fails loudly instead of
    silently touching the real file - a guarantee that can't be forgotten the
    way a list of which tests currently remember to sandbox it could be."""
    real_cache = cst._INDEX_CACHE_FILE.resolve()
    existed_before = real_cache.exists()
    content_before = real_cache.read_bytes() if existed_before else None
    mtime_before = real_cache.stat().st_mtime if existed_before else None
    real_read_text = Path.read_text

    def guarded_read_text(self, *args, **kwargs):
        assert self.resolve() != real_cache, "read the real trigger-index cache"
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    yield

    assert real_cache.exists() == existed_before, "wrote the real trigger-index cache"
    if existed_before:
        assert real_cache.read_bytes() == content_before, (
            "wrote the real trigger-index cache"
        )
        assert real_cache.stat().st_mtime == mtime_before, (
            "wrote the real trigger-index cache"
        )


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_extracts_quoted_phrases_in_order() -> None:
    text = skill_md("x", 'Use when foo. Triggers on "alpha", "beta gamma".')
    assert cst.extract_triggers(text) == ["alpha", "beta gamma"]


@pytest.mark.unit
def test_description_without_quotes_yields_no_phrases() -> None:
    # Prose-only triggering is legitimate, not an error.
    assert cst.extract_triggers(skill_md("x", "Use when nothing is quoted.")) == []


@pytest.mark.unit
def test_folds_a_description_wrapped_across_lines() -> None:
    text = (
        '---\nname: x\ndescription: Use when foo.\n  Triggers on "alpha".\n---\n\n# x\n'
    )
    assert cst.extract_triggers(text) == ["alpha"]


@pytest.mark.unit
def test_stops_at_the_next_frontmatter_key() -> None:
    text = '---\ndescription: Triggers on "alpha".\nmodel: "sonnet"\n---\n\n# x\n'
    assert cst.extract_triggers(text) == ["alpha"]


@pytest.mark.unit
def test_ignores_quotes_in_the_body() -> None:
    text = skill_md("x", 'Triggers on "alpha".', body='Do not match "beta" here.')
    assert cst.extract_triggers(text) == ["alpha"]


@pytest.mark.unit
def test_deduplicates_case_insensitively_keeping_first_spelling() -> None:
    text = skill_md("x", 'Triggers on "AGENTS.md", "agents.md".')
    assert cst.extract_triggers(text) == ["AGENTS.md"]


@pytest.mark.unit
def test_file_without_frontmatter_yields_no_phrases() -> None:
    assert cst.extract_triggers('# x\n\nTriggers on "alpha".\n') == []


# --------------------------------------------------------------------------- #
# Regression detection
# --------------------------------------------------------------------------- #
@pytest.mark.integration
def test_replaying_76feb4475_names_both_lost_phrases(tmp_path: Path) -> None:
    """The regression this hook exists for.

    "agents.md" also vanished literally, but "AGENTS.md" survives it
    case-folded, so exactly two phrases are genuinely lost.
    """
    repo = make_repo(tmp_path / "repo")
    path = commit_skill(repo, "skills/manage-agents-md/SKILL.md", BEFORE_76FEB4475)
    path.write_text(skill_md("manage-agents-md", AFTER_76FEB4475), encoding="utf-8")

    assert cst.dropped_since_head(str(path)) == [
        "create AGENTS.md",
        "improve AGENTS.md",
    ]


@pytest.mark.integration
def test_adding_a_phrase_drops_nothing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    path = commit_skill(repo, "skills/a/SKILL.md", 'Triggers on "alpha".')
    path.write_text(skill_md("a", 'Triggers on "alpha", "beta".'), encoding="utf-8")

    assert cst.dropped_since_head(str(path)) == []


@pytest.mark.integration
def test_rewording_prose_outside_quotes_drops_nothing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    path = commit_skill(repo, "skills/a/SKILL.md", 'Use when foo. Triggers on "alpha".')
    path.write_text(
        skill_md("a", 'Use when something else entirely. Triggers on "alpha".'),
        encoding="utf-8",
    )

    assert cst.dropped_since_head(str(path)) == []


@pytest.mark.integration
def test_recasing_a_phrase_drops_nothing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    path = commit_skill(repo, "skills/a/SKILL.md", 'Triggers on "Alpha".')
    path.write_text(skill_md("a", 'Triggers on "alpha".'), encoding="utf-8")

    assert cst.dropped_since_head(str(path)) == []


@pytest.mark.integration
def test_uncommitted_new_skill_is_silent(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    path = repo / "skills" / "new" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(skill_md("new", 'Triggers on "alpha".'), encoding="utf-8")

    assert cst.dropped_since_head(str(path)) == []


@pytest.mark.integration
def test_path_outside_any_repo_is_silent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = sandbox_home(monkeypatch, tmp_path)  # no ~/.buvis in the sandbox
    path = home / ".claude" / "skills" / "loose" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(skill_md("loose", 'Triggers on "alpha".'), encoding="utf-8")

    assert cst.committed_text(str(path)) is None
    assert cst.dropped_since_head(str(path)) == []


@pytest.mark.integration
def test_git_failure_is_silent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    path = commit_skill(repo, "skills/a/SKILL.md", 'Triggers on "alpha".')
    path.write_text(skill_md("a", "No triggers at all."), encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise OSError("git is missing")

    monkeypatch.setattr(cst.subprocess, "run", boom)

    assert cst.committed_text(str(path)) is None
    assert cst.dropped_since_head(str(path)) == []


@pytest.mark.integration
def test_tracked_claude_file_resolves_from_an_unrelated_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The bare-repo mitigation: ~/.buvis resolves pathspecs against cwd, so a
    relative one returns nothing and every file looks clean. Absolute paths and
    `HEAD:<path-from-root>` must resolve from anywhere."""
    if not (Path.home() / ".buvis").is_dir():
        pytest.skip("~/.buvis bare repo not present")
    tracked = Path.home() / ".claude" / "AGENTS.md"
    if not tracked.exists():
        pytest.skip("~/.claude/AGENTS.md not present")

    monkeypatch.chdir(tmp_path)

    assert cst.committed_text(str(tracked)) is not None


# --------------------------------------------------------------------------- #
# Collision detection
# --------------------------------------------------------------------------- #
@pytest.mark.integration
def test_reports_a_phrase_two_skills_claim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = sandbox_home(monkeypatch, tmp_path)
    sandbox_cache_file(monkeypatch, tmp_path)
    skills = home / ".claude" / "skills"
    for name in ("a", "b"):
        (skills / name).mkdir(parents=True)
        (skills / name / "SKILL.md").write_text(
            skill_md(name, 'Triggers on "audit config".'),
            encoding="utf-8",
        )

    hits = cst.collisions(str(skills / "a" / "SKILL.md"), ["audit config"])

    assert list(hits) == ["audit config"]
    assert hits["audit config"] == [str(skills / "b" / "SKILL.md")]


@pytest.mark.integration
def test_collision_scan_reaches_installed_plugin_skills(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = sandbox_home(monkeypatch, tmp_path)
    sandbox_cache_file(monkeypatch, tmp_path)
    mine = home / ".claude" / "skills" / "a" / "SKILL.md"
    mine.parent.mkdir(parents=True)
    mine.write_text(skill_md("a", 'Triggers on "audit config".'), encoding="utf-8")
    plugin = (
        home
        / ".claude"
        / "plugins"
        / "cache"
        / "mkt"
        / "plug"
        / "1.0.0"
        / "skills"
        / "p"
    )
    plugin.mkdir(parents=True)
    (plugin / "SKILL.md").write_text(
        skill_md("p", 'Triggers on "audit config".'),
        encoding="utf-8",
    )

    hits = cst.collisions(str(mine), ["audit config"])

    assert hits["audit config"] == [str(plugin / "SKILL.md")]


@pytest.mark.integration
def test_a_skill_does_not_collide_with_itself(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = sandbox_home(monkeypatch, tmp_path)
    sandbox_cache_file(monkeypatch, tmp_path)
    mine = home / ".claude" / "skills" / "a" / "SKILL.md"
    mine.parent.mkdir(parents=True)
    mine.write_text(skill_md("a", 'Triggers on "alpha".'), encoding="utf-8")

    assert cst.collisions(str(mine), ["alpha"]) == {}


@pytest.mark.integration
def test_collisions_between_two_other_skills_stay_silent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = sandbox_home(monkeypatch, tmp_path)
    sandbox_cache_file(monkeypatch, tmp_path)
    skills = home / ".claude" / "skills"
    for name in ("b", "c"):
        (skills / name).mkdir(parents=True)
        (skills / name / "SKILL.md").write_text(
            skill_md(name, 'Triggers on "shared".'),
            encoding="utf-8",
        )
    mine = skills / "a" / "SKILL.md"
    mine.parent.mkdir(parents=True)
    mine.write_text(skill_md("a", 'Triggers on "mine".'), encoding="utf-8")

    assert cst.collisions(str(mine), ["mine"]) == {}


@pytest.mark.unit
def test_no_phrases_skips_the_directory_walk(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args, **_kwargs):
        raise AssertionError("collisions must not scan when there is nothing to match")

    monkeypatch.setattr(Path, "glob", fail)

    assert cst.collisions("/nowhere/SKILL.md", []) == {}


# --------------------------------------------------------------------------- #
# Trigger index cache
# --------------------------------------------------------------------------- #
@pytest.mark.integration
def test_glob_paths_finds_skill_and_plugin_skill_matches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = sandbox_home(monkeypatch, tmp_path)
    skill = home / ".claude" / "skills" / "a" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(skill_md("a", 'Triggers on "alpha".'), encoding="utf-8")
    plugin = (
        home
        / ".claude"
        / "plugins"
        / "cache"
        / "mkt"
        / "plug"
        / "1.0.0"
        / "skills"
        / "p"
        / "SKILL.md"
    )
    plugin.parent.mkdir(parents=True)
    plugin.write_text(skill_md("p", 'Triggers on "beta".'), encoding="utf-8")

    assert set(cst._glob_paths()) == {skill.resolve(), plugin.resolve()}


@pytest.mark.integration
def test_glob_paths_is_empty_when_no_skills_exist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sandbox_home(monkeypatch, tmp_path)

    assert cst._glob_paths() == []


@pytest.mark.unit
def test_max_mtime_of_empty_list_is_zero() -> None:
    assert cst._max_mtime([]) == 0.0


@pytest.mark.integration
def test_max_mtime_returns_the_highest_mtime(tmp_path: Path) -> None:
    older = tmp_path / "older.md"
    newer = tmp_path / "newer.md"
    older.write_text("x", encoding="utf-8")
    newer.write_text("y", encoding="utf-8")
    os.utime(older, (1_000_000, 1_000_000))
    os.utime(newer, (1_000_100, 1_000_100))

    assert cst._max_mtime([older, newer]) == 1_000_100.0


@pytest.mark.integration
def test_max_mtime_skips_a_raced_delete(tmp_path: Path) -> None:
    present = tmp_path / "present.md"
    present.write_text("x", encoding="utf-8")
    os.utime(present, (1_000_000, 1_000_000))
    gone = tmp_path / "gone.md"  # never created: simulates a raced delete

    assert cst._max_mtime([present, gone]) == 1_000_000.0


@pytest.mark.unit
def test_index_over_of_empty_list_is_empty() -> None:
    assert cst._index_over([]) == {}


@pytest.mark.integration
def test_index_over_maps_casefolded_phrase_to_sorted_owners(tmp_path: Path) -> None:
    # Named so alphabetic path order is the reverse of scan order, to catch a
    # missing sort of the owners list.
    late = tmp_path / "zzz" / "SKILL.md"
    early = tmp_path / "aaa" / "SKILL.md"
    late.parent.mkdir(parents=True)
    early.parent.mkdir(parents=True)
    late.write_text(skill_md("zzz", 'Triggers on "Alpha".'), encoding="utf-8")
    early.write_text(skill_md("aaa", 'Triggers on "alpha", "Beta".'), encoding="utf-8")

    index = cst._index_over([late, early])

    assert index == {
        "alpha": sorted([str(late), str(early)]),
        "beta": [str(early)],
    }


@pytest.mark.integration
def test_cached_index_excludes_the_given_path_from_its_contents(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sandbox_cache_file(monkeypatch, tmp_path)
    mine = tmp_path / "mine" / "SKILL.md"
    other = tmp_path / "other" / "SKILL.md"
    mine.parent.mkdir(parents=True)
    other.parent.mkdir(parents=True)
    mine.write_text(skill_md("mine", 'Triggers on "alpha".'), encoding="utf-8")
    other.write_text(skill_md("other", 'Triggers on "alpha".'), encoding="utf-8")

    index = cst._cached_index([mine, other], exclude=mine)

    assert index == {"alpha": [str(other)]}


@pytest.mark.integration
def test_cached_index_reuses_the_cache_when_nothing_changed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sandbox_cache_file(monkeypatch, tmp_path)
    mine = tmp_path / "mine" / "SKILL.md"
    other = tmp_path / "other" / "SKILL.md"
    mine.parent.mkdir(parents=True)
    other.parent.mkdir(parents=True)
    mine.write_text(skill_md("mine", 'Triggers on "alpha".'), encoding="utf-8")
    other.write_text(skill_md("other", 'Triggers on "alpha".'), encoding="utf-8")

    cst._cached_index([mine, other], exclude=mine)
    reads = count_skill_md_reads(monkeypatch)

    cst._cached_index([mine, other], exclude=mine)

    assert reads == []


@pytest.mark.integration
def test_cached_index_key_ignores_mtime_of_the_excluded_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Repeated saves of the file being edited must not invalidate the cache -
    its own mtime never contributes to the cache key."""
    sandbox_cache_file(monkeypatch, tmp_path)
    mine = tmp_path / "mine" / "SKILL.md"
    other = tmp_path / "other" / "SKILL.md"
    mine.parent.mkdir(parents=True)
    other.parent.mkdir(parents=True)
    mine.write_text(skill_md("mine", 'Triggers on "alpha".'), encoding="utf-8")
    other.write_text(skill_md("other", 'Triggers on "beta".'), encoding="utf-8")
    os.utime(other, (1_000_000, 1_000_000))

    cst._cached_index([mine, other], exclude=mine)

    # Simulate a re-save of the excluded (edited) file: content unchanged,
    # mtime moves forward.
    mine.write_text(skill_md("mine", 'Triggers on "alpha".'), encoding="utf-8")
    os.utime(mine, (2_000_000, 2_000_000))
    reads = count_skill_md_reads(monkeypatch)

    cst._cached_index([mine, other], exclude=mine)

    assert reads == []


@pytest.mark.integration
def test_cache_reuse_is_keyed_by_which_files_not_just_their_max_mtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The cache key is only the candidates' max mtime, which does not
    identify WHICH files are in the candidate set. Editing A excludes A
    (candidates {B, C}); editing B excludes B (candidates {A, C}). Both
    candidate sets share C's mtime as their maximum, so a cache keyed on
    mtime alone reuses the {B, C} index for the {A, C} lookup: it omits A (a
    real collision goes unreported) and still contains B (B appears to
    collide with itself)."""
    home = sandbox_home(monkeypatch, tmp_path)
    sandbox_cache_file(monkeypatch, tmp_path)
    skills = home / ".claude" / "skills"
    a = skills / "a" / "SKILL.md"
    b = skills / "b" / "SKILL.md"
    c = skills / "c" / "SKILL.md"
    for p in (a, b, c):
        p.parent.mkdir(parents=True)
    a.write_text(skill_md("a", 'Triggers on "shared".'), encoding="utf-8")
    b.write_text(skill_md("b", 'Triggers on "shared".'), encoding="utf-8")
    c.write_text(skill_md("c", 'Triggers on "onlyc".'), encoding="utf-8")
    os.utime(a, (1_000_000, 1_000_000))
    os.utime(b, (1_000_050, 1_000_050))
    os.utime(c, (1_000_100, 1_000_100))  # C holds the max in both candidate sets

    cst.collisions(str(a), ["shared"])  # warms the cache over {b, c}

    hits = cst.collisions(str(b), ["shared"])

    # Exact equality catches both failure modes at once: A missing would fail
    # it (the real collision with A must be reported), and B present would
    # too (B must never be listed as an owner of its own phrase).
    assert hits.get("shared") == [str(a)]


@pytest.mark.integration
def test_cache_persist_failure_does_not_break_the_collision_advisory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = sandbox_home(monkeypatch, tmp_path)
    monkeypatch.setattr(
        cst,
        "_INDEX_CACHE_FILE",
        tmp_path / "missing-parent" / "cache.json",
    )
    skills = home / ".claude" / "skills"
    a = skills / "a" / "SKILL.md"
    b = skills / "b" / "SKILL.md"
    a.parent.mkdir(parents=True)
    b.parent.mkdir(parents=True)
    a.write_text(skill_md("a", 'Triggers on "shared".'), encoding="utf-8")
    b.write_text(skill_md("b", 'Triggers on "shared".'), encoding="utf-8")

    hits = cst.collisions(str(a), ["shared"])

    assert hits == {"shared": [str(b)]}


@pytest.mark.integration
def test_collisions_detects_a_phrase_added_after_a_warm_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = sandbox_home(monkeypatch, tmp_path)
    sandbox_cache_file(monkeypatch, tmp_path)
    skills = home / ".claude" / "skills"
    a = skills / "a" / "SKILL.md"
    b = skills / "b" / "SKILL.md"
    a.parent.mkdir(parents=True)
    b.parent.mkdir(parents=True)
    a.write_text(skill_md("a", 'Triggers on "alpha".'), encoding="utf-8")
    b.write_text(skill_md("b", 'Triggers on "beta".'), encoding="utf-8")
    os.utime(a, (1_000_000, 1_000_000))
    os.utime(b, (1_000_000, 1_000_000))

    # Warm the cache: no collision yet.
    assert cst.collisions(str(a), ["alpha"]) == {}

    # B now also claims "alpha" - a genuinely new collision, at a distinct mtime.
    b.write_text(skill_md("b", 'Triggers on "beta", "alpha".'), encoding="utf-8")
    os.utime(b, (1_000_002, 1_000_002))

    hits = cst.collisions(str(a), ["alpha"])

    assert hits == {"alpha": [str(b)]}


@pytest.mark.integration
def test_collisions_does_not_reread_skill_files_on_a_warm_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = sandbox_home(monkeypatch, tmp_path)
    sandbox_cache_file(monkeypatch, tmp_path)
    skills = home / ".claude" / "skills"
    a = skills / "a" / "SKILL.md"
    b = skills / "b" / "SKILL.md"
    a.parent.mkdir(parents=True)
    b.parent.mkdir(parents=True)
    a.write_text(skill_md("a", 'Triggers on "alpha".'), encoding="utf-8")
    b.write_text(skill_md("b", 'Triggers on "beta".'), encoding="utf-8")

    cst.collisions(str(a), ["alpha"])  # warms the cache
    reads = count_skill_md_reads(monkeypatch)

    cst.collisions(str(a), ["alpha"])

    assert reads == []


@pytest.mark.integration
def test_cached_index_key_detects_a_content_change_below_the_current_max_mtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The cache key is only the candidates' max mtime plus their sorted
    paths - neither identifies a content change to a candidate whose OWN
    mtime stays below the current maximum. C holds the max mtime both before
    and after B's content and mtime change (which stays below C's), so a key
    built from (paths, max-mtime) is byte-identical across both calls and the
    stale index - missing B's newly-added collision with A's phrase - is
    reused."""
    sandbox_cache_file(monkeypatch, tmp_path)
    a = tmp_path / "a" / "SKILL.md"
    b = tmp_path / "b" / "SKILL.md"
    c = tmp_path / "c" / "SKILL.md"
    for p in (a, b, c):
        p.parent.mkdir(parents=True)
    a.write_text(skill_md("a", 'Triggers on "shared".'), encoding="utf-8")
    b.write_text(skill_md("b", 'Triggers on "onlyb".'), encoding="utf-8")
    c.write_text(skill_md("c", 'Triggers on "onlyc".'), encoding="utf-8")
    os.utime(a, (1_000_000, 1_000_000))
    os.utime(b, (1_000_050, 1_000_050))
    os.utime(c, (1_000_200, 1_000_200))  # C holds the max, unaffected by B's change

    cst._cached_index([a, b, c], exclude=a)  # warms the cache over {b, c}

    # B now also claims A's phrase, at a new mtime that still sits below C's.
    b.write_text(skill_md("b", 'Triggers on "onlyb", "shared".'), encoding="utf-8")
    os.utime(b, (1_000_150, 1_000_150))

    index = cst._cached_index([a, b, c], exclude=a)

    assert index.get("shared") == [str(b)]


@pytest.mark.integration
def test_cached_index_ignores_a_cache_file_in_the_pre_fingerprint_key_format(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A cache file whose key is the older `{"paths": [...], "mtime": <max>}`
    shape - rather than a per-candidate fingerprint - must be treated as a
    plain miss and rebuilt, never raise. The stored "paths" list is made to
    include an entry no real candidate set could ever produce, so the miss is
    guaranteed under any key shape, old or new."""
    cache_file = sandbox_cache_file(monkeypatch, tmp_path)
    mine = tmp_path / "mine" / "SKILL.md"
    other = tmp_path / "other" / "SKILL.md"
    mine.parent.mkdir(parents=True)
    other.parent.mkdir(parents=True)
    mine.write_text(skill_md("mine", 'Triggers on "alpha".'), encoding="utf-8")
    other.write_text(skill_md("other", 'Triggers on "beta".'), encoding="utf-8")
    cache_file.write_text(
        json.dumps(
            {
                "key": {
                    "paths": [str(other), "/nonexistent/bogus/SKILL.md"],
                    "mtime": 1_000_000.0,
                },
                "index": {"stale": [str(other)]},
            }
        ),
        encoding="utf-8",
    )

    index = cst._cached_index([mine, other], exclude=mine)

    assert index == {"beta": [str(other)]}


@pytest.mark.integration
def test_write_cache_failure_does_not_leak_a_temp_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`_write_cache` creates a `NamedTemporaryFile(delete=False)` before the
    operation that can fail. A failed write (here, `json.dump` raising) must
    not leave that temp file behind in the cache directory, and the existing
    swallow-and-continue contract - no raise, fresh index still returned -
    must hold."""
    cache_dir = tmp_path / "cachedir"
    cache_dir.mkdir()
    monkeypatch.setattr(cst, "_INDEX_CACHE_FILE", cache_dir / "cache.json")
    mine = tmp_path / "mine" / "SKILL.md"
    other = tmp_path / "other" / "SKILL.md"
    mine.parent.mkdir(parents=True)
    other.parent.mkdir(parents=True)
    mine.write_text(skill_md("mine", 'Triggers on "alpha".'), encoding="utf-8")
    other.write_text(skill_md("other", 'Triggers on "alpha".'), encoding="utf-8")

    def raising_dump(*_args, **_kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(json, "dump", raising_dump)

    index = cst._cached_index([mine, other], exclude=mine)

    assert index == {"alpha": [str(other)]}
    assert list(cache_dir.iterdir()) == []


# --------------------------------------------------------------------------- #
# Hook delivery
# --------------------------------------------------------------------------- #
@pytest.mark.integration
def test_index_cache_file_is_redirected_by_a_home_override(tmp_path: Path) -> None:
    """`_INDEX_CACHE_FILE` is bound at import time from the script's own
    directory, so a subprocess launched with an overridden $HOME - exactly
    how `run_hook` drives the hook - still writes the operator's real cache
    file. It must instead resolve under `Path.home()`, matching `_glob_paths`,
    so a $HOME override redirects it."""
    home = tmp_path / "sandboxhome"
    skill = home / ".claude" / "skills" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(skill_md("demo", 'Triggers on "alpha".'), encoding="utf-8")

    result = run_hook(
        {"tool_name": "Edit", "tool_input": {"file_path": str(skill)}},
        home=home,
    )

    assert result.returncode == 0
    cache_files = list(home.rglob(cst._INDEX_CACHE_FILE.name))
    assert cache_files, "expected the trigger-index cache under the sandbox HOME"
    real_cache = cst._INDEX_CACHE_FILE.resolve()
    assert real_cache not in {p.resolve() for p in cache_files}


@pytest.mark.integration
def test_non_skill_edit_prints_nothing(tmp_path: Path) -> None:
    other = tmp_path / "notes.md"
    other.write_text("hello", encoding="utf-8")

    result = run_hook({"tool_name": "Edit", "tool_input": {"file_path": str(other)}})

    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.integration
def test_clean_skill_edit_prints_nothing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    path = commit_skill(repo, "skills/a/SKILL.md", 'Triggers on "alpha".')
    path.write_text(skill_md("a", 'Use when x. Triggers on "alpha".'), encoding="utf-8")

    result = run_hook(
        {"tool_name": "Edit", "tool_input": {"file_path": str(path)}},
        home=tmp_path / "home",
    )

    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.integration
def test_missing_file_path_prints_nothing() -> None:
    result = run_hook({"tool_name": "Edit", "tool_input": {}})

    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.integration
def test_dropped_phrase_surfaces_as_additional_context(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    path = commit_skill(repo, "skills/manage-agents-md/SKILL.md", BEFORE_76FEB4475)
    path.write_text(skill_md("manage-agents-md", AFTER_76FEB4475), encoding="utf-8")

    result = run_hook(
        {"tool_name": "Edit", "tool_input": {"file_path": str(path)}},
        home=tmp_path / "home",
    )

    assert result.returncode == 0
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "create AGENTS.md" in context
    assert "improve AGENTS.md" in context
    assert "promote memories" not in context  # kept phrases are never reported


@pytest.mark.unit
def test_findings_are_empty_for_an_unreadable_path() -> None:
    assert cst.findings("/nonexistent/SKILL.md") == []


@pytest.mark.unit
def test_main_survives_an_internal_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def boom(_path: str) -> list[str]:
        raise RuntimeError("scan exploded")

    monkeypatch.setattr(cst, "findings", boom)
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {"tool_name": "Edit", "tool_input": {"file_path": "/x/SKILL.md"}},
            ),
        ),
    )

    assert cst.main() == 0
    assert capsys.readouterr().out == ""


@pytest.mark.unit
def test_run_returns_the_dispatcher_triple() -> None:
    payload = {"tool_name": "Edit", "tool_input": {"file_path": "/x/y.md"}}

    assert cst.run(payload) == (0, "", "")
