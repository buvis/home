"""Hygiene checks for the reviewer agent registry (~/.claude/agents/).

PRD 00109 moved 14 reviewer personas out of skill reference files and workflow
JS into flat agent files. These tests enforce the conventions in
`references/agent-registry.md` mechanically, so a persona edit cannot quietly
break dispatch, blow the boot-prefix budget, hand a reviewer write access, or
bake a personal path into a prompt.

Stdlib + pytest. Binds to the LIVE registry, not a fixture: the point is that
the installed roster is well-formed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

AGENTS_DIR = Path.home() / ".claude" / "agents"

CONSENSUS = ("alice", "bob", "carl", "quinn")
DIMENSIONS = ("rita", "cora", "grace", "toby", "mallory")
ROSTER = CONSENSUS + ("blake", "eve") + DIMENSIONS + ("trent", "victor", "pat")

# CLI-dispatched personas: the runner owns the tool policy, so they carry no
# `tools` key at all (agent-registry.md § Tool sets).
CLI_DISPATCHED = ("bob", "carl", "quinn", "pat")

# Read-only lanes: the diff arrives inline, they never hunt for code.
READ_ONLY = DIMENSIONS + ("trent",)

# Lanes that must locate code themselves. Grep/Glob are unregistered in this
# build, so searching means `rg` via Bash — see agent-registry.md § Tool sets.
READ_AND_BASH = ("alice", "blake", "eve", "victor")

DESCRIPTION_MAX = 120

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.DOTALL)


def _parse(name: str) -> tuple[dict[str, str], str]:
    """Return ({frontmatter key: value}, body) for one agent file."""
    text = (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    assert match, f"{name}.md must open with a --- frontmatter block"
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields, match.group(2)


@pytest.fixture(scope="module")
def registry() -> dict[str, tuple[dict[str, str], str]]:
    if not AGENTS_DIR.is_dir():
        pytest.fail(f"{AGENTS_DIR} does not exist; the registry is the PRD's deliverable")
    return {name: _parse(name) for name in ROSTER}


def test_every_roster_persona_has_a_file() -> None:
    missing = [name for name in ROSTER if not (AGENTS_DIR / f"{name}.md").is_file()]
    assert not missing, f"missing agent files: {missing}"


def test_roster_is_exactly_fourteen() -> None:
    assert len(ROSTER) == 14
    assert len(set(ROSTER)) == 14, "duplicate persona name in the roster"


def test_registry_holds_no_unexpected_agents(registry) -> None:
    # A stray file still costs boot prefix and can shadow a dispatch name.
    on_disk = {path.stem for path in AGENTS_DIR.glob("*.md")}
    assert on_disk == set(ROSTER), f"unexpected agent files: {sorted(on_disk - set(ROSTER))}"


@pytest.mark.parametrize("name", ROSTER)
def test_name_field_matches_the_filename(registry, name: str) -> None:
    fields, _ = registry[name]
    assert fields.get("name") == name, f"{name}.md declares name: {fields.get('name')!r}"


@pytest.mark.parametrize("name", ROSTER)
def test_description_is_present_and_within_the_boot_budget(registry, name: str) -> None:
    fields, _ = registry[name]
    description = fields.get("description", "")
    assert description, f"{name}.md has no description"
    assert len(description) <= DESCRIPTION_MAX, (
        f"{name}.md description is {len(description)} chars, over the "
        f"{DESCRIPTION_MAX}-char boot-prefix budget"
    )
    assert "\n" not in description, f"{name}.md description must be one line"


@pytest.mark.parametrize("name", ROSTER)
def test_no_reviewer_can_modify_the_repo(registry, name: str) -> None:
    fields, _ = registry[name]
    tools = fields.get("tools", "")
    for forbidden in ("Edit", "Write", "NotebookEdit"):
        assert forbidden not in tools, f"{name}.md grants {forbidden}; reviewers never mutate"


@pytest.mark.parametrize("name", CLI_DISPATCHED)
def test_cli_personas_declare_no_tools(registry, name: str) -> None:
    fields, _ = registry[name]
    assert "tools" not in fields, (
        f"{name}.md is CLI-dispatched; the runner owns its tool policy"
    )


@pytest.mark.parametrize("name", READ_ONLY)
def test_inline_diff_lanes_are_read_only(registry, name: str) -> None:
    fields, _ = registry[name]
    assert fields.get("tools") == "Read", (
        f"{name}.md receives its diff inline and must stay Read-only"
    )


@pytest.mark.parametrize("name", READ_AND_BASH)
def test_code_hunting_lanes_can_search(registry, name: str) -> None:
    # Grep/Glob are unregistered in this build; without Bash these agents
    # cannot run `rg`, and each of their prompts orders them to find the code.
    fields, _ = registry[name]
    assert fields.get("tools") == "Read, Bash", (
        f"{name}.md must carry 'Read, Bash' — it is told to locate code itself"
    )


def test_eve_pins_the_fable_model(registry) -> None:
    fields, _ = registry["eve"]
    assert fields.get("model") == "fable"


@pytest.mark.parametrize("name", ROSTER)
def test_body_carries_no_personal_paths(registry, name: str) -> None:
    _, body = registry[name]
    for leak in ("/Users/", "~/.claude"):
        assert leak not in body, (
            f"{name}.md body contains {leak!r}; run-specific paths belong in "
            f"placeholders the consuming skill substitutes"
        )


@pytest.mark.parametrize("name", ROSTER)
def test_body_is_not_empty(registry, name: str) -> None:
    _, body = registry[name]
    assert body.strip(), f"{name}.md has no persona body"


def test_placeholders_are_declared_in_the_conventions(registry) -> None:
    """Every {PLACEHOLDER} a persona uses must be documented, or a consuming
    skill will have nothing telling it what to substitute."""
    conventions = (
        Path.home() / ".claude" / "skills" / "review-work-completion"
        / "references" / "agent-registry.md"
    ).read_text(encoding="utf-8")
    used: set[str] = set()
    for name in ROSTER:
        _, body = registry[name]
        used.update(re.findall(r"\{([A-Z_]+)\}", body))
    undocumented = sorted(p for p in used if f"{{{p}}}" not in conventions)
    assert not undocumented, f"placeholders used but not documented: {undocumented}"
