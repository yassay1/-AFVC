"""LangGraph 节点实现 —— AFCDiagnosisAgent 的 6 个核心节点。"""

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage

from backend.agent.state import AfcAgentState
from backend.agent.prompts import QUESTION_PARSE_PROMPT, REPORT_GENERATION_PROMPT
from backend.core.llm import get_parse_llm, get_report_llm


# ── 工具路由表 ──────────────────────────────────────────────

TASK_TOOL_MAP: dict[str, list[str]] = {
    "data_overview": ["get_data_summary_tool"],
    "high_risk_ranking": ["get_high_risk_devices_tool"],
    "full_diagnosis": ["get_integrated_analysis_tool"],
    "risk_query": ["predict_device_risk_tool"],
    "history_query": ["get_device_history_tool"],
    "advice_query": ["get_maintenance_advice_tool"],
    "risk_explanation": ["predict_device_risk_tool", "get_maintenance_advice_tool"],
    "risk_and_advice_query": [
        "get_device_history_tool",
        "predict_device_risk_tool",
        "get_maintenance_advice_tool",
    ],
}


def _clean_json_string(text: str) -> str:
    """清除 LLM 输出中可能包裹的 markdown 代码块标记。"""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_assetnum_from_query(query: str) -> str | None:
    """从自然语言中正则提取设备编号。

    匹配优先级：
    1. "设备 XXXXX" 格式（如"设备 100023"）
    2. 字母+数字格式（如 EX011115、GX010301）
    3. 10 位纯数字（如 1000029970）
    """
    patterns = [
        r'设备\s*([A-Za-z0-9]{3,})',
        r'([A-Z]{2,}\d{5,})',
        r'(\d{10,})',
    ]
    for pattern in patterns:
        match = re.search(pattern, query)
        if match:
            return match.group(1)
    return None


# ── 节点 1：问题解析 ──────────────────────────────────────────

def parse_question_node(state: AfcAgentState) -> dict[str, Any]:
    """使用 LLM 解析用户自然语言问题。

    从问题中提取：
    - assetnum：设备编号
    - task_type：任务类型
    - time_window：时间窗口
    """
    query = state["query"]
    errors: list[str] = []

    try:
        llm = get_parse_llm()
        prompt = QUESTION_PARSE_PROMPT.format(query=query)
        response = llm.invoke([HumanMessage(content=prompt)])
        raw_output = response.content if hasattr(response, "content") else str(response)
        cleaned = _clean_json_string(raw_output)
        parsed = json.loads(cleaned)

        assetnum = parsed.get("assetnum")
        task_type = parsed.get("task_type", "full_diagnosis")
        time_window = parsed.get("time_window")

        # 如果 task_type 不在已知类型中，回退为 full_diagnosis
        if task_type not in TASK_TOOL_MAP:
            task_type = "full_diagnosis"

        return {
            "assetnum": assetnum,
            "task_type": task_type,
            "time_window": time_window,
            "errors": errors,
        }

    except json.JSONDecodeError:
        # LLM 返回格式异常，使用规则兜底
        assetnum = _extract_assetnum_from_query(query)
        task_type = _rule_based_parse_task_type(query)
        errors.append("LLM 返回非 JSON，已使用规则兜底解析")

        return {
            "assetnum": assetnum,
            "task_type": task_type,
            "time_window": None,
            "errors": errors,
        }

    except Exception as e:
        # LLM 不可用或其他异常，使用规则兜底
        assetnum = _extract_assetnum_from_query(query)
        task_type = _rule_based_parse_task_type(query)
        errors.append(f"LLM 解析不可用（{str(e)}），已使用规则兜底解析")

        return {
            "assetnum": assetnum,
            "task_type": task_type,
            "time_window": None,
            "errors": errors,
        }


def _rule_based_parse_task_type(query: str) -> str:
    """规则兜底：判断任务类型。"""
    if any(w in query for w in ["整体", "概览", "这批", "数据怎么样", "工单数据"]):
        return "data_overview"
    if any(w in query for w in ["高风险", "优先巡检", "巡检重点", "优先"]):
        return "high_risk_ranking"
    if any(w in query for w in ["为什么", "预警", "红色", "橙色"]):
        return "risk_explanation"
    if any(w in query for w in ["风险", "预测"]):
        if any(w in query for w in ["检查", "建议", "处理", "维修"]):
            return "risk_and_advice_query"
        return "risk_query"
    if any(w in query for w in ["检查", "建议", "处理", "维修"]):
        return "advice_query"
    if any(w in query for w in ["历史", "故障", "记录", "以前"]):
        return "history_query"
    return "full_diagnosis"


# ── 节点 2：设备校验 ──────────────────────────────────────────

def resolve_asset_node(state: AfcAgentState) -> dict[str, Any]:
    """校验设备编号是否存在。

    如果任务类型不需要设备编号（如全局概览），跳过校验。
    如果需要设备编号但用户未提供或设备不存在，记录错误。
    """
    assetnum = state.get("assetnum")
    task_type = state.get("task_type", "full_diagnosis")
    errors: list[str] = list(state.get("errors", []))

    # 不需要设备编号的任务
    no_device_tasks = {"data_overview", "high_risk_ranking"}

    if task_type in no_device_tasks:
        return {
            "asset_exists": True,
            "errors": errors,
        }

    if not assetnum:
        errors.append("未从问题中识别到设备编号，请提供设备编号")
        return {
            "asset_exists": False,
            "errors": errors,
        }

    # 通过设备列表校验
    try:
        from backend.agent.tools import list_devices_tool
        result = list_devices_tool.invoke({})
        devices = result.get("devices", [])
        device_ids = {d.get("assetnum", "") for d in devices}

        if str(assetnum) in device_ids:
            return {
                "asset_exists": True,
                "assetnum": str(assetnum),
                "errors": errors,
            }
        else:
            errors.append(f"设备编号 {assetnum} 在当前工单数据中不存在")
            return {
                "asset_exists": False,
                "errors": errors,
            }
    except Exception as e:
        # 设备列表获取失败时，宽松处理——允许继续
        errors.append(f"设备校验异常（已宽松处理）：{str(e)}")
        return {
            "asset_exists": True,
            "errors": errors,
        }


# ── 节点 3：任务路由 ──────────────────────────────────────────

def route_task_node(state: AfcAgentState) -> dict[str, Any]:
    """根据 task_type 选择需要调用的工具列表。"""
    task_type = state.get("task_type", "full_diagnosis")
    selected_tools = TASK_TOOL_MAP.get(task_type, ["get_integrated_analysis_tool"])
    return {"selected_tools": selected_tools}


# ── 节点 4：工具执行 ──────────────────────────────────────────

def execute_tools_node(state: AfcAgentState) -> dict[str, Any]:
    """按路由结果调用 LangChain Tools，保存工具返回结果。"""
    selected_tools: list[str] = state.get("selected_tools", [])
    assetnum: str | None = state.get("assetnum")
    errors: list[str] = list(state.get("errors", []))
    tool_results: dict[str, Any] = {}

    from backend.agent.tools import TOOL_BY_NAME

    for tool_name in selected_tools:
        tool = TOOL_BY_NAME.get(tool_name)
        if tool is None:
            errors.append(f"工具 {tool_name} 未注册")
            continue

        try:
            # 根据工具签名传参
            if tool_name == "get_data_summary_tool":
                result = tool.invoke({"top_n": 10})
            elif tool_name == "get_high_risk_devices_tool":
                result = tool.invoke({"top_n": 10})
            elif tool_name == "get_device_history_tool":
                result = tool.invoke({"assetnum": assetnum, "limit": 50})
            elif tool_name == "predict_device_risk_tool":
                result = tool.invoke({"assetnum": assetnum})
            elif tool_name == "get_warning_level_tool":
                # 如果之前已经获取了风险值，直接传入
                pred_result = tool_results.get("predict_device_risk_tool", {})
                risk_30d = pred_result.get("risk_30d", 0.0)
                risk_90d = pred_result.get("risk_90d", 0.0)
                result = tool.invoke({"risk_30d": risk_30d, "risk_90d": risk_90d})
            elif tool_name == "get_maintenance_advice_tool":
                result = tool.invoke({"assetnum": assetnum})
            elif tool_name == "get_integrated_analysis_tool":
                result = tool.invoke({"assetnum": assetnum, "history_limit": 50})
            else:
                result = tool.invoke({"assetnum": assetnum})

            tool_results[tool_name] = result
        except Exception as e:
            errors.append(f"工具 {tool_name} 调用失败：{str(e)}")
            tool_results[tool_name] = {"status": "error", "message": str(e)}

    return {
        "tool_results": tool_results,
        "errors": errors,
    }


# ── 节点 5：证据整合 ──────────────────────────────────────────

def merge_evidence_node(state: AfcAgentState) -> dict[str, Any]:
    """将工具返回的 JSON 结果整合成结构化的证据包。"""
    tool_results = state.get("tool_results", {})
    assetnum = state.get("assetnum", "未知")
    selected_tools = state.get("selected_tools", [])

    evidence: dict[str, Any] = {
        "assetnum": assetnum,
        "device_info": {},
        "history_summary": {},
        "risk_prediction": {},
        "warning_result": {},
        "maintenance_advice": {},
        "data_overview": {},
        "high_risk_devices": {},
    }

    # 从综合分析中提取各维度
    integrated = tool_results.get("get_integrated_analysis_tool", {})
    if integrated.get("status") == "success":
        evidence["device_info"] = integrated.get("device_profile", {})
        evidence["history_summary"] = integrated.get("history_summary", {})
        evidence["risk_prediction"] = integrated.get("risk_prediction", {})
        evidence["maintenance_advice"] = integrated.get("maintenance_advice", {})

    # 单体工具结果补充/覆盖
    if "get_device_history_tool" in tool_results:
        hist = tool_results["get_device_history_tool"]
        evidence["history_summary"]["raw"] = hist

    if "predict_device_risk_tool" in tool_results:
        pred = tool_results["predict_device_risk_tool"]
        if pred.get("status") == "success":
            evidence["risk_prediction"] = pred
            # 从预测结果提取风险值生成预警
            risk_30d = pred.get("risk_30d", 0.0)
            risk_90d = pred.get("risk_90d", 0.0)
            if "get_warning_level_tool" in tool_results:
                evidence["warning_result"] = tool_results["get_warning_level_tool"]
            else:
                evidence["warning_result"] = {
                    "warning_level": pred.get("warning_level", "未计算"),
                    "suggested_inspection_window": pred.get("suggested_inspection_window", "未计算"),
                    "warning_reason": pred.get("warning_reason", "未计算"),
                }

    if "get_maintenance_advice_tool" in tool_results:
        advice = tool_results["get_maintenance_advice_tool"]
        if advice.get("status") == "success":
            evidence["maintenance_advice"] = advice

    if "get_data_summary_tool" in tool_results:
        evidence["data_overview"] = tool_results["get_data_summary_tool"]

    if "get_high_risk_devices_tool" in tool_results:
        evidence["high_risk_devices"] = tool_results["get_high_risk_devices_tool"]

    # 证据来源标注
    evidence["sources"] = selected_tools

    return {"evidence": evidence}


# ── 节点 6：报告生成 ──────────────────────────────────────────

def generate_report_node(state: AfcAgentState) -> dict[str, Any]:
    """使用 LLM 基于工具证据生成最终诊断报告。"""
    query = state["query"]
    evidence = state.get("evidence", {})

    # 尝试使用 LLM 生成
    try:
        llm = get_report_llm()
        evidence_json = json.dumps(evidence, ensure_ascii=False, indent=2, default=str)
        prompt = REPORT_GENERATION_PROMPT.format(
            evidence=evidence_json,
            query=query,
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        final_answer = response.content if hasattr(response, "content") else str(response)
    except Exception:
        # LLM 不可用时使用模板
        final_answer = _template_report(query, evidence)

    return {"final_answer": final_answer}


def _template_report(query: str, evidence: dict[str, Any]) -> str:
    """模板化报告生成（LLM 不可用时的兜底方案）。"""
    device_info = evidence.get("device_info", {})
    risk = evidence.get("risk_prediction", {})
    warning = evidence.get("warning_result", {})
    advice = evidence.get("maintenance_advice", {})
    history = evidence.get("history_summary", {})
    sources = evidence.get("sources", [])

    lines = []
    lines.append("【AFC 设备智能诊断报告】")
    lines.append("")
    lines.append("一、设备识别结果")
    lines.append(f"- 设备编号：{evidence.get('assetnum', '未知')}")
    lines.append(f"- 所属车站：{device_info.get('station_name', '未知')}")
    lines.append(f"- 所属线路：{device_info.get('line', '未知')}")
    lines.append(f"- 品牌：{device_info.get('brand', '未知')}")
    lines.append("")
    lines.append("二、历史工单摘要")
    recent = history.get("recent_descriptions", [])
    if recent:
        for i, desc in enumerate(recent[:3], 1):
            lines.append(f"{i}. {desc}")
    else:
        lines.append("- 暂无最近故障描述")
    lines.append("")
    lines.append("三、多时间窗口复发风险")
    lines.append(f"- 7 天风险：{risk.get('risk_7d', 'N/A')}")
    lines.append(f"- 14 天风险：{risk.get('risk_14d', 'N/A')}")
    lines.append(f"- 21 天风险：{risk.get('risk_21d', 'N/A')}")
    lines.append(f"- 30 天风险：{risk.get('risk_30d', 'N/A')}")
    lines.append(f"- 60 天风险：{risk.get('risk_60d', 'N/A')}")
    lines.append(f"- 90 天风险：{risk.get('risk_90d', 'N/A')}")
    lines.append("")
    lines.append("四、预警等级与原因")
    lines.append(f"- 当前预警等级：{warning.get('warning_level', risk.get('warning_level', 'N/A'))}")
    lines.append(f"- 建议巡检窗口：{warning.get('suggested_inspection_window', risk.get('suggested_inspection_window', 'N/A'))}")
    lines.append("")
    lines.append("五、维修与巡检建议")
    phenomena = advice.get("recognized_fault_phenomena", [])
    causes = advice.get("possible_causes", [])
    inspections = advice.get("inspection_suggestions", [])
    spare_parts = advice.get("spare_part_suggestions", [])
    if phenomena:
        lines.append("识别到的故障现象：")
        for p in phenomena:
            lines.append(f"- {p}")
    if causes:
        lines.append("可能原因：")
        for c in causes[:5]:
            lines.append(f"- {c}")
    if inspections:
        lines.append("建议检查方向：")
        for s in inspections[:5]:
            lines.append(f"- {s}")
    if spare_parts:
        lines.append("备件建议：")
        for sp in spare_parts[:5]:
            lines.append(f"- {sp}")
    lines.append("")
    lines.append("六、工具调用记录")
    for tool in sources:
        lines.append(f"- {tool}")
    lines.append("")
    lines.append("七、科学边界说明")
    lines.append("- 风险预测表示未来时间窗口内再次产生故障工单的风险，不等同于精确预测物理故障发生日期")
    lines.append("- 维修建议是巡检方向参考，不是最终根因诊断结论")
    lines.append("- current_faildate 是工单记录时间，不直接等同于物理故障发生时刻")
    lines.append("- 最终维修判断需结合现场检测、设备日志和人工经验")
    lines.append("")
    lines.append("---")
    lines.append(f"本报告由 AFCDiagnosisAgent 自动生成 | 原始问题：{query}")

    return "\n".join(lines)
