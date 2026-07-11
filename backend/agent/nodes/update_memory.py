"""Update cross-turn memory for the AFC Agent."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from backend.agent.state import AfcAgentState, CHAT_ROUTES

GLOBAL_GOALS = {"data_overview", "high_risk_ranking"}


def _build_tool_results_summary(tool_results: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for tool_name, result in tool_results.items():
        if not isinstance(result, dict) or result.get("status") != "success":
            continue
        item: dict[str, Any] = {}
        for key in (
            "assetnum",
            "station_name",
            "warning_level",
            "risk_30d",
            "risk_90d",
            "suggested_inspection_window",
        ):
            if key in result:
                item[key] = result[key]
        profile = result.get("device_profile") if isinstance(result.get("device_profile"), dict) else {}
        if profile:
            item.setdefault("assetnum", profile.get("assetnum"))
            item.setdefault("station_name", profile.get("station_name"))
        if item:
            summary[tool_name] = item
    return summary


def _build_evidence_summary(evidence_packet: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "assetnum": evidence_packet.get("assetnum"),
        "sources": evidence_packet.get("sources", []),
        "missing_evidence": evidence_packet.get("missing_evidence", []),
    }
    device = evidence_packet.get("device_profile") or {}
    for key in ("assetnum", "station_name", "line", "brand"):
        if device.get(key):
            summary[key] = device[key]
    warning = evidence_packet.get("warning") or {}
    if warning.get("warning_level"):
        summary["warning_level"] = warning["warning_level"]
    return summary


def update_memory_node(state: AfcAgentState) -> dict[str, Any]:
    query = state.get("query", "")
    final_answer = state.get("final_answer", "")
    query_understanding = state.get("query_understanding", {})
    route = query_understanding.get("route", "direct_chat")
    business_goal = query_understanding.get("business_goal")
    assetnum = query_understanding.get("assetnum")
    time_window = query_understanding.get("time_window")
    tool_results = state.get("tool_results", {})
    evidence_packet = state.get("evidence_packet", {})

    messages = list(state.get("messages", [])) + [
        HumanMessage(content=query),
        AIMessage(content=final_answer),
    ]
    messages = messages[-20:]

    if route in CHAT_ROUTES:
        last_assetnum = state.get("last_assetnum")
        last_route = state.get("last_route")
        last_business_goal = state.get("last_business_goal")
        should_clear = False
    elif route == "business_global" or business_goal in GLOBAL_GOALS:
        last_assetnum = None
        last_route = route
        last_business_goal = business_goal
        should_clear = True
    elif route == "needs_clarification":
        last_assetnum = state.get("last_assetnum")
        last_route = state.get("last_route")
        last_business_goal = state.get("last_business_goal")
        should_clear = False
    elif route == "business_device" and assetnum:
        last_assetnum = assetnum
        last_route = route
        last_business_goal = business_goal
        should_clear = False
    else:
        last_assetnum = state.get("last_assetnum")
        last_route = state.get("last_route")
        last_business_goal = state.get("last_business_goal")
        should_clear = False

    tool_results_summary = _build_tool_results_summary(tool_results)
    evidence_summary = _build_evidence_summary(evidence_packet)

    if last_assetnum and last_business_goal:
        conversation_focus = f"device {last_assetnum}, business_goal={last_business_goal}"
    elif last_assetnum:
        conversation_focus = f"device {last_assetnum}"
    else:
        conversation_focus = None

    memory_update = {
        "last_assetnum": last_assetnum,
        "last_route": last_route,
        "last_business_goal": last_business_goal,
        "last_time_window": time_window,
        "last_tool_results_summary": tool_results_summary,
        "last_evidence_summary": evidence_summary,
        "conversation_focus": conversation_focus,
        "should_clear_active_asset": should_clear,
    }

    return {
        "memory_update": memory_update,
        "messages": messages,
        "last_assetnum": last_assetnum,
        "last_route": last_route,
        "last_business_goal": last_business_goal,
        "last_time_window": time_window,
        "last_tool_results_summary": tool_results_summary,
        "last_evidence_summary": evidence_summary,
    }
