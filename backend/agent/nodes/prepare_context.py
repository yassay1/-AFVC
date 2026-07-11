"""Prepare cross-turn context for downstream Agent nodes."""

from __future__ import annotations

import re
from typing import Any

from backend.agent.state import AfcAgentState, CAPABILITY_BOUNDARY


def _truncate_text(text: str, max_len: int = 300) -> str:
    text = str(text).replace("\n", " ").strip()
    return text[:max_len] + "..." if len(text) > max_len else text


def _format_recent_messages(messages: list[Any], limit: int = 6) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    for message in messages[-limit:]:
        role = message.__class__.__name__.replace("Message", "")
        content = getattr(message, "content", str(message))
        formatted.append({"role": role, "content": _truncate_text(str(content))})
    return formatted


def _build_recent_summary(messages: list[Any]) -> str | None:
    if len(messages) <= 4:
        return None
    lines: list[str] = []
    for msg in messages[-6:]:
        role = msg.__class__.__name__.replace("Message", "")
        content = _truncate_text(str(getattr(msg, "content", "")), 150)
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _build_conversation_focus(
    last_assetnum: str | None,
    last_route: str | None,
    last_business_goal: str | None,
) -> str | None:
    if not last_assetnum:
        return None
    parts = [f"device {last_assetnum}"]
    if last_route:
        parts.append(f"route={last_route}")
    if last_business_goal:
        parts.append(f"business_goal={last_business_goal}")
    return ", ".join(parts)


def prepare_context_node(state: AfcAgentState) -> dict[str, Any]:
    query = state.get("query", "").strip()
    messages = state.get("messages", [])
    last_assetnum = state.get("last_assetnum")
    last_route = state.get("last_route")
    last_business_goal = state.get("last_business_goal")
    last_time_window = state.get("last_time_window")
    last_tool_results_summary = state.get("last_tool_results_summary", {})
    last_evidence_summary = state.get("last_evidence_summary", {})

    known_entities: list[str] = []
    if last_assetnum:
        known_entities.append(last_assetnum)
    for match in re.findall(r"[A-Z]{2,}\d{5,}|\d{10,}", query):
        if match not in known_entities:
            known_entities.append(match)

    return {
        "context_packet": {
            "current_query": query,
            "active_assetnum": last_assetnum,
            "active_route": last_route,
            "active_business_goal": last_business_goal,
            "active_time_window": last_time_window,
            "recent_messages": _format_recent_messages(messages, limit=6),
            "recent_messages_summary": _build_recent_summary(messages),
            "last_tool_results_summary": last_tool_results_summary or {},
            "last_evidence_summary": last_evidence_summary or {},
            "conversation_focus": _build_conversation_focus(
                last_assetnum, last_route, last_business_goal
            ),
            "known_entities": known_entities,
            "capability_boundary": CAPABILITY_BOUNDARY,
        }
    }
