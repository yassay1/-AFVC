"""规则优先规划工具；仅开放组合分析使用 LLM。"""
from __future__ import annotations
import json, re
from typing import Any
from backend.agent.llm_json import call_llm_json
from backend.agent.schemas import AnswerPolicy, ToolPlan
from backend.agent.state import AfcAgentState
from backend.agent.tools import TOOL_BY_NAME
from backend.core.llm import get_parse_llm

MAX_TOOL_CALLS=5
_ASSET_REQUIRED_TOOLS={"get_integrated_analysis_tool","predict_device_risk_tool","get_device_history_tool","get_maintenance_advice_tool","predict_device_fault_type_tool"}
_FIXED={
 "data_overview":("get_data_summary_tool","data_overview"), "high_risk_ranking":("get_high_risk_devices_tool","high_risk_devices"),
 "device_risk":("predict_device_risk_tool","risk_prediction"), "device_history":("get_device_history_tool","history_summary"),
 "device_advice":("get_maintenance_advice_tool","maintenance_advice"), "fault_type_prediction":("predict_device_fault_type_tool","fault_prediction"),
 "full_diagnosis":("get_integrated_analysis_tool","device_profile"), "manual_search":("search_maintenance_manual_tool","manual_evidence"),
}
_MISSING_TOOL={v[1]:v[0] for v in _FIXED.values()}
_MISSING_TOOL.update(device_profile="get_integrated_analysis_tool",warning="predict_device_risk_tool")

def _extract_window_days(q:str)->int:
    from backend.domain.risk import SUPPORTED_PREDICTION_WINDOWS
    m=re.search(r"(\d+)\s*(?:天|日)",q); days=int(m.group(1)) if m else 30
    return days if days in SUPPORTED_PREDICTION_WINDOWS else 30
def _style(q:str)->str:
    if any(x in q for x in ("简单说","简洁","直接说")): return "concise"
    if any(x in q for x in ("详细分析","完整报告")): return "detailed"
    if any(x in q for x in ("按步骤","SOP","操作流程")): return "sop"
    return "standard"
def _policy(q:str, grounded=False, general=False)->AnswerPolicy:
    return AnswerPolicy(style=_style(q),must_use_evidence=grounded,allow_general_knowledge=general,must_cite_sources=grounded,must_include_boundary=grounded)
def _tool_args(name:str,state:AfcAgentState,asset:str|None)->dict[str,Any]:
    args={}
    if name in _ASSET_REQUIRED_TOOLS: args["assetnum"]=asset
    if name in {"get_data_summary_tool","get_high_risk_devices_tool"}: args["top_n"]=10
    if name=="get_device_history_tool": args.update(assetnum=asset,limit=50)
    if name=="get_integrated_analysis_tool": args.update(assetnum=asset,history_limit=50)
    if name=="search_maintenance_manual_tool": args.update(query=state.get("query",""),assetnum=asset)
    if name=="predict_device_fault_type_tool": args.update(assetnum=asset,window_days=_extract_window_days(state.get("query","")),top_k=3)
    return args
def _item(name:str,evidence:str,state:AfcAgentState,asset:str|None)->dict[str,Any]:
    return {"tool_name":name,"args":_tool_args(name,state,asset),"purpose":f"补充 {evidence} 证据","expected_evidence":[evidence]}
def _plan_by_route(u:dict[str,Any],state:AfcAgentState)->dict[str,Any]:
    route=u.get("route","direct_chat"); goal=u.get("business_goal"); asset=u.get("assetnum"); q=state.get("query","")
    modes={"direct_chat":"direct_chat","capability_query":"capability_intro","conversation":"conversational","needs_clarification":"ask_for_assetnum","unsupported":"unsupported"}
    if route in modes:
        p=_policy(q,general=route=="conversation")
        return ToolPlan(tool_calls=[],use_existing_evidence=bool(state.get("evidence_packet",{}).get("available_evidence")),reason="当前路由不需要业务工具",answer_mode=modes[route],answer_policy=p).model_dump()
    if route=="business_device" and not asset:
        return ToolPlan(tool_calls=[],reason="缺少设备编号",answer_mode="ask_for_assetnum",answer_policy=_policy(q)).model_dump()
    if goal in _FIXED:
        name,ev=_FIXED[goal]
        expected=[ev]
        if goal=="full_diagnosis": expected=["device_profile","history_summary","risk_prediction","maintenance_advice"]
        call=_item(name,expected[0],state,asset); call["expected_evidence"]=expected
        return ToolPlan(tool_calls=[call],reason="固定业务目标使用明确工具映射",answer_mode="evidence_based",answer_policy=_policy(q,grounded=True)).model_dump()
    return ToolPlan(tool_calls=[],reason="无法确定工具",answer_mode="ask_for_assetnum",answer_policy=_policy(q)).model_dump()

TOOL_PLAN_SYSTEM="""你是 AFC 智能运维 Agent 的开放分析工具规划器。只输出 ToolPlan JSON。只能使用给定白名单工具；不得重复调用参数相同且已成功的工具；优先补齐 missing_evidence；每个调用必须给出 purpose 和 expected_evidence；不得超过最大调用数；缺设备编号时不得规划设备工具。不要回答用户问题。"""
def _descriptions()->str: return "\n".join(f"- {n}: {getattr(t,'description','')}" for n,t in TOOL_BY_NAME.items())
def _prompt(state:AfcAgentState)->str:
    ep=state.get("evidence_packet",{})
    payload={"用户原问题":state.get("query",""),"query_understanding":state.get("query_understanding",{}),"evidence_packet":ep,"available_evidence":ep.get("available_evidence",[]),"missing_evidence":ep.get("missing_evidence",[]),"上一轮 evidence_evaluation":state.get("evidence_evaluation",{}),"tool_trace":state.get("tool_trace",[]),"已成功工具":[x.get("tool") for x in state.get("tool_trace",[]) if x.get("status")=="success"],"已失败工具":[x.get("tool") for x in state.get("tool_trace",[]) if x.get("status")=="error"],"工具循环次数":state.get("tool_loop_count",0)}
    return f"可用工具（最多 {MAX_TOOL_CALLS} 个调用）：\n{_descriptions()}\n\n规划上下文：\n{json.dumps(payload,ensure_ascii=False,indent=2,default=str)}\n\n只输出 ToolPlan JSON。"
def _fallback_open(state:AfcAgentState)->dict[str,Any]:
    u=state.get("query_understanding",{}); asset=u.get("assetnum"); ep=state.get("evidence_packet",{}); missing=state.get("evidence_evaluation",{}).get("missing_evidence") or ep.get("missing_evidence") or ["risk_prediction","history_summary"]
    successful={x.get("tool") for x in state.get("tool_trace",[]) if x.get("status")=="success"}
    calls=[]
    for ev in missing:
        name=_MISSING_TOOL.get(ev)
        if name and name not in successful and len(calls)<MAX_TOOL_CALLS: calls.append(_item(name,ev,state,asset))
    return ToolPlan(tool_calls=calls,use_existing_evidence=bool(ep.get("available_evidence")),reason="按缺失证据进行开放分析规则兜底规划",answer_mode="evidence_based",answer_policy=_policy(state.get("query",""),grounded=True)).model_dump()
def _sanitize(plan:dict[str,Any],state:AfcAgentState)->dict[str,Any]:
    u=state.get("query_understanding",{}); asset=u.get("assetnum"); successful={(x.get("tool"),json.dumps(x.get("args",{}),sort_keys=True,ensure_ascii=False)) for x in state.get("tool_trace",[]) if x.get("status")=="success"}; calls=[]
    for c in plan.get("tool_calls",[])[:MAX_TOOL_CALLS]:
        name=c.get("tool_name"); args=dict(c.get("args",{}))
        if name not in TOOL_BY_NAME or (name in _ASSET_REQUIRED_TOOLS and not asset): continue
        if name in _ASSET_REQUIRED_TOOLS: args.setdefault("assetnum",asset)
        if (name,json.dumps(args,sort_keys=True,ensure_ascii=False)) in successful: continue
        c["args"]=args; calls.append(c)
    plan["tool_calls"]=calls; plan["answer_mode"]="evidence_based"; plan["answer_policy"]=_policy(state.get("query",""),grounded=True).model_dump()
    return ToolPlan.model_validate(plan).model_dump()
def plan_tools_node(state:AfcAgentState)->dict[str,Any]:
    u=state.get("query_understanding",{}); errors=list(state.get("errors",[]))
    if u.get("business_goal")!="open_analysis": plan=_plan_by_route(u,state)
    else:
        try:
            prompt=_prompt(state); result=call_llm_json(llm=get_parse_llm(),prompt=prompt,schema=ToolPlan,system_prompt=TOOL_PLAN_SYSTEM,max_repair_attempts=2,repair_context=prompt); plan=_sanitize(result.model_dump(),state)
            if not plan["tool_calls"] and state.get("evidence_evaluation",{}).get("missing_evidence"): plan=_fallback_open(state)
        except Exception as exc:
            errors.append(f"LLM 工具规划不可用，使用规则兜底：{exc}"); plan=_fallback_open(state)
    return {"tool_plan":plan,"answer_policy":plan["answer_policy"],"errors":errors}
