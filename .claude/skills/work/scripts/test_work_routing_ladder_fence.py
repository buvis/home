"""Tests for work_routing.py — the codex eligibility fence, extracted from
model-ladder.md § Codex rung.

`_codex_eligible` mirrors the `codex_eligible(task)` fence in
`run-autopilot/references/model-ladder.md` § Codex rung, but nothing at
runtime reads that fence — this suite is its only consumer. The tests below
EXTRACT the fence's clauses from the ladder text at test time instead of
hardcoding a second copy of them, the same house pattern
`review-work-completion/scripts/test_codex_doubt_guard.sh` uses for its jq
predicate: a hardcoded copy would only prove `_codex_eligible` works, not
that the documented fence and the mirrored rule stayed in sync. If someone
edits the fence's field or value, these tests go red instead of the drift
surfacing later as a silently wrong routing decision.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).with_name("work_routing.py")
_SPEC = importlib.util.spec_from_file_location("work_routing", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
work_routing = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(work_routing)


_LADDER_PATH = (
    Path(__file__).parent
    / ".."
    / ".."
    / "run-autopilot"
    / "references"
    / "model-ladder.md"
).resolve()

_CODEX_RUNG_HEADING_RE = re.compile(r"^## Codex rung\s*$", re.MULTILINE)
_NEXT_HEADING_RE = re.compile(r"^## ", re.MULTILINE)
_FENCE_RE = re.compile(r"```\n(.*?)\n[ \t]*```", re.DOTALL)
_CLAUSE_RE = re.compile(
    r"^\s*(?P<combinator>\w+)?\s*task\.(?P<field>\w+)\s*==\s*(?P<value>.+?)\s*$"
)


def _find_codex_eligible_block(ladder_text: str) -> str:
    """The fenced `codex_eligible(task)` block from `ladder_text`'s
    `## Codex rung` section.

    Raises, naming what could not be found, rather than returning `None` or
    skipping — a missing rule is the exact drift this guard exists to catch.
    """
    heading_match = _CODEX_RUNG_HEADING_RE.search(ladder_text)
    if heading_match is None:
        raise ValueError("'## Codex rung' heading not found in the ladder text")

    section_start = heading_match.end()
    next_heading_match = _NEXT_HEADING_RE.search(ladder_text, section_start)
    section_end = (
        next_heading_match.start() if next_heading_match else len(ladder_text)
    )
    section_text = ladder_text[section_start:section_end]

    for candidate in _FENCE_RE.findall(section_text):
        lines = candidate.splitlines()
        if lines and lines[0].strip().startswith("codex_eligible("):
            return candidate

    raise ValueError(
        "no fenced block starting with 'codex_eligible(' found in "
        "the '## Codex rung' section"
    )


def _validate_disjunction(combinators: list[str | None]) -> None:
    """Raises unless every combinator after the first clause is `OR`.

    The fence is documented as a disjunction (§ Codex rung: "OR"); the first
    clause has no combinator by construction, so only clauses after it are
    checked. A single-clause fence never reaches this loop body.
    """
    for combinator in combinators[1:]:
        if combinator != "OR":
            raise ValueError(
                f"'codex_eligible(task)' fence joins its clauses with "
                f"{combinator!r}, not the documented disjunction 'OR'"
            )


def _parse_fence_clauses(target_block: str) -> list[tuple[str, object]]:
    """The `(field, value)` clauses parsed line-by-line from `target_block`,
    after checking they are joined by the documented disjunction.
    """
    clauses: list[tuple[str, object]] = []
    combinators: list[str | None] = []
    for line in target_block.splitlines():
        clause_match = _CLAUSE_RE.search(line)
        if clause_match is None:
            continue
        field, raw_value = clause_match.group("field"), clause_match.group("value")
        combinators.append(clause_match.group("combinator"))
        if raw_value == "true":
            value: object = True
        elif raw_value == "false":
            value = False
        elif raw_value.startswith('"') and raw_value.endswith('"'):
            value = raw_value[1:-1]
        else:
            value = raw_value
        clauses.append((field, value))

    if not clauses:
        raise ValueError(
            "'codex_eligible(task)' block found but no "
            "'task.<field> == <value>' clause could be parsed from it"
        )

    _validate_disjunction(combinators)

    return clauses


def _extract_codex_eligible_clauses(ladder_text: str) -> list[tuple[str, object]]:
    """The `(field, value)` clauses of the `codex_eligible(task)` fence in
    `ladder_text`'s `## Codex rung` section.

    Never a hardcoded copy of the fence: an edit to `ladder_text` changes what
    this returns. Raises, naming what could not be found, rather than
    returning an empty list or skipping — a missing rule is the exact drift
    this guard exists to catch.
    """
    target_block = _find_codex_eligible_block(ladder_text)
    return _parse_fence_clauses(target_block)


_UNRELATED_EXCLUSION_REASON = "not_a_real_exclusion_reason"

# The candidate space for the iff check below: every value each field of the
# metadata vocabulary actually ranges over, not a copy of the fence's clauses.
# `/plan-tasks` writes `qwen_excluded_reason`; its values are enumerated in
# `work/SKILL.md`'s step-3 routing table prose ("ui", "tier", "files",
# "contract"). The sentinel is a value no real clause should ever use.
_CODEX_ELIGIBLE_CANDIDATES: list[tuple[str, object]] = [
    ("qwen_eligible", True),
    ("qwen_eligible", False),
    ("qwen_excluded_reason", "ui"),
    ("qwen_excluded_reason", "tier"),
    ("qwen_excluded_reason", "files"),
    ("qwen_excluded_reason", "contract"),
    ("qwen_excluded_reason", _UNRELATED_EXCLUSION_REASON),
]

_LADDER_TEXT_MISSING_FENCE = """\
## Codex rung

Some prose about the rung with no fenced predicate at all.

## Memory gate
"""

_ALTERED_LADDER_TEXT = """\
## Codex rung

- **Fences**: the eligibility predicate, evaluated at routing time:

  ```
  codex_eligible(task) =
        task.qwen_eligible == true
     OR task.qwen_excluded_reason == "tier"
  ```

## Memory gate
"""

_LADDER_TEXT_AND_COMBINATOR = """\
## Codex rung

- **Fences**: the eligibility predicate, evaluated at routing time:

  ```
  codex_eligible(task) =
        task.qwen_eligible == true
     AND task.qwen_excluded_reason == "files"
  ```

## Memory gate
"""

_LADDER_TEXT_SINGLE_CLAUSE = """\
## Codex rung

- **Fences**: the eligibility predicate, evaluated at routing time:

  ```
  codex_eligible(task) =
        task.qwen_eligible == true
  ```

## Memory gate
"""


def test_model_ladder_relative_path_resolves_to_a_real_file() -> None:
    # A guard on the guard: if the ladder ever moves, this fails with a plain
    # "no such file" message instead of a confusing failure inside the tests
    # below that read it.
    assert _LADDER_PATH.is_file()


def test_codex_eligible_agrees_with_every_clause_extracted_from_the_real_ladder() -> (
    None
):
    # Two checks, not one. The per-clause loop below reads whatever clauses
    # the ladder actually documents, so it still catches a clause ADDED for a
    # field this suite has never seen (a fixed candidate space cannot
    # enumerate an unknown future field name). The iff loop that follows
    # catches the mirror direction within the documented metadata vocabulary:
    # a clause silently DELETED (or narrowed to an undocumented value), which
    # a one-directional "every extracted clause is honored" loop would miss,
    # since deleting a clause only shrinks what it iterates over.
    ladder_text = _LADDER_PATH.read_text()
    clauses = _extract_codex_eligible_clauses(ladder_text)

    for field, value in clauses:
        task = {field: value}
        assert work_routing._codex_eligible(task) is True, (
            f"_codex_eligible must be True for a task carrying only "
            f"{field!r}: {value!r} — the clause extracted from "
            f"model-ladder.md § Codex rung"
        )

    reason_values = {
        value for field, value in clauses if field == "qwen_excluded_reason"
    }
    assert _UNRELATED_EXCLUSION_REASON not in reason_values, (
        "the sentinel exclusion reason collided with a real clause value; "
        "pick a different sentinel"
    )

    for field, value in _CODEX_ELIGIBLE_CANDIDATES:
        expected = (field, value) in clauses
        actual = work_routing._codex_eligible({field: value})
        assert actual is expected, (
            f"_codex_eligible({{{field!r}: {value!r}}}) returned {actual!r}, "
            f"but the ladder's extracted clauses "
            f"{'do' if expected else 'do not'} grant eligibility for this pair"
        )


def test_extractor_distinguishes_an_altered_exclusion_reason_from_the_real_one() -> (
    None
):
    # Proves the guard actually bites: this altered ladder text (never the
    # real file — that one is off-limits) differs from the real fence only in
    # the excluded-reason clause's value, "tier" instead of "files". The
    # comparison the test above performs against the real clause would fail
    # if run against this text: `_codex_eligible` still checks == "files", so
    # a task built from the altered clause must DISAGREE, not agree.
    altered_clauses = _extract_codex_eligible_clauses(_ALTERED_LADDER_TEXT)
    reason_clauses = [
        (field, value)
        for field, value in altered_clauses
        if field == "qwen_excluded_reason"
    ]

    assert reason_clauses == [("qwen_excluded_reason", "tier")]

    field, value = reason_clauses[0]
    assert work_routing._codex_eligible({field: value}) is False


def test_extractor_raises_when_the_codex_rung_section_has_no_fenced_predicate() -> (
    None
):
    with pytest.raises(ValueError, match="codex_eligible"):
        _extract_codex_eligible_clauses(_LADDER_TEXT_MISSING_FENCE)


def test_extractor_raises_when_the_fence_joins_clauses_with_a_non_or_combinator() -> (
    None
):
    # `_CLAUSE_RE` parses each clause line independently, so an `OR` silently
    # rewritten to `AND` in the ladder would otherwise leave the extracted
    # clause list unchanged and this guard green, even though `_codex_eligible`
    # hard-codes `or`. The extractor must refuse instead of parsing past it.
    with pytest.raises(ValueError, match="AND"):
        _extract_codex_eligible_clauses(_LADDER_TEXT_AND_COMBINATOR)


def test_extractor_does_not_raise_for_a_single_clause_fence_with_no_combinator() -> (
    None
):
    # A single-clause fence has no combinator at all; the combinator check
    # must not misfire on its absence.
    clauses = _extract_codex_eligible_clauses(_LADDER_TEXT_SINGLE_CLAUSE)

    assert clauses == [("qwen_eligible", True)]
