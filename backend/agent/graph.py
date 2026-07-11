"""LangGraph 工作流：八节点 LLM-driven Context-Aware Tool Agent。

流程（v0.3/v0.4）：
START → prepare_context → understand_query → plan_tools → execute_tools
→ merge_evidence → evaluate_evidence
  ├── need_more_tools 且 tool_loop_count < 2 → plan_tools（补充工具）
  └── ready_to_answer → generate_answer
→ update_memory → END

InMemorySaver 作为进程内记忆，用于演示多轮上下文。
"""

from __future__ import annotations

from typing import Optional

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph

from backend.agent.nodes.prepare_context import prepare_context_node
from backend.agent.nodes.understand_query import understand_query_node
from backend.agent.nodes.plan_tools import plan_tools_node
from backend.agent.nodes.execute_tools import execute_tools_node
from backend.agent.nodes.merge_evidence import merge_evidence_node
from backend.agent.nodes.evaluate_evidence import evaluate_evidence_node, MAX_TOOL_LOOPS
from backend.agent.nodes.generate_answer import generate_answer_node
from backend.agent.nodes.update_memory import update_memory_node
from backend.agent.state import AfcAgentState

_CHECKPOINTER = InMemorySaver()
_AGENT_GRAPH = None


def _should_get_more_tools(state: AfcAgentState) -> str:
    """条件边：判断是否需要补充工具。"""
    evaluation = state.get("evidence_evaluation", {})
    tool_loop_count = state.get("tool_loop_count", 0)

    if evaluation.get("need_more_tools") and tool_loop_count < MAX_TOOL_LOOPS:
        return "plan_tools"
    return "generate_answer"


def create_agent_graph():
    """创建八节点 AFC 诊断 Agent 图。"""
    workflow = StateGraph(AfcAgentState)

    # 添加节点
    workflow.add_node("prepare_context", prepare_context_node)
    workflow.add_node("understand_query", understand_query_node)
    workflow.add_node("plan_tools", plan_tools_node)
    workflow.add_node("execute_tools", execute_tools_node)
    workflow.add_node("merge_evidence", merge_evidence_node)
    workflow.add_node("evaluate_evidence", evaluate_evidence_node)
    workflow.add_node("generate_answer", generate_answer_node)
    workflow.add_node("update_memory", update_memory_node)

    # 定义边
    workflow.set_entry_point("prepare_context")
    workflow.add_edge("prepare_context", "understand_query")
    workflow.add_edge("understand_query", "plan_tools")
    workflow.add_edge("plan_tools", "execute_tools")
    workflow.add_edge("execute_tools", "merge_evidence")
    workflow.add_edge("merge_evidence", "evaluate_evidence")

    # 条件边：根据证据评估结果决定下一步
    workflow.add_conditional_edges(
        "evaluate_evidence",
        _should_get_more_tools,
        {
            "plan_tools": "plan_tools",
            "generate_answer": "generate_answer",
        },
    )
    workflow.add_edge("generate_answer", "update_memory")
    workflow.add_edge("update_memory", END)

    return workflow.compile(checkpointer=_CHECKPOINTER)


def get_agent_graph():
    """获取懒加载的 Agent 图实例。"""
    global _AGENT_GRAPH
    if _AGENT_GRAPH is None:
        _AGENT_GRAPH = create_agent_graph()
    return _AGENT_GRAPH


def _new_turn_state(query: str) -> dict:
    """构造本轮输入，显式清空所有临时字段。"""
    return {
        "query": query.strip(),
        "context_packet": {},
        "query_understanding": {},
        "tool_plan": {},
        "tool_results": {},
        "tool_trace": [],
        "evidence_packet": {},
        "evidence_evaluation": {},
        "answer_policy": {},
        "final_answer": "",
        "memory_update": {},
        "tool_loop_count": 0,
        "errors": [],
    }


def _api_evidence_from_packet(evidence_packet: dict) -> dict:
    """将 v0.3 evidence_packet 转成旧 API evidence 形状。"""
    return {
        "assetnum": evidence_packet.get("assetnum"),
        "device_info": evidence_packet.get("device_profile") or {},
        "history_summary": evidence_packet.get("history_summary") or {},
        "risk_prediction": evidence_packet.get("risk_prediction") or {},
        "warning_result": evidence_packet.get("warning") or {},
        "maintenance_advice": evidence_packet.get("maintenance_advice") or {},
        "data_overview": evidence_packet.get("data_overview") or {},
        "high_risk_devices": evidence_packet.get("high_risk_devices") or {},
        "sources": evidence_packet.get("sources", []),
        "tool_errors": evidence_packet.get("tool_errors", []),
    }


def _api_selected_tools(final_state: dict) -> list[str]:
    """从 v0.3 tool_trace/tool_plan 回填旧 API selected_tools。"""
    selected_tools: list[str] = []
    for trace in final_state.get("tool_trace", []):
        tool_name = trace.get("tool")
        if tool_name and tool_name not in selected_tools:
            selected_tools.append(tool_name)
    if selected_tools:
        return selected_tools
    for tc in final_state.get("tool_plan", {}).get("tool_calls", []):
        tool_name = tc.get("tool_name")
        if tool_name and tool_name not in selected_tools:
            selected_tools.append(tool_name)
    return selected_tools


def _api_asset_exists(query_understanding: dict, evidence_packet: dict, tool_trace: list[dict]) -> bool | None:
    """根据 v0.3.0 状态估算旧 API asset_exists。"""
    route = query_understanding.get("route", "")
    # 非设备路由 → 不需要 assetnum
    if route in {"direct_chat", "capability_query", "business_global", "unsupported"}:
        return True
    if route == "needs_clarification":
        return False
    if query_understanding.get("needs_asset") and not query_understanding.get("assetnum"):
        return False
    if evidence_packet.get("assetnum") and evidence_packet.get("sources"):
        return True
    if any(t.get("status") == "success" for t in tool_trace):
        return True
    if any(t.get("status") == "error" for t in tool_trace):
        return False
    return None


def run_diagnosis(query: str, session_id: Optional[str] = None) -> dict:
    """运行 AFC 诊断 Agent（v0.3 八节点版），返回完整可追踪结果。"""
    graph = get_agent_graph()

    if not session_id:
        import uuid
        session_id = f"single-{uuid.uuid4().hex[:12]}"

    config = {"configurable": {"thread_id": session_id}}
    input_state = _new_turn_state(query)

    try:
        final_state = graph.invoke(input_state, config=config)
    except Exception as exc:
        return {
            "status": "error",
            "query": query,
            "assetnum": None,
            "time_window": None,
            "selected_tools": [],
            "tool_results": {},
            "tool_trace": [],
            "evidence": {},
            "final_answer": f"Agent 工作流执行异常：{str(exc)}",
            "errors": [str(exc)],
            "session_id": session_id,
            "route": None,
            "business_goal": None,
        }

    query_understanding = final_state.get("query_understanding", {})
    evidence_packet = final_state.get("evidence_packet", {})
    tool_trace = final_state.get("tool_trace", [])
    tool_plan = final_state.get("tool_plan", {})
    selected_tools = _api_selected_tools(final_state)
    asset_exists = _api_asset_exists(query_understanding, evidence_packet, tool_trace)
    assetnum = query_understanding.get("assetnum") or evidence_packet.get("assetnum")
    route = query_understanding.get("route", "")

    return {
        "status": "success",
        "query": final_state.get("query", query),
        # 兼容字段
        "intent": query_understanding,
        "assetnum": assetnum,
        "time_window": query_understanding.get("time_window"),
        "requires_asset": query_understanding.get("needs_asset"),
        "is_global": route in {"capability_query", "business_global", "direct_chat", "unsupported"},
        "asset_exists": asset_exists,
        "selected_tools": selected_tools,
        "tool_results": final_state.get("tool_results", {}),
        "tool_trace": tool_trace,
        "evidence": _api_evidence_from_packet(evidence_packet),
        "final_answer": final_state.get("final_answer", ""),
        "errors": final_state.get("errors", []),
        "session_id": session_id,
        "last_assetnum": final_state.get("last_assetnum"),
        "last_route": final_state.get("last_route"),
        "last_business_goal": final_state.get("last_business_goal"),
        # v0.3.0 新字段
        "context_packet": final_state.get("context_packet", {}),
        "query_understanding": final_state.get("query_understanding", {}),
        "tool_plan": tool_plan,
        "evidence_packet": evidence_packet,
        "evidence_evaluation": final_state.get("evidence_evaluation", {}),
        # v0.3.0 路由字段
        "route": route,
        "business_goal": query_understanding.get("business_goal"),
        "answer_mode": tool_plan.get("answer_mode", ""),
    }
