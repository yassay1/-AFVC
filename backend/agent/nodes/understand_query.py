"""理解用户问题；仅产出语义路由，不决定工具。"""
from __future__ import annotations

import json
import re
from typing import Any

from backend.agent.llm_json import call_llm_json
from backend.agent.schemas import QueryUnderstanding
from backend.agent.state import AfcAgentState
from backend.core.llm import get_parse_llm

_CHAT_KEYWORDS = ("你好", "您好", "hello", "hi", "嗨", "在吗", "谢谢", "再见")
_CAPABILITY_KEYWORDS = ("你会干什么", "你能做什么", "有什么功能", "功能介绍", "使用说明", "怎么用", "帮助", "help")
_GLOBAL_KEYWORDS = ("整体情况", "概览", "这批工单", "工单数据", "高风险设备", "优先巡检", "巡检重点", "当前高风险")
_UNSUPPORTED_KEYWORDS = ("写论文", "天气", "推荐电影", "推荐音乐", "点外卖", "翻译", "写代码", "炒股")
_REFERENCE_PHRASES = ("那它", "它", "这个设备", "该设备", "刚才那个", "刚才那台", "这台", "那台", "那应该")
_BUSINESS_KEYWORDS = ("分析", "风险", "故障", "检查", "建议", "维修", "诊断", "历史", "预警", "巡检", "复发", "再坏", "手册", "规程", "工单")
_EXPLANATION_KEYWORDS = ("一般怎么", "原理", "什么意思", "怎么理解", "为什么不代表", "风险模型", "概率怎么解释", "可信度怎么看")
_OPEN_CONNECTORS = ("比较", "矛盾", "原因", "综合", "结合", "最值得关注", "为什么")
_SWITCH_PATTERNS = (r"换成\s*([A-Za-z0-9]{3,})", r"换到\s*([A-Za-z0-9]{3,})", r"切换(?:到|成)?\s*(?:设备\s*)?([A-Za-z0-9]{3,})", r"再看(?:一下)?\s*(?:设备\s*)?([A-Za-z0-9]{3,})")

def _contains_any(q: str, phrases: tuple[str, ...]) -> bool: return any(x in q for x in phrases)
def _has_reference_pronoun(q: str) -> bool: return _contains_any(q, _REFERENCE_PHRASES)
def _has_device_switch(q: str) -> str | None:
    values = [x for p in _SWITCH_PATTERNS for x in re.findall(p, q, re.I)]
    return values[-1].upper() if values else None
def _extract_assetnum(q: str) -> str | None:
    values = [x for p in (r"设备\s*([A-Za-z0-9]{3,})", r"([A-Z]{2,}\d{5,})", r"(\d{10,})") for x in re.findall(p, q)]
    return values[-1].upper() if values else None
def _extract_time_window(q: str) -> str | None:
    for keys, value in [(("7天","七天","一周","1周"),"7d"),(("14天","两周","二周"),"14d"),(("21天","三周"),"21d"),(("30天","一个月","一月","未来一个月"),"30d"),(("60天","两个月","二个月"),"60d"),(("90天","三个月"),"90d")]:
        if any(k in q for k in keys): return value
    return None
def _is_chat(q: str) -> bool: return _contains_any(q, _CHAT_KEYWORDS) or q.lower() in {"hello","hi"}
def _is_capability_question(q: str) -> bool: return _contains_any(q, _CAPABILITY_KEYWORDS) or "help" in q.lower()
def _is_global_question(q: str) -> bool: return _contains_any(q, _GLOBAL_KEYWORDS)
def _is_unsupported(q: str) -> bool: return _contains_any(q, _UNSUPPORTED_KEYWORDS) or ("推荐" in q and "电影" in q)
def _looks_like_business_question(q: str) -> bool: return bool(_extract_assetnum(q)) or _contains_any(q, _BUSINESS_KEYWORDS)
def _is_general_explanation(q: str) -> bool: return _contains_any(q, _EXPLANATION_KEYWORDS) or ("风险" in q and "不代表" in q)
def _is_open_analysis(q: str) -> bool:
    dimensions = sum(bool(_contains_any(q, keys)) for keys in (("风险","预警","概率"),("历史","记录","工单"),("维修","建议","巡检"),("手册","规程")))
    return dimensions >= 2 or (dimensions >= 1 and _contains_any(q, _OPEN_CONNECTORS))

def _detect_business_goal(q: str) -> str | None:
    if _contains_any(q, ("手册","规程","标准")): return "manual_search"
    if _is_open_analysis(q): return "open_analysis"
    if _contains_any(q, ("会发生什么故障","可能出现什么错误","下次可能坏哪里","最可能出现什么问题","未来可能报什么错","哪个模块最可能故障","最可能发生什么","什么故障","哪种故障","哪类故障","故障类型","故障类别","哪个模块")): return "fault_type_prediction"
    risk = _contains_any(q, ("风险","预测","复发","再坏","再次故障","什么时候"))
    advice = _contains_any(q, ("检查","建议","处理","维修","先看","先检查"))
    if risk and advice: return "full_diagnosis"
    if _contains_any(q, ("为什么","预警","红色","橙色","黄色")) or risk: return "device_risk"
    if _contains_any(q, ("历史","最近","以前","出过","记录","工单")): return "device_history"
    if advice: return "device_advice"
    return "full_diagnosis"

def _detect_route(q: str, ctx: dict[str, Any]):
    if _is_chat(q) and not _looks_like_business_question(q): return "direct_chat",None,None,None,False
    if _is_capability_question(q): return "capability_query",None,None,None,False
    if _is_unsupported(q): return "unsupported",None,None,None,False
    if _is_general_explanation(q) and not _extract_assetnum(q): return "conversation","general_explanation",None,None,False
    if _is_global_question(q): return "business_global",("high_risk_ranking" if "高风险" in q or "优先" in q else "data_overview"),None,None,False
    asset = _has_device_switch(q) or _extract_assetnum(q)
    if not asset and _has_reference_pronoun(q): asset = ctx.get("active_assetnum")
    if not asset and ctx.get("active_assetnum") and _looks_like_business_question(q): asset = ctx["active_assetnum"]
    if asset: return "business_device",_detect_business_goal(q),asset,_extract_time_window(q),True
    if _looks_like_business_question(q): return "needs_clarification",None,None,None,False
    return "direct_chat",None,None,None,False

UNDERSTAND_QUERY_SYSTEM = """你是 AFC 智能运维 Agent 的需求理解器。你只负责理解用户需求，不负责选择工具，也不得输出 needs_tools 或 needs_rag。必须区分普通闲聊、能力询问、AFC 一般解释、固定业务查询、开放组合分析、缺参数和越界任务。最终只能输出一个符合 QueryUnderstanding 的根 JSON object。禁止输出 JSON array、input/output 包装、Markdown 代码块、解释文字或任何额外字段。一般原理或概率解释属于 conversation/general_explanation；同时结合风险、历史、维修等多维证据且有设备编号的问题属于 business_device/open_analysis。"""

def _build_understand_prompt(q: str, ctx: dict[str, Any]) -> str:
    example_general = {
        "route": "conversation", "business_goal": "general_explanation",
        "assetnum": None, "time_window": None, "needs_asset": False,
        "context_used": False, "information_need": "解释风险概率与确定性故障之间的区别",
        "user_question_rewrite": "解释风险高为什么不代表设备一定发生故障", "confidence": 0.95,
    }
    example_open = {
        "route": "business_device", "business_goal": "open_analysis",
        "assetnum": "1000029970", "time_window": None, "needs_asset": True,
        "context_used": False, "information_need": "结合风险预测和历史工单解释两者是否矛盾",
        "user_question_rewrite": "综合设备风险和历史维修记录进行解释", "confidence": 0.93,
    }
    example_ranking = {
        "route": "business_global", "business_goal": "high_risk_ranking",
        "assetnum": None, "time_window": None, "needs_asset": False,
        "context_used": False, "information_need": "查询当前高风险设备",
        "user_question_rewrite": "查询当前高风险设备排行", "confidence": 0.95,
    }
    skeleton = {
        "route": "business_global", "business_goal": "high_risk_ranking",
        "assetnum": None, "time_window": None, "needs_asset": False,
        "context_used": False, "information_need": "用中文描述信息需求",
        "user_question_rewrite": "用中文重写用户问题", "confidence": 0.95,
    }
    return (
        "你需要把用户问题转换为 QueryUnderstanding。\n\n"
        "Route 合法值（只能选择其中一个）：\n"
        "direct_chat, capability_query, conversation, business_global, business_device, "
        "needs_clarification, unsupported\n\n"
        "BusinessGoal 合法值（只能选择其中一个或 null）：\n"
        "data_overview, high_risk_ranking, device_risk, device_history, device_advice, "
        "fault_type_prediction, full_diagnosis, manual_search, general_explanation, "
        "open_analysis, null\n\n"
        "关键配对规则：\n"
        "- data_overview 和 high_risk_ranking 必须使用 business_global。\n"
        "- general_explanation 必须使用 conversation。\n"
        "- open_analysis 必须使用 business_device，并提供 assetnum。\n"
        "- direct_chat、capability_query、unsupported 的 business_goal 必须为 null。\n\n"
        "以下示例使用普通文本分段。示例标题和用户问题不是输出字段，最终不得返回 input、output、输入或输出包装。\n\n"
        "示例一\n用户问题：为什么风险高不代表一定会故障？\n正确根 JSON object：\n"
        f"{json.dumps(example_general, ensure_ascii=False, indent=2)}\n\n"
        "示例二\n用户问题：为什么设备 1000029970 风险高，但最近维修记录很少？\n正确根 JSON object：\n"
        f"{json.dumps(example_open, ensure_ascii=False, indent=2)}\n\n"
        "示例三\n用户问题：当前高风险设备有哪些\n正确根 JSON object：\n"
        f"{json.dumps(example_ranking, ensure_ascii=False, indent=2)}\n\n"
        f"当前上下文：\n{json.dumps(ctx, ensure_ascii=False, default=str)}\n\n"
        f"当前用户问题：\n{q}\n\n"
        "输出限制：最终只能返回下面形状的一个根 JSON object；禁止 JSON array，禁止 input/output 包装，"
        "禁止 Markdown 代码块，禁止解释文字，禁止额外字段。字段名和枚举值保持英文。\n\n"
        "QueryUnderstanding JSON 骨架（最终按用户问题填写）：\n"
        f"{json.dumps(skeleton, ensure_ascii=False, indent=2)}"
    )

def _rule_based_understanding(q: str, ctx: dict[str, Any]) -> dict[str, Any]:
    route, goal, asset, window, needs_asset = _detect_route(q, ctx)
    return QueryUnderstanding(route=route,business_goal=goal,assetnum=asset,time_window=window,needs_asset=needs_asset,context_used=bool(asset and asset==ctx.get("active_assetnum")),information_need=f"{route}: {goal or q}",user_question_rewrite=q,confidence=.9).model_dump()

def _post_process_llm_understanding(data: dict[str, Any], q: str, ctx: dict[str, Any]) -> dict[str, Any]:
    rule = _rule_based_understanding(q, ctx)
    if _is_general_explanation(q) and not _extract_assetnum(q): return rule
    explicit = _has_device_switch(q) or _extract_assetnum(q)
    if explicit:
        data.update(assetnum=explicit, route="business_device", needs_asset=True)
        if _is_open_analysis(q): data["business_goal"]="open_analysis"
    elif _has_reference_pronoun(q) and ctx.get("active_assetnum"):
        data.update(assetnum=ctx["active_assetnum"], route="business_device", needs_asset=True, context_used=True)
        if _is_open_analysis(q): data["business_goal"]="open_analysis"
    return QueryUnderstanding.model_validate(data).model_dump()

def understand_query_node(state: AfcAgentState) -> dict[str, Any]:
    q=state.get("query","").strip(); ctx=state.get("context_packet",{}); errors=list(state.get("errors",[]))
    try:
        prompt=_build_understand_prompt(q,ctx)
        result=call_llm_json(llm=get_parse_llm(),prompt=prompt,schema=QueryUnderstanding,system_prompt=UNDERSTAND_QUERY_SYSTEM,max_repair_attempts=2,repair_context=prompt)
        understanding=_post_process_llm_understanding(result.model_dump(),q,ctx)
    except Exception as exc:
        errors.append(f"LLM 问题理解不可用，使用规则兜底：{exc}")
        understanding=_rule_based_understanding(q,ctx)
    return {"query_understanding":understanding,"errors":errors}
