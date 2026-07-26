"""Tests for work_routing.py — `codex_attempt_outcome`.

Pins the pure classifier over a codex implementor attempt's signals: no I/O,
no env, no filesystem. Three infra arms (timeout, empty output, no-edit) are
checked in strict order before the gate-failure count is ever read, and none
of them may stamp an escalation — an infra failure is not evidence codex
lacked the capability. `no_edit=None` (the detector itself failed) must fall
through to the gate rules exactly like `no_edit=False`, never like
`no_edit=True`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).with_name("work_routing.py")
_SPEC = importlib.util.spec_from_file_location("work_routing", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
work_routing = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(work_routing)


def _signals(
    watchdog_timeout: bool = False,
    output_nonempty: bool = True,
    no_edit: bool | None = False,
    gate_failures_at_codex: int = 0,
) -> dict[str, object]:
    """A codex attempt's signals; defaults describe a clean pass at gate 0."""
    return {
        "watchdog_timeout": watchdog_timeout,
        "output_nonempty": output_nonempty,
        "no_edit": no_edit,
        "gate_failures_at_codex": gate_failures_at_codex,
    }


_INFRA_TIMEOUT = {
    "arm": "infra",
    "next": "claude_at_tier",
    "cause": "timeout",
    "codex_outcome": "aborted",
    "escalation_reason": None,
    "escalated_from": None,
}

_INFRA_NO_OUTPUT = {
    "arm": "infra",
    "next": "claude_at_tier",
    "cause": "subagent_infra_failure",
    "codex_outcome": "aborted",
    "escalation_reason": None,
    "escalated_from": None,
}

_INFRA_NO_EDIT = {
    "arm": "infra",
    "next": "claude_at_tier",
    "cause": "codex_no_edit",
    "codex_outcome": "aborted",
    "escalation_reason": None,
    "escalated_from": None,
}

_PASS = {
    "arm": "pass",
    "next": "proceed",
    "cause": None,
    "codex_outcome": "completed",
    "escalation_reason": None,
    "escalated_from": None,
}

_CAPABILITY_RETRY = {
    "arm": "capability",
    "next": "feedback_retry_codex",
    "cause": None,
    "codex_outcome": None,
    "escalation_reason": None,
    "escalated_from": None,
}

_CAPABILITY_ESCALATE = {
    "arm": "capability",
    "next": "escalate_claude_at_tier",
    "cause": None,
    "codex_outcome": "escalated",
    "escalation_reason": "gate_failure",
    "escalated_from": "codex",
}


def test_watchdog_timeout_is_infra_and_aborts() -> None:
    outcome = work_routing.codex_attempt_outcome(_signals(watchdog_timeout=True))

    assert outcome == _INFRA_TIMEOUT


def test_watchdog_timeout_outranks_every_other_signal() -> None:
    # A fixture that would otherwise fail the output and no-edit checks too,
    # and would otherwise escalate on gate count — rule 1 must still win
    # outright, since it is checked first.
    outcome = work_routing.codex_attempt_outcome(
        _signals(
            watchdog_timeout=True,
            output_nonempty=False,
            no_edit=True,
            gate_failures_at_codex=2,
        )
    )

    assert outcome == _INFRA_TIMEOUT


def test_missing_output_is_infra_when_the_watchdog_did_not_fire() -> None:
    outcome = work_routing.codex_attempt_outcome(_signals(output_nonempty=False))

    assert outcome == _INFRA_NO_OUTPUT


def test_missing_output_outranks_no_edit_and_the_gate_failure_count() -> None:
    # no_edit=True and gate_failures_at_codex=2 would each produce a verdict of
    # their own; rule 2 is checked before either, so it must still win.
    outcome = work_routing.codex_attempt_outcome(
        _signals(output_nonempty=False, no_edit=True, gate_failures_at_codex=2)
    )

    assert outcome == _INFRA_NO_OUTPUT


def test_no_edit_true_is_infra_and_never_escalates() -> None:
    # gate_failures_at_codex=2 would otherwise escalate on its own; the
    # no-edit arm must win instead, and must not carry the escalation stamp.
    outcome = work_routing.codex_attempt_outcome(
        _signals(no_edit=True, gate_failures_at_codex=2)
    )

    assert outcome == _INFRA_NO_EDIT


@pytest.mark.parametrize(
    "signals, expected",
    [
        pytest.param(_signals(watchdog_timeout=True), _INFRA_TIMEOUT, id="timeout"),
        pytest.param(
            _signals(output_nonempty=False),
            _INFRA_NO_OUTPUT,
            id="subagent_infra_failure",
        ),
        pytest.param(_signals(no_edit=True), _INFRA_NO_EDIT, id="codex_no_edit"),
    ],
)
def test_infra_arms_never_carry_an_escalation_stamp(
    signals: dict[str, object], expected: dict[str, object]
) -> None:
    # The asymmetry that makes the design work: an infra failure is never
    # evidence codex lacked the capability, so no infra arm may stamp an
    # escalation onto the entry that follows it.
    outcome = work_routing.codex_attempt_outcome(signals)

    assert outcome == expected
    assert outcome["escalation_reason"] is None
    assert outcome["escalated_from"] is None


def test_gate_zero_failures_is_pass_and_proceed() -> None:
    outcome = work_routing.codex_attempt_outcome(_signals(gate_failures_at_codex=0))

    assert outcome == _PASS


def test_indeterminate_no_edit_detector_falls_through_to_pass() -> None:
    # no_edit=None must never be treated as no-change; with a clean gate count
    # it reaches the same pass verdict no_edit=False would.
    outcome = work_routing.codex_attempt_outcome(
        _signals(no_edit=None, gate_failures_at_codex=0)
    )

    assert outcome == _PASS


def test_no_edit_true_and_no_edit_none_diverge_on_an_otherwise_identical_fixture() -> None:
    # The detector's INDETERMINATE answer must not collapse into its
    # unchanged-tree answer: same gate count, same everything else, opposite
    # arms entirely.
    unchanged = work_routing.codex_attempt_outcome(
        _signals(no_edit=True, gate_failures_at_codex=0)
    )
    indeterminate = work_routing.codex_attempt_outcome(
        _signals(no_edit=None, gate_failures_at_codex=0)
    )

    assert unchanged == _INFRA_NO_EDIT
    assert indeterminate == _PASS


def test_one_gate_failure_is_capability_retry_not_escalation() -> None:
    outcome = work_routing.codex_attempt_outcome(_signals(gate_failures_at_codex=1))

    assert outcome == _CAPABILITY_RETRY


def test_indeterminate_no_edit_with_one_gate_failure_falls_through_to_retry() -> None:
    outcome = work_routing.codex_attempt_outcome(
        _signals(no_edit=None, gate_failures_at_codex=1)
    )

    assert outcome == _CAPABILITY_RETRY


@pytest.mark.parametrize("gate_failures_at_codex", [2, 3, 5])
def test_two_or_more_gate_failures_escalates_to_claude_at_the_task_tier(
    gate_failures_at_codex: int,
) -> None:
    # The escalation target is the task's OWN tier, never a rung up and never
    # a repair — that is encoded entirely in the fixed `_CAPABILITY_ESCALATE`
    # shape, which this fires for any count from 2 upward.
    outcome = work_routing.codex_attempt_outcome(
        _signals(gate_failures_at_codex=gate_failures_at_codex)
    )

    assert outcome == _CAPABILITY_ESCALATE


def test_indeterminate_no_edit_with_two_gate_failures_falls_through_to_escalation() -> None:
    outcome = work_routing.codex_attempt_outcome(
        _signals(no_edit=None, gate_failures_at_codex=2)
    )

    assert outcome == _CAPABILITY_ESCALATE


def test_output_always_has_exactly_the_six_contract_keys() -> None:
    outcome = work_routing.codex_attempt_outcome(_signals())

    assert set(outcome) == {
        "arm",
        "next",
        "cause",
        "codex_outcome",
        "escalation_reason",
        "escalated_from",
    }
