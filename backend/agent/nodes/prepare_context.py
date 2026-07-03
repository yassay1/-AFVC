"""prepare_context_node —— 上下文整理节点。

职责：
只整理上下文，不判断意图，不调用业务工具。
输出 ContextPacket，告诉后续 LLM 当前对话焦点和能力边界。
"""

from __future__ import annotations

from typing import Any

from backend.agent.state import AfcAgentState, CAPABILITY_BOUNDARY


def _truncate_text(text: str, max_len: int = 300) -> str:
    """截断长文本。"""
    text = str(text).replace("\n", " ").strip()
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def _format_recent_messages(messages: list[Any], limit: int = 6) -> list[dict[str, Any]]:
    """格式化最近消息为简单 dict 列表。"""
    formatted: list[dict[str, Any]] = []
    for message in messages[-limit:]:
        role = message.__class__.__name__.replace("Message", "")
        content = getattr(message, "content", str(message))
        formatted.append({"role": role, "content": _truncate_text(str(content))})
    return formatted


def _build_conversation_focus(
    last_assetnum: str | None,
    last_task_type: str | None,
) -> str | None:
    """构建对话焦点描述。"""
    if not last_assetnum:
        return None
    parts = [f"上一轮分析设备 {last_assetnum}"]
    if last_task_type:
        parts.append(f"任务类型为 {last_task_type}")
    return "，".join(parts)


def _build_recent_summary(messages: list[Any]) -> str | None:
    """如果消息较多，生成简单摘要。"""
    if len(messages) <= 4:
        return None
    lines: list[str] = []
    for msg in messages[-6:]:
        role = msg.__class__.__name__.replace("Message", "")
        content = _truncate_text(str(getattr(msg, "content", "")), 150)
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def prepare_context_node(state: AfcAgentState) -> dict[str, Any]:
    """整理上下文，输出 ContextPacket。

    输入：
    - query, messages
    - last_assetnum, last_task_type, last_time_window
    - last_tool_results_summary, last_evidence_summary

    输出：
    - context_packet
    """
    query = state.get("query", "").strip()
    messages = state.get("messages", [])
    last_assetnum = state.get("last_assetnum")
    last_task_type = state.get("last_task_type")
    last_time_window = state.get("last_time_window")
    last_tool_results_summary = state.get("last_tool_results_summary", {})
    last_evidence_summary = state.get("last_evidence_summary", {})

    # 格式化最近消息
    recent_messages = _format_recent_messages(messages, limit=6)
    recent_messages_summary = _build_recent_summary(messages)

    # 对话焦点
    conversation_focus = _build_conversation_focus(last_assetnum, last_task_type)

    # 已知实体
    known_entities: list[str] = []
    if last_assetnum:
        known_entities.append(last_assetnum)
    # 从 query 中提取可能的设备编号
    import re
    asset_matches = re.findall(r"[A-Z]{2,}\d{5,}|\d{10,}", query)
    for m in asset_matches:
        if m not in known_entities:
            known_entities.append(m)

    context_packet = {
        "current_query": query,
        "active_assetnum": last_assetnum,
        "active_task_type": last_task_type,
        "active_time_window": last_time_window,
        "recent_messages": recent_messages,
        "recent_messages_summary": recent_messages_summary,
        "last_tool_results_summary": last_tool_results_summary or {},
        "last_evidence_summary": last_evidence_summary or {},
        "conversation_focus": conversation_focus,
        "known_entities": known_entities,
        "capability_boundary": CAPABILITY_BOUNDARY,
    }

    return {"context_packet": context_packet}
