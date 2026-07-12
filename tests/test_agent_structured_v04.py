"""v0.4 structured four-LLM-node behavior with fake models."""
import json
from langchain_core.messages import AIMessage, SystemMessage

from backend.agent.graph import _should_get_more_tools
from backend.agent.nodes.evaluate_evidence import MAX_TOOL_LOOPS,evaluate_evidence_node
from backend.agent.nodes.generate_answer import DEFAULT_BOUNDARY,GROUNDED_ANSWER_SYSTEM,generate_answer_node,render_generated_answer
from backend.agent.nodes.merge_evidence import merge_evidence_node
from backend.agent.nodes.plan_tools import plan_tools_node
from backend.agent.nodes.understand_query import understand_query_node
from backend.agent.schemas import GeneratedAnswer
from backend.agent.state import create_initial_state

ASSET="1000029970"

class FakeLLM:
    def __init__(self,payload): self.payload=payload; self.calls=[]
    def invoke(self,messages):
        self.calls.append(messages)
        return AIMessage(content=json.dumps(self.payload,ensure_ascii=False))

def disable_understand(monkeypatch):
    monkeypatch.setattr("backend.agent.nodes.understand_query.get_parse_llm",lambda: (_ for _ in ()).throw(RuntimeError("off")))

def test_chat_capability_clarify_unsupported_structured(monkeypatch):
    disable_understand(monkeypatch)
    for query,route,mode,kind in [("你好","direct_chat","direct_chat","direct_chat"),("你能做什么？","capability_query","capability_intro","capability"),("帮我查设备风险","needs_clarification","ask_for_assetnum","clarification"),("推荐一部电影","unsupported","unsupported","unsupported")]:
        state=create_initial_state(query); state["context_packet"]={}
        state.update(understand_query_node(state)); state.update(plan_tools_node(state)); state.update(merge_evidence_node(state)); out=generate_answer_node(state)
        assert state["query_understanding"]["route"]==route
        assert state["tool_plan"]["answer_mode"]==mode and state["tool_plan"]["tool_calls"]==[]
        assert out["generated_answer"]["answer_type"]==kind
        assert out["final_answer"]==render_generated_answer(GeneratedAnswer.model_validate(out["generated_answer"]))

def test_general_explanation_uses_conversation_llm(monkeypatch):
    disable_understand(monkeypatch); fake=FakeLLM({"answer_type":"conversational","direct_answer":"风险是概率，不是确定事件。","key_evidence":[],"analysis":[],"recommendations":[],"sources":[],"boundary_notice":None,"follow_up_question":None})
    monkeypatch.setattr("backend.agent.nodes.generate_answer.get_conversation_llm",lambda:fake)
    state=create_initial_state("为什么风险高不代表一定故障？"); state["context_packet"]={}; state.update(understand_query_node(state)); state.update(plan_tools_node(state)); state.update(merge_evidence_node(state)); out=generate_answer_node(state)
    assert state["query_understanding"]["route"]=="conversation" and state["query_understanding"]["business_goal"]=="general_explanation"
    assert state["tool_plan"]["answer_mode"]=="conversational" and state["tool_plan"]["tool_calls"]==[] and fake.calls
    assert isinstance(fake.calls[0][0],SystemMessage)

def test_fixed_risk_plan_and_grounded_system_prompt(monkeypatch):
    fake=FakeLLM({"answer_type":"grounded","direct_answer":"未来30天存在复发风险。","key_evidence":["30天风险为60%"],"analysis":[],"recommendations":[],"sources":["predict_device_risk_tool","fake_tool"],"boundary_notice":None,"follow_up_question":None})
    monkeypatch.setattr("backend.agent.nodes.generate_answer.get_report_llm",lambda:fake)
    state=create_initial_state(f"设备 {ASSET} 未来30天风险怎么样？"); state["query_understanding"]={"route":"business_device","business_goal":"device_risk","assetnum":ASSET,"needs_asset":True}; state.update(plan_tools_node(state))
    assert [x["tool_name"] for x in state["tool_plan"]["tool_calls"]]==["predict_device_risk_tool"]
    state["evidence_packet"]={"assetnum":ASSET,"risk_prediction":{"risk_30d":.6},"available_evidence":["risk_prediction"],"sources":["predict_device_risk_tool"],"missing_evidence":[],"tool_errors":[]}; state["evidence_evaluation"]={"decision":"proceed","evidence_sufficient":True,"missing_evidence":[],"reason":"ok","evaluation_method":"rule"}
    out=generate_answer_node(state)
    assert isinstance(fake.calls[0][0],SystemMessage) and fake.calls[0][0].content==GROUNDED_ANSWER_SYSTEM
    assert out["generated_answer"]["boundary_notice"]==DEFAULT_BOUNDARY
    assert out["generated_answer"]["sources"]==["predict_device_risk_tool"]
    assert any("不存在的来源" in e for e in out["errors"])

def test_open_analysis_plan_and_replan_avoid_successful_tool(monkeypatch):
    plan_fake=FakeLLM({"tool_calls":[{"tool_name":"predict_device_risk_tool","args":{"assetnum":ASSET},"purpose":"风险","expected_evidence":["risk_prediction"]},{"tool_name":"get_device_history_tool","args":{"assetnum":ASSET,"limit":50},"purpose":"历史","expected_evidence":["history_summary"]}],"use_existing_evidence":False,"reason":"综合风险和历史","answer_mode":"evidence_based","answer_policy":{}})
    monkeypatch.setattr("backend.agent.nodes.plan_tools.get_parse_llm",lambda:plan_fake)
    state=create_initial_state(f"为什么设备 {ASSET} 风险高，但最近维修记录很少？"); state["query_understanding"]={"route":"business_device","business_goal":"open_analysis","assetnum":ASSET,"needs_asset":True}; first=plan_tools_node(state)["tool_plan"]
    assert {x["tool_name"] for x in first["tool_calls"]}=={"predict_device_risk_tool","get_device_history_tool"}
    state["tool_trace"]=[{"tool":"predict_device_risk_tool","args":{"assetnum":ASSET},"status":"success"}]; state["evidence_packet"]={"available_evidence":["risk_prediction"],"missing_evidence":["history_summary"]}; state["evidence_evaluation"]={"decision":"replan","evidence_sufficient":False,"missing_evidence":["history_summary"],"reason":"missing","evaluation_method":"llm"}
    replan_fake=FakeLLM({"tool_calls":[{"tool_name":"get_device_history_tool","args":{"assetnum":ASSET,"limit":50},"purpose":"补历史","expected_evidence":["history_summary"]}],"use_existing_evidence":True,"reason":"只补缺失证据","answer_mode":"evidence_based","answer_policy":{}}); monkeypatch.setattr("backend.agent.nodes.plan_tools.get_parse_llm",lambda:replan_fake)
    second=plan_tools_node(state)["tool_plan"]
    assert [x["tool_name"] for x in second["tool_calls"]]==["get_device_history_tool"]

def test_evaluation_stop_failures_and_loop_limit():
    state=create_initial_state("x"); state["tool_plan"]={"answer_mode":"evidence_based"}; state["query_understanding"]={"business_goal":"device_risk"}; state["evidence_packet"]={"sources":[],"tool_errors":[{"error_type":"tool_execution_error"}],"missing_evidence":["risk_prediction"]}
    ev=evaluate_evidence_node(state)["evidence_evaluation"]; assert ev["decision"]=="stop" and not ev["evidence_sufficient"]
    state["evidence_packet"]={"sources":["predict_device_risk_tool"],"tool_errors":[],"missing_evidence":["history_summary"]}; state["tool_loop_count"]=MAX_TOOL_LOOPS
    ev=evaluate_evidence_node(state)["evidence_evaluation"]; assert ev["decision"]=="stop" and not ev["evidence_sufficient"] and "最大工具循环" in ev["reason"]
    assert _should_get_more_tools({"evidence_evaluation":{"decision":"replan"},"tool_loop_count":1})=="plan_tools"
    assert _should_get_more_tools({"evidence_evaluation":{"decision":"replan"},"tool_loop_count":2})=="generate_answer"

def test_manual_grounded_then_template_fallback(monkeypatch):
    state=create_initial_state("按手册检查票卡模块"); state["query_understanding"]={"route":"business_device","business_goal":"manual_search","assetnum":ASSET,"needs_asset":True}; state.update(plan_tools_node(state)); state["evidence_packet"]={"assetnum":ASSET,"manual_evidence":[{"content":"检查读卡器","source":"manual.md"}],"available_evidence":["manual_evidence"],"sources":["search_maintenance_manual_tool"],"missing_evidence":[],"tool_errors":[]}; state["evidence_evaluation"]={"decision":"proceed","evidence_sufficient":True,"missing_evidence":[],"reason":"ok","evaluation_method":"rule"}
    fake=FakeLLM({"answer_type":"grounded","direct_answer":"按手册检查读卡器。","key_evidence":[],"analysis":[],"recommendations":[],"sources":["search_maintenance_manual_tool"],"boundary_notice":"边界","follow_up_question":None}); monkeypatch.setattr("backend.agent.nodes.generate_answer.get_report_llm",lambda:fake)
    assert generate_answer_node(state)["generated_answer"]["direct_answer"]=="按手册检查读卡器。"
    monkeypatch.setattr("backend.agent.nodes.generate_answer.get_report_llm",lambda:(_ for _ in ()).throw(RuntimeError("off")))
    out=generate_answer_node(state); assert out["generated_answer"]["answer_type"]=="grounded" and any("模板兜底" in e for e in out["errors"])

def test_multiturn_open_analysis_uses_active_asset(monkeypatch):
    disable_understand(monkeypatch); state=create_initial_state("那它为什么风险高？"); state["context_packet"]={"active_assetnum":ASSET}
    u=understand_query_node(state)["query_understanding"]
    assert u["assetnum"]==ASSET and u["route"]=="business_device"
