"""LangGraph 三节点混合型诊断 Agent。

节点职责：
1. parse_intent_node：结构化理解用户问题，完成多轮指代和输入校验。
2. reason_act_node：选择并调用白名单工具，生成可追踪证据。
3. generate_report_node：按场景生成最终回答，LLM 优先、模板兜底。
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from backend.agent.report_builder import (
    build_advice_report,
    build_capability_report,
    build_data_overview_report,
    build_device_error_report,
    build_full_diagnosis_report,
    build_high_risk_report,
    build_history_report,
    build_risk_advice_report,
    build_risk_explanation_report,
    build_risk_report,
)
from backend.agent.state import AfcAgentState
from backend.agent.tools import ALL_TOOLS, TOOL_BY_NAME
from backend.core.llm import get_parse_llm, get_report_llm


TASK_TYPES = {
    "capability_query",
    "data_overview",
    "high_risk_ranking",
    "full_diagnosis",
    "risk_query",
    "history_query",
    "advice_query",
    "risk_explanation",
    "risk_and_advice_query",
}

NO_DEVICE_TASKS = {"capability_query", "data_overview", "high_risk_ranking"}

TASK_TOOL_MAP: dict[str, list[str]] = {
    "capability_query": [],
    "data_overview": ["get_data_summary_tool"],
    "high_risk_ranking": ["get_high_risk_devices_tool"],
    "full_diagnosis": ["get_integrated_analysis_tool"],
    "risk_query": ["predict_device_risk_tool"],
    "history_query": ["get_device_history_tool"],
    "advice_query": ["get_maintenance_advice_tool"],
    "risk_explanation": ["predict_device_risk_tool"],
    "risk_and_advice_query": ["predict_device_risk_tool", "get_maintenance_advice_tool"],
}

MAX_TOOL_CALLS = 5

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

_GLOBAL_QUESTION_KEYWORDS = [
    "整体情况", "概览", "这批工单", "数据怎么样", "工单数据",
    "高风险设备", "优先巡检", "巡检重点", "当前高风险",
    "有哪些高风险", "今天优先",
]

_CAPABILITY_KEYWORDS = [
    "你会干什么", "你是谁", "怎么用", "有什么功能",
    "你能做什么", "你能干什么", "功能介绍", "使用说明",
    "你能干嘛", "你会什么", "能做什么", "帮助", "help",
    "你好", "嗨", "hello", "hi",
]


class IntentParseResult(BaseModel):
    """LLM structured output 的解析结果。"""

    intent: Literal[
        "capability_query",
        "data_overview",
        "high_risk_ranking",
        "full_diagnosis",
        "risk_query",
        "history_query",
        "advice_query",
        "risk_explanation",
        "risk_and_advice_query",
    ] = Field(description="用户意图类型")
    assetnum: str | None = Field(default=None, description="AFC 设备编号")
    time_window: str | None = Field(default=None, description="7d/14d/21d/30d/60d/90d 或 null")
    requires_asset: bool = Field(description="该问题是否必须有设备编号")
    is_global: bool = Field(description="是否是全局问题")
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


def _has_reference_pronoun(query: str) -> bool:
    return any(re.search(pattern, query, flags=re.IGNORECASE) for pattern in _REFERENCE_PATTERNS)


def _has_device_switch(query: str) -> str | None:
    matches: list[str] = []
    for pattern in _SWITCH_PATTERNS:
        matches.extend(re.findall(pattern, query, flags=re.IGNORECASE))
    return matches[-1].upper() if matches else None


def _is_capability_question(query: str) -> bool:
    q = query.lower()
    return any(kw.lower() in q for kw in _CAPABILITY_KEYWORDS)


def _is_global_question(query: str) -> bool:
    return any(kw in query for kw in _GLOBAL_QUESTION_KEYWORDS)


def _extract_assetnum_from_query(query: str) -> str | None:
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
        if any(keyword in query for keyword in keywords):
            return value
    return None


def _rule_based_parse_task_type(query: str) -> str:
    if _is_capability_question(query):
        return "capability_query"
    if any(w in query for w in ["整体", "概览", "这批", "数据怎么样", "工单数据"]):
        return "data_overview"
    if any(w in query for w in ["高风险", "优先巡检", "巡检重点", "优先"]):
        return "high_risk_ranking"
    has_risk = any(w in query for w in ["风险", "预测"])
    has_advice = any(w in query for w in ["检查", "建议", "处理", "维修", "先看"])
    if has_risk and has_advice:
        return "risk_and_advice_query"
    if any(w in query for w in ["为什么", "预警", "红色", "橙色", "黄色"]):
        return "risk_explanation"
    if has_risk:
        return "risk_query"
    if has_advice:
        return "advice_query"
    if any(w in query for w in ["历史", "故障", "记录", "以前", "最近有哪些"]):
        return "history_query"
    return "full_diagnosis"


def _resolve_multiturn_context(
    query: str,
    last_assetnum: str | None,
    last_task_type: str | None,
    last_time_window: str | None,
) -> tuple[str | None, str | None, str | None, str]:
    switch_device = _has_device_switch(query)
    if switch_device:
        task_type = _rule_based_parse_task_type(query)
        if task_type == "full_diagnosis" and last_task_type not in NO_DEVICE_TASKS:
            task_type = last_task_type or "full_diagnosis"
        hint = f"用户从上一轮设备 {last_assetnum} 切换到新设备 {switch_device}"
        return switch_device, task_type, _extract_time_window(query) or last_time_window, hint

    if _is_global_question(query) or _is_capability_question(query):
        return None, None, None, ""

    explicit_asset = _extract_assetnum_from_query(query)
    if explicit_asset:
        return explicit_asset, None, _extract_time_window(query), ""

    if _has_reference_pronoun(query) and last_assetnum:
        task_type = _rule_based_parse_task_type(query)
        time_window = _extract_time_window(query) or last_time_window
        hint = f"用户使用指代词，自动继承上一轮设备 {last_assetnum}"
        return last_assetnum, task_type, time_window, hint

    return None, None, _extract_time_window(query), ""


def _normalize_intent(raw: dict[str, Any], query: str) -> dict[str, Any]:
    task_type = raw.get("intent") or raw.get("task_type") or "full_diagnosis"
    if task_type not in TASK_TYPES:
        task_type = _rule_based_parse_task_type(query)

    assetnum = raw.get("assetnum")
    if assetnum:
        assetnum = str(assetnum).strip().upper()
        if assetnum in {"NULL", "NONE", "无"}:
            assetnum = None

    time_window = raw.get("time_window") or _extract_time_window(query)
    requires_asset = task_type not in NO_DEVICE_TASKS
    is_global = task_type in {"data_overview", "high_risk_ranking"}

    return {
        "intent": task_type,
        "assetnum": assetnum,
        "time_window": time_window,
        "requires_asset": requires_asset,
        "is_global": is_global,
        "confidence": float(raw.get("confidence", 0.7) or 0.7),
    }


def _rule_parse_intent(query: str) -> dict[str, Any]:
    task_type = _rule_based_parse_task_type(query)
    return _normalize_intent(
        {
            "intent": task_type,
            "assetnum": _extract_assetnum_from_query(query),
            "time_window": _extract_time_window(query),
            "confidence": 0.65,
        },
        query,
    )


def _format_recent_messages(messages: list[Any], limit: int = 6) -> str:
    formatted: list[str] = []
    for message in messages[-limit:]:
        role = message.__class__.__name__.replace("Message", "")
        content = getattr(message, "content", str(message))
        text = str(content).replace("\n", " ").strip()
        if len(text) > 300:
            text = text[:300] + "..."
        formatted.append(f"{role}: {text}")
    return "\n".join(formatted) if formatted else "无"


def parse_intent_node(state: AfcAgentState) -> dict[str, Any]:
    """理解用户问题并输出经过校验的结构化意图。"""
    query = state["query"].strip()
    errors: list[str] = []
    last_assetnum = state.get("last_assetnum")
    last_task_type = state.get("last_task_type")
    last_time_window = state.get("last_time_window")
    recent_messages = _format_recent_messages(state.get("messages", []))

    resolved_asset, resolved_task, resolved_time, hint = _resolve_multiturn_context(
        query, last_assetnum, last_task_type, last_time_window
    )

    # 明显问题规则优先，避免能力/全局问题误入设备诊断。
    if _is_capability_question(query) or _is_global_question(query):
        parsed = _rule_parse_intent(query)
    else:
        try:
            llm = get_parse_llm()
            structured_llm = llm.with_structured_output(IntentParseResult)
            prompt = (
                "你是 AFC 智能运维 Agent 的意图解析器。"
                "必须只输出一个合法 JSON 对象，不允许输出解释性自然语言、Markdown 或多余文本。"
                "输出必须符合 IntentParseResult 结构。"
                "JSON 字段只能包含：intent, assetnum, time_window, requires_asset, is_global, confidence。"
                "intent 只能是 capability_query, data_overview, high_risk_ranking, full_diagnosis, "
                "risk_query, history_query, advice_query, risk_explanation, risk_and_advice_query。"
                "如果当前问题没有设备编号，但它是对上一轮设备的追问，请继承 last_assetnum。"
                "“什么时候再次故障 / 什么时候会复发 / 多久可能再坏 / 大约什么时候会再次故障”归类为 risk_query。"
                "能力询问、数据概览、高风险设备不需要设备编号；设备诊断、风险、历史、建议和预警解释需要设备编号。"
                f"\n\n上下文："
                f"\nlast_assetnum: {last_assetnum or 'null'}"
                f"\nlast_task_type: {last_task_type or 'null'}"
                f"\nlast_time_window: {last_time_window or 'null'}"
                f"\ncontext_hint: {hint or '无'}"
                f"\n最近对话：\n{recent_messages}"
                f"\n\n当前用户问题：{query}"
                "\n\n只输出 JSON。"
            )
            result = structured_llm.invoke([HumanMessage(content=prompt)])
            parsed = _normalize_intent(
                result.model_dump() if hasattr(result, "model_dump") else dict(result),
                query,
            )
        except Exception as exc:
            parsed = _rule_parse_intent(query)
            errors.append(f"LLM 解析不可用，已使用规则兜底解析：{str(exc)}")

    if resolved_asset:
        parsed["assetnum"] = resolved_asset
        errors.append(f"多轮上下文补全：自动关联设备 {resolved_asset}")
    if resolved_task:
        parsed["intent"] = resolved_task
        parsed["requires_asset"] = resolved_task not in NO_DEVICE_TASKS
        parsed["is_global"] = resolved_task in {"data_overview", "high_risk_ranking"}
    if resolved_time and not parsed.get("time_window"):
        parsed["time_window"] = resolved_time

    parsed = _normalize_intent(parsed, query)

    return {
        "intent": parsed,
        "assetnum": parsed["assetnum"],
        "task_type": parsed["intent"],
        "time_window": parsed["time_window"],
        "requires_asset": parsed["requires_asset"],
        "is_global": parsed["is_global"],
        "errors": errors,
    }


def _invoke_tool(tool_name: str, assetnum: str | None, tool_args: dict[str, Any] | None = None) -> dict[str, Any]:
    tool = TOOL_BY_NAME[tool_name]
    args = dict(tool_args or {})

    if tool_name == "get_data_summary_tool":
        args.setdefault("top_n", 10)
    elif tool_name == "get_high_risk_devices_tool":
        args.setdefault("top_n", 10)
    elif tool_name == "list_devices_tool":
        args = {}
    elif tool_name == "get_device_history_tool":
        args.setdefault("assetnum", assetnum)
        args.setdefault("limit", 50)
    elif tool_name == "get_integrated_analysis_tool":
        args.setdefault("assetnum", assetnum)
        args.setdefault("history_limit", 50)
    elif tool_name in {"predict_device_risk_tool", "get_maintenance_advice_tool"}:
        args.setdefault("assetnum", assetnum)

    return tool.invoke(args)


def _device_exists(assetnum: str) -> tuple[bool, dict[str, Any]]:
    result = _invoke_tool("list_devices_tool", None)
    devices = result.get("devices", []) if isinstance(result, dict) else []
    device_ids = {str(item.get("assetnum", "")).strip().upper() for item in devices}
    return assetnum.strip().upper() in device_ids, result


def _select_tools_with_llm(state: AfcAgentState) -> list[tuple[str, dict[str, Any]]]:
    """让 LLM 基于工具描述选择工具。失败或无工具调用时抛异常给兜底。"""
    task_type = state.get("task_type", "full_diagnosis")
    if task_type == "capability_query":
        return []

    llm = get_parse_llm()
    llm_with_tools = llm.bind_tools(ALL_TOOLS)
    assetnum = state.get("assetnum")
    prompt = (
        "你是 AFC 运维诊断 Agent 的工具调度器。"
        "只能调用提供的工具，最多选择必要工具，不要回答用户。"
        "全局概览只调用数据概览工具；高风险清单只调用高风险设备工具；"
        "设备完整诊断优先调用综合分析工具；风险+建议问题需要风险和建议工具。"
        f"\n用户问题：{state['query']}"
        f"\n解析意图：{json.dumps(state.get('intent', {}), ensure_ascii=False)}"
        f"\n当前设备：{assetnum or '无'}"
    )
    response = llm_with_tools.invoke([HumanMessage(content=prompt)])
    tool_calls = getattr(response, "tool_calls", None) or []
    selected: list[tuple[str, dict[str, Any]]] = []
    for call in tool_calls[:MAX_TOOL_CALLS]:
        name = call.get("name")
        args = call.get("args") or {}
        if name in TOOL_BY_NAME:
            selected.append((name, args))
    if not selected and task_type != "capability_query":
        raise RuntimeError("LLM 未返回有效 tool_calls")
    return selected


def _select_tools_by_rule(state: AfcAgentState) -> list[tuple[str, dict[str, Any]]]:
    task_type = state.get("task_type", "full_diagnosis")
    return [(name, {}) for name in TASK_TOOL_MAP.get(task_type, ["get_integrated_analysis_tool"])]


def _merge_evidence(
    assetnum: str | None,
    selected_tools: list[str],
    tool_results: dict[str, Any],
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "assetnum": assetnum,
        "device_info": {},
        "history_summary": {},
        "risk_prediction": {},
        "warning_result": {},
        "maintenance_advice": {},
        "data_overview": {},
        "high_risk_devices": {},
        "sources": selected_tools,
    }

    integrated = tool_results.get("get_integrated_analysis_tool", {})
    if isinstance(integrated, dict) and integrated.get("status") == "success":
        evidence["device_info"] = integrated.get("device_profile", {})
        evidence["history_summary"] = integrated.get("history_summary", {})
        evidence["risk_prediction"] = integrated.get("risk_prediction", {})
        evidence["warning_result"] = {
            "warning_level": integrated.get("risk_prediction", {}).get("warning_level"),
            "suggested_inspection_window": integrated.get("risk_prediction", {}).get("suggested_inspection_window"),
            "warning_reason": integrated.get("risk_prediction", {}).get("warning_reason"),
        }
        evidence["maintenance_advice"] = integrated.get("maintenance_advice", {})

    history = tool_results.get("get_device_history_tool", {})
    if isinstance(history, dict) and history.get("status") == "success":
        evidence["history_summary"]["raw"] = history

    risk = tool_results.get("predict_device_risk_tool", {})
    if isinstance(risk, dict) and risk.get("status") == "success":
        evidence["risk_prediction"] = risk
        evidence["device_info"] = {
            "assetnum": risk.get("assetnum"),
            "station_name": risk.get("station_name"),
            "line": risk.get("line"),
            "brand": risk.get("brand"),
            "subsystem": risk.get("subsystem"),
        }
        evidence["warning_result"] = {
            "warning_level": risk.get("warning_level"),
            "suggested_inspection_window": risk.get("suggested_inspection_window"),
            "warning_reason": risk.get("warning_reason"),
        }

    advice = tool_results.get("get_maintenance_advice_tool", {})
    if isinstance(advice, dict) and advice.get("status") == "success":
        evidence["maintenance_advice"] = advice
        if not evidence["device_info"]:
            evidence["device_info"] = {
                "assetnum": advice.get("assetnum"),
                "station_name": advice.get("station_name"),
                "line": advice.get("line"),
                "brand": advice.get("brand"),
                "subsystem": advice.get("subsystem"),
            }

    if "get_data_summary_tool" in tool_results:
        evidence["data_overview"] = tool_results["get_data_summary_tool"]
    if "get_high_risk_devices_tool" in tool_results:
        evidence["high_risk_devices"] = tool_results["get_high_risk_devices_tool"]

    return evidence


def reason_act_node(state: AfcAgentState) -> dict[str, Any]:
    """校验上下文、选择工具、执行工具，并标准化证据。"""
    assetnum = state.get("assetnum")
    task_type = state.get("task_type", "full_diagnosis")
    requires_asset = state.get("requires_asset", task_type not in NO_DEVICE_TASKS)
    errors: list[str] = list(state.get("errors", []))
    selected_tools: list[str] = []
    tool_results: dict[str, Any] = {}
    tool_trace: list[dict[str, Any]] = []

    if task_type == "capability_query":
        return {
            "asset_exists": True,
            "selected_tools": [],
            "tool_results": {},
            "tool_trace": [],
            "evidence": {"sources": [], "assetnum": None},
            "errors": errors,
        }

    if requires_asset and not assetnum:
        errors.append("未从问题中识别到设备编号，请提供设备编号")
        return {
            "asset_exists": False,
            "selected_tools": [],
            "tool_results": {},
            "tool_trace": [],
            "evidence": {"sources": [], "assetnum": None},
            "errors": errors,
        }

    if requires_asset and assetnum:
        try:
            exists, list_result = _device_exists(assetnum)
            tool_trace.append({"tool": "list_devices_tool", "status": list_result.get("status", "unknown"), "purpose": "asset_validation"})
            if not exists:
                errors.append(f"设备编号 {assetnum} 在当前工单数据中不存在")
                return {
                    "asset_exists": False,
                    "selected_tools": [],
                    "tool_results": {},
                    "tool_trace": tool_trace,
                    "evidence": {"sources": [], "assetnum": assetnum},
                    "errors": errors,
                }
        except Exception as exc:
            errors.append(f"设备校验异常（已宽松处理）：{str(exc)}")

    try:
        selected = _select_tools_with_llm(state)
    except Exception as exc:
        selected = _select_tools_by_rule(state)
        errors.append(f"LLM 工具选择不可用，已使用规则兜底工具选择：{str(exc)}")

    for tool_name, args in selected[:MAX_TOOL_CALLS]:
        if tool_name not in TOOL_BY_NAME:
            errors.append(f"工具 {tool_name} 未注册或不在白名单中")
            continue
        if tool_name in selected_tools:
            continue
        try:
            result = _invoke_tool(tool_name, assetnum, args)
            selected_tools.append(tool_name)
            tool_results[tool_name] = result
            tool_trace.append({
                "tool": tool_name,
                "args": args,
                "status": result.get("status", "success") if isinstance(result, dict) else "success",
            })
        except Exception as exc:
            selected_tools.append(tool_name)
            message = str(exc)
            tool_results[tool_name] = {"status": "error", "message": message}
            tool_trace.append({"tool": tool_name, "args": args, "status": "error", "message": message})
            errors.append(f"工具 {tool_name} 调用失败：{message}")

    evidence = _merge_evidence(assetnum, selected_tools, tool_results)
    return {
        "asset_exists": True,
        "selected_tools": selected_tools,
        "tool_results": tool_results,
        "tool_trace": tool_trace,
        "evidence": evidence,
        "errors": errors,
    }


def _build_tool_results_summary(tool_results: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for tool_name, result in tool_results.items():
        if not isinstance(result, dict) or result.get("status") != "success":
            continue
        item: dict[str, Any] = {}
        for key in [
            "assetnum", "station_name", "warning_level", "risk_30d", "risk_90d",
            "suggested_inspection_window",
        ]:
            if key in result:
                item[key] = result[key]
        if "device_profile" in result:
            profile = result["device_profile"]
            item["assetnum"] = profile.get("assetnum")
            item["station_name"] = profile.get("station_name")
        if item:
            summary[tool_name] = item
    return summary


def _template_report_by_task(state: AfcAgentState) -> str:
    task_type = state.get("task_type", "full_diagnosis")
    tool_results = state.get("tool_results", {})
    evidence = state.get("evidence", {})
    assetnum = state.get("assetnum")
    query = state.get("query", "")
    errors = state.get("errors", [])

    if task_type == "capability_query":
        return build_capability_report()
    if task_type == "data_overview":
        return build_data_overview_report(tool_results)
    if task_type == "high_risk_ranking":
        return build_high_risk_report(tool_results)
    if state.get("asset_exists") is False or (state.get("requires_asset") and not assetnum):
        return build_device_error_report(assetnum, query, errors)
    if task_type == "risk_query":
        return build_risk_report(evidence, query)
    if task_type == "history_query":
        return build_history_report(evidence, query)
    if task_type == "advice_query":
        return build_advice_report(evidence, query)
    if task_type == "risk_explanation":
        return build_risk_explanation_report(evidence, query)
    if task_type == "risk_and_advice_query":
        return build_risk_advice_report(evidence, query)
    return build_full_diagnosis_report(evidence, query)


def generate_report_node(state: AfcAgentState) -> dict[str, Any]:
    """根据实际工具结果生成场景化最终回答。"""
    task_type = state.get("task_type", "full_diagnosis")

    if task_type == "capability_query" or state.get("asset_exists") is False:
        final_answer = _template_report_by_task(state)
    else:
        try:
            llm = get_report_llm()
            payload = {
                "query": state.get("query"),
                "intent": state.get("intent"),
                "selected_tools": state.get("selected_tools", []),
                "tool_results": state.get("tool_results", {}),
                "evidence": state.get("evidence", {}),
            }
            prompt = (
                "你是 AFC 智能运维诊断 Agent 的报告生成节点。"
                "请严格根据本轮 selected_tools、tool_results 和 evidence 回答；"
                "不要输出与实际工具不一致的报告；不要编造风险值、预警等级、设备信息或维修建议。"
                "能力询问输出系统能力介绍；数据概览输出工单概览；高风险输出清单；"
                "设备任务按用户问题只回答相关维度。"
                "末尾必须保留科学边界：风险预测不等于一定故障，维修建议是巡检方向不是最终根因。"
                f"\n\n本轮数据：\n{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}"
            )
            response = llm.invoke([HumanMessage(content=prompt)])
            final_answer = response.content if hasattr(response, "content") else str(response)
        except Exception:
            final_answer = _template_report_by_task(state)

    tool_results = state.get("tool_results", {})
    messages = list(state.get("messages", []))
    messages.append(HumanMessage(content=state.get("query", "")))
    messages.append(AIMessage(content=final_answer))

    last_assetnum = state.get("assetnum") if task_type not in NO_DEVICE_TASKS else state.get("last_assetnum")

    return {
        "final_answer": final_answer,
        "last_assetnum": last_assetnum,
        "last_task_type": task_type,
        "last_time_window": state.get("time_window"),
        "last_tool_results_summary": _build_tool_results_summary(tool_results),
        "messages": messages[-20:],
    }


# ── 旧节点名兼容包装：测试和文档仍可直接调用这些函数 ─────────────

def parse_question_node(state: AfcAgentState) -> dict[str, Any]:
    return parse_intent_node(state)


def resolve_asset_node(state: AfcAgentState) -> dict[str, Any]:
    task_type = state.get("task_type", "full_diagnosis")
    compat_state = {
        **state,
        "requires_asset": task_type not in NO_DEVICE_TASKS,
        "selected_tools": [],
        "tool_results": {},
        "evidence": {},
        "tool_trace": [],
    }
    result = reason_act_node(compat_state)
    return {"asset_exists": result.get("asset_exists"), "errors": result.get("errors", [])}


def route_task_node(state: AfcAgentState) -> dict[str, Any]:
    return {"selected_tools": [name for name, _ in _select_tools_by_rule(state)]}


def execute_tools_node(state: AfcAgentState) -> dict[str, Any]:
    selected = state.get("selected_tools", [])
    if not selected:
        return {"tool_results": {}, "errors": list(state.get("errors", []))}
    tool_results: dict[str, Any] = {}
    errors = list(state.get("errors", []))
    for tool_name in selected:
        try:
            tool_results[tool_name] = _invoke_tool(tool_name, state.get("assetnum"), {})
        except Exception as exc:
            errors.append(f"工具 {tool_name} 调用失败：{str(exc)}")
            tool_results[tool_name] = {"status": "error", "message": str(exc)}
    return {"tool_results": tool_results, "errors": errors}


def merge_evidence_node(state: AfcAgentState) -> dict[str, Any]:
    return {
        "evidence": _merge_evidence(
            state.get("assetnum"),
            state.get("selected_tools", []),
            state.get("tool_results", {}),
        )
    }
