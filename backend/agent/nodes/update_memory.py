"""update_memory_node —— 记忆更新节点（v0.3.0 升级）。

职责：
更新多轮对话状态，保存本轮的设备、任务类型、证据摘要等。

v0.3.0 升级：
- direct_chat / capability_intro / unsupported：保留业务上下文，不污染
- ask_for_assetnum：记录 pending business_goal，不设置 last_assetnum
- business_global：清除设备绑定
- business_device：更新设备和业务目标
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from backend.agent.state import AfcAgentState, NO_DEVICE_TASKS, CHAT_ROUTES

# v0.3.0: 全局问题清除设备绑定
GLOBAL_GOALS = {"data_overview", "high_risk_ranking"}


def _build_tool_results_summary(tool_results: dict[str, Any]) -> dict[str, Any]:
    """从原始 tool_results 中提取精简摘要。"""
    summary: dict[str, Any] = {}
    for tool_name, result in tool_results.items():
        if not isinstance(result, dict) or result.get("status") != "success":
            continue
        item: dict[str, Any] = {}
        for key in [
            "assetnum", "station_name", "warning_level",
            "risk_30d", "risk_90d", "suggested_inspection_window",
        ]:
            if key in result:
                item[key] = result[key]
        if "device_profile" in result:
            profile = result["device_profile"]
            if not item.get("assetnum"):
                item["assetnum"] = profile.get("assetnum")
            if not item.get("station_name"):
                item["station_name"] = profile.get("station_name")
        if item:
            summary[tool_name] = item
    return summary


def _build_evidence_summary(evidence_packet: dict[str, Any]) -> dict[str, Any]:
    """从 evidence_packet 中提取精简摘要。"""
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
    """更新多轮对话记忆（v0.3.0 升级版）。

    保存：
    - messages（最近 20 条）
    - last_assetnum（非全局/闲聊时更新）
    - last_task_type
    - last_time_window
    - last_tool_results_summary
    - last_evidence_summary
    - conversation_focus

    v0.3.0 规则：
    - direct_chat / capability_intro / unsupported：保留原业务上下文
    - ask_for_assetnum：不设置 last_assetnum，保留 last_task_type
    - business_global：清除设备绑定
    - business_device：更新设备和业务目标
    """
    query = state.get("query", "")
    final_answer = state.get("final_answer", "")
    query_understanding = state.get("query_understanding", {})
    route = query_understanding.get("route", "direct_chat")
    business_goal = query_understanding.get("business_goal")
    task_type = query_understanding.get("task_type", "")
    assetnum = query_understanding.get("assetnum")
    time_window = query_understanding.get("time_window")
    tool_results = state.get("tool_results", {})
    evidence_packet = state.get("evidence_packet", {})
    existing_messages = list(state.get("messages", []))

    # ── 构建本轮消息 ──
    messages = existing_messages + [
        HumanMessage(content=query),
        AIMessage(content=final_answer),
    ]
    messages = messages[-20:]

    # ── 决定是否更新活跃设备 ──
    # 闲聊/能力介绍/不支持 → 保留原上下文
    if route in CHAT_ROUTES:
        last_assetnum = state.get("last_assetnum")
        last_task_type = state.get("last_task_type")
        should_clear = False
    # 全局问题 → 清除设备
    elif route == "business_global" or business_goal in GLOBAL_GOALS:
        last_assetnum = None
        last_task_type = task_type
        should_clear = True
    # 缺参数 → 不更新设备
    elif route == "needs_clarification":
        last_assetnum = state.get("last_assetnum")
        last_task_type = state.get("last_task_type")
        should_clear = False
    # 单设备 → 更新设备
    elif route == "business_device" and assetnum:
        last_assetnum = assetnum
        last_task_type = task_type
        should_clear = False
    else:
        last_assetnum = state.get("last_assetnum")
        last_task_type = state.get("last_task_type")
        should_clear = False

    # ── 工具结果和证据摘要 ──
    tool_results_summary = _build_tool_results_summary(tool_results)
    evidence_summary = _build_evidence_summary(evidence_packet)

    # ── 对话焦点 ──
    if last_assetnum and route == "business_device":
        conversation_focus = f"设备 {last_assetnum} 的 {business_goal or task_type}"
    elif last_assetnum:
        conversation_focus = f"设备 {last_assetnum}"
    else:
        conversation_focus = state.get("last_evidence_summary", {}).get("conversation_focus") if route in CHAT_ROUTES else None

    memory_update = {
        "last_assetnum": last_assetnum,
        "last_task_type": last_task_type,
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
        "last_task_type": last_task_type,
        "last_time_window": time_window,
        "last_tool_results_summary": tool_results_summary,
        "last_evidence_summary": evidence_summary,
    }
