"""evaluate_evidence_node —— 证据评估节点（v0.3.0 升级）。

职责：
判断证据是否足够回答用户问题。
如果不足，建议补充工具调用。

v0.3.0 升级：
- 尊重 answer_mode：非 evidence_based 模式不需要业务证据
- 工具错误可能导致证据不足
- 缺少设备编号的工具错误不再触发补工具循环
"""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.agent.llm_json import LLMJsonError, call_llm_json
from backend.agent.schemas import EvidenceEvaluation
from backend.agent.state import AfcAgentState
from backend.core.llm import get_parse_llm

# 最大工具补充轮次
MAX_TOOL_LOOPS = 2
logger = logging.getLogger(__name__)

# 不需要业务证据的 answer_mode
_NO_EVIDENCE_MODES = {"direct_chat", "capability_intro", "ask_for_assetnum", "unsupported"}

EVALUATE_SYSTEM = """你是 AFC 智能运维 Agent 的证据评估器。

你的任务是判断当前收集的证据是否足够回答用户问题。
不要回答用户问题，只评估证据充分性。

## 核心规则

首先检查 answer_mode：
- 如果 answer_mode 是 direct_chat / capability_intro / ask_for_assetnum / unsupported：
  → answerable=true, need_more_tools=false（这些模式不需要业务证据）

如果 answer_mode 是 evidence_based，则检查：
1. 用户问风险，但没有 risk_prediction → answerable=false, 需要 predict_device_risk_tool
2. 用户问维修手册/规程，但没有 manual_evidence → answerable=false, 需要 search_maintenance_manual_tool
3. 用户问历史，但没有 history_summary → answerable=false, 需要 get_device_history_tool
4. 用户问维修建议，但没有 maintenance_advice → answerable=false, 需要 get_maintenance_advice_tool
5. 用户问数据概览，但没有 data_overview → answerable=false, 需要 get_data_summary_tool
6. 用户问高风险设备，但没有 high_risk_devices → answerable=false, 需要 get_high_risk_devices_tool
7. 用户问故障类型预测（fault_type_prediction），但没有 fault_prediction → answerable=false, 需要 predict_device_fault_type_tool
8. 用户问完整诊断（full_diagnosis）但缺历史/风险/建议中任意一项 → answerable=false

9. 如果 tool_errors 中有 missing_required_argument 类型的错误 → 不要建议补充工具
   （缺少设备编号，再补工具也没用）
10. 如果所有工具都失败了且没有有效证据 → answerable=false, need_more_tools=false
   （不要无限循环）

## EvidenceEvaluation JSON Schema

根对象必须直接包含以下字段：
- answerable: boolean，当前证据是否足够回答用户问题
- need_more_tools: boolean，是否还需要补充工具调用
- missing_evidence: array[string]，缺失的证据类型；没有缺失时输出 []
- suggested_next_tools: array[object]，建议补充的工具调用；不需要补工具时输出 []
- reason: string，证据评估理由

suggested_next_tools 中每个对象必须包含：
- tool_name: string
- args: object
- purpose: string
- expected_evidence: array[string]

## 正确输出样例

{
  "answerable": true,
  "need_more_tools": false,
  "missing_evidence": [],
  "suggested_next_tools": [],
  "reason": "risk_prediction、history_summary 和 maintenance_advice 已满足当前问题"
}

## 输出
只输出 EvidenceEvaluation JSON。不要输出 markdown、解释文字或节点状态包装对象。"""


EVALUATE_OUTPUT_CONTRACT = """## 最终输出格式要求
只输出一个合法 JSON object，不要 markdown，不要解释文字。
JSON 根对象必须直接包含且只需要包含这些字段：
answerable, need_more_tools, missing_evidence, suggested_next_tools, reason。
不要增加任何外层包装字段，不要输出节点状态对象。
字段类型必须符合 EvidenceEvaluation：answerable/need_more_tools 为 boolean；missing_evidence/suggested_next_tools 为 array；reason 为 string。
"""


EVALUATE_JSON_SKELETON = """{
  "answerable": true,
  "need_more_tools": false,
  "missing_evidence": [],
  "suggested_next_tools": [],
  "reason": "当前证据已经足够回答用户问题"
}"""


def _rule_based_evaluate(state: AfcAgentState) -> dict[str, Any]:
    """规则化证据评估（v0.3.0 升级版）。"""
    evidence_packet = state.get("evidence_packet", {})
    query_understanding = state.get("query_understanding", {})
    tool_plan = state.get("tool_plan", {})
    answer_mode = tool_plan.get("answer_mode", "evidence_based")
    assetnum = query_understanding.get("assetnum")

    # ── 非 evidence_based 模式 → 不需要业务证据 ──
    if answer_mode in _NO_EVIDENCE_MODES:
        return {
            "answerable": True,
            "need_more_tools": False,
            "missing_evidence": [],
            "suggested_next_tools": [],
            "reason": f"answer_mode={answer_mode}，不需要业务证据",
        }

    # ── 检查是否有 missing_required_argument 错误 → 不补工具 ──
    tool_errors = evidence_packet.get("tool_errors", [])
    has_missing_arg = any(e.get("error_type") == "missing_required_argument" for e in tool_errors)
    if has_missing_arg and not evidence_packet.get("sources"):
        return {
            "answerable": True,
            "need_more_tools": False,
            "missing_evidence": [],
            "suggested_next_tools": [],
            "reason": "工具缺少设备编号，不应继续补工具，直接生成追问回答",
        }

    # ── evidence_based 模式：检查缺失证据 ──
    missing = evidence_packet.get("missing_evidence", [])
    answerable = len(missing) == 0 and len(evidence_packet.get("sources", [])) > 0
    need_more_tools = not answerable

    suggested: list[dict[str, Any]] = []
    for m in missing:
        if m == "risk_prediction":
            suggested.append({
                "tool_name": "predict_device_risk_tool",
                "args": {"assetnum": assetnum} if assetnum else {},
                "purpose": "补充风险预测证据",
                "expected_evidence": ["risk_7d", "risk_30d", "risk_90d", "warning_level"],
            })
        elif m == "maintenance_advice":
            suggested.append({
                "tool_name": "get_maintenance_advice_tool",
                "args": {"assetnum": assetnum} if assetnum else {},
                "purpose": "补充维修建议证据",
                "expected_evidence": ["inspection_suggestions", "possible_causes"],
            })
        elif m == "history_summary":
            suggested.append({
                "tool_name": "get_device_history_tool",
                "args": {"assetnum": assetnum, "limit": 50} if assetnum else {},
                "purpose": "补充历史工单证据",
                "expected_evidence": ["history", "history_count"],
            })
        elif m == "manual_evidence":
            suggested.append({
                "tool_name": "search_maintenance_manual_tool",
                "args": {"query": state.get("query", ""), "assetnum": assetnum},
                "purpose": "补充维修手册证据",
                "expected_evidence": ["manual_steps", "manual_cause"],
            })
        elif m == "fault_prediction":
            suggested.append({
                "tool_name": "predict_device_fault_type_tool",
                "args": {"assetnum": assetnum, "window_days": 30, "top_k": 3} if assetnum else {},
                "purpose": "补充故障类型预测证据",
                "expected_evidence": ["most_likely_fault", "fault_type_predictions"],
            })

    # 如果所有工具都失败了
    if not evidence_packet.get("sources") and tool_errors:
        answerable = True
        need_more_tools = False
        return {
            "answerable": True,
            "need_more_tools": False,
            "missing_evidence": [],
            "suggested_next_tools": [],
            "reason": "所有工具调用失败，不再补充工具",
        }

    return {
        "answerable": answerable,
        "need_more_tools": need_more_tools,
        "missing_evidence": missing,
        "suggested_next_tools": suggested if need_more_tools else [],
        "reason": f"规则化评估: answer_mode={answer_mode}, missing={missing}",
    }


def evaluate_evidence_node(state: AfcAgentState) -> dict[str, Any]:
    """评估证据是否足够（v0.3.0 升级版）。

    输入：query, query_understanding, tool_plan, evidence_packet, context_packet
    输出：evidence_evaluation
    """
    evidence_packet = state.get("evidence_packet", {})
    query_understanding = state.get("query_understanding", {})
    tool_plan = state.get("tool_plan", {})
    tool_loop_count = state.get("tool_loop_count", 0)
    answer_mode = tool_plan.get("answer_mode", "")
    errors: list[str] = list(state.get("errors", []))

    # ── 非 evidence_based → 直接可回答 ──
    if answer_mode in _NO_EVIDENCE_MODES:
        return {
            "evidence_evaluation": {
                "answerable": True,
                "need_more_tools": False,
                "missing_evidence": [],
                "suggested_next_tools": [],
                "reason": f"answer_mode={answer_mode}，不需要业务证据",
            },
            "errors": errors,
        }

    # ── 尝试 LLM 评估 ──
    evaluation: dict[str, Any] | None = None
    try:
        llm = get_parse_llm()
    except Exception as exc:
        error_message = (
            "evaluate_evidence LLM failed "
            "schema=EvidenceEvaluation stage=llm_init "
            f"error={str(exc)}"
        )
        logger.exception(error_message)
        errors.append(error_message)
    else:
        try:
            prompt = (
                f"## 用户问题\n{state.get('query', '')}\n"
                f"\n## 问题理解\n{json.dumps(query_understanding, ensure_ascii=False, indent=2)}\n"
                f"\n## 工具计划\n{json.dumps(tool_plan, ensure_ascii=False, indent=2)}\n"
                f"\n## 证据包\n{json.dumps(evidence_packet, ensure_ascii=False, indent=2, default=str)}\n"
                f"\n## 工具循环次数\n{tool_loop_count}/{MAX_TOOL_LOOPS}\n"
                f"\n{EVALUATE_OUTPUT_CONTRACT}"
                f"\n## JSON skeleton\n{EVALUATE_JSON_SKELETON}\n"
            )
            repair_context = (
                f"{prompt}\n\n"
                "Repair reminder: output the EvidenceEvaluation root JSON object only. "
                "The root fields must be answerable, need_more_tools, missing_evidence, "
                "suggested_next_tools, and reason. Do not wrap the object in any state or node field. "
                "Use this exact shape:\n"
                f"{EVALUATE_JSON_SKELETON}"
            )
            result = call_llm_json(
                llm=llm,
                prompt=prompt,
                schema=EvidenceEvaluation,
                system_prompt=EVALUATE_SYSTEM,
                max_repair_attempts=2,
                repair_context=repair_context,
            )
            evaluation = result.model_dump()
        except LLMJsonError as exc:
            logger.error(
                "evaluate_evidence LLM failed\n%s",
                exc.to_log_message(include_raw=True, raw_limit=8000),
            )
            errors.append(
                "evaluate_evidence LLM failed "
                f"schema=EvidenceEvaluation stage={exc.final_stage} "
                f"error={str(exc)}"
            )
        except Exception as exc:
            error_message = (
                "evaluate_evidence LLM failed "
                "schema=EvidenceEvaluation stage=unknown "
                f"error={str(exc)}"
            )
            logger.exception(error_message)
            errors.append(error_message)

    if evaluation is None:
        evaluation = _rule_based_evaluate(state)

    # ── 工具循环限制 ──
    if tool_loop_count >= MAX_TOOL_LOOPS and evaluation.get("need_more_tools"):
        evaluation["need_more_tools"] = False
        evaluation["answerable"] = True
        evaluation["reason"] = f"已达到最大工具循环次数 {MAX_TOOL_LOOPS}，强制进入回答阶段"

    return {
        "evidence_evaluation": evaluation,
        "errors": errors,
    }
