"""understand_query_node —— 问题理解节点（v0.3.0 升级）。

职责：
调用 LLM 或规则，把用户自然语言 + context_packet 解析成 QueryUnderstanding。
v0.3.0 升级：从细粒度 task_type 升级为粗粒度 route + business_goal 双字段。

route 决定"怎么处理"（闲聊/能力/全局/单设备/缺参数/不支持），
business_goal 决定"具体做什么"（概览/排行/风险/历史/建议/诊断/手册）。
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from backend.agent.llm_json import call_llm_json
from backend.agent.schemas import QueryUnderstanding, route_to_task_type
from backend.agent.state import AfcAgentState, NO_DEVICE_ROUTES
from backend.core.llm import get_parse_llm


# ── 规则辅助：关键词与正则 ──────────────────────────────────────

# 闲聊/问候
_CHAT_KEYWORDS = [
    "你好", "hello", "hi", "嗨", "在吗", "早上好", "下午好", "晚上好",
    "谢谢", "辛苦了", "你真厉害", "随便聊聊", "再见", "拜拜",
]

# 能力询问
_CAPABILITY_KEYWORDS = [
    "你会干什么", "你是谁", "怎么用", "有什么功能",
    "你能做什么", "你能干什么", "功能介绍", "使用说明",
    "你能干嘛", "你会什么", "能做什么", "帮助", "help",
    "支持哪些功能", "可以分析什么", "怎么查询",
]

# 全局数据问题
_GLOBAL_KEYWORDS = [
    "整体情况", "概览", "这批工单", "数据怎么样", "工单数据",
    "高风险设备", "优先巡检", "巡检重点", "当前高风险",
    "有哪些高风险", "今天优先",
]

# 超出系统能力
_UNSUPPORTED_KEYWORDS = [
    "写论文", "天气", "数学题", "推荐电影", "推荐音乐", "点外卖",
    "翻译", "写代码", "编程", "炒股",
]

# 指代模式
_REFERENCE_PATTERNS = [
    r"^那它", r"^它", r"那它", r"它",
    r"这个设备", r"该设备", r"这设备",
    r"刚才那个", r"刚才那台", r"刚才的",
    r"这台", r"那台", r"那一台",
    r"那应该", r"那这个",
]

# 设备切换模式
_SWITCH_PATTERNS = [
    r"换成?\s*([A-Za-z0-9]{3,})",
    r"换到\s*([A-Za-z0-9]{3,})",
    r"换至\s*([A-Za-z0-9]{3,})",
    r"再看下?\s*(?:设备\s*)?([A-Za-z0-9]{3,})",
    r"切换(?:到|成)\s*(?:设备\s*)?([A-Za-z0-9]{3,})",
    r"(?:换|改)(?:成|为|到)\s*(?:设备\s*)?([A-Za-z0-9]{3,})",
]

_BUSINESS_KEYWORDS = [
    "分析", "风险", "故障", "检查", "建议", "维修", "诊断", "历史", "预警", "巡检",
    "复发", "再坏", "手册", "规程", "工单",
]


# ── 公开辅助函数（被 compat.py 等引用）───────────────────────

def _has_reference_pronoun(query: str) -> bool:
    return any(re.search(p, query, re.IGNORECASE) for p in _REFERENCE_PATTERNS)


def _has_device_switch(query: str) -> str | None:
    matches: list[str] = []
    for pattern in _SWITCH_PATTERNS:
        matches.extend(re.findall(pattern, query, re.IGNORECASE))
    return matches[-1].upper() if matches else None


def _is_capability_question(query: str) -> bool:
    q = query.lower()
    return any(kw.lower() in q for kw in _CAPABILITY_KEYWORDS)


def _is_global_question(query: str) -> bool:
    return any(kw in query for kw in _GLOBAL_KEYWORDS)


def _is_chat(query: str) -> bool:
    q = query.lower()
    return any(kw.lower() in q for kw in _CHAT_KEYWORDS)


def _looks_like_business_question(query: str) -> bool:
    return bool(_extract_assetnum(query)) or any(kw in query for kw in _BUSINESS_KEYWORDS)


def _is_unsupported(query: str) -> bool:
    return any(kw in query for kw in _UNSUPPORTED_KEYWORDS)


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


# ── 规则化 route 判断 ────────────────────────────────────────────

def _detect_route(
    query: str,
    context_packet: dict[str, Any],
) -> tuple[str, str | None, str | None, str | None, bool, bool]:
    """规则化路由检测。

    Returns:
        (route, business_goal, assetnum, time_window, needs_asset, needs_rag)
    """
    # 1. 闲聊
    if _is_chat(query) and not _looks_like_business_question(query):
        return ("direct_chat", None, None, None, False, False)

    # 2. 能力询问
    if _is_capability_question(query):
        return ("capability_query", None, None, None, False, False)

    # 3. 超出能力
    if _is_unsupported(query):
        return ("unsupported", None, None, None, False, False)

    # 4. 设备切换
    switch = _has_device_switch(query)
    if switch:
        bg = _detect_business_goal(query)
        return ("business_device", bg, switch, _extract_time_window(query), True, "手册" in query or "规程" in query or bg == "manual_search")

    # 5. 全局问题
    if _is_global_question(query):
        if "高风险" in query or "优先" in query or "Top" in query.upper():
            return ("business_global", "high_risk_ranking", None, None, False, False)
        if "概览" in query or "整体" in query or "这批" in query:
            return ("business_global", "data_overview", None, None, False, False)
        return ("business_global", "data_overview", None, None, False, False)

    # 6. 显式设备编号
    assetnum = _extract_assetnum(query)
    if assetnum:
        bg = _detect_business_goal(query)
        return ("business_device", bg, assetnum, _extract_time_window(query), True, "手册" in query or "规程" in query or bg == "manual_search")

    # 7. 指代继承
    active_assetnum = context_packet.get("active_assetnum")
    if _has_reference_pronoun(query) and active_assetnum:
        bg = _detect_business_goal(query)
        return ("business_device", bg, active_assetnum, _extract_time_window(query), True, "手册" in query or "规程" in query)

    # 8. 看起来像业务问题但缺设备编号
    if _looks_like_business_question(query):
        if active_assetnum:
            bg = _detect_business_goal(query)
            return ("business_device", bg, active_assetnum, _extract_time_window(query), True, False)
        return ("needs_clarification", None, None, None, False, False)

    # 9. 兜底 → 闲聊
    return ("direct_chat", None, None, None, False, False)


def _detect_business_goal(query: str) -> str | None:
    """从 query 文本推断 business_goal。"""
    has_risk = any(w in query for w in ["风险", "预测"])
    has_advice = any(w in query for w in ["检查", "建议", "处理", "维修", "先看"])
    has_history = any(w in query for w in ["故障", "历史", "最近", "以前", "出过", "记录"])
    has_warning = any(w in query for w in ["为什么", "预警", "红色", "橙色", "黄色"])
    has_manual = any(w in query for w in ["手册", "规程", "按标准"])

    if has_manual:
        return "manual_search"
    if has_risk and has_advice:
        return "full_diagnosis"
    if has_warning:
        return "device_risk"
    if has_risk:
        return "device_risk"
    if has_history:
        return "device_history"
    if has_advice:
        return "device_advice"
    # 无明确信号 → 完整诊断
    return "full_diagnosis"


# ── Prompt 模板 ───────────────────────────────────────────────────

UNDERSTAND_QUERY_SYSTEM = """你是 AFC 智能运维 Agent 的意图解析器。

你的任务是把用户自然语言问题解析成结构化 JSON。
你只负责解析，不负责回答或诊断。

## 输出格式要求

必须只输出一个合法 JSON 对象，不要加任何解释、markdown 标记或多余文本。

## route 语义（粗粒度路由）

- direct_chat: 闲聊/问候 ("你好""谢谢""早上好")
- capability_query: 询问系统能力 ("你能做什么""支持哪些功能")
- business_global: 全局数据问题 ("数据概览""高风险设备")
- business_device: 单设备业务问题 ("分析设备1000029970")
- needs_clarification: 缺少关键参数（想做业务分析但没有设备编号且无上下文）
- unsupported: 超出系统能力（写论文/天气/电影）

## business_goal 语义（细粒度目标，仅 business_global / business_device 需要）

- data_overview: 数据概览
- high_risk_ranking: 高风险设备排行
- device_risk: 单设备风险查询
- device_history: 单设备历史查询
- device_advice: 单设备维修建议
- full_diagnosis: 单设备完整诊断
- manual_search: 维修手册检索

## 关键规则

1. "你好""谢谢""在吗" → route=direct_chat, business_goal=null, needs_tools=false
2. "你能做什么""你是谁" → route=capability_query, business_goal=null, needs_tools=false
3. "整体情况""工单数据" → route=business_global, business_goal=data_overview
4. "高风险""优先巡检" → route=business_global, business_goal=high_risk_ranking
5. 有设备编号 + "风险" → route=business_device, business_goal=device_risk
6. 有设备编号 + "故障/历史" → route=business_device, business_goal=device_history
7. 有设备编号 + "检查/建议" → route=business_device, business_goal=device_advice
8. 有设备编号 + "分析/诊断/综合" → route=business_device, business_goal=full_diagnosis
9. 有设备编号 + "手册/规程" → route=business_device, business_goal=manual_search, needs_rag=true
10. 业务关键词但无设备编号且上下文无设备 → route=needs_clarification
11. 指代词（它/这个设备/刚才那个）+ 上下文有设备 → 继承设备编号, route=business_device
12. "换成XXX" → 切换设备, route=business_device
13. "什么时候再次故障/什么时候会复发" → route=business_device, business_goal=device_risk
14. "那应该先检查什么"等追问 → 继承设备, business_goal=device_advice
15. 写论文/天气/电影 → route=unsupported
16. 很短的问候、无业务关键词且无设备编号 → route=direct_chat

## 字段一致性要求

- 如果当前用户问题中明确出现设备编号，必须原样填写 assetnum，不允许输出 null。
- 如果 route=business_device，assetnum 必须有值，needs_asset=true，needs_tools=true。
- 如果用户问“未来30天风险高吗/风险/预测/复发”，business_goal 必须是 device_risk，time_window 应填写 30d。
- 如果没有设备编号且上下文也没有 active_assetnum，不能输出 route=business_device，应输出 route=needs_clarification。
- task_type 必须与 route + business_goal 一致，例如 business_device + device_risk → risk_query。"""


def _build_understand_prompt(query: str, context_packet: dict[str, Any]) -> str:
    """构建问题理解 Prompt。"""
    extracted_assetnum = _extract_assetnum(query)
    extracted_time_window = _extract_time_window(query)
    return (
        f"## 上下文信息\n"
        f"- active_assetnum: {context_packet.get('active_assetnum') or 'null'}\n"
        f"- active_task_type: {context_packet.get('active_task_type') or 'null'}\n"
        f"- active_time_window: {context_packet.get('active_time_window') or 'null'}\n"
        f"- conversation_focus: {context_packet.get('conversation_focus') or '无'}\n"
        f"- known_entities: {json.dumps(context_packet.get('known_entities', []), ensure_ascii=False)}\n"
        f"- recent_messages_summary: {context_packet.get('recent_messages_summary') or '无'}\n"
        f"\n## 当前问题中的显式抽取提示\n"
        f"- extracted_assetnum_from_query: {extracted_assetnum or 'null'}\n"
        f"- extracted_time_window_from_query: {extracted_time_window or 'null'}\n"
        f"- 注意：如果 extracted_assetnum_from_query 不为 null，输出 JSON 的 assetnum 必须等于该值。\n"
        f"\n## 当前用户问题\n{query}\n"
        f"\n请输出 QueryUnderstanding JSON（只输出 JSON，必须包含 route 和 business_goal 字段）："
    )


def _rule_based_understanding(
    query: str, context_packet: dict[str, Any]
) -> dict[str, Any]:
    """当 LLM 不可用时的规则兜底 — v0.3.0 升级版。"""
    route, business_goal, assetnum, time_window, needs_asset, needs_rag = _detect_route(query, context_packet)

    needs_tools = route in ("business_global", "business_device")
    task_type = route_to_task_type(route, business_goal)
    context_used = False

    # 后处理：指代继承
    active_assetnum = context_packet.get("active_assetnum")
    if _has_reference_pronoun(query) and active_assetnum and not assetnum:
        assetnum = active_assetnum
        route = "business_device"
        business_goal = business_goal or _detect_business_goal(query)
        needs_asset = True
        needs_tools = True
        task_type = route_to_task_type(route, business_goal)
        context_used = True

    # 设备切换
    switch = _has_device_switch(query)
    if switch:
        assetnum = switch
        route = "business_device"
        business_goal = business_goal or _detect_business_goal(query)
        needs_asset = True
        needs_tools = True
        task_type = route_to_task_type(route, business_goal)
        context_used = True

    # confidence 赋值
    confidence_map = {
        "direct_chat": 0.95,
        "capability_query": 0.9,
        "business_global": 0.9,
        "business_device": 0.85,
        "needs_clarification": 0.8,
        "unsupported": 0.9,
    }
    confidence = confidence_map.get(route, 0.7)

    # information_need 生成
    info_need_map = {
        "direct_chat": "用户闲聊/问候",
        "capability_query": "用户询问系统能力",
        "business_global": f"用户询问全局数据：{business_goal}",
        "business_device": f"用户询问设备 {assetnum} 的 {business_goal}",
        "needs_clarification": "用户想做业务分析但缺少设备编号",
        "unsupported": "用户问题超出系统能力范围",
    }

    return QueryUnderstanding(
        route=route,
        business_goal=business_goal,
        task_type=task_type,
        assetnum=assetnum,
        time_window=time_window,
        needs_asset=needs_asset,
        needs_tools=needs_tools,
        needs_rag=needs_rag,
        context_used=context_used,
        information_need=info_need_map.get(route, "无法判断用户意图"),
        user_question_rewrite=query,
        confidence=confidence,
    ).model_dump()


# ── 节点入口 ──────────────────────────────────────────────────────

def understand_query_node(state: AfcAgentState) -> dict[str, Any]:
    """理解用户问题并输出结构化 QueryUnderstanding。

    输入：query, context_packet
    输出：query_understanding（含 route + business_goal + task_type）
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
            repair_context=(
                f"当前用户问题: {query}\n"
                f"显式设备编号: {_extract_assetnum(query) or 'null'}\n"
                f"显式时间窗口: {_extract_time_window(query) or 'null'}\n"
                f"上下文: {json.dumps(context_packet, ensure_ascii=False, default=str)}"
            ),
        )
        understanding = result.model_dump()

        # LLM 后处理：确保 route 和 business_goal 合理
        _post_process_llm_understanding(understanding, query, context_packet)
    except Exception as exc:
        errors.append(f"LLM 问题理解不可用，使用规则兜底：{str(exc)}")

    # 规则兜底
    if understanding is None:
        understanding = _rule_based_understanding(query, context_packet)

    # 最终后处理：指代继承和设备切换
    active_assetnum = context_packet.get("active_assetnum")
    if (
        active_assetnum
        and not understanding.get("assetnum")
        and _has_reference_pronoun(query)
    ):
        understanding["assetnum"] = active_assetnum
        understanding["context_used"] = True
        understanding["needs_asset"] = True
        if understanding.get("route") in ("needs_clarification", "direct_chat", None):
            understanding["route"] = "business_device"
            understanding["business_goal"] = understanding.get("business_goal") or _detect_business_goal(query)
            understanding["needs_tools"] = True
            understanding["task_type"] = route_to_task_type(
                understanding["route"], understanding["business_goal"]
            )

    switch = _has_device_switch(query)
    if switch:
        understanding["assetnum"] = switch
        understanding["route"] = "business_device"
        understanding["needs_tools"] = True
        understanding["task_type"] = route_to_task_type(
            understanding["route"], understanding.get("business_goal")
        )

    # 确保 task_type 与 route 一致
    if not understanding.get("task_type") or understanding.get("task_type") == "unknown":
        understanding["task_type"] = route_to_task_type(
            understanding.get("route", "direct_chat"),
            understanding.get("business_goal"),
        )

    return {
        "query_understanding": understanding,
        "errors": errors,
    }


def _post_process_llm_understanding(
    understanding: dict[str, Any],
    query: str,
    context_packet: dict[str, Any],
) -> None:
    """对 LLM 输出的 understanding 做安全后处理。"""
    route = understanding.get("route", "direct_chat")

    # 如果 route=unknown 但看起来像闲聊，修正
    if route == "unsupported" and (_is_chat(query) or _is_capability_question(query)):
        understanding["route"] = "direct_chat" if _is_chat(query) else "capability_query"
        understanding["needs_tools"] = False
        understanding["needs_asset"] = False
        understanding["business_goal"] = None
        route = understanding["route"]

    # 如果 route 是 direct_chat 但 extract 出了设备编号，可能是误判
    if route == "direct_chat" and _extract_assetnum(query):
        understanding["route"] = "business_device"
        understanding["business_goal"] = _detect_business_goal(query)
        understanding["needs_tools"] = True
        understanding["needs_asset"] = True
        route = "business_device"

    # 短业务问题（如“风险分析”“故障建议”）不能被 LLM 误归为闲聊。
    if route == "direct_chat" and _looks_like_business_question(query):
        active_assetnum = context_packet.get("active_assetnum")
        understanding["route"] = "business_device" if active_assetnum or _extract_assetnum(query) else "needs_clarification"
        understanding["business_goal"] = _detect_business_goal(query)
        understanding["assetnum"] = understanding.get("assetnum") or _extract_assetnum(query) or active_assetnum
        understanding["needs_asset"] = understanding["route"] == "business_device"
        understanding["needs_tools"] = understanding["route"] == "business_device"
        understanding["context_used"] = bool(active_assetnum and understanding.get("assetnum") == active_assetnum)
        route = understanding["route"]

    # 确保非业务 route 的 needs_tools=false
    route = understanding.get("route", route)
    if route in ("direct_chat", "capability_query", "needs_clarification", "unsupported"):
        understanding["needs_tools"] = False

    # 确保有设备编号时 needs_asset=true
    route = understanding.get("route", route)
    if understanding.get("assetnum") and route == "business_device":
        understanding["needs_asset"] = True

    understanding["task_type"] = route_to_task_type(
        understanding.get("route", route),
        understanding.get("business_goal"),
    )
