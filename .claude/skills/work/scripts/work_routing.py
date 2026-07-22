"""Implementor routing for /work step 3 — the deterministic table plus the codex rung.

Pure decision core: two functions over plain dicts, no I/O, no env reads of its
own, no side effects. It pins the step-3 routing table (the `fable` override,
rows 1-7, first match wins) and the codex interception so the SKILL.md prose
cannot drift from the rule silently.
"""

from __future__ import annotations

# The rows whose verdict is "Claude at the task's (original) tier" — the only
# rows the codex rung may intercept.
_INTERCEPTION_ROWS = frozenset({"row3", "row4", "row6", "row7"})


def route(task: dict, env: dict, state: dict, probes: dict) -> dict:
    """Pick the implementor for one claimed task."""
    tier = task["model"]
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


def _table_row(task: dict, env: dict, state: dict, probes: dict) -> str:
    if _is_ui(task):
        return "row1"
    if task["model"] == "opus":
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
