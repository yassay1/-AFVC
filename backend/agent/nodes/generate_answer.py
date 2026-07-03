"""generate_answer_node —— 答案生成节点。

职责：
基于 evidence_packet 生成最终回答。
只基于证据回答，不能编造任何数据。
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

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
from backend.core.llm import get_report_llm

GENERATE_ANSWER_SYSTEM = """你是 AFC 智能运维诊断 Agent 的报告生成器。

## 严格约束（违反任何一条都是严重错误）

1. **只能基于 evidence_packet 中的证据回答**
2. **不能编造设备数据**（设备编号、车站、风险值、预警等级等都必须来自证据）
3. **不能编造维修手册内容**
4. **不能把风险预测说成确定故障**
5. **不能预测具体故障日期**
6. **用户问"什么时候再次故障"时，要转化为风险窗口回答**
7. **如果证据不足，要明确说明证据不足**
8. **回答要自然、简洁、偏运维人员口吻**
9. **末尾必须包含科学边界说明**

## 回答策略
- 风险预测 → 用"风险窗口"表达，如 "未来30天约有 X% 概率再次产生故障工单"
- 维修建议 → "建议巡检方向" 不是 "根因诊断"
- 维修手册 → 引用来源文件
- 预警 → 解释触发原因"""


def _build_llm_prompt(state: AfcAgentState) -> str:
    """构建 LLM 回答 Prompt。"""
    evidence_packet = state.get("evidence_packet", {})
    query_understanding = state.get("query_understanding", {})
    answer_policy = state.get("answer_policy", {})

    return (
        f"## 用户问题\n{state.get('query', '')}\n"
        f"\n## 问题理解\n{json.dumps(query_understanding, ensure_ascii=False, indent=2)}\n"
        f"\n## 证据包\n{json.dumps(evidence_packet, ensure_ascii=False, indent=2, default=str)}\n"
        f"\n## 回答策略\n{json.dumps(answer_policy, ensure_ascii=False, indent=2)}\n"
        f"\n请基于证据生成最终回答。"
    )


def _legacy_evidence_from_packet(evidence_packet: dict[str, Any]) -> dict[str, Any]:
    """将 evidence_packet 转换为旧报告模板需要的字段形状。"""
    return {
        "assetnum": evidence_packet.get("assetnum"),
        "device_info": evidence_packet.get("device_profile") or {},
        "history_summary": evidence_packet.get("history_summary") or {},
        "risk_prediction": evidence_packet.get("risk_prediction") or {},
        "warning_result": evidence_packet.get("warning") or {},
        "maintenance_advice": evidence_packet.get("maintenance_advice") or {},
        "manual_evidence": evidence_packet.get("manual_evidence") or [],
        "data_overview": evidence_packet.get("data_overview") or {},
        "high_risk_devices": evidence_packet.get("high_risk_devices") or [],
        "sources": evidence_packet.get("sources", []),
    }


def _has_only_tool_errors(state: AfcAgentState) -> bool:
    tool_results = state.get("tool_results", {})
    return bool(tool_results) and all(
        isinstance(result, dict) and result.get("status") == "error"
        for result in tool_results.values()
    )


def _template_by_task(state: AfcAgentState) -> str:
    """按 task_type 分派模板生成。"""
    query_understanding = state.get("query_understanding", {})
    task_type = query_understanding.get("task_type", "unknown")
    query = state.get("query", "")
    errors = state.get("errors", [])
    assetnum = query_understanding.get("assetnum")

    evidence_packet = state.get("evidence_packet", {})
    evidence = _legacy_evidence_from_packet(evidence_packet)

    if task_type == "capability_query":
        return build_capability_report()
    if task_type == "data_overview":
        return build_data_overview_report(state.get("tool_results", {}))
    if task_type == "high_risk_ranking":
        return build_high_risk_report(state.get("tool_results", {}))
    if query_understanding.get("needs_asset") and not assetnum:
        return build_device_error_report(assetnum, query, errors)
    if _has_only_tool_errors(state) and not evidence_packet.get("sources"):
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
    if task_type == "manual_query":
        manual_evidence = evidence.get("manual_evidence")
        if not manual_evidence:
            return (
                f"【AFC 维修手册检索】\n\n设备 {assetnum} 维修手册检索未返回结果。\n"
                f"当前知识库可能缺少相关手册文件。\n\n"
                f"建议：请将维护手册 .txt/.md 放入 backend/data/knowledge/manuals 目录。"
            )
        return build_advice_report(evidence, query)
    return build_full_diagnosis_report(evidence, query)


def generate_answer_node(state: AfcAgentState) -> dict[str, Any]:
    """基于证据生成最终回答。

    输入：query, query_understanding, evidence_packet, answer_policy
    输出：final_answer
    """
    query_understanding = state.get("query_understanding", {})
    task_type = query_understanding.get("task_type", "unknown")
    errors: list[str] = list(state.get("errors", []))

    # 能力询问 / 设备不存在 → 模板
    if task_type == "capability_query" or (query_understanding.get("needs_asset") and not query_understanding.get("assetnum")):
        final_answer = _template_by_task(state)
    else:
        # 尝试 LLM 生成
        try:
            llm = get_report_llm()
            prompt = _build_llm_prompt(state)
            response = llm.invoke([HumanMessage(content=prompt)])
            final_answer = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            errors.append(f"LLM 报告生成失败，使用模板兜底：{str(exc)}")
            final_answer = _template_by_task(state)

    # 如果 final_answer 缺少科学边界说明，自动追加
    boundary_keywords = ["科学边界", "不代表", "不是最终根因", "不等同于", "巡检方向参考"]
    if not any(kw in final_answer for kw in boundary_keywords):
        final_answer += (
            "\n\n---\n"
            "**科学边界说明：**\n"
            "- 风险预测表示未来时间窗口内再次产生故障工单的风险，不等同于精确预测物理故障发生日期。\n"
            "- 维修建议是基于历史工单现象形成的巡检方向参考，不是最终根因诊断结论。\n"
            "- 最终维修判断需结合现场检测、设备日志和人工经验。"
        )

    return {
        "final_answer": final_answer,
        "errors": errors,
    }
