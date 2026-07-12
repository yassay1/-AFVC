"""规则优先评估证据；仅开放分析允许 LLM 辅助。"""
from __future__ import annotations
import json, logging
from typing import Any
from backend.agent.llm_json import call_llm_json
from backend.agent.schemas import EvidenceEvaluation
from backend.agent.state import AfcAgentState
from backend.core.llm import get_parse_llm

MAX_TOOL_LOOPS=2
logger=logging.getLogger(__name__)
_NO_EVIDENCE_MODES={"direct_chat","capability_intro","conversational","ask_for_assetnum","unsupported"}
EVALUATE_SYSTEM="""你是 AFC 智能运维 Agent 的开放分析证据评估器。你只判断现有证据能否支持用户要求的综合解释、还缺什么证据，以及下一步是 proceed、replan、clarify 或 stop。不得回答用户问题，不得生成工具计划或 suggested_next_tools，不得编造证据。只输出符合 EvidenceEvaluation 的 JSON。"""

def _evaluation(decision:str,sufficient:bool,missing:list[str],reason:str,method:str="rule")->dict[str,Any]:
    return EvidenceEvaluation(decision=decision,evidence_sufficient=sufficient,missing_evidence=missing,reason=reason,evaluation_method=method).model_dump()
def _rule_based_evaluate(state:AfcAgentState)->dict[str,Any]:
    ep=state.get("evidence_packet",{}); mode=state.get("tool_plan",{}).get("answer_mode","evidence_based"); loops=state.get("tool_loop_count",0); missing=list(ep.get("missing_evidence",[])); sources=ep.get("sources",[]); errors=ep.get("tool_errors",[])
    if mode in _NO_EVIDENCE_MODES: return _evaluation("proceed",True,[],"当前回答模式不依赖业务证据")
    if any(e.get("error_type")=="missing_required_argument" for e in errors) and not sources: return _evaluation("clarify",False,[],"缺少设备编号，无法继续调用设备工具")
    if not sources and errors: return _evaluation("stop",False,missing,"工具全部失败，停止补充工具并进入失败说明")
    if not missing and sources: return _evaluation("proceed",True,[],"所需证据均已取得")
    if loops>=MAX_TOOL_LOOPS: return _evaluation("stop",False,missing,f"证据仍不充分，已达到最大工具循环次数 {MAX_TOOL_LOOPS}")
    if missing: return _evaluation("replan",False,missing,"仍可通过工具补充缺失证据")
    return _evaluation("stop",False,missing,"没有可用来源，且证据不可再补充")
def _prompt(state:AfcAgentState)->str:
    ep=state.get("evidence_packet",{})
    payload={"用户问题":state.get("query",""),"query_understanding":state.get("query_understanding",{}),"tool_plan":state.get("tool_plan",{}),"evidence_packet":ep,"available_evidence":ep.get("available_evidence",[]),"missing_evidence":ep.get("missing_evidence",[]),"tool_trace":state.get("tool_trace",[]),"tool_loop_count":f"{state.get('tool_loop_count',0)}/{MAX_TOOL_LOOPS}"}
    return f"请评估以下开放分析证据：\n{json.dumps(payload,ensure_ascii=False,indent=2,default=str)}\n只输出 EvidenceEvaluation JSON。"
def evaluate_evidence_node(state:AfcAgentState)->dict[str,Any]:
    errors=list(state.get("errors",[])); rule=_rule_based_evaluate(state); u=state.get("query_understanding",{})
    if state.get("tool_plan",{}).get("answer_mode") in _NO_EVIDENCE_MODES or u.get("business_goal")!="open_analysis": return {"evidence_evaluation":rule,"errors":errors}
    if rule["decision"] in {"clarify","stop"}: return {"evidence_evaluation":rule,"errors":errors}
    try:
        prompt=_prompt(state); result=call_llm_json(llm=get_parse_llm(),prompt=prompt,schema=EvidenceEvaluation,system_prompt=EVALUATE_SYSTEM,max_repair_attempts=2,repair_context=prompt); evaluation=result.model_dump(); evaluation["evaluation_method"]="llm"
        if state.get("tool_loop_count",0)>=MAX_TOOL_LOOPS and evaluation["decision"]=="replan": evaluation=_evaluation("stop",False,evaluation["missing_evidence"],f"证据仍不充分，已达到最大工具循环次数 {MAX_TOOL_LOOPS}","hybrid")
        if evaluation["decision"]=="proceed" and evaluation["missing_evidence"]: evaluation["evaluation_method"]="hybrid"
    except Exception as exc:
        logger.exception("开放分析证据评估 LLM 失败"); errors.append(f"LLM 证据评估不可用，使用规则兜底：{exc}"); evaluation=rule
    return {"evidence_evaluation":evaluation,"errors":errors}
