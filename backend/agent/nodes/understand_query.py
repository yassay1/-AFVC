"""understand_query_node —— 问题理解节点。

职责：
调用 LLM，把用户自然语言 + context_packet 解析成 QueryUnderstanding。
这是第一个核心 LLM 节点。
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from backend.agent.llm_json import call_llm_json
from backend.agent.schemas import QueryUnderstanding
from backend.agent.state import AfcAgentState, NO_DEVICE_TASKS
from backend.core.llm import get_parse_llm


# ── 规则辅助 ──────────────────────────────────────────────────────

_CAPABILITY_KEYWORDS = [
    "你会干什么", "你是谁", "怎么用", "有什么功能",
    "你能做什么", "你能干什么", "功能介绍", "使用说明",
    "你能干嘛", "你会什么", "能做什么", "帮助", "help",
    "你好", "嗨", "hello", "hi",
]

_GLOBAL_KEYWORDS = [
    "整体情况", "概览", "这批工单", "数据怎么样", "工单数据",
    "高风险设备", "优先巡检", "巡检重点", "当前高风险",
    "有哪些高风险", "今天优先",
]

_REFERENCE_PATTERNS = [
    r"^那它", r"^它", r"那它", r"它",
    r"这个设备", r"该设备", r"这设备",
    r"刚才那个", r"刚才那台", r"刚才的",
    r"这台", r"那台", r"那一台",
    r"那应该", r"那这个",
]

_SWITCH_PATTERNS = [
    r"换成?\s*([A-Za-z0-9]{3,})",
    r"再看下?\s*(?:设备\s*)?([A-Za-z0-9]{3,})",
    r"切换(?:到|成)\s*(?:设备\s*)?([A-Za-z0-9]{3,})",
    r"(?:换|改)(?:成|为|到)\s*(?:设备\s*)?([A-Za-z0-9]{3,})",
]


def _is_capability_question(query: str) -> bool:
    q = query.lower()
    return any(kw.lower() in q for kw in _CAPABILITY_KEYWORDS)


def _is_global_question(query: str) -> bool:
    return any(kw in query for kw in _GLOBAL_KEYWORDS)


def _has_reference_pronoun(query: str) -> bool:
    return any(re.search(p, query, re.IGNORECASE) for p in _REFERENCE_PATTERNS)


def _has_device_switch(query: str) -> str | None:
    matches: list[str] = []
    for pattern in _SWITCH_PATTERNS:
        matches.extend(re.findall(pattern, query, re.IGNORECASE))
    return matches[-1].upper() if matches else None


def _extract_assetnum(query: str) -> str | None:
    patterns = [
        r"设备\s*([A-Za-z0-9]{3,})",
        r"([A-Z]{2,}\d{5,})",
        r"(\d{10,})",
    ]
    found: list[str] = []
    for pattern in patterns:
        found.extend(re.findall(pattern, query))
    return found[-1].upper() if found else None


def _extract_time_window(query: str) -> str | None:
    mapping = [
        (["7天", "七天", "一周", "1周"], "7d"),
        (["14天", "两周", "二周"], "14d"),
        (["21天", "三周"], "21d"),
        (["30天", "一个月", "一月", "未来一个月"], "30d"),
        (["60天", "两个月", "二个月"], "60d"),
        (["90天", "三个月"], "90d"),
    ]
    for keywords, value in mapping:
        if any(k in query for k in keywords):
            return value
    return None


# ── Prompt 模板 ───────────────────────────────────────────────────

UNDERSTAND_QUERY_SYSTEM = """你是 AFC 智能运维 Agent 的意图解析器。

你的任务是把用户自然语言问题解析成结构化 JSON。
你只负责解析，不负责回答或诊断。

## 输出格式要求

必须只输出一个合法 JSON 对象，不要加任何解释、markdown 标记或多余文本。

## task_type 可选值

- capability_query: 询问系统能力/功能 ("你会干什么?")
- data_overview: 查看工单数据整体情况 ("这批工单整体情况怎么样?")
- high_risk_ranking: 查看高风险设备排名 ("当前高风险设备有哪些?")
- full_diagnosis: 对单台设备做完整诊断 ("帮我分析设备 1000029970")
- risk_query: 查询单设备风险 ("设备 1000029970 未来30天风险高吗?")
- history_query: 查询单设备历史工单 ("设备 1000029970 最近有哪些故障?")
- advice_query: 查询维修建议 ("设备 1000029970 应该检查什么?")
- risk_explanation: 解释预警原因 ("为什么设备 1000029970 是红色预警?")
- risk_and_advice_query: 既问风险又问建议
- manual_query: 明确要求按维修手册/规程回答 ("按维修手册应该查哪里?")
- followup_rewrite: 是对上一轮问题的追问改写
- unknown: 无法判断意图

## 关键规则

1. "什么时候再次故障 / 什么时候会复发 / 大约什么时候会再次故障" → risk_query
2. "按维修手册/按规程/按标准流程" → manual_query 或 needs_rag=true
3. 如果当前问题没有明确设备，但上下文中有 active_assetnum 且用户使用了指代词（他/它/这个设备），则 assetnum 继承上下文
4. 如果上下文中有 active_assetnum 且用户说 "换成XXX"，则 assetnum 切换为新设备
5. capability_query / data_overview / high_risk_ranking 不需要设备编号 (needs_asset=false)
6. "那应该先检查什么?" 等追问 → advice_query
7. "那为什么是黄色预警?" → risk_explanation
8. "再简短一点" → 保持上一轮 task_type，context_used=true"""


def _build_understand_prompt(query: str, context_packet: dict[str, Any]) -> str:
    """构建问题理解 Prompt。"""
    return (
        f"## 上下文信息\n"
        f"- active_assetnum: {context_packet.get('active_assetnum') or 'null'}\n"
        f"- active_task_type: {context_packet.get('active_task_type') or 'null'}\n"
        f"- active_time_window: {context_packet.get('active_time_window') or 'null'}\n"
        f"- conversation_focus: {context_packet.get('conversation_focus') or '无'}\n"
        f"- known_entities: {json.dumps(context_packet.get('known_entities', []), ensure_ascii=False)}\n"
        f"- recent_messages_summary: {context_packet.get('recent_messages_summary') or '无'}\n"
        f"\n## 当前用户问题\n{query}\n"
        f"\n请输出 QueryUnderstanding JSON（只输出 JSON）："
    )


def _rule_based_fallback(
    query: str, context_packet: dict[str, Any]
) -> dict[str, Any]:
    """当 LLM 不可用时的规则兜底。"""
    # 能力问题
    if _is_capability_question(query):
        return QueryUnderstanding(
            task_type="capability_query",
            assetnum=None,
            time_window=None,
            needs_asset=False,
            needs_rag=False,
            context_used=False,
            information_need="用户询问系统能力",
            user_question_rewrite=query,
            confidence=1.0,
        ).model_dump()

    # 全局问题
    if _is_global_question(query):
        task_type = "high_risk_ranking" if "高风险" in query or "优先" in query else "data_overview"
        return QueryUnderstanding(
            task_type=task_type,
            assetnum=None,
            time_window=None,
            needs_asset=False,
            needs_rag=False,
            context_used=False,
            information_need="用户询问全局数据",
            user_question_rewrite=query,
            confidence=0.9,
        ).model_dump()

    # 设备切换
    switch = _has_device_switch(query)
    if switch:
        return QueryUnderstanding(
            task_type="followup_rewrite",
            assetnum=switch,
            time_window=None,
            needs_asset=True,
            needs_rag=False,
            context_used=True,
            information_need=f"用户切换到设备 {switch}",
            user_question_rewrite=query,
            confidence=0.95,
        ).model_dump()

    # 指代继承
    active_assetnum = context_packet.get("active_assetnum")
    if _has_reference_pronoun(query) and active_assetnum:
        task_type = "full_diagnosis"
        if "风险" in query or "预测" in query:
            task_type = "risk_query"
        elif "检查" in query or "建议" in query or "先看" in query:
            task_type = "advice_query"
        elif "故障" in query or "历史" in query or "最近" in query:
            task_type = "history_query"
        elif "预警" in query or "为什么" in query:
            task_type = "risk_explanation"
        elif "手册" in query or "规程" in query:
            task_type = "manual_query"

        return QueryUnderstanding(
            task_type=task_type,
            assetnum=active_assetnum,
            time_window=_extract_time_window(query),
            needs_asset=True,
            needs_rag=("手册" in query or "规程" in query or task_type == "manual_query"),
            context_used=True,
            information_need=f"用户基于上下文设备 {active_assetnum} 追问",
            user_question_rewrite=f"查询设备 {active_assetnum} 的 {task_type}",
            confidence=0.85,
        ).model_dump()

    # 显式设备
    assetnum = _extract_assetnum(query)
    if assetnum:
        # 判断 task_type
        if "风险" in query and ("建议" in query or "检查" in query):
            task_type = "risk_and_advice_query"
        elif "风险" in query or "预测" in query:
            task_type = "risk_query"
        elif "检查" in query or "建议" in query or "处理" in query:
            task_type = "advice_query"
        elif "故障" in query or "历史" in query or "最近" in query:
            task_type = "history_query"
        elif "预警" in query or "为什么" in query:
            task_type = "risk_explanation"
        elif "手册" in query or "规程" in query:
            task_type = "manual_query"
        else:
            task_type = "full_diagnosis"

        return QueryUnderstanding(
            task_type=task_type,
            assetnum=assetnum,
            time_window=_extract_time_window(query),
            needs_asset=True,
            needs_rag=("手册" in query or "规程" in query or task_type == "manual_query"),
            context_used=False,
            information_need=f"用户询问设备 {assetnum} 的 {task_type}",
            user_question_rewrite=query,
            confidence=0.8,
        ).model_dump()

    # 兜底
    return QueryUnderstanding(
        task_type="unknown",
        assetnum=None,
        time_window=None,
        needs_asset=False,
        needs_rag=False,
        context_used=False,
        information_need="无法判断用户意图",
        user_question_rewrite=query,
        confidence=0.3,
    ).model_dump()


# ── 节点入口 ──────────────────────────────────────────────────────

def understand_query_node(state: AfcAgentState) -> dict[str, Any]:
    """理解用户问题并输出结构化 QueryUnderstanding。

    输入：query, context_packet
    输出：query_understanding
    """
    query = state.get("query", "").strip()
    context_packet = state.get("context_packet", {})
    errors: list[str] = list(state.get("errors", []))

    understanding: dict[str, Any] | None = None

    # 尝试 LLM
    try:
        llm = get_parse_llm()
        prompt = _build_understand_prompt(query, context_packet)
        result = call_llm_json(
            llm=llm,
            prompt=prompt,
            schema=QueryUnderstanding,
            system_prompt=UNDERSTAND_QUERY_SYSTEM,
        )
        understanding = result.model_dump()
    except Exception as exc:
        errors.append(f"LLM 问题理解不可用，使用规则兜底：{str(exc)}")

    # 规则兜底
    if understanding is None:
        understanding = _rule_based_fallback(query, context_packet)

    # 后处理：如果 context_packet 有 active_assetnum 且确实是指代追问，覆盖
    active_assetnum = context_packet.get("active_assetnum")
    if (
        active_assetnum
        and not understanding.get("assetnum")
        and understanding.get("needs_asset")
        and _has_reference_pronoun(query)
    ):
        understanding["assetnum"] = active_assetnum
        understanding["context_used"] = True

    # 后处理：设备切换
    switch = _has_device_switch(query)
    if switch:
        understanding["assetnum"] = switch

    return {
        "query_understanding": understanding,
        "errors": errors,
    }
