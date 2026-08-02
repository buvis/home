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
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[1]
HOOK = HOOKS_DIR / "check_skill_triggers.py"

if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

import check_skill_triggers as cst

# Verbatim from `git show 76feb4475 -- .claude/skills/manage-agents-md/SKILL.md`.
BEFORE_76FEB4475 = (
    'Use when creating, auditing, or improving an AGENTS.md file for AI coding '
    'agents (progressive disclosure, context window budgeting). Triggers on '
    '"agents.md", "AGENTS.md", "create AGENTS.md", "audit AGENTS.md", '
    '"improve AGENTS.md".'
)
AFTER_76FEB4475 = (
    'Use when creating, auditing, or improving an AGENTS.md file, or promoting '
    'project memories into it (progressive disclosure, context budgeting). '
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


def run_hook(payload: dict, home: Path | None = None) -> subprocess.CompletedProcess[str]:
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
    text = '---\nname: x\ndescription: Use when foo.\n  Triggers on "alpha".\n---\n\n# x\n'
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

    assert cst.dropped_since_head(str(path)) == ["create AGENTS.md", "improve AGENTS.md"]


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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = sandbox_home(monkeypatch, tmp_path)
    skills = home / ".claude" / "skills"
    for name in ("a", "b"):
        (skills / name).mkdir(parents=True)
        (skills / name / "SKILL.md").write_text(
            skill_md(name, 'Triggers on "audit config".'), encoding="utf-8"
        )

    hits = cst.collisions(str(skills / "a" / "SKILL.md"), ["audit config"])

    assert list(hits) == ["audit config"]
    assert hits["audit config"] == [str(skills / "b" / "SKILL.md")]


@pytest.mark.integration
def test_collision_scan_reaches_installed_plugin_skills(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = sandbox_home(monkeypatch, tmp_path)
    mine = home / ".claude" / "skills" / "a" / "SKILL.md"
    mine.parent.mkdir(parents=True)
    mine.write_text(skill_md("a", 'Triggers on "audit config".'), encoding="utf-8")
    plugin = (
        home / ".claude" / "plugins" / "cache" / "mkt" / "plug" / "1.0.0" / "skills" / "p"
    )
    plugin.mkdir(parents=True)
    (plugin / "SKILL.md").write_text(
        skill_md("p", 'Triggers on "audit config".'), encoding="utf-8"
    )

    hits = cst.collisions(str(mine), ["audit config"])

    assert hits["audit config"] == [str(plugin / "SKILL.md")]


@pytest.mark.integration
def test_a_skill_does_not_collide_with_itself(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = sandbox_home(monkeypatch, tmp_path)
    mine = home / ".claude" / "skills" / "a" / "SKILL.md"
    mine.parent.mkdir(parents=True)
    mine.write_text(skill_md("a", 'Triggers on "alpha".'), encoding="utf-8")

    assert cst.collisions(str(mine), ["alpha"]) == {}


@pytest.mark.integration
def test_collisions_between_two_other_skills_stay_silent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = sandbox_home(monkeypatch, tmp_path)
    skills = home / ".claude" / "skills"
    for name in ("b", "c"):
        (skills / name).mkdir(parents=True)
        (skills / name / "SKILL.md").write_text(
            skill_md(name, 'Triggers on "shared".'), encoding="utf-8"
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
# Hook delivery
# --------------------------------------------------------------------------- #
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
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(_path: str) -> list[str]:
        raise RuntimeError("scan exploded")

    monkeypatch.setattr(cst, "findings", boom)
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "/x/SKILL.md"}})
        ),
    )

    assert cst.main() == 0
    assert capsys.readouterr().out == ""


@pytest.mark.unit
def test_run_returns_the_dispatcher_triple() -> None:
    payload = {"tool_name": "Edit", "tool_input": {"file_path": "/x/y.md"}}

    assert cst.run(payload) == (0, "", "")
