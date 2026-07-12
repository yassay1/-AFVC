"""将所有回答先结构化为 GeneratedAnswer，再统一渲染 Markdown。"""
from __future__ import annotations
import json
from typing import Any
from backend.agent.llm_json import call_llm_json
from backend.agent.report_builder import build_advice_report,build_capability_report,build_data_overview_report,build_device_error_report,build_fault_type_prediction_report,build_full_diagnosis_report,build_high_risk_report,build_history_report,build_manual_report,build_risk_report
from backend.agent.schemas import AnswerPolicy,EvidencePacket,GeneratedAnswer
from backend.agent.state import AfcAgentState,CAPABILITY_BOUNDARY
from backend.core.llm import get_conversation_llm,get_report_llm

DEFAULT_BOUNDARY="风险预测表示未来时间窗口内再次产生故障工单的可能性，不等同于精确预测物理故障日期；维修建议属于巡检方向参考，最终判断仍需结合现场检测、设备日志和人工经验。"
GROUNDED_ANSWER_SYSTEM="""你是 AFC 智能运维 Agent 的证据型报告生成器。具体设备事实只能来自 EvidencePacket，不得编造设备编号、站点、风险值、故障类型、手册条目或来源。可以解释和组合证据，但不能补充不存在的事实。风险只能表述为未来时间窗口内再次产生故障工单的概率，不得预测精确故障日期。维修建议只能作为巡检方向。manual_search 必须忠实于 manual_evidence 并保留来源。evidence_evaluation.evidence_sufficient=false 时必须明确说明证据不足。只输出符合 GeneratedAnswer 的 JSON；不输出 Markdown、节点 State 或工具原始 JSON。"""
CONVERSATIONAL_ANSWER_SYSTEM="""你是 AFC 智能运维对话助手。可以解释 AFC 概念、风险模型和概率含义，通俗化上一轮结论，并回答项目范围内的一般问题。可以使用通用知识解释，但不得编造当前设备状态，不得把一般知识说成某台设备事实，不得声称调用了未调用的工具，不得编造数据库内容。只输出符合 GeneratedAnswer 的 JSON，不输出 Markdown。"""

def render_generated_answer(g:GeneratedAnswer)->str:
    parts=[g.direct_answer.strip()]
    for title,items in (("关键证据",g.key_evidence),("分析",g.analysis),("建议",g.recommendations),("来源",g.sources)):
        if items: parts.append(f"## {title}\n"+"\n".join(f"- {x}" for x in items))
    if g.boundary_notice: parts.append(f"## 科学边界\n{g.boundary_notice}")
    if g.follow_up_question: parts.append(g.follow_up_question)
    return "\n\n".join(x for x in parts if x)

def ensure_generated_answer(g:GeneratedAnswer,policy:AnswerPolicy,packet:EvidencePacket,errors:list[str]|None=None)->GeneratedAnswer:
    data=g.model_dump(); allowed=set(packet.sources); invalid=[x for x in data["sources"] if x not in allowed]
    if invalid and errors is not None: errors.append(f"模型输出了不存在的来源，已过滤：{invalid}")
    data["sources"]=[x for x in data["sources"] if x in allowed]
    if data["answer_type"]=="grounded" and policy.must_include_boundary and not data["boundary_notice"]: data["boundary_notice"]=DEFAULT_BOUNDARY
    return GeneratedAnswer.model_validate(data)

def _fixed(mode:str)->GeneratedAnswer:
    if mode=="direct_chat": return GeneratedAnswer(answer_type="direct_chat",direct_answer="你好，我是 AFC 智能运维助手。")
    if mode=="capability_intro": return GeneratedAnswer(answer_type="capability",direct_answer=build_capability_report())
    if mode=="ask_for_assetnum": return GeneratedAnswer(answer_type="clarification",direct_answer="请提供设备编号。",follow_up_question="请直接输入设备编号。")
    return GeneratedAnswer(answer_type="unsupported",direct_answer="该问题超出当前 AFC 运维系统范围。")
def _legacy(ep:dict[str,Any])->dict[str,Any]:
    return {"assetnum":ep.get("assetnum"),"device_info":ep.get("device_profile") or {},"history_summary":ep.get("history_summary") or {},"risk_prediction":ep.get("risk_prediction") or {},"warning_result":ep.get("warning") or {},"maintenance_advice":ep.get("maintenance_advice") or {},"manual_evidence":ep.get("manual_evidence") or [],"data_overview":ep.get("data_overview") or {},"high_risk_devices":ep.get("high_risk_devices") or [],"fault_prediction":ep.get("fault_prediction") or {},"sources":ep.get("sources",[])}
def _template(state:AfcAgentState)->str:
    u=state.get("query_understanding",{}); goal=u.get("business_goal"); ep=state.get("evidence_packet",{}); evidence=_legacy(ep); q=state.get("query","")
    if not ep.get("sources") and ep.get("tool_errors"): return build_device_error_report(u.get("assetnum"),q,state.get("errors",[]))
    if goal=="data_overview": return build_data_overview_report(state.get("tool_results",{}))
    if goal=="high_risk_ranking": return build_high_risk_report(state.get("tool_results",{}))
    if goal=="device_risk": return build_risk_report(evidence,q)
    if goal=="device_history": return build_history_report(evidence,q)
    if goal=="device_advice": return build_advice_report(evidence,q)
    if goal=="manual_search": return build_manual_report(evidence,q)
    if goal=="fault_type_prediction": return build_fault_type_prediction_report(evidence,q)
    return build_full_diagnosis_report(evidence,q)
def _grounded_prompt(state:AfcAgentState)->str:
    payload={"query":state.get("query",""),"query_understanding":state.get("query_understanding",{}),"evidence_packet":state.get("evidence_packet",{}),"evidence_evaluation":state.get("evidence_evaluation",{}),"answer_policy":state.get("answer_policy",{})}
    return f"请基于以下整理后的证据生成结构化回答：\n{json.dumps(payload,ensure_ascii=False,indent=2,default=str)}\n只输出 GeneratedAnswer JSON。"
def _conversation_prompt(state:AfcAgentState)->str:
    ctx=state.get("context_packet",{}); payload={"query":state.get("query",""),"recent_messages":ctx.get("recent_messages",[]),"recent_messages_summary":ctx.get("recent_messages_summary"),"capability_boundary":ctx.get("capability_boundary",CAPABILITY_BOUNDARY),"last_evidence_summary":ctx.get("last_evidence_summary",{}),"answer_policy":state.get("answer_policy",{})}
    return f"请回答以下 AFC 范围内的一般问题：\n{json.dumps(payload,ensure_ascii=False,indent=2,default=str)}\n只输出 GeneratedAnswer JSON。"
def generate_answer_node(state:AfcAgentState)->dict[str,Any]:
    mode=state.get("tool_plan",{}).get("answer_mode","evidence_based"); errors=list(state.get("errors",[])); policy=AnswerPolicy.model_validate(state.get("answer_policy",{})); packet=EvidencePacket.model_validate(state.get("evidence_packet",{}))
    if mode in {"direct_chat","capability_intro","ask_for_assetnum","unsupported"}: generated=_fixed(mode)
    elif mode=="conversational":
        try:
            prompt=_conversation_prompt(state); generated=call_llm_json(llm=get_conversation_llm(),prompt=prompt,schema=GeneratedAnswer,system_prompt=CONVERSATIONAL_ANSWER_SYSTEM,max_repair_attempts=2,repair_context=prompt)
        except Exception as exc:
            errors.append(f"对话 LLM 生成失败，使用代码兜底：{exc}"); generated=GeneratedAnswer(answer_type="conversational",direct_answer="风险概率表示在给定时间窗口内再次产生故障工单的可能性，并不表示设备一定会发生故障。")
    else:
        try:
            prompt=_grounded_prompt(state); generated=call_llm_json(llm=get_report_llm(),prompt=prompt,schema=GeneratedAnswer,system_prompt=GROUNDED_ANSWER_SYSTEM,max_repair_attempts=2,repair_context=prompt)
        except Exception as exc:
            errors.append(f"LLM 报告生成失败，使用模板兜底：{exc}"); generated=GeneratedAnswer(answer_type="error" if not packet.sources else "grounded",direct_answer=_template(state),sources=packet.sources,boundary_notice=DEFAULT_BOUNDARY)
    generated=ensure_generated_answer(generated,policy,packet,errors)
    return {"generated_answer":generated.model_dump(),"final_answer":render_generated_answer(generated),"errors":errors}
