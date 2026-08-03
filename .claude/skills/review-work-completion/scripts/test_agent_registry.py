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

# bob, carl, quinn and pat are CLI-dispatched, and their runner owns the tool
# policy on that path (it never reads this frontmatter). They still declare a
# set, because every registry file is ALSO registered as a native agent type,
# where an absent `tools` key means "inherit everything" — Edit and Write
# included. They are classified in the two groups below like everyone else.

# Read-only lanes: the diff arrives inline, they never hunt for code.
READ_ONLY = DIMENSIONS + ("trent", "bob", "quinn", "pat")

# Lanes that must locate code themselves. Grep/Glob are unregistered in this
# build, so searching means `rg` via Bash — see agent-registry.md § Tool sets.
READ_AND_BASH = ("alice", "blake", "eve", "victor", "carl")

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
        pytest.fail(
            f"{AGENTS_DIR} does not exist; the registry is the PRD's deliverable",
        )
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
    assert on_disk == set(ROSTER), (
        f"unexpected agent files: {sorted(on_disk - set(ROSTER))}"
    )


@pytest.mark.parametrize("name", ROSTER)
def test_name_field_matches_the_filename(registry, name: str) -> None:
    fields, _ = registry[name]
    assert fields.get("name") == name, (
        f"{name}.md declares name: {fields.get('name')!r}"
    )


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
def test_every_persona_declares_a_tool_set(registry, name: str) -> None:
    # An absent `tools` key does NOT mean "no tools" — the harness registers
    # every file here as a native agent type, and a file with no `tools` key
    # inherits the full set, Edit and Write included. Absence is the hazard,
    # so presence is the assertion.
    fields, _ = registry[name]
    assert "tools" in fields, (
        f"{name}.md declares no tools; a registered agent with no `tools` key "
        f"inherits every tool, including Edit and Write"
    )


@pytest.mark.parametrize("name", ROSTER)
def test_no_reviewer_can_modify_the_repo(registry, name: str) -> None:
    fields, _ = registry[name]
    tools = fields.get("tools", "")
    assert tools, f"{name}.md declares no tools, so it inherits mutating ones"
    for forbidden in ("Edit", "Write", "NotebookEdit"):
        assert forbidden not in tools, (
            f"{name}.md grants {forbidden}; reviewers never mutate"
        )


@pytest.mark.parametrize("name", READ_ONLY)
def test_inline_diff_lanes_are_read_only(registry, name: str) -> None:
    fields, _ = registry[name]
    assert fields.get("tools") == "Read", (
        f"{name}.md receives its diff inline and must stay Read-only"
    )


def test_every_persona_is_classified_by_tool_set() -> None:
    # A new persona added to ROSTER but to neither tool-set group would slip
    # past both assertions above and go unchecked.
    classified = set(READ_ONLY) | set(READ_AND_BASH)
    assert classified == set(ROSTER), (
        f"unclassified personas: {sorted(set(ROSTER) - classified)}"
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


def test_dispatch_references_document_the_fail_closed_contract() -> None:
    """There is no fallback prompt anywhere, and the references must say so.

    Without this the registry degrades quietly: a lane whose persona file went
    missing would be repaired by whoever hits it next writing a prompt inline,
    which is precisely the scattering this PRD removed.
    """
    skill_dir = Path.home() / ".claude" / "skills" / "review-work-completion"
    conventions = (skill_dir / "references" / "agent-registry.md").read_text(
        encoding="utf-8",
    )
    skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "fallback prompt" in conventions.lower(), (
        "agent-registry.md must state that no fallback prompt exists"
    )
    assert "fail-closed" in skill.lower() or "fail closed" in skill.lower(), (
        "SKILL.md must document the fail-closed preflight over the roster"
    )
    assert "never a fallback prompt" in skill.lower(), (
        "SKILL.md must state that a missing roster file fails the reviewer "
        "rather than falling back to an inline prompt"
    )


def test_no_persona_prompt_text_survives_outside_the_registry() -> None:
    """The sweep PRD 00109 Phase 2 asks for, as an assertion rather than a
    one-off grep: a distinctive line from each extracted source must appear in
    its agent file and nowhere else under skills/ or workflows/."""
    claude = Path.home() / ".claude"
    signatures = {
        "victor": "You are an adversarial verifier.",
        "rita": "No scope creep: features nobody asked for.",
        "mallory": "No SQL or command injection risk.",
        "blake": "You are Blake, a hostile auditor",
        "eve": "Assume the work is subtly wrong until proven",
        "bob": "Perform STATIC analysis only",
        "carl": "you are the panel's",
    }
    for name, signature in signatures.items():
        assert (
            signature.lower()
            in (AGENTS_DIR / f"{name}.md")
            .read_text(
                encoding="utf-8",
            )
            .lower()
        ), f"{name}.md no longer carries its signature line: {signature!r}"
        for root in (claude / "skills", claude / "workflows"):
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix not in {
                    ".md",
                    ".js",
                    ".mjs",
                    ".py",
                }:
                    continue
                # The goldens fixture is the frozen pre-migration record and is
                # SUPPOSED to hold this text; the sweep test names it here too.
                if path.name in {"prompt-goldens.json", "test_agent_registry.py"}:
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                assert signature.lower() not in text.lower(), (
                    f"{name}'s persona text still lives in {path}; the registry "
                    f"is meant to be its only home"
                )


def test_placeholders_are_declared_in_the_conventions(registry) -> None:
    """Every {PLACEHOLDER} a persona uses must be documented, or a consuming
    skill will have nothing telling it what to substitute."""
    conventions = (
        Path.home()
        / ".claude"
        / "skills"
        / "review-work-completion"
        / "references"
        / "agent-registry.md"
    ).read_text(encoding="utf-8")
    used: set[str] = set()
    for name in ROSTER:
        _, body = registry[name]
        used.update(re.findall(r"\{([A-Z_]+)\}", body))
    undocumented = sorted(p for p in used if f"{{{p}}}" not in conventions)
    assert not undocumented, f"placeholders used but not documented: {undocumented}"


def _skill_text() -> str:
    return (
        Path.home() / ".claude" / "skills" / "review-work-completion" / "SKILL.md"
    ).read_text(encoding="utf-8")


def _table_row(text: str, persona: str) -> str:
    """Return the sole markdown table row whose leading cell is `persona`.

    Anchors on the leading cell rather than the whole file: SKILL.md
    legitimately mentions the pack elsewhere (the step that generates it),
    and that mention must not make an assertion about one persona's row lie.
    """
    matches = re.findall(rf"^\|\s*{re.escape(persona)}\s*\|.*$", text, re.MULTILINE)
    assert len(matches) == 1, (
        f"expected exactly one '| {persona} |' table row in SKILL.md, found "
        f"{len(matches)}"
    )
    return matches[0]


@pytest.mark.parametrize("name", CONSENSUS)
def test_consensus_personas_carry_the_full_pack_placeholder(
    registry, name: str
) -> None:
    """Alice, Bob, Carl and Quinn are the consensus lens: each body must use
    {PACK_FILE} so the cycle's full context pack is prepended for it."""
    _, body = registry[name]
    assert "{PACK_FILE}" in body, f"{name}.md body must use {{PACK_FILE}}"


def test_eve_body_uses_findings_precedent(registry) -> None:
    """Eve is the doubt lens: she gets the pack's findings precedent, not the
    full pack."""
    _, body = registry["eve"]
    assert "{PACK_FINDINGS}" in body, "eve.md body must use {PACK_FINDINGS}"


def test_eve_body_does_not_use_the_full_pack_placeholder(registry) -> None:
    """The doubt lens is the one lens where findings-only isolation is
    mechanically enforceable: her body must not carry {PACK_FILE}."""
    _, body = registry["eve"]
    assert "{PACK_FILE}" not in body, "eve.md body must not use {PACK_FILE}"


def test_blake_body_is_pack_free(registry) -> None:
    """Blake is the blind lens by design: no pack placeholder, and no mention
    of the pack artifact by name, anywhere in his body."""
    _, body = registry["blake"]
    for forbidden in ("{PACK_FILE}", "{PACK_FINDINGS}", "PACK_"):
        assert forbidden not in body, (
            f"blake.md body contains {forbidden!r}; the blind lens is "
            f"pack-free by design"
        )
    assert "engram-pack" not in body.lower(), (
        "blake.md body must not reference the pack artifact"
    )


def test_blake_prepare_prompts_row_names_no_pack_placeholder() -> None:
    """The blind invocation path is pack-free too: Blake's row in the
    'Prepare agent prompts' substitution table must not name a pack
    placeholder."""
    row = _table_row(_skill_text(), "Blake")
    assert "PACK_" not in row, (
        f"Blake's SKILL.md substitution-table row mentions a pack placeholder: {row!r}"
    )


def test_alice_and_eve_prepare_prompts_rows_name_their_pack_placeholders() -> None:
    """Alice's row names the full pack; Eve's row names findings precedent
    only, matching the wiring contract."""
    text = _skill_text()
    alice_row = _table_row(text, "Alice")
    eve_row = _table_row(text, "Eve")
    assert "{PACK_FILE}" in alice_row, (
        f"Alice's row must name {{PACK_FILE}}: {alice_row!r}"
    )
    assert "{PACK_FINDINGS}" in eve_row, (
        f"Eve's row must name {{PACK_FINDINGS}}: {eve_row!r}"
    )


def test_bob_prepare_prompts_row_names_both_pack_placeholders() -> None:
    """Bob's row already declares his prompt is assembled from agents/bob.md
    **plus** the "Two lenses" and "Rubric verdicts" sections of agents/eve.md
    appended — exactly the sections that carry {PACK_FINDINGS}. So Bob's
    assembled prompt contains that placeholder even though his own file
    never will; if his row doesn't declare the substitution, an
    unsubstituted literal `{PACK_FINDINGS}` ships to the reviewer. He must
    keep naming {PACK_FILE} too: he's a consensus reviewer and his own body
    already uses it."""
    row = _table_row(_skill_text(), "Bob")
    assert "{PACK_FILE}" in row, f"Bob's row must name {{PACK_FILE}}: {row!r}"
    assert "{PACK_FINDINGS}" in row, (
        f"Bob's row must name {{PACK_FINDINGS}}: {row!r}"
    )
