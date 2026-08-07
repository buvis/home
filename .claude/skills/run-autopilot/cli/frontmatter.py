#!/usr/bin/env python3
"""frontmatter.py - the Phase-0 PRD frontmatter parse and its defaults.

PURE: takes the PRD's TEXT, returns (fields, warnings). No disk, no PyYAML -
the recognized grammar is flat `key: value` lines, which is all any PRD in the
tree has ever used.

    parse(text) -> (fields, warnings)

`fields` maps STATE keys (not PRD keys) to effective values, and carries only
what Phase 0 should write: an absent optional field stays absent rather than
being written as a null. `warnings` holds the lines the caller prints.

Three dispositions, and the difference is deliberate:

- Invalid value      -> the default, plus one warning naming the field.
- Absent field       -> the default, silently. Warning on every unset field
                        would fire five times for a bare PRD, contradicting
                        the ONE-line whole-block fallback below.
- Malformed block or
  no frontmatter     -> every default, plus exactly one warning (MALFORMED).

Only the first 20 lines are read, per the Phase-0 contract: a block that has
not closed by then is malformed, and a `---` rule further down the body can
never be mistaken for the closing delimiter.

`default_model` is deliberately NOT recognized here. It belongs to
`/plan-tasks` and is re-read from the PRD at Phase 6 rework dispatch; Phase 0
never touches it, so it falls through as an unknown key.
"""

from __future__ import annotations

_HEAD_LINES = 20

# PRD key -> (state key, allowed values, default). Every one of these takes
# its default and warns when the value is not allowed.
_ENUMS: dict[str, tuple[str, tuple[str, ...], str]] = {
    "catchup": ("catchup_mode", ("run", "skip", "force"), "run"),
    "design": ("design_mode", ("run", "skip"), "run"),
    "doubt_reviewer": ("doubt_reviewer", ("codex", "fable"), "codex"),
    "consensus_engine": (
        "consensus_engine",
        ("legacy", "shadow", "workflow"),
        "legacy",
    ),
}

_REWORK_CAP_DEFAULT = 2

# The two opt-in markers: recognized only at their exact value, absent
# otherwise, and never warned about - an unset opt-in is the normal case.
_OPT_INS: dict[str, tuple[str, str, object]] = {
    "design_gate": ("design_gate", "user", "user"),
    "pause_on_ambiguity": ("pause_on_ambiguity", "true", True),
}

MALFORMED_WARNING = (
    "autopilot: PRD frontmatter malformed; defaulting catchup_mode=run, "
    "rework_cap=2, design_mode=run, doubt_reviewer=codex, "
    "consensus_engine=legacy"
)


def defaults() -> dict:
    """The effective fields for a PRD that declares nothing."""
    fields = {state_key: default for state_key, _allowed, default in _ENUMS.values()}
    fields["rework_cap"] = _REWORK_CAP_DEFAULT
    return fields


def _block(text: str) -> list[str] | None:
    """The frontmatter body lines, or None when absent or unterminated."""
    lines = text.splitlines()[:_HEAD_LINES]
    if not lines or lines[0].strip() != "---":
        return None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return lines[1:index]
    return None


def _pairs(body: list[str]) -> dict[str, str]:
    """Flat `key: value` lines as a dict. Splits on the FIRST colon only -
    `title: Harden the gate: part two` keeps its colon in the value."""
    pairs = {}
    for line in body:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        pairs[key.strip()] = value.strip()
    return pairs


def _rework_cap(raw: str) -> int | None:
    """`raw` as a positive int, or None when it is not one."""
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def parse(text: str) -> tuple[dict, list[str]]:
    """Parse `text`'s frontmatter into (state fields, warnings)."""
    fields = defaults()
    body = _block(text)
    if body is None:
        return fields, [MALFORMED_WARNING]

    declared = _pairs(body)
    warnings: list[str] = []

    for prd_key, (state_key, allowed, default) in _ENUMS.items():
        if prd_key not in declared:
            continue
        value = declared[prd_key]
        if value in allowed:
            fields[state_key] = value
        else:
            warnings.append(
                f"autopilot: PRD frontmatter {prd_key}={value!r} is not one of "
                f"{'/'.join(allowed)}; defaulting to {default}",
            )

    if "rework_cap" in declared:
        capped = _rework_cap(declared["rework_cap"])
        if capped is None:
            warnings.append(
                f"autopilot: PRD frontmatter rework_cap={declared['rework_cap']!r} "
                f"is not a positive integer; defaulting to {_REWORK_CAP_DEFAULT}",
            )
        else:
            fields["rework_cap"] = capped

    for prd_key, (state_key, marker, value) in _OPT_INS.items():
        if declared.get(prd_key) == marker:
            fields[state_key] = value

    return fields, warnings
