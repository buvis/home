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

# Both anchors are relative to this file, never to $HOME. The roster sits beside
# the skill in either layout - `~/.claude/{agents,skills/run-agoge}` personally,
# `<plugin>/{agents,skills/run-agoge}` once PRD 00103 extracts it - so the same
# expression resolves in both. A `Path.home()` anchor would have shipped with the
# plugin and then validated the INSTALLER's personal agents instead of the
# plugin's own: green on a machine carrying a stale copy, and green on one
# carrying no copy at all only by accident.
AGENTS_DIR = Path(__file__).resolve().parents[3] / "agents"
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

# Paths that exist only on the author's machine. PRD 00103 ships this tree as a
# public plugin, where each of these is a pointer an installer cannot follow.
EXTRACTION_FORBIDDEN = ("/Users/", "~/.claude", "work/references/", "rules/")

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


def test_the_roster_anchor_is_relative_to_this_skill_not_to_home() -> None:
    """PRD 00103 ships this suite inside the plugin. A `$HOME` anchor would make
    it validate the installer's own agents rather than the plugin's, so it would
    pass on a machine with a stale personal copy and fail on a clean one."""
    assert AGENTS_DIR == Path(__file__).resolve().parents[3] / "agents"
    assert AGENTS_DIR.is_dir(), f"roster not found beside the skill at {AGENTS_DIR}"


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
    for forbidden in EXTRACTION_FORBIDDEN:
        assert forbidden not in text, f"{playbook}-playbook.md names {forbidden}"


def _shipped_markdown() -> list[Path]:
    """Every markdown file the plugin carries: the skill and all its references."""
    return [REFERENCES.parent / "SKILL.md", *sorted(REFERENCES.glob("*.md"))]


@pytest.mark.parametrize("path", _shipped_markdown(), ids=lambda p: p.name)
def test_every_shipped_file_is_extraction_clean(path: Path) -> None:
    """Widened past the playbooks on 2026-08-06, during the extraction itself.

    It could not be widened before: `finding-contract.md` cited
    `rules/communication.md` for the walkthrough packet, and `SKILL.md` cited a
    sibling personal skill for the roster conventions. Both are now inlined, so
    the whole shipped surface can hold the line the playbooks already held.

    `dev/local/` is deliberately NOT forbidden here. It is a repo-relative
    contract path - where the profile and the reports live inside the TARGET
    repo - so it travels correctly to any installer. What does not travel is a
    path only the author's machine has.
    """
    text = path.read_text(encoding="utf-8")
    for forbidden in EXTRACTION_FORBIDDEN:
        assert forbidden not in text, (
            f"{path.name} names {forbidden}, which an installer cannot open and "
            "will not be told it cannot open"
        )


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
#
# What they are NOT, established by mutation on 2026-08-05 rather than assumed:
# appending "an unattended loop dispatch is exempt from this gate" to trudy's
# charter - the exact inversion of the rule - leaves every one of them green.
# They check that a phrase is present, so they catch a deletion and miss a
# contradiction. Read them as drift detectors, not as a guard on the gate's
# semantics. Verifying that would need a behavioural harness the pack does not
# have; the gate itself is prose a model obeys, which is what the PRD chose.

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
        assert "run nothing" in _text(path), f"{path.name} lost its refusal instruction"
    # The prose above is advisory; this is the row the master actually acts on.
    # Deleting it while widening the gate would leave no skip instruction at all.
    skill = _text(SKILL)
    assert "do not dispatch her" in skill, (
        "the resolution table's no-assertion row must still refuse the dispatch"
    )
    assert "authorization not asserted" in skill, (
        "a skipped security lane must carry its reason into the report"
    )


def test_a_veto_outranks_an_invocation_assertion() -> None:
    """A veto is the human saying no; an authorization answers a different
    question. The flag must never be able to overrule it, and the rule has to
    live in the table that decides rather than in prose one step earlier."""
    skill = _text(SKILL)
    assert "| vetoed |" in skill, (
        "the resolution table needs its own veto row; a veto stated only in "
        "step 3 is not where the dispatch decision is made"
    )
    assert "never dispatch her" in skill


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
    assert "The profile wins over the invocation" in text, (
        "with two asserting routes the skill has to say which one decides"
    )
    assert "empty source is an error" in text, (
        "asserting anonymously is the one failure this gate cannot tolerate"
    )
    assert "itself another flag" in text, (
        "`--authorized --refresh-profile` must be the empty-source error, not a "
        "source named after the next flag"
    )


def test_an_authorization_unarmed_verdict_does_not_gate_the_security_lane() -> None:
    """Found by running it: recon marks trudy `unarmed` when the profile says
    `not asserted`, which collides with step 3's "dispatch only armed lanes".

    The 2026-08-05 proof run resolved it correctly, but by reasoning rather than
    by instruction. Left unstated, the invocation route arms her only when
    whoever runs the skill happens to read past the cost gate.

    Assertions here are load-bearing tokens, not whole sentences: the first
    version pinned two exact sentences, which meant correcting the rule forced
    editing the test that guards it.
    """
    text = _text(SKILL)
    assert "verdict about *surface*" in text, (
        "step 3 must distinguish a surface verdict from an authorization one"
    )
    assert "A surface `unarmed` still stands" in text, (
        "the exception must not void a surface verdict too — a repo with nothing "
        "to run does not become probeable because a flag was passed"
    )
    assert "If the row gives no reason" in text, (
        "an unexplained row has to fall to the safe side, or the exception "
        "swallows the cost gate"
    )


def test_recon_decides_the_security_lane_on_surface_alone() -> None:
    """The root cause of the two findings above, fixed where it starts.

    The profile contract has an `unarmed` row carry its reason rather than
    tactics, while a dispatch builds the lane's prompt from those tactics. So
    recon disarming trudy on authorization is how an invocation-armed lane gets
    dispatched with an empty strategy section and probes blind. The proof run
    escaped it only because recon volunteered tactics under an unarmed row.
    """
    text = _text(SKILL)
    assert "trudy is armed or unarmed on surface alone" in text
    assert "never decides her row" in text, (
        "recon must be told the Authorization line is not hers to act on"
    )


def test_the_report_records_which_act_authorized_the_probe() -> None:
    """A reader must tell an invocation assertion from a hand-edited profile."""
    text = _text(REFERENCES / "finding-contract.md")
    assert '"authorization"' in text, "the sidecar shape must carry the route"
    assert "which human act authorized it" in text, (
        "the markdown summary must name the route too; the sidecar alone is not "
        "what a human reads"
    )
