"""generate_answer_node —— 答案生成节点（v0.3.0 升级）。

职责：
根据 answer_mode 生成最终回答。
只有 evidence_based 模式才需要基于 EvidencePacket 回答。

v0.3.0 升级：新增 5 种 answer_mode 的回答模板。
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage

from backend.agent.report_builder import (
    build_advice_report,
    build_capability_report,
    build_data_overview_report,
    build_device_error_report,
    build_fault_type_prediction_report,
    build_full_diagnosis_report,
    build_high_risk_report,
    build_history_report,
    build_manual_report,
    build_risk_report,
)
from backend.agent.state import AfcAgentState
from backend.core.llm import get_report_llm

GENERATE_ANSWER_SYSTEM = """你是 AFC 智能运维诊断 Agent 的报告生成器。

## 严格约束（违反任何一条都是严重错误）

1. **只能基于 evidence_packet 中的证据回答**（evidence_based 模式）
2. **不能编造设备数据**（设备编号、车站、风险值、预警等级等都必须来自证据）
3. **不能编造维修手册内容**
4. **不能把风险预测说成确定故障**
5. **不能预测具体故障日期**
6. **用户问"什么时候再次故障"时，要转化为风险窗口回答**
7. **如果证据不足，要明确说明证据不足**
8. **回答要自然、简洁、偏运维人员口吻**
9. **末尾必须包含科学边界说明**
10. **对于 direct_chat 模式，回复自然问候 + 简短能力介绍**
11. **故障类型预测必须区分三个概率概念**
    - overall_failure_risk：总体故障风险（预测窗口内发生故障工单的概率）
    - conditional_probability：条件概率（如果发生故障，属于某一类别的概率）
    - estimated_occurrence_probability：综合估计发生概率 = 前者 × 后者
12. **禁止把 conditional_probability 直接说成实际发生概率**
13. **如果故障类型预测结果 unavailable，不能自行编造预测概率**
14. **禁止使用"一定发生""即将损坏"等确定性表述**

## 回答策略
- 风险预测 → 用"风险窗口"表达，如 "未来30天约有 X% 概率再次产生故障工单"
- 维修建议 → "建议巡检方向" 不是 "根因诊断"
- 维修手册 → 引用来源文件
- 预警 → 解释触发原因

## 输出结构建议
- 先直接回答用户问题
- 再列出关键证据和工具来源
- 最后给出科学边界说明

不要输出工具原始 JSON，不要输出节点状态字段。"""


ANSWER_FINAL_CONTRACT = """## 最终回答要求
只基于 evidence_packet 中已有证据回答；不要编造设备信息、风险值、预警等级、维修手册内容或工具来源。
如果证据不足，直接说明证据不足，不要自行补全。
风险只能表述为未来时间窗口内再次产生故障工单的概率或风险，不要预测具体故障日期。
维修建议只能表述为巡检方向参考，不要写成已确认根因。
当 business_goal 是 device_advice 或 full_diagnosis，且 evidence_packet.maintenance_advice.maintenance_sop 存在时，优先按"维修建议、优先排查顺序、现场排查步骤、异常判定标准、处理动作、推荐备件、维修后复测、升级处理条件、注意事项"的 SOP 结构输出。
SOP 内容必须使用 maintenance_sop 和 spare_part_suggestions 中已有条目，不要只罗列 possible_causes 或 inspection_suggestions。
故障类型预测必须区分：总体故障风险（overall_failure_risk）、条件故障类型概率（conditional_probability）、综合估计发生概率（estimated_occurrence_probability）。不要把 conditional_probability 直接说成实际发生概率。
如果故障类型预测结果 unavailable，不能自行编造预测概率。可以回答"当前暂无模型预测结果"并补充现有风险信息。
禁止使用"一定发生""即将损坏"等确定性表述，禁止预测精确故障日期和真实物理根因。
回答末尾必须包含科学边界说明。
不要输出工具原始 JSON、节点状态字段或调试信息。
"""


# ── answer_mode 回答模板 ─────────────────────────────────────────

def _direct_chat_answer() -> str:
    """闲聊/问候的回答。"""
    return (
        "你好，我是地铁 AFC 故障复发风险预测与智能维修建议助手。\n\n"
        "我可以帮你完成以下工作：\n\n"
        "📊 **数据概览** — 了解工单整体情况\n"
        '  试试问："这批工单整体情况怎么样？"\n\n'
        "🚨 **高风险设备** — 查看当前最需要关注的设备\n"
        '  试试问："当前高风险设备有哪些？"\n\n'
        "🔍 **单设备诊断** — 分析某台设备的完整状况\n"
        '  试试问："帮我分析设备 1000029970"\n\n'
        "📈 **风险预测** — 查看设备未来复发风险\n"
        '  试试问："设备 1000029970 未来30天风险高吗？"\n\n'
        "🔧 **维修建议** — 获得巡检方向参考\n"
        '  试试问："设备 1000029970 应该检查什么？"\n\n'
        "📋 **历史查询** — 查看设备过往故障记录\n"
        '  试试问："设备 1000029970 最近有哪些故障？"\n\n'
        "---\n"
        "请直接输入你的问题开始使用！"
    )


def _capability_intro_answer() -> str:
    """系统能力介绍的回答。"""
    return build_capability_report()


def _ask_for_assetnum_answer() -> str:
    """缺少设备编号时的追问。"""
    return (
        "可以，请先提供设备编号，例如 1000029970 或 EX011115。\n\n"
        "拿到设备编号后，我可以帮你查询：\n"
        "- 设备历史故障工单\n"
        "- 未来 7/14/21/30/60/90 天复发风险\n"
        "- 红橙黄绿预警等级与建议巡检窗口\n"
        "- 维修与巡检建议\n"
        "- 单设备综合诊断报告\n\n"
        "请直接输入设备编号即可。"
    )


def _unsupported_answer() -> str:
    """超出系统能力的回答。"""
    return (
        "这个问题超出了当前 AFC 故障诊断系统的范围。\n\n"
        "我主要支持以下功能：\n"
        "- 查看工单数据概览\n"
        "- 查看高风险设备排行\n"
        "- 查询设备历史故障工单\n"
        "- 预测设备未来复发风险\n"
        "- 生成维修与巡检建议\n"
        "- 单设备综合诊断分析\n\n"
        "你可以提供设备编号让我继续分析，或尝试其他 AFC 运维相关问题。"
    )


# ── 兼容辅助 ──────────────────────────────────────────────────────

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
        "fault_prediction": evidence_packet.get("fault_prediction") or {},
        "sources": evidence_packet.get("sources", []),
    }


def _template_by_goal(state: AfcAgentState) -> str:
    """按 business_goal 分派模板生成（evidence_based 时）。"""
    query_understanding = state.get("query_understanding", {})
    business_goal = query_understanding.get("business_goal")
    query = state.get("query", "")
    errors = state.get("errors", [])
    assetnum = query_understanding.get("assetnum")

    evidence_packet = state.get("evidence_packet", {})
    evidence = _legacy_evidence_from_packet(evidence_packet)

    # 检查是否有工具错误
    tool_errors = evidence_packet.get("tool_errors", [])
    has_missing_asset_error = any(e.get("error_type") == "missing_required_argument" for e in tool_errors)
    if has_missing_asset_error and not evidence_packet.get("sources"):
        return _ask_for_assetnum_answer()

    if query_understanding.get("route") in {"capability_query", "direct_chat"}:
        return build_capability_report()
    if business_goal == "data_overview":
        return build_data_overview_report(state.get("tool_results", {}))
    if business_goal == "high_risk_ranking":
        return build_high_risk_report(state.get("tool_results", {}))
    if query_understanding.get("needs_asset") and not assetnum:
        return _ask_for_assetnum_answer()
    if not evidence_packet.get("sources") and tool_errors:
        return _ask_for_assetnum_answer() if has_missing_asset_error else build_device_error_report(assetnum, query, errors)
    if business_goal == "device_risk":
        return build_risk_report(evidence, query)
    if business_goal == "device_history":
        return build_history_report(evidence, query)
    if business_goal == "device_advice":
        return build_advice_report(evidence, query)
    if business_goal == "manual_search":
        return build_manual_report(evidence, query)
    if business_goal == "fault_type_prediction":
        return build_fault_type_prediction_report(evidence, query)
    # 默认完整诊断
    return build_full_diagnosis_report(evidence, query)


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
        f"\n{ANSWER_FINAL_CONTRACT}"
    )


def _auto_append_boundary(answer: str) -> str:
    """如果回答缺少科学边界说明，自动追加。"""
    boundary_keywords = ["科学边界", "不代表", "不是最终根因", "不等同于", "巡检方向参考"]
    if not any(kw in answer for kw in boundary_keywords):
        answer += (
            "\n\n---\n"
            "**科学边界说明：**\n"
            "- 风险预测表示未来时间窗口内再次产生故障工单的风险，不等同于精确预测物理故障发生日期。\n"
            "- 维修建议是基于历史工单现象形成的巡检方向参考，不是最终根因诊断结论。\n"
            "- 最终维修判断需结合现场检测、设备日志和人工经验。"
        )
    return answer


# ── 节点入口 ──────────────────────────────────────────────────────

def generate_answer_node(state: AfcAgentState) -> dict[str, Any]:
    """基于 evidence_packet 生成最终回答（v0.3.0 升级版）。

    输入：query, query_understanding, evidence_packet, answer_policy, tool_plan
    输出：final_answer

    v0.3.0: 根据 answer_mode 分派回答策略。
    """
    tool_plan = state.get("tool_plan", {})
    answer_mode = tool_plan.get("answer_mode", "evidence_based")
    query_understanding = state.get("query_understanding", {})
    errors: list[str] = list(state.get("errors", []))

    # ── 按 answer_mode 分派 ──

    # 1. direct_chat
    if answer_mode == "direct_chat":
        return {
            "final_answer": _direct_chat_answer(),
            "errors": errors,
        }

    # 2. capability_intro
    if answer_mode == "capability_intro":
        return {
            "final_answer": _capability_intro_answer(),
            "errors": errors,
        }

    # 3. ask_for_assetnum
    if answer_mode == "ask_for_assetnum":
        return {
            "final_answer": _ask_for_assetnum_answer(),
            "errors": errors,
        }

    # 4. unsupported
    if answer_mode == "unsupported":
        return {
            "final_answer": _unsupported_answer(),
            "errors": errors,
        }

    # 5. evidence_based — 需要证据
    # 先检查是否有工具错误导致无有效证据
    evidence_packet = state.get("evidence_packet", {})
    tool_errors = evidence_packet.get("tool_errors", [])
    has_missing_asset_error = any(
        e.get("error_type") == "missing_required_argument" for e in tool_errors
    )
    if has_missing_asset_error and not evidence_packet.get("sources"):
        return {
            "final_answer": _ask_for_assetnum_answer(),
            "errors": errors,
        }

    # manual_search always uses the template builder for consistent formatting
    if query_understanding.get("business_goal") == "manual_search":
        final_answer = _template_by_goal(state)
        return {
            "final_answer": _auto_append_boundary(final_answer),
            "errors": errors,
        }

    # 尝试 LLM 生成
    try:
        llm = get_report_llm()
        prompt = _build_llm_prompt(state)
        response = llm.invoke([HumanMessage(content=prompt)])
        final_answer = response.content if hasattr(response, "content") else str(response)
    except Exception as exc:
        errors.append(f"LLM 报告生成失败，使用模板兜底：{str(exc)}")
        final_answer = _template_by_goal(state)

    # 补科学边界
    final_answer = _auto_append_boundary(final_answer)

    return {
        "final_answer": final_answer,
        "errors": errors,
    }
