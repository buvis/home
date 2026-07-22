"""Implementor routing for /work step 3 — the deterministic table plus the codex rung.

Pure decision core: three functions over plain dicts, no I/O, no env reads of its
own, no side effects. It pins the step-3 routing table (the `fable` override,
rows 1-7, first match wins), the codex interception, and codex attempt outcomes
so the SKILL.md prose cannot drift from the rules silently.
"""

from __future__ import annotations

# The rows whose verdict is "Claude at the task's (original) tier" — the only
# rows the codex rung may intercept.
_INTERCEPTION_ROWS = frozenset({"row3", "row4", "row6", "row7"})

_CODEX_ATTEMPT_OUTCOMES = {
    "timeout": {
        "arm": "infra",
        "next": "claude_at_tier",
        "cause": "timeout",
        "codex_outcome": "aborted",
        "escalation_reason": None,
        "escalated_from": None,
    },
    "no_output": {
        "arm": "infra",
        "next": "claude_at_tier",
        "cause": "subagent_infra_failure",
        "codex_outcome": "aborted",
        "escalation_reason": None,
        "escalated_from": None,
    },
    "no_edit": {
        "arm": "infra",
        "next": "claude_at_tier",
        "cause": "codex_no_edit",
        "codex_outcome": "aborted",
        "escalation_reason": None,
        "escalated_from": None,
    },
    "pass": {
        "arm": "pass",
        "next": "proceed",
        "cause": None,
        "codex_outcome": "completed",
        "escalation_reason": None,
        "escalated_from": None,
    },
    "retry": {
        "arm": "capability",
        "next": "feedback_retry_codex",
        "cause": None,
        "codex_outcome": None,
        "escalation_reason": None,
        "escalated_from": None,
    },
    "escalate": {
        "arm": "capability",
        "next": "escalate_claude_at_tier",
        "cause": None,
        "codex_outcome": "escalated",
        "escalation_reason": "gate_failure",
        "escalated_from": "codex",
    },
}


def _tier(task: dict) -> str:
    """The task's model tier. A legacy plan (no `model`, or `model: None`) is sonnet."""
    return task.get("model") or "sonnet"


def route(task: dict, env: dict, state: dict, probes: dict) -> dict:
    """Pick the implementor for one claimed task."""
    tier = _tier(task)
    if tier == "fable":
        return {"implementor": "claude", "tier": tier, "rule": "fable_override"}

    rule = _table_row(task, env, state, probes)
    if rule in _INTERCEPTION_ROWS and _intercepted_by_codex(task, env, state):
        return {"implementor": "codex", "tier": tier, "rule": "codex_interception"}

    if rule == "row1":
        implementor = "gemini" if probes["gemini_available"] else "claude"
    elif rule == "row5":
        implementor = "qwen"
    else:
        implementor = "claude"
    return {"implementor": implementor, "tier": tier, "rule": rule}


def needs_probe(state: dict, batch_id: str) -> bool:
    """True when no codex probe verdict is cached for exactly this batch."""
    return state.get("codex_probe", {}).get("batch_id") != batch_id


def codex_attempt_outcome(signals: dict) -> dict:
    """Classify a codex implementor attempt and name its next action."""
    if signals["watchdog_timeout"]:
        outcome = "timeout"
    elif not signals["output_nonempty"]:
        outcome = "no_output"
    elif signals["no_edit"] is True:
        outcome = "no_edit"
    elif signals["gate_failures_at_codex"] == 0:
        outcome = "pass"
    elif signals["gate_failures_at_codex"] == 1:
        outcome = "retry"
    else:
        outcome = "escalate"
    return _CODEX_ATTEMPT_OUTCOMES[outcome].copy()


def _table_row(task: dict, env: dict, state: dict, probes: dict) -> str:
    if _is_ui(task):
        return "row1"
    if _tier(task) == "opus":
        return "row2"
    if not task.get("qwen_eligible", False):
        return "row7"
    if env.get("_AUTOPILOT_ESCALATION") != "legacy" and state.get(
        "qwen_breaker", {}
    ).get("tripped"):
        return "row3"
    if probes["memory_gate_exit"] != 0:
        return "row4"
    if probes.get("qwen_preflight") == "healthy":
        return "row5"
    return "row6"


def _is_ui(task: dict) -> bool:
    if "is_ui" in task:
        return bool(task["is_ui"])
    return task.get("qwen_excluded_reason") == "ui"


def _codex_eligible(task: dict) -> bool:
    return bool(task.get("qwen_eligible", False)) or (
        task.get("qwen_excluded_reason") == "files"
    )


def _intercepted_by_codex(task: dict, env: dict, state: dict) -> bool:
    return (
        _codex_eligible(task)
        and env.get("_WORK_CODEX_RUNG") != "off"
        and env.get("_AUTOPILOT_ESCALATION") != "legacy"
        and state.get("codex_probe", {}).get("verdict") == "healthy"
    )
