"""Tests for work_routing.py — the /work step-3 implementor routing table.

Pins the fable override, the first-match-wins table (rows 1-7), and the codex
interception rung (PRD 00077), including its two hard promises: with the rung
toggled off every verdict is the pre-PRD one, and the rung adds no new
failure class. `route` and `needs_probe` are pure functions over dicts, so
every test here is pure — nothing shells out, nothing touches the filesystem.

Each of the four inputs is varied against an otherwise identical fixture, so a
verdict cannot be reproduced by keying on the task tier or on which key set a
flag. `gemini_available`, the cached codex probe, `_AUTOPILOT_ESCALATION` and
`_WORK_CODEX_RUNG` each flip a verdict on a fixture that changes in no other
way, and the codex families run at both haiku and sonnet.
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


BATCH_ID = "batch-00077"
OTHER_BATCH_ID = "batch-00078"

QWEN_PREFLIGHT_FAILURES = [
    "pi_missing",
    "endpoint_unreachable",
    "model_id_missing",
    "completion_failed",
]

# Both backend tiers the table can route away from claude. Every codex- and
# qwen-family test runs at both, so no rule can be keyed on the tier instead of
# on the condition it is supposed to read.
BACKEND_MODELS = ["haiku", "sonnet"]

# The two ways a task declares itself UI: derived from the exclusion reason, or
# stated outright.
UI_TASK_SHAPES = [
    pytest.param(
        {"qwen_eligible": False, "qwen_excluded_reason": "ui"},
        id="derived_from_excluded_reason",
    ),
    pytest.param({"is_ui": True}, id="explicit_is_ui_flag"),
]

# The two ways a codex-eligible files task reaches row 7: `qwen_eligible` false,
# or absent (a plan written before the qwen rung).
FILES_TASK_SHAPES = [
    pytest.param(
        {"qwen_eligible": False, "qwen_excluded_reason": "files"},
        id="qwen_eligible_false",
    ),
    pytest.param({"qwen_excluded_reason": "files"}, id="qwen_eligible_absent"),
]

# Every way a qwen-eligible task gets fenced off qwen and back onto claude at
# its original tier: the breaker (row 3), the memory gate (row 4), a failed
# preflight (row 6). All four are codex interception rows.
QWEN_PATH_FENCES = [
    pytest.param(
        {"qwen_breaker": {"tripped": True}},
        {"qwen_preflight": None},
        "row3",
        id="row3_breaker_tripped",
    ),
    pytest.param(
        {},
        {"qwen_preflight": None, "memory_gate_exit": 1},
        "row4",
        id="row4_memory_pressure",
    ),
    pytest.param(
        {},
        {"qwen_preflight": None, "memory_gate_exit": 2},
        "row4",
        id="row4_memory_probe_failed",
    ),
    pytest.param(
        {},
        {"qwen_preflight": "endpoint_unreachable"},
        "row6",
        id="row6_preflight_unhealthy",
    ),
]


def _task(model: str = "sonnet", **overrides: object) -> dict[str, object]:
    """A task at `model`; each test names only the fields its rule reads."""
    return {"model": model, **overrides}


def _env(**overrides: object) -> dict[str, object]:
    """Process env — an absent key means the variable is unset."""
    return dict(overrides)


def _state(
    probe_verdict: str | None = "healthy", **overrides: object
) -> dict[str, object]:
    """Autopilot state; default is a codex probe cached healthy for BATCH_ID.

    `probe_verdict=None` drops the `codex_probe` key entirely (no cache).
    """
    state: dict[str, object] = {}
    if probe_verdict is not None:
        state["codex_probe"] = {"batch_id": BATCH_ID, "verdict": probe_verdict}
    state.update(overrides)
    return state


def _probes(
    qwen_preflight: str | None = "healthy", **overrides: object
) -> dict[str, object]:
    """Probe results; default is memory headroom OK, qwen healthy, gemini up.

    `qwen_preflight=None` drops the key, modelling the rows that must decide
    before any preflight probe is run.
    """
    probes: dict[str, object] = {"memory_gate_exit": 0, "gemini_available": True}
    if qwen_preflight is not None:
        probes["qwen_preflight"] = qwen_preflight
    probes.update(overrides)
    return probes


def _route(
    task: dict[str, object],
    env: dict[str, object] | None = None,
    state: dict[str, object] | None = None,
    probes: dict[str, object] | None = None,
) -> dict[str, object]:
    return work_routing.route(
        task,
        _env() if env is None else env,
        _state() if state is None else state,
        _probes() if probes is None else probes,
    )


# Tier is an echo on purpose: gemini, qwen, codex and claude all run the task at
# the task's own tier, so `tier == task["model"]` in every assertion below. The
# fable override is the only row that pins a tier of its own, and there the task
# model already says fable. Equal tiers are the rule, not missing coverage; there
# is no downgrade rule to test.


# --- fable override ---------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        {"qwen_eligible": True},
        {"is_ui": True, "qwen_excluded_reason": "ui"},
        {"qwen_eligible": False, "qwen_excluded_reason": "files"},
    ],
    ids=["qwen_eligible", "ui", "codex_eligible_files"],
)
def test_fable_task_always_routes_to_claude_at_fable(
    extra: dict[str, object],
) -> None:
    # The override outranks the whole table: even a task that would otherwise
    # be gemini-, qwen-, or codex-bound stays on claude at the fable tier.
    verdict = _route(
        _task("fable", **extra),
        env=_env(_WORK_CODEX_RUNG="on"),
        state=_state(qwen_breaker={"tripped": True}),
    )

    assert verdict == {
        "implementor": "claude",
        "tier": "fable",
        "rule": "fable_override",
    }


# --- row 1: UI tasks and the gemini fallback --------------------------------


@pytest.mark.parametrize("model", BACKEND_MODELS + ["opus"])
@pytest.mark.parametrize("gemini_available", [True, False])
@pytest.mark.parametrize("ui_fields", UI_TASK_SHAPES)
def test_ui_task_routes_to_gemini_at_task_tier_only_when_gemini_is_available(
    ui_fields: dict[str, object], gemini_available: bool, model: str
) -> None:
    # `gemini_available` is the only thing that moves between the two halves of
    # this matrix: same tiers, same UI entry shapes, same everything else. The
    # opus tier rides along because row 1 is first-match and outranks row 2.
    verdict = _route(
        _task(model, **ui_fields),
        probes=_probes(gemini_available=gemini_available),
    )

    assert verdict == {
        "implementor": "gemini" if gemini_available else "claude",
        "tier": model,
        "rule": "row1",
    }


def test_explicit_is_ui_false_overrides_the_ui_excluded_reason() -> None:
    # `is_ui` is only *derived* from qwen_excluded_reason when it is absent; a
    # present False must win, dropping the task into the backend rows.
    verdict = _route(_task("sonnet", is_ui=False, qwen_excluded_reason="ui"))

    assert verdict == {"implementor": "claude", "tier": "sonnet", "rule": "row7"}


# --- row 2: opus stays on claude ---------------------------------------------


def test_opus_backend_task_routes_to_claude_at_opus() -> None:
    verdict = _route(_task("opus", qwen_eligible=False, qwen_excluded_reason="tier"))

    assert verdict == {"implementor": "claude", "tier": "opus", "rule": "row2"}


def test_opus_task_is_never_intercepted_by_codex() -> None:
    # Codex-eligible by the letter of codex_eligible() (qwen_eligible true) and
    # with a healthy probe, yet row 2 is not an interception row.
    verdict = _route(
        _task("opus", qwen_eligible=True),
        env=_env(_WORK_CODEX_RUNG="on"),
        state=_state(qwen_breaker={"tripped": True}),
    )

    assert verdict == {"implementor": "claude", "tier": "opus", "rule": "row2"}


# --- row 5: qwen preflight healthy -------------------------------------------


@pytest.mark.parametrize("model", BACKEND_MODELS)
def test_qwen_eligible_task_with_healthy_preflight_routes_to_qwen(model: str) -> None:
    # Row 5 is untouched by the codex rung: rung on, codex probe healthy, still
    # qwen, because row 5 is not a claude-at-tier row.
    verdict = _route(
        _task(model, qwen_eligible=True),
        env=_env(_WORK_CODEX_RUNG="on"),
    )

    assert verdict == {"implementor": "qwen", "tier": model, "rule": "row5"}


def test_untripped_qwen_breaker_does_not_fence_qwen() -> None:
    # Row 3 keys on the `tripped` flag, not on the presence of the slice.
    verdict = _route(
        _task("sonnet", qwen_eligible=True),
        state=_state(qwen_breaker={"tripped": False}),
    )

    assert verdict == {"implementor": "qwen", "tier": "sonnet", "rule": "row5"}


# --- row 7: not qwen-eligible ------------------------------------------------


@pytest.mark.parametrize("model", BACKEND_MODELS)
def test_legacy_plan_without_qwen_eligible_routes_to_claude_at_tier(model: str) -> None:
    # A plan written before the qwen rung carries no `qwen_eligible` key; an
    # absent key is false, and false alone is not codex-eligible either.
    verdict = _route(_task(model))

    assert verdict == {"implementor": "claude", "tier": model, "rule": "row7"}


@pytest.mark.parametrize("model", BACKEND_MODELS)
@pytest.mark.parametrize("reason", ["tier", "contract"])
def test_non_files_exclusion_reasons_are_not_codex_eligible(
    reason: str, model: str
) -> None:
    verdict = _route(_task(model, qwen_eligible=False, qwen_excluded_reason=reason))

    assert verdict == {"implementor": "claude", "tier": model, "rule": "row7"}


# --- codex interception: the files family (row 7) ----------------------------
#
# Every test in this section uses the same task shapes at the same two tiers.
# Only one input moves per test, so each verdict names the input it depends on.


@pytest.mark.parametrize("model", BACKEND_MODELS)
@pytest.mark.parametrize("files_fields", FILES_TASK_SHAPES)
def test_files_exclusion_reason_routes_to_codex_at_task_tier(
    files_fields: dict[str, object], model: str
) -> None:
    verdict = _route(_task(model, **files_fields))

    assert verdict == {
        "implementor": "codex",
        "tier": model,
        "rule": "codex_interception",
    }


@pytest.mark.parametrize("model", BACKEND_MODELS)
def test_codex_rung_off_preserves_row7_claude_verdict(model: str) -> None:
    verdict = _route(
        _task(model, qwen_eligible=False, qwen_excluded_reason="files"),
        env=_env(_WORK_CODEX_RUNG="off"),
    )

    assert verdict == {"implementor": "claude", "tier": model, "rule": "row7"}


@pytest.mark.parametrize("model", BACKEND_MODELS)
@pytest.mark.parametrize(
    "probe_verdict", ["unhealthy", None], ids=["probe_unhealthy", "no_cached_probe"]
)
def test_unusable_codex_probe_preserves_row7_claude_verdict(
    probe_verdict: str | None, model: str
) -> None:
    # Identical to the codex-positive fixture above except for the cached probe,
    # so passing this test requires actually reading state["codex_probe"].
    verdict = _route(
        _task(model, qwen_eligible=False, qwen_excluded_reason="files"),
        state=_state(probe_verdict),
    )

    assert verdict == {"implementor": "claude", "tier": model, "rule": "row7"}


@pytest.mark.parametrize("model", BACKEND_MODELS)
def test_legacy_escalation_blocks_codex_interception_on_files_tasks(model: str) -> None:
    # Same fixture as test_files_exclusion_reason_routes_to_codex_at_task_tier,
    # which routes to codex; the kill switch is the only difference.
    verdict = _route(
        _task(model, qwen_eligible=False, qwen_excluded_reason="files"),
        env=_env(_AUTOPILOT_ESCALATION="legacy"),
    )

    assert verdict == {"implementor": "claude", "tier": model, "rule": "row7"}


# --- codex interception: the qwen-path fences (rows 3, 4, 6) -----------------
#
# Rows 3, 4 and 6 all park a qwen-eligible task on claude at its original tier.
# Each is an interception row, and each is exercised at both backend tiers.


@pytest.mark.parametrize("model", BACKEND_MODELS)
@pytest.mark.parametrize("fence_state, fence_probes, expected_rule", QWEN_PATH_FENCES)
def test_qwen_fenced_task_routes_to_codex_at_task_tier(
    fence_state: dict[str, object],
    fence_probes: dict[str, object],
    expected_rule: str,
    model: str,
) -> None:
    # The qwen fences guard the local llama-server (its breaker, its RAM, its
    # endpoint); codex runs remotely, so none of them may reroute away from it.
    # Rows 3 and 4 decide before any preflight runs, hence no qwen_preflight key.
    # `expected_rule` is unused here: the interception replaces the fencing
    # row's rule, and the two tests below pin which row it was.
    verdict = _route(
        _task(model, qwen_eligible=True),
        state=_state(**fence_state),
        probes=_probes(**fence_probes),
    )

    assert verdict == {
        "implementor": "codex",
        "tier": model,
        "rule": "codex_interception",
    }


@pytest.mark.parametrize("model", BACKEND_MODELS)
@pytest.mark.parametrize("fence_state, fence_probes, expected_rule", QWEN_PATH_FENCES)
def test_codex_rung_off_preserves_the_fenced_claude_verdict(
    fence_state: dict[str, object],
    fence_probes: dict[str, object],
    expected_rule: str,
    model: str,
) -> None:
    # With the rung off each fence yields exactly its pre-PRD verdict: claude at
    # the original tier, decided by the row that fenced it.
    verdict = _route(
        _task(model, qwen_eligible=True),
        env=_env(_WORK_CODEX_RUNG="off"),
        state=_state(**fence_state),
        probes=_probes(**fence_probes),
    )

    assert verdict == {"implementor": "claude", "tier": model, "rule": expected_rule}


@pytest.mark.parametrize("model", BACKEND_MODELS)
@pytest.mark.parametrize("fence_state, fence_probes, expected_rule", QWEN_PATH_FENCES)
def test_unhealthy_codex_probe_preserves_the_fenced_claude_verdict(
    fence_state: dict[str, object],
    fence_probes: dict[str, object],
    expected_rule: str,
    model: str,
) -> None:
    # An unhealthy batch probe must leave every interception row exactly where
    # the table put it — the rung adds no new failure class.
    verdict = _route(
        _task(model, qwen_eligible=True),
        state=_state("unhealthy", **fence_state),
        probes=_probes(**fence_probes),
    )

    assert verdict == {"implementor": "claude", "tier": model, "rule": expected_rule}


@pytest.mark.parametrize("preflight", QWEN_PREFLIGHT_FAILURES)
def test_codex_rung_off_preserves_row6_for_every_preflight_failure(
    preflight: str,
) -> None:
    verdict = _route(
        _task("sonnet", qwen_eligible=True),
        env=_env(_WORK_CODEX_RUNG="off"),
        probes=_probes(qwen_preflight=preflight),
    )

    assert verdict == {"implementor": "claude", "tier": "sonnet", "rule": "row6"}


@pytest.mark.parametrize("model", BACKEND_MODELS)
@pytest.mark.parametrize("memory_gate_exit", [1, 2])
def test_tripped_breaker_outranks_the_memory_gate(
    memory_gate_exit: int, model: str
) -> None:
    # Both row 3 and row 4 apply; first-match-wins makes it row 3. Only the
    # rung-off verdict can show which row decided, since the interception
    # collapses both into the same codex verdict.
    verdict = _route(
        _task(model, qwen_eligible=True),
        env=_env(_WORK_CODEX_RUNG="off"),
        state=_state(qwen_breaker={"tripped": True}),
        probes=_probes(qwen_preflight=None, memory_gate_exit=memory_gate_exit),
    )

    assert verdict == {"implementor": "claude", "tier": model, "rule": "row3"}


@pytest.mark.parametrize("model", BACKEND_MODELS)
def test_legacy_escalation_lifts_the_breaker_fence_back_to_qwen(model: str) -> None:
    # Row 3 itself is conditioned on the escalation not being legacy, so under
    # legacy a tripped breaker no longer fences a task whose preflight is
    # healthy: it falls through to row 5. Without legacy this fixture is codex.
    verdict = _route(
        _task(model, qwen_eligible=True),
        env=_env(_AUTOPILOT_ESCALATION="legacy"),
        state=_state(qwen_breaker={"tripped": True}),
    )

    assert verdict == {"implementor": "qwen", "tier": model, "rule": "row5"}


@pytest.mark.parametrize("model", BACKEND_MODELS)
def test_legacy_escalation_blocks_codex_on_the_qwen_preflight_row(model: str) -> None:
    # Legacy skips row 3 and blocks the interception, so a tripped breaker with
    # a failed preflight lands on row 6 instead of row 3 or codex.
    verdict = _route(
        _task(model, qwen_eligible=True),
        env=_env(_AUTOPILOT_ESCALATION="legacy"),
        state=_state(qwen_breaker={"tripped": True}),
        probes=_probes(qwen_preflight="completion_failed"),
    )

    assert verdict == {"implementor": "claude", "tier": model, "rule": "row6"}


# --- codex interception: parsing the rung -----------------------------------


@pytest.mark.parametrize(
    "rung",
    ["on", "", "0", "OFF"],
    ids=["on", "empty", "zero", "wrong_case_off"],
)
def test_only_the_exact_value_off_disables_the_codex_rung(rung: str) -> None:
    # The same fixture is claude/row3 under _WORK_CODEX_RUNG=off (pinned above)
    # and codex under every other value, including unrecognised ones: the test
    # of the toggle is `!= "off"`, not membership in a known-values list.
    verdict = _route(
        _task("sonnet", qwen_eligible=True),
        env=_env(_WORK_CODEX_RUNG=rung),
        state=_state(qwen_breaker={"tripped": True}),
        probes=_probes(qwen_preflight=None),
    )

    assert verdict == {
        "implementor": "codex",
        "tier": "sonnet",
        "rule": "codex_interception",
    }


# --- needs_probe -------------------------------------------------------------


def test_probe_needed_when_no_verdict_is_cached() -> None:
    assert work_routing.needs_probe({}, BATCH_ID) is True


@pytest.mark.parametrize(
    "queried_batch_id",
    [
        OTHER_BATCH_ID,
        "batch-0007",
        "batch-000771",
        "batch-00077-retry",
        "rerun-batch-00077",
        "BATCH-00077",
        "",
    ],
    ids=[
        "sibling_batch",
        "prefix_of_cached_id",
        "cached_id_is_a_prefix",
        "cached_id_plus_suffix",
        "cached_id_with_prefix",
        "case_differs",
        "empty",
    ],
)
def test_probe_needed_when_cached_verdict_is_for_another_batch(
    queried_batch_id: str,
) -> None:
    # Batch identity is an exact string match, not a prefix or substring test.
    assert work_routing.needs_probe(_state(), queried_batch_id) is True


def test_probe_needed_when_cached_slice_has_no_batch_id() -> None:
    # A malformed cache cannot be attributed to this batch, so it is re-probed
    # rather than trusted.
    malformed = {"codex_probe": {"verdict": "healthy"}}

    assert work_routing.needs_probe(malformed, BATCH_ID) is True


@pytest.mark.parametrize("probe_verdict", ["healthy", "unhealthy"])
def test_cached_verdict_for_the_same_batch_is_reused(probe_verdict: str) -> None:
    # The cache is keyed on batch identity alone: an unhealthy verdict is a
    # decision for the batch, not a reason to re-probe per task.
    assert work_routing.needs_probe(_state(probe_verdict), BATCH_ID) is False


@pytest.mark.parametrize("probe_verdict", ["healthy", "unhealthy"])
def test_cached_verdict_is_reused_for_any_batch_id_not_just_the_default(
    probe_verdict: str,
) -> None:
    # The match is cached-id == queried-id. Varying only the queried id would let
    # an implementation hardcode the default fixture's literal.
    state = {"codex_probe": {"batch_id": OTHER_BATCH_ID, "verdict": probe_verdict}}

    assert work_routing.needs_probe(state, OTHER_BATCH_ID) is False


# --- second-order conditions: value, not mere presence ----------------------
#
# Each test below fixes a hole where a condition could be reproduced by reading
# a key's PRESENCE rather than its VALUE, or by exploiting two conditions that
# co-varied in every other fixture.


@pytest.mark.parametrize("model", BACKEND_MODELS)
def test_memory_gate_fires_even_when_a_preflight_verdict_is_present(
    model: str,
) -> None:
    # Every other row-4 fixture also omits `qwen_preflight`, so row 4 could be
    # reproduced as "no preflight key". Here the preflight is present AND
    # healthy: only the non-zero memory gate can send this off qwen.
    verdict = _route(
        _task(model, qwen_eligible=True),
        probes=_probes(memory_gate_exit=1),
    )

    assert verdict == {
        "implementor": "codex",
        "tier": model,
        "rule": "codex_interception",
    }


def test_memory_gate_fires_on_an_untripped_breaker() -> None:
    # An untripped breaker slice is present. Keying row 3 on slice presence
    # rather than on `tripped` would misreport this as row3.
    verdict = _route(
        _task("sonnet", qwen_eligible=True),
        env=_env(_WORK_CODEX_RUNG="off"),
        state=_state(qwen_breaker={"tripped": False}),
        probes=_probes(qwen_preflight=None, memory_gate_exit=1),
    )

    assert verdict == {"implementor": "claude", "tier": "sonnet", "rule": "row4"}


def test_tripped_breaker_fires_before_the_preflight_is_read() -> None:
    # The non-legacy twin of the escalation-lift test: same tripped breaker, same
    # healthy preflight, no kill switch. Row 3 must win. Without this, an
    # implementation that skips row 3 whenever a preflight value exists passes
    # the legacy test for the wrong reason and escalation is never measured.
    verdict = _route(
        _task("sonnet", qwen_eligible=True),
        env=_env(_WORK_CODEX_RUNG="off"),
        state=_state(qwen_breaker={"tripped": True}),
    )

    assert verdict == {"implementor": "claude", "tier": "sonnet", "rule": "row3"}


@pytest.mark.parametrize("escalation", ["normal", "aggressive", "", "LEGACY"])
def test_only_the_exact_value_legacy_blocks_the_codex_interception(
    escalation: str,
) -> None:
    # Mirrors the rung's values parade. `_AUTOPILOT_ESCALATION` appearing in env
    # at all must not block interception — only the exact string "legacy" does.
    verdict = _route(
        _task("sonnet", qwen_excluded_reason="files"),
        env=_env(_AUTOPILOT_ESCALATION=escalation),
    )

    assert verdict == {
        "implementor": "codex",
        "tier": "sonnet",
        "rule": "codex_interception",
    }


def test_legacy_escalation_blocks_interception_alongside_an_active_rung() -> None:
    # Both knobs present, rung explicitly on: the block must come from the
    # escalation VALUE, not from "env carries an unexpected key".
    verdict = _route(
        _task("sonnet", qwen_excluded_reason="files"),
        env=_env(_WORK_CODEX_RUNG="on", _AUTOPILOT_ESCALATION="legacy"),
    )

    assert verdict == {"implementor": "claude", "tier": "sonnet", "rule": "row7"}


def test_qwen_eligible_false_without_a_reason_is_not_codex_eligible() -> None:
    # `qwen_eligible: False` with no exclusion reason recorded. Reading the key's
    # presence instead of its value would send this down the qwen path.
    verdict = _route(_task("sonnet", qwen_eligible=False))

    assert verdict == {"implementor": "claude", "tier": "sonnet", "rule": "row7"}


@pytest.mark.parametrize(
    "probe",
    [
        pytest.param({"batch_id": BATCH_ID, "verdict": "timeout"}, id="timeout"),
        pytest.param({"batch_id": BATCH_ID, "verdict": ""}, id="empty_verdict"),
        pytest.param({"batch_id": BATCH_ID}, id="no_verdict_key"),
    ],
)
def test_only_a_healthy_verdict_admits_the_codex_interception(
    probe: dict[str, object],
) -> None:
    # Interception requires verdict == "healthy" exactly. An implementation
    # testing `!= "unhealthy"` would treat an unrecognised verdict as usable.
    verdict = _route(
        _task("sonnet", qwen_excluded_reason="files"),
        state={"codex_probe": probe},
    )

    assert verdict == {"implementor": "claude", "tier": "sonnet", "rule": "row7"}


@pytest.mark.parametrize("rung", ["on", "off"])
def test_the_rung_toggle_never_moves_a_healthy_qwen_task(rung: str) -> None:
    # Row 5 is outside the interception rows, so the toggle is inert here in both
    # directions — the pre-PRD promise holds on the qwen row too, not just on the
    # claude rows.
    verdict = _route(
        _task("sonnet", qwen_eligible=True),
        env=_env(_WORK_CODEX_RUNG=rung),
    )

    assert verdict == {"implementor": "qwen", "tier": "sonnet", "rule": "row5"}


# --- codex_attempt_outcome ---------------------------------------------------
#
# A pure classifier over a codex implementor attempt's signals: no I/O, no env,
# no filesystem. Three infra arms (timeout, empty output, no-edit) are checked
# in strict order before the gate-failure count is ever read, and none of them
# may stamp an escalation — an infra failure is not evidence codex lacked the
# capability. `no_edit=None` (the detector itself failed) must fall through to
# the gate rules exactly like `no_edit=False`, never like `no_edit=True`.


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


# --- legacy tasks: absent `model` treated as sonnet --------------------------
#
# SKILL.md states in four places that a task with no `model` field — a plan
# written before `metadata.model` existed — is treated as `sonnet`. These pin
# that rule at the routing-table boundary: a missing key must behave exactly
# like an explicit `"model": "sonnet"` for every row it can reach.


def _legacy_task(**overrides: object) -> dict[str, object]:
    """A task from a plan written before `metadata.model` existed — no `model` key."""
    return dict(overrides)


def test_legacy_task_without_model_routes_at_sonnet() -> None:
    # Plain case: no `model`, no `qwen_eligible`. Row 7's own rule treats an
    # absent `qwen_eligible` as false, so this must land on row 7 at the
    # task's tier. If absent `model` is not treated as sonnet, `route` raises
    # KeyError instead of ever returning a verdict.
    verdict = _route(_legacy_task())

    assert verdict == {"implementor": "claude", "tier": "sonnet", "rule": "row7"}


def test_legacy_task_is_never_treated_as_opus() -> None:
    # Row 2 fires on `task["model"] == "opus"`. A missing `model` key must not
    # read as opus — if it did, this verdict would come back as
    # {"implementor": "claude", "tier": "opus", "rule": "row2"}.
    verdict = _route(_legacy_task())

    assert verdict["tier"] != "opus"
    assert verdict["rule"] != "row2"


def test_legacy_task_that_is_qwen_eligible_still_reaches_the_qwen_row() -> None:
    # Absent `model` must not short-circuit the rest of the table: with
    # `qwen_eligible` true and a healthy preflight this must still fall
    # through to row 5, still reporting the tier as "sonnet".
    verdict = _route(_legacy_task(qwen_eligible=True))

    assert verdict == {"implementor": "qwen", "tier": "sonnet", "rule": "row5"}


def test_legacy_task_with_files_exclusion_reaches_codex_interception_at_sonnet() -> None:
    # Row 7's codex-eligible files family, on a legacy task: no `model` key,
    # `qwen_excluded_reason` "files", a healthy cached codex probe and the
    # rung on must still intercept, and the reported tier must be "sonnet".
    verdict = _route(
        _legacy_task(qwen_excluded_reason="files"),
        env=_env(_WORK_CODEX_RUNG="on"),
    )

    assert verdict == {
        "implementor": "codex",
        "tier": "sonnet",
        "rule": "codex_interception",
    }


# --- codex eligibility fence: extracted from model-ladder.md § Codex rung ---
#
# `_codex_eligible` mirrors the `codex_eligible(task)` fence in
# `run-autopilot/references/model-ladder.md` § Codex rung, but nothing at
# runtime reads that fence — this suite is its only consumer. The tests below
# EXTRACT the fence's clauses from the ladder text at test time instead of
# hardcoding a second copy of them, the same house pattern
# `review-work-completion/scripts/test_codex_doubt_guard.sh` uses for its jq
# predicate: a hardcoded copy would only prove `_codex_eligible` works, not
# that the documented fence and the mirrored rule stayed in sync. If someone
# edits the fence's field or value, these tests go red instead of the drift
# surfacing later as a silently wrong routing decision.

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
    r"^\s*(?P<combinator>\w+)?\s*task\.metadata\.(?P<field>\w+)\s*==\s*(?P<value>.+?)\s*$"
)


def _extract_codex_eligible_clauses(ladder_text: str) -> list[tuple[str, object]]:
    """The `(field, value)` clauses of the `codex_eligible(task)` fence in
    `ladder_text`'s `## Codex rung` section.

    Never a hardcoded copy of the fence: an edit to `ladder_text` changes what
    this returns. Raises, naming what could not be found, rather than
    returning an empty list or skipping — a missing rule is the exact drift
    this guard exists to catch.
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

    target_block: str | None = None
    for candidate in _FENCE_RE.findall(section_text):
        lines = candidate.splitlines()
        if lines and lines[0].strip().startswith("codex_eligible("):
            target_block = candidate
            break

    if target_block is None:
        raise ValueError(
            "no fenced block starting with 'codex_eligible(' found in "
            "the '## Codex rung' section"
        )

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
            "'task.metadata.<field> == <value>' clause could be parsed from it"
        )

    # The fence is documented as a disjunction (§ Codex rung: "OR"); the first
    # clause has no combinator by construction, so only clauses after it are
    # checked. A single-clause fence never reaches this loop body.
    for combinator in combinators[1:]:
        if combinator != "OR":
            raise ValueError(
                f"'codex_eligible(task)' fence joins its clauses with "
                f"{combinator!r}, not the documented disjunction 'OR'"
            )

    return clauses


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
        task.metadata.qwen_eligible == true
     OR task.metadata.qwen_excluded_reason == "tier"
  ```

## Memory gate
"""

_LADDER_TEXT_AND_COMBINATOR = """\
## Codex rung

- **Fences**: the eligibility predicate, evaluated at routing time:

  ```
  codex_eligible(task) =
        task.metadata.qwen_eligible == true
     AND task.metadata.qwen_excluded_reason == "files"
  ```

## Memory gate
"""

_LADDER_TEXT_SINGLE_CLAUSE = """\
## Codex rung

- **Fences**: the eligibility predicate, evaluated at routing time:

  ```
  codex_eligible(task) =
        task.metadata.qwen_eligible == true
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
