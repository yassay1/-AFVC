"""Understand user query as route + business_goal."""

from __future__ import annotations

import json
import re
from typing import Any

from backend.agent.llm_json import call_llm_json
from backend.agent.schemas import QueryUnderstanding
from backend.agent.state import AfcAgentState
from backend.core.llm import get_parse_llm

_CHAT_KEYWORDS = ("你好", "您好", "hello", "hi", "嗨", "在吗", "谢谢", "再见")
_CAPABILITY_KEYWORDS = (
    "你会干什么",
    "你能做什么",
    "有什么功能",
    "功能介绍",
    "使用说明",
    "怎么用",
    "帮助",
    "help",
)
_GLOBAL_KEYWORDS = (
    "整体情况",
    "概览",
    "这批工单",
    "工单数据",
    "高风险设备",
    "优先巡检",
    "巡检重点",
    "当前高风险",
)
_UNSUPPORTED_KEYWORDS = ("写论文", "天气", "推荐电影", "推荐音乐", "点外卖", "翻译", "写代码", "炒股")
_REFERENCE_PHRASES = ("那它", "它", "这个设备", "该设备", "刚才那个", "刚才那台", "这台", "那台", "那应该")
_BUSINESS_KEYWORDS = (
    "分析",
    "风险",
    "故障",
    "检查",
    "建议",
    "维修",
    "诊断",
    "历史",
    "预警",
    "巡检",
    "复发",
    "再坏",
    "手册",
    "规程",
    "工单",
)
_SWITCH_PATTERNS = (
    r"换成\s*([A-Za-z0-9]{3,})",
    r"换到\s*([A-Za-z0-9]{3,})",
    r"切换(?:到|成)?\s*(?:设备\s*)?([A-Za-z0-9]{3,})",
    r"再看(?:一下)?\s*(?:设备\s*)?([A-Za-z0-9]{3,})",
)


def _contains_any(query: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in query for phrase in phrases)


def _has_reference_pronoun(query: str) -> bool:
    return _contains_any(query, _REFERENCE_PHRASES)


def _has_device_switch(query: str) -> str | None:
    matches: list[str] = []
    for pattern in _SWITCH_PATTERNS:
        matches.extend(re.findall(pattern, query, re.IGNORECASE))
    return matches[-1].upper() if matches else None


def _is_capability_question(query: str) -> bool:
    lower = query.lower()
    return _contains_any(query, _CAPABILITY_KEYWORDS) or "help" in lower


def _is_global_question(query: str) -> bool:
    return _contains_any(query, _GLOBAL_KEYWORDS)


def _is_chat(query: str) -> bool:
    lower = query.lower()
    return _contains_any(query, _CHAT_KEYWORDS) or lower in {"hello", "hi"}


def _is_unsupported(query: str) -> bool:
    return _contains_any(query, _UNSUPPORTED_KEYWORDS)


def _extract_assetnum(query: str) -> str | None:
    patterns = (r"设备\s*([A-Za-z0-9]{3,})", r"([A-Z]{2,}\d{5,})", r"(\d{10,})")
    found: list[str] = []
    for pattern in patterns:
        found.extend(re.findall(pattern, query))
    return found[-1].upper() if found else None


def _extract_time_window(query: str) -> str | None:
    mapping = [
        (("7天", "七天", "一周", "1周"), "7d"),
        (("14天", "两周", "二周"), "14d"),
        (("21天", "三周"), "21d"),
        (("30天", "一个月", "一月", "未来一个月"), "30d"),
        (("60天", "两个月", "二个月"), "60d"),
        (("90天", "三个月"), "90d"),
    ]
    for keywords, value in mapping:
        if any(k in query for k in keywords):
            return value
    return None


def _looks_like_business_question(query: str) -> bool:
    return bool(_extract_assetnum(query)) or _contains_any(query, _BUSINESS_KEYWORDS)


def _detect_business_goal(query: str) -> str | None:
    has_manual = _contains_any(query, ("手册", "规程", "标准"))
    has_fault_type = _contains_any(
        query,
        (
            "会发生什么故障",
            "可能出现什么错误",
            "下次可能坏哪里",
            "最可能出现什么问题",
            "未来可能报什么错",
            "哪个模块最可能故障",
            "最可能发生什么",
            "什么故障",
            "哪种故障",
            "哪类故障",
            "故障类型",
            "故障类别",
            "哪个模块",
        ),
    )
    has_risk = _contains_any(query, ("风险", "预测", "复发", "再坏", "再次故障", "什么时候"))
    has_advice = _contains_any(query, ("检查", "建议", "处理", "维修", "先看", "先检查"))
    has_history = _contains_any(query, ("历史", "最近", "以前", "出过", "记录", "工单"))
    has_warning = _contains_any(query, ("为什么", "预警", "红色", "橙色", "黄色"))

    if has_manual:
        return "manual_search"
    if has_fault_type:
        return "fault_type_prediction"
    if has_risk and has_advice:
        return "full_diagnosis"
    if has_warning or has_risk:
        return "device_risk"
    if has_history:
        return "device_history"
    if has_advice:
        return "device_advice"
    return "full_diagnosis"


def _detect_route(query: str, context_packet: dict[str, Any]) -> tuple[str, str | None, str | None, str | None, bool, bool]:
    if _is_chat(query) and not _looks_like_business_question(query):
        return "direct_chat", None, None, None, False, False
    if _is_capability_question(query):
        return "capability_query", None, None, None, False, False
    if _is_unsupported(query):
        return "unsupported", None, None, None, False, False

    switch = _has_device_switch(query)
    if switch:
        goal = _detect_business_goal(query)
        return "business_device", goal, switch, _extract_time_window(query), True, goal == "manual_search"

    if _is_global_question(query):
        goal = "high_risk_ranking" if ("高风险" in query or "优先" in query) else "data_overview"
        return "business_global", goal, None, None, False, False

    assetnum = _extract_assetnum(query)
    if assetnum:
        goal = _detect_business_goal(query)
        return "business_device", goal, assetnum, _extract_time_window(query), True, goal == "manual_search"

    active_assetnum = context_packet.get("active_assetnum")
    if _has_reference_pronoun(query) and active_assetnum:
        goal = _detect_business_goal(query)
        return "business_device", goal, active_assetnum, _extract_time_window(query), True, goal == "manual_search"

    if _looks_like_business_question(query):
        if active_assetnum:
            goal = _detect_business_goal(query)
            return "business_device", goal, active_assetnum, _extract_time_window(query), True, goal == "manual_search"
        return "needs_clarification", None, None, None, False, False

    return "direct_chat", None, None, None, False, False


UNDERSTAND_QUERY_SYSTEM = """You parse AFC maintenance questions.
Return only a JSON object matching QueryUnderstanding.
Use route and business_goal as the only semantic routing fields.
"""

UNDERSTAND_JSON_SKELETON = """{
  "route": "business_device",
  "business_goal": "device_risk",
  "assetnum": "1000029970",
  "time_window": "30d",
  "needs_asset": true,
  "needs_tools": true,
  "needs_rag": false,
  "context_used": false,
  "information_need": "query device recurrence risk",
  "user_question_rewrite": "query recurrence risk for device 1000029970 in 30 days",
  "confidence": 0.95
}"""


def _build_understand_prompt(query: str, context_packet: dict[str, Any]) -> str:
    return (
        "Context:\n"
        f"- active_assetnum: {context_packet.get('active_assetnum') or 'null'}\n"
        f"- active_route: {context_packet.get('active_route') or 'null'}\n"
        f"- active_business_goal: {context_packet.get('active_business_goal') or 'null'}\n"
        f"- active_time_window: {context_packet.get('active_time_window') or 'null'}\n"
        f"- known_entities: {json.dumps(context_packet.get('known_entities', []), ensure_ascii=False)}\n\n"
        "Route values: direct_chat, capability_query, business_global, business_device, "
        "needs_clarification, unsupported.\n"
        "Business goals: data_overview, high_risk_ranking, device_risk, device_history, "
        "device_advice, fault_type_prediction, full_diagnosis, manual_search, null.\n"
        f"User query:\n{query}\n\n"
        f"JSON skeleton:\n{UNDERSTAND_JSON_SKELETON}"
    )


def _rule_based_understanding(query: str, context_packet: dict[str, Any]) -> dict[str, Any]:
    route, business_goal, assetnum, time_window, needs_asset, needs_rag = _detect_route(query, context_packet)
    needs_tools = route in {"business_global", "business_device"}
    context_used = bool(assetnum and assetnum == context_packet.get("active_assetnum"))
    info_need_map = {
        "direct_chat": "casual chat",
        "capability_query": "ask about agent capabilities",
        "business_global": f"global business query: {business_goal}",
        "business_device": f"device {assetnum} business query: {business_goal}",
        "needs_clarification": "business query missing required device id",
        "unsupported": "unsupported query",
    }
    return QueryUnderstanding(
        route=route,
        business_goal=business_goal,
        assetnum=assetnum,
        time_window=time_window,
        needs_asset=needs_asset,
        needs_tools=needs_tools,
        needs_rag=needs_rag,
        context_used=context_used,
        information_need=info_need_map.get(route, "unknown"),
        user_question_rewrite=query,
        confidence=0.9 if route != "business_device" else 0.85,
    ).model_dump()


def _post_process_llm_understanding(
    understanding: dict[str, Any],
    query: str,
    context_packet: dict[str, Any],
) -> None:
    active_assetnum = context_packet.get("active_assetnum")
    explicit_assetnum = _extract_assetnum(query)

    if understanding.get("route") == "direct_chat" and _looks_like_business_question(query):
        understanding["route"] = "business_device" if (explicit_assetnum or active_assetnum) else "needs_clarification"
        understanding["business_goal"] = _detect_business_goal(query) if understanding["route"] == "business_device" else None

    if explicit_assetnum:
        understanding["assetnum"] = explicit_assetnum
    elif not understanding.get("assetnum") and active_assetnum and _has_reference_pronoun(query):
        understanding["assetnum"] = active_assetnum
        understanding["context_used"] = True

    switch = _has_device_switch(query)
    if switch:
        understanding["assetnum"] = switch
        understanding["route"] = "business_device"
        understanding["business_goal"] = understanding.get("business_goal") or _detect_business_goal(query)
        understanding["context_used"] = True

    if understanding.get("route") == "business_device":
        understanding["business_goal"] = understanding.get("business_goal") or _detect_business_goal(query)
        understanding["needs_asset"] = True
        understanding["needs_tools"] = True
    elif understanding.get("route") in {"direct_chat", "capability_query", "needs_clarification", "unsupported"}:
        understanding["needs_tools"] = False
        understanding["needs_asset"] = False
        if understanding.get("route") != "needs_clarification":
            understanding["business_goal"] = None


def understand_query_node(state: AfcAgentState) -> dict[str, Any]:
    query = state.get("query", "").strip()
    context_packet = state.get("context_packet", {})
    errors: list[str] = list(state.get("errors", []))
    understanding: dict[str, Any] | None = None

    try:
        llm = get_parse_llm()
        prompt = _build_understand_prompt(query, context_packet)
        result = call_llm_json(
            llm=llm,
            prompt=prompt,
            schema=QueryUnderstanding,
            system_prompt=UNDERSTAND_QUERY_SYSTEM,
            max_repair_attempts=2,
            repair_context=prompt,
        )
        understanding = result.model_dump()
        _post_process_llm_understanding(understanding, query, context_packet)
        understanding = QueryUnderstanding(**understanding).model_dump()
    except Exception as exc:
        errors.append(f"LLM query understanding unavailable, used rule fallback: {str(exc)}")

    if understanding is None:
        understanding = _rule_based_understanding(query, context_packet)

    return {"query_understanding": understanding, "errors": errors}
