"""plan_tools_node —— 工具规划节点。

职责：
调用 LLM，根据 QueryUnderstanding + ContextPacket + 可用工具列表 + 已有证据，
规划工具调用。
"""

from __future__ import annotations

import json
from typing import Any

from backend.agent.llm_json import call_llm_json
from backend.agent.schemas import ToolPlan
from backend.agent.state import AfcAgentState
from backend.agent.tools import TOOL_BY_NAME
from backend.core.llm import get_parse_llm


# ── 工具描述 ──────────────────────────────────────────────────────

def _build_tool_descriptions() -> str:
    """构建可用工具列表描述。"""
    lines: list[str] = []
    for name, tool in TOOL_BY_NAME.items():
        desc = getattr(tool, "description", "无描述")
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines)


# ── 规则化工具映射 ──────────────────────────────────────────────

TASK_TOOL_MAP: dict[str, list[dict[str, Any]]] = {
    "capability_query": [],
    "data_overview": [
        {"tool_name": "get_data_summary_tool", "args": {}, "purpose": "获取工单数据概览"}
    ],
    "high_risk_ranking": [
        {"tool_name": "get_high_risk_devices_tool", "args": {"top_n": 10}, "purpose": "获取高风险设备清单"}
    ],
    "full_diagnosis": [
        {"tool_name": "get_integrated_analysis_tool", "args": {}, "purpose": "获取设备综合分析（历史+风险+建议）"}
    ],
    "risk_query": [
        {"tool_name": "predict_device_risk_tool", "args": {}, "purpose": "获取设备多时间窗口风险预测"}
    ],
    "history_query": [
        {"tool_name": "get_device_history_tool", "args": {"limit": 50}, "purpose": "获取设备历史工单记录"}
    ],
    "advice_query": [
        {"tool_name": "get_maintenance_advice_tool", "args": {}, "purpose": "获取设备维修与巡检建议"}
    ],
    "risk_explanation": [
        {"tool_name": "predict_device_risk_tool", "args": {}, "purpose": "获取风险预测及预警原因"}
    ],
    "risk_and_advice_query": [
        {"tool_name": "predict_device_risk_tool", "args": {}, "purpose": "获取风险预测"},
        {"tool_name": "get_maintenance_advice_tool", "args": {}, "purpose": "获取维修建议"},
    ],
    "manual_query": [
        {"tool_name": "search_maintenance_manual_tool", "args": {"query": ""}, "purpose": "检索维修手册"}
    ],
    "followup_rewrite": [
        {"tool_name": "get_integrated_analysis_tool", "args": {}, "purpose": "获取设备综合分析"}
    ],
    "unknown": [
        {"tool_name": "get_integrated_analysis_tool", "args": {}, "purpose": "默认尝试综合分析"}
    ],
}


def _rule_based_plan(state: AfcAgentState) -> dict[str, Any]:
    """规则化工具规划（LLM 不可用时回退）。"""
    query_understanding = state.get("query_understanding", {})
    task_type = query_understanding.get("task_type", "full_diagnosis")
    assetnum = query_understanding.get("assetnum")

    plan_items = TASK_TOOL_MAP.get(task_type, TASK_TOOL_MAP["full_diagnosis"])
    tool_calls = []
    for item in plan_items:
        tc = dict(item)
        if "args" in tc and assetnum and "assetnum" not in tc["args"]:
            if tc["tool_name"] in {
                "predict_device_risk_tool",
                "get_maintenance_advice_tool",
                "get_integrated_analysis_tool",
                "get_device_history_tool",
            }:
                tc["args"] = {**tc["args"], "assetnum": assetnum}
        if tc["tool_name"] == "search_maintenance_manual_tool":
            tc["args"] = {**tc["args"], "query": state.get("query", ""), "assetnum": assetnum}
        tool_calls.append(tc)

    return {
        "tool_calls": tool_calls,
        "use_existing_evidence": len(tool_calls) == 0,
        "reason": f"规则化工具规划：task_type={task_type}",
        "answer_policy": {
            "must_not_predict_exact_failure_date": True,
            "must_answer_with_risk_window": True,
        },
    }


PLAN_TOOLS_SYSTEM = """你是 AFC 智能运维 Agent 的工具规划器。

你的任务是：根据问题理解和上下文，规划需要调用的工具。
你只规划工具，不回答用户问题。

## 可用工具
{tool_descriptions}

## 规划原则
1. capability_query → 不需要工具
2. data_overview → get_data_summary_tool
3. high_risk_ranking → get_high_risk_devices_tool
4. full_diagnosis → 优先 get_integrated_analysis_tool
5. risk_query → predict_device_risk_tool
6. history_query → get_device_history_tool
7. advice_query → get_maintenance_advice_tool
8. risk_explanation → predict_device_risk_tool
9. risk_and_advice_query → predict_device_risk_tool + get_maintenance_advice_tool
10. manual_query / 用户说"按维修手册/规程" → search_maintenance_manual_tool
11. 如果已有 evidence 足够回答，tool_calls 可以为空，use_existing_evidence=true
12. 每个工具调用必须说明 purpose 和 expected_evidence

## 输出
只输出一个合法的 ToolPlan JSON 对象。"""


def plan_tools_node(state: AfcAgentState) -> dict[str, Any]:
    """规划工具调用。

    输入：query_understanding, context_packet, evidence_packet
    输出：tool_plan + answer_policy
    """
    query_understanding = state.get("query_understanding", {})
    task_type = query_understanding.get("task_type", "unknown")
    assetnum = query_understanding.get("assetnum")
    errors: list[str] = list(state.get("errors", []))
    evidence_packet = state.get("evidence_packet", {})

    # 不需要设备编号的任务；其中只有 capability_query 不需要业务工具。
    NO_DEVICE_TASKS = {"capability_query", "data_overview", "high_risk_ranking"}
    needs_asset = query_understanding.get("needs_asset", task_type not in NO_DEVICE_TASKS)

    # 能力询问不需要业务工具；数据概览/高风险清单仍应调用全局业务工具。
    if task_type == "capability_query":
        return {
            "tool_plan": {
                "tool_calls": [],
                "use_existing_evidence": False,
                "reason": "capability_query 不需要业务工具",
                "answer_policy": {},
            },
            "answer_policy": {},
            "errors": errors,
        }

    # 需要设备但没有设备 → 不规划工具
    if needs_asset and not assetnum:
        errors.append("未从问题中识别到设备编号，请提供设备编号")
        return {
            "tool_plan": {
                "tool_calls": [],
                "use_existing_evidence": False,
                "reason": "未识别到设备编号，无法规划工具",
                "answer_policy": {"missing_asset": True},
            },
            "answer_policy": {"missing_asset": True},
            "errors": errors,
        }

    # 尝试 LLM 规划
    try:
        llm = get_parse_llm()
        tool_descriptions = _build_tool_descriptions()
        system_prompt = PLAN_TOOLS_SYSTEM.format(tool_descriptions=tool_descriptions)

        prompt = (
            f"## 问题理解\n{json.dumps(query_understanding, ensure_ascii=False, indent=2)}\n"
            f"\n## 已有证据\n{json.dumps(evidence_packet, ensure_ascii=False, indent=2) if evidence_packet else '无'}\n"
            f"\n## 任务类型\n{task_type}\n"
            f"\n请输出 ToolPlan JSON（只输出 JSON）："
        )

        result = call_llm_json(llm=llm, prompt=prompt, schema=ToolPlan, system_prompt=system_prompt)
        tool_plan = result.model_dump()
    except Exception as exc:
        errors.append(f"LLM 工具规划不可用，使用规则兜底：{str(exc)}")
        tool_plan = _rule_based_plan(state)

    # 如果 tool_calls 为空且不是能力询问，使用规则兜底
    if not tool_plan.get("tool_calls") and task_type != "capability_query":
        tool_plan = _rule_based_plan(state)

    # 后处理：如果 task_type 是 manual_query 但没规划 RAG 工具
    if task_type == "manual_query":
        has_rag = any(
            tc.get("tool_name") == "search_maintenance_manual_tool"
            for tc in tool_plan.get("tool_calls", [])
        )
        if not has_rag and "search_maintenance_manual_tool" in TOOL_BY_NAME:
            tool_plan.setdefault("tool_calls", []).append({
                "tool_name": "search_maintenance_manual_tool",
                "args": {"query": state.get("query", ""), "assetnum": assetnum},
                "purpose": "按用户要求检索维修手册",
                "expected_evidence": ["manual_steps", "manual_cause"],
            })

    # 后处理：从已知工具中补充 assetnum
    if assetnum:
        for tc in tool_plan.get("tool_calls", []):
            if not tc.get("args", {}).get("assetnum") and tc.get("tool_name") in {
                "predict_device_risk_tool", "get_maintenance_advice_tool",
                "get_integrated_analysis_tool", "get_device_history_tool",
            }:
                tc.setdefault("args", {})["assetnum"] = assetnum

    return {
        "tool_plan": tool_plan,
        "answer_policy": tool_plan.get("answer_policy", {}),
        "errors": errors,
    }
