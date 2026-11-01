"""Anthropic review transports; launcher identity never establishes model origin."""

from __future__ import annotations

import re
from typing import Any


def backends(env: dict[str, str]) -> list[str]:
    names = env.get("AUTOCODEX_ANTHROPIC_BACKENDS", "kiro,copilot,claude").split(",")
    if (
        not names
        or len(set(names)) != len(names)
        or any(name not in {"kiro", "copilot", "claude"} for name in names)
    ):
        raise ValueError("AUTOCODEX_ANTHROPIC_BACKENDS must list unique kiro,copilot,claude routes")
    return names


def concrete_model(model: str, env: dict[str, str]) -> str:
    if model in {"opus", "sonnet", "haiku"}:
        selected = env.get(f"AUTOCODEX_ANTHROPIC_{model.upper()}_MODEL", f"claude-{model}-5.5")
        if not re.fullmatch(rf"claude-{model}-[0-9][a-z0-9.-]*", selected):
            raise ValueError(
                f"review route requires an explicit Claude {model} model: {selected!r}"
            )
        return selected
    if not re.fullmatch(r"claude-(?:opus|sonnet|haiku)-[0-9][a-z0-9.-]*", model):
        raise ValueError(f"review route requires an explicit Anthropic model: {model!r}")
    return model


def argv(backend: str, model: str, prompt: str, env: dict[str, str]) -> list[str]:
    """Only read tools are authorized; no shell, edits, resume or permission bypass."""
    if backend == "kiro":
        return [
            env.get("AUTOCODEX_KIRO_BIN", "kiro-cli"),
            "chat",
            "--no-interactive",
            "--model",
            model,
            "--effort",
            "xhigh",
            "--output-format",
            "stream-json",
            "--trust-tools=fs_read,read_file,glob,grep",
            prompt,
        ]
    return [
        env.get("AUTOCODEX_COPILOT_BIN", "copilot"),
        "--model",
        model,
        "--reasoning-effort",
        "xhigh",
        "--output-format",
        "json",
        "--no-ask-user",
        "--disable-builtin-mcps",
        "--available-tools",
        "view,glob,grep",
        "--allow-tool",
        "read",
        "-p",
        prompt,
    ]


def accept(events: Any, event: dict[str, Any]) -> bool:
    """Consume observed CLI envelopes, never model names mentioned in prose."""
    if events.provider == "kiro":
        return accept_kiro(events, event)
    return accept_copilot(events, event)


def accept_kiro(events: Any, event: dict[str, Any]) -> bool:
    kind, data = event.get("type"), event.get("data")
    if not isinstance(data, dict):
        return False
    if data.get("sessionId"):
        events.thread_id = str(data["sessionId"])
    if kind == "runFinished":
        events.success = (
            data.get("status") == "success"
            and data.get("stopReason") == "end_turn"
            and data.get("finalTextTruncated") is False
            and not events.permission_denied
        )
        events.text = str(data.get("finalText") or "")
        return True
    update = data.get("update")
    if kind != "sessionUpdate" or not isinstance(update, dict):
        return False
    meta = update.get("_meta", {}).get("kiro", {})
    if update.get("sessionUpdate") == "tool_call_update" and update.get("status") == "failed":
        message = str(update.get("rawOutput", {}).get("message", ""))
        if meta.get("policyDenial") or "The permission request failed before it was answered" in message:
            events.permission_denied = True
            events.success = False
            events.error = message or "Kiro tool blocked by permission policy"
    if update.get("sessionUpdate") == "config_option_update":
        for option in update.get("configOptions", []):
            if option.get("id") == "model":
                events.selected_model = option.get("currentValue", "")
            elif option.get("id") == "effortLevel":
                events.selected_effort = option.get("currentValue", "")
    if meta.get("kind") == "turn_start":
        events.models.add(events.selected_model)
        events.efforts.add(events.selected_effort)
    if meta.get("kind") == "display_error":
        events.error = str(meta.get("message") or "")
        error_type = str(meta.get("errorType") or "")
        if error_type in {"quota_exceeded", "rate_limit_error", "usage_limit"}:
            events.api_status = 429
        if "permission" in error_type:
            events.permission_denied = True
    return update.get("sessionUpdate") in {
        "agent_message_chunk",
        "tool_call",
        "tool_call_update",
    } or meta.get("kind") in {"turn_start", "turn_end", "display_error"}


def accept_copilot(events: Any, event: dict[str, Any]) -> bool:
    kind, data = event.get("type"), event.get("data", {})
    if not isinstance(data, dict):
        return False
    if kind == "model.call_start":
        events.models.add(str(data.get("model") or ""))
    elif kind == "user.message":
        reasoning = data.get("responsesReasoning", {})
        if isinstance(reasoning, dict) and reasoning.get("effort"):
            events.efforts.add(str(reasoning["effort"]))
    elif kind == "assistant.message" and not data.get("parentToolCallId"):
        events.text = str(data.get("content") or "")
    elif kind in {"model.call_failure", "session.error"}:
        events.error = str(data.get("errorMessage") or data.get("message") or "")
        events.api_status = data.get("statusCode")
        if "permission" in str(data.get("errorType", "")):
            events.permission_denied = True
    elif kind == "result":
        events.success = (
            event.get("exitCode") == 0 and not events.error and not events.permission_denied
        )
        events.thread_id = str(event.get("sessionId") or "")
        events.usage = event.get("usage") or {}
    return kind in {
        "model.call_start",
        "assistant.message",
        "model.call_failure",
        "session.error",
        "result",
        "tool.execution_complete",
    }
