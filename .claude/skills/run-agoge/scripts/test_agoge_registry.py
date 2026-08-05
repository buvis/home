"""Hygiene for the agoge specialist roster.

    uv run --with pytest pytest test_agoge_registry.py

These assertions stand in for plugin-dev's `validate-agent.sh`, which PRD 00100
names as the gate. That script cannot serve as one: under `set -euo pipefail` it
runs `((warning_count++))`, which evaluates to the pre-increment value `0` and so
returns exit status 1, aborting the script at its FIRST warning. It fails 00109's
shipped `rita.md` the same way. The error-level checks it means to enforce -
name, description, model, color, a non-empty second-person system prompt - are
asserted here instead, where they run and keep running.

Two of its warnings are declined on purpose: `<example>` blocks and a "Use this
agent when" opening would both blow the 120-character description budget the
registry convention imposes, because descriptions land in the boot prefix.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

AGENTS_DIR = Path.home() / ".claude" / "agents"
REFERENCES = Path(__file__).resolve().parent.parent / "references"

RECON = "olivia"
SPECIALISTS = ("walter", "heidi", "judy", "wendy", "peggy", "trudy")
ROSTER = (RECON, *SPECIALISTS)

# Four are pasted into a lane's dispatch prompt; authoring is the master's own.
PLAYBOOKS = ("browser", "data", "perf", "security", "authoring")

# Which playbook a lane must acknowledge in its own body.
HARNESS_LANES = {
    "judy": "browser",
    "walter": "browser",
    "heidi": "data",
    "peggy": "perf",
    "trudy": "security",
}

DESCRIPTION_MAX = 120
VALID_COLORS = {"blue", "cyan", "green", "yellow", "magenta", "red"}
VALID_MODELS = {"inherit", "sonnet", "opus", "haiku", "fable"}

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.DOTALL)


def _parse(name: str) -> tuple[dict[str, str], str]:
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
    return {name: _parse(name) for name in ROSTER}


def test_every_specialist_has_a_file() -> None:
    missing = [name for name in ROSTER if not (AGENTS_DIR / f"{name}.md").is_file()]
    assert not missing, f"missing agoge agent files: {missing}"


def test_roster_is_recon_plus_six_specialists() -> None:
    assert len(ROSTER) == 7
    assert len(set(ROSTER)) == 7, "duplicate persona name in the roster"


@pytest.mark.parametrize("name", ROSTER)
def test_name_matches_the_filename(registry, name: str) -> None:
    fields, _ = registry[name]
    assert fields.get("name") == name, "the name IS the dispatch name"


@pytest.mark.parametrize("name", ROSTER)
def test_description_fits_the_boot_prefix_budget(registry, name: str) -> None:
    fields, _ = registry[name]
    description = fields.get("description", "")
    assert description, f"{name}.md needs a description"
    assert len(description) <= DESCRIPTION_MAX, (
        f"{name}.md description is {len(description)} chars; it lands in the "
        f"boot prefix, so {DESCRIPTION_MAX} is a budget, not a style rule"
    )


@pytest.mark.parametrize("name", ROSTER)
def test_model_and_color_are_declared_and_valid(registry, name: str) -> None:
    """The two fields validate-agent.sh treats as errors."""
    fields, _ = registry[name]
    assert fields.get("model") in VALID_MODELS, f"{name}.md: {fields.get('model')!r}"
    assert fields.get("color") in VALID_COLORS, f"{name}.md: {fields.get('color')!r}"


@pytest.mark.parametrize("name", ROSTER)
def test_tools_is_declared(registry, name: str) -> None:
    """An absent `tools` key inherits everything, Edit and Write included."""
    fields, _ = registry[name]
    assert "tools" in fields, f"{name}.md omits `tools`"


@pytest.mark.parametrize("name", SPECIALISTS)
def test_no_specialist_can_modify_the_product(registry, name: str) -> None:
    """A prober that can edit the thing it probes invalidates its own result."""
    fields, _ = registry[name]
    tools = {tool.strip() for tool in fields["tools"].split(",")}
    assert not tools & {"Edit", "Write", "NotebookEdit"}, (
        f"{name}.md carries {sorted(tools)}; only olivia writes, and only the profile"
    )


def test_olivia_alone_may_write_and_only_the_profile(registry) -> None:
    fields, _ = registry[RECON]
    tools = {tool.strip() for tool in fields["tools"].split(",")}
    assert "Write" in tools, "olivia writes the strategy profile"
    assert "Edit" not in tools, (
        "a profile refresh rewrites the file whole; Edit would only widen what "
        "she can change in a target repo she is supposed to observe"
    )


@pytest.mark.parametrize("name", ROSTER)
def test_body_carries_no_personal_paths(registry, name: str) -> None:
    """Extraction-clean: PRD 00103 lifts these files into a released plugin."""
    _, body = registry[name]
    for forbidden in ("/Users/", "~/.claude", "dev/local"):
        assert forbidden not in body, f"{name}.md body names {forbidden}"


@pytest.mark.parametrize("name", ROSTER)
def test_body_is_a_second_person_system_prompt(registry, name: str) -> None:
    _, body = registry[name]
    assert body.strip(), f"{name}.md has an empty system prompt"
    assert re.search(r"\bYou are\b", body), f"{name}.md should address the agent"


@pytest.mark.parametrize("playbook", PLAYBOOKS)
def test_every_playbook_exists_and_says_something(playbook: str) -> None:
    path = REFERENCES / f"{playbook}-playbook.md"
    assert path.is_file(), f"missing {path.name}"
    assert len(path.read_text(encoding="utf-8").strip()) > 500, (
        f"{path.name} is too thin to be doctrine"
    )


@pytest.mark.parametrize("playbook", PLAYBOOKS)
def test_playbooks_are_extraction_clean(playbook: str) -> None:
    """PRD 00103 lifts these into a released plugin, verbatim.

    A playbook is pasted into a dispatch prompt, so a reference to a file only
    this machine has is worse than useless: the agent cannot open it and does
    not know that it could not.
    """
    text = (REFERENCES / f"{playbook}-playbook.md").read_text(encoding="utf-8")
    for forbidden in ("/Users/", "~/.claude", "work/references/", "rules/"):
        assert forbidden not in text, f"{playbook}-playbook.md names {forbidden}"


@pytest.mark.parametrize("playbook", PLAYBOOKS)
def test_playbooks_stay_inside_the_dispatch_budget(playbook: str) -> None:
    """One playbook plus recon output plus the contract must fit in 50KB."""
    size = (REFERENCES / f"{playbook}-playbook.md").stat().st_size
    assert size < 10_000, f"{playbook}-playbook.md is {size} bytes; keep it lean"


@pytest.mark.parametrize("name,playbook", sorted(HARNESS_LANES.items()))
def test_each_harness_lane_points_at_its_playbook(registry, name, playbook) -> None:
    """A pasted playbook a charter never mentions reads as optional context."""
    _, raw = registry[name]
    body = " ".join(raw.split())  # these bodies wrap at 80; the phrase may not
    assert f"{playbook} playbook" in body, (
        f"{name}.md must tell its agent the {playbook} playbook is binding"
    )


def test_only_the_master_authors(registry) -> None:
    """The authoring playbook is never dispatched, so no charter may claim it."""
    for name in ROSTER:
        _, raw = registry[name]
        body = " ".join(raw.split()).lower()
        assert "authoring playbook" not in body, (
            f"{name}.md points at the authoring playbook; every specialist is "
            "pinned read-and-run, so the master authors and they do not"
        )


@pytest.mark.parametrize("name", SPECIALISTS)
def test_every_specialist_states_its_honesty_rule(registry, name: str) -> None:
    """The contract's whole point: a lane that did not run never reads as a pass.

    Each charter has to carry the rule in its own body, because the body is the
    system prompt and is all the agent has before its dispatch prompt arrives.
    """
    _, body = registry[name]
    assert re.search(r"unverified|skipped|mocked|refused", body), (
        f"{name}.md must say what it reports when it cannot run its surface"
    )


# ── The authorization gate (PRD 00117) ────────────────────────────────────────
#
# Two human acts may assert that a target is the operator's own: a line the
# operator wrote in the strategy profile, or `--authorized <source>` passed at
# invocation. The second exists because a fresh profile always reads `not
# asserted` and recon may not change it, which left the security lane dark in
# every unattended drain. Neither route lets the machine assert for itself.
#
# The gate is stated in four places that must agree: trudy's charter, the
# security playbook, the profile contract, and the skill's dispatch step. These
# assertions are what stops one of the four drifting out of step with the rest.

SKILL = REFERENCES.parent / "SKILL.md"


def _text(path) -> str:
    """Collapsed to one line: these files wrap at 80, so a phrase may not be."""
    return " ".join(path.read_text(encoding="utf-8").split())


def test_trudy_requires_a_named_source_not_just_an_assertion(registry) -> None:
    """An unsourced assertion is one nothing can attribute to a human."""
    _, raw = registry["trudy"]
    body = " ".join(raw.split())
    assert "names the human act" in body, (
        "trudy.md must require the assertion to name its source; without that "
        "the machine's own claim is indistinguishable from the operator's"
    )
    assert "counts as absent" in body, (
        "trudy.md must say what an unsourced assertion is treated as, or the "
        "requirement is advice rather than a gate"
    )


def test_the_gate_still_fails_closed_everywhere_it_is_stated() -> None:
    """Widening who may assert must not weaken what happens with no assertion."""
    for path in (AGENTS_DIR / "trudy.md", REFERENCES / "security-playbook.md"):
        text = _text(path)
        assert "run nothing" in text or "run nothing," in text, (
            f"{path.name} lost its refusal instruction"
        )


def test_the_security_playbook_names_both_routes() -> None:
    """A pasted playbook is all the lane has; a route missing here is unusable."""
    text = _text(REFERENCES / "security-playbook.md")
    assert "strategy profile" in text, "the playbook must name the profile route"
    assert "authorization argument" in text, (
        "the playbook must name the invocation route, or a lane authorized that "
        "way reads its own prompt as unauthorized and skips"
    )


def test_the_profile_contract_keeps_recon_out_of_the_assertion() -> None:
    """The widened gate must not become a licence for the machine to assert."""
    text = _text(REFERENCES / "finding-contract.md")
    assert "The machine never edits this section" in text
    assert "not a fact an agent can establish" in text
    assert "Two human acts can assert, and only two" in text, (
        "the contract must bound the routes; an open-ended list invites a third"
    )


def test_the_skill_documents_the_flag_and_its_resolution_order() -> None:
    text = _text(SKILL)
    assert "--authorized <source>" in text, "the argument must be documented"
    assert "The profile wins when both are present" in text, (
        "with two routes the skill has to say which one decides"
    )
    assert "empty source is an error" in text, (
        "asserting anonymously is the one failure this gate cannot tolerate"
    )


def test_the_report_records_which_act_authorized_the_probe() -> None:
    """A reader must tell an invocation assertion from a hand-edited profile."""
    text = _text(REFERENCES / "finding-contract.md")
    assert '"authorization"' in text, "the sidecar shape must carry the route"
    assert "which human act authorized it" in text, (
        "the markdown summary must name the route too; the sidecar alone is not "
        "what a human reads"
    )
