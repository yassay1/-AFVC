"""update_memory_node —— 记忆更新节点。

职责：
更新多轮对话状态，保存本轮的设备、任务类型、证据摘要等。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from backend.agent.state import AfcAgentState, NO_DEVICE_TASKS


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

    # 提取关键设备的简要信息
    device = evidence_packet.get("device_profile") or {}
    for key in ("assetnum", "station_name", "line", "brand"):
        if device.get(key):
            summary[key] = device[key]

    # 提取预警信息
    warning = evidence_packet.get("warning") or {}
    if warning.get("warning_level"):
        summary["warning_level"] = warning["warning_level"]

    return summary


def update_memory_node(state: AfcAgentState) -> dict[str, Any]:
    """更新多轮对话记忆。

    保存：
    - messages（最近 20 条）
    - last_assetnum（非全局任务时更新）
    - last_task_type
    - last_time_window
    - last_tool_results_summary
    - last_evidence_summary
    - conversation_focus
    """
    query = state.get("query", "")
    final_answer = state.get("final_answer", "")
    query_understanding = state.get("query_understanding", {})
    task_type = query_understanding.get("task_type", "")
    assetnum = query_understanding.get("assetnum")
    time_window = query_understanding.get("time_window")
    tool_results = state.get("tool_results", {})
    evidence_packet = state.get("evidence_packet", {})
    existing_messages = list(state.get("messages", []))

    # 构建本轮消息
    messages = existing_messages + [
        HumanMessage(content=query),
        AIMessage(content=final_answer),
    ]
    # 最多保留 20 条
    messages = messages[-20:]

    # 判断是否更新活跃设备
    # data_overview / high_risk_ranking / capability_query 不更新 active asset
    should_clear = task_type in NO_DEVICE_TASKS
    last_assetnum = None if should_clear else (assetnum or state.get("last_assetnum"))

    # 工具结果摘要
    tool_results_summary = _build_tool_results_summary(tool_results)
    evidence_summary = _build_evidence_summary(evidence_packet)

    # 对话焦点
    if last_assetnum and task_type:
        conversation_focus = f"设备 {last_assetnum} 的 {task_type}"
    elif last_assetnum:
        conversation_focus = f"设备 {last_assetnum}"
    else:
        conversation_focus = None

    memory_update = {
        "last_assetnum": last_assetnum,
        "last_task_type": task_type if not should_clear else state.get("last_task_type"),
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
        "last_task_type": task_type if not should_clear else state.get("last_task_type"),
        "last_time_window": time_window,
        "last_tool_results_summary": tool_results_summary,
        "last_evidence_summary": evidence_summary,
    }
