"""LangGraph 工作流：三节点混合型 AFC 诊断 Agent。

流程：
START -> parse_intent -> reason_act -> generate_report -> END

InMemorySaver 仅作为 MVP 级进程内记忆，用于演示多轮上下文。
后续可替换为 SQLite/PostgreSQL checkpointer，节点状态边界无需大改。
"""

from typing import Optional

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph

from backend.agent.nodes import generate_report_node, parse_intent_node, reason_act_node
from backend.agent.state import AfcAgentState


_CHECKPOINTER = InMemorySaver()
_AGENT_GRAPH = None


def create_agent_graph():
    """创建三节点 AFC 诊断 Agent 图。"""
    workflow = StateGraph(AfcAgentState)
    workflow.add_node("parse_intent", parse_intent_node)
    workflow.add_node("reason_act", reason_act_node)
    workflow.add_node("generate_report", generate_report_node)

    workflow.set_entry_point("parse_intent")
    workflow.add_edge("parse_intent", "reason_act")
    workflow.add_edge("reason_act", "generate_report")
    workflow.add_edge("generate_report", END)

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
        "intent": {},
        "assetnum": None,
        "task_type": None,
        "time_window": None,
        "requires_asset": True,
        "is_global": False,
        "asset_exists": None,
        "selected_tools": [],
        "tool_results": {},
        "tool_trace": [],
        "evidence": {},
        "final_answer": "",
        "errors": [],
    }


def run_diagnosis(query: str, session_id: Optional[str] = None) -> dict:
    """运行 AFC 诊断 Agent，返回完整可追踪结果。"""
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
            "task_type": None,
            "time_window": None,
            "selected_tools": [],
            "tool_results": {},
            "tool_trace": [],
            "evidence": {},
            "final_answer": f"Agent 工作流执行异常：{str(exc)}",
            "errors": [str(exc)],
            "session_id": session_id,
        }

    return {
        "status": "success",
        "query": final_state.get("query", query),
        "intent": final_state.get("intent", {}),
        "assetnum": final_state.get("assetnum"),
        "task_type": final_state.get("task_type"),
        "time_window": final_state.get("time_window"),
        "requires_asset": final_state.get("requires_asset"),
        "is_global": final_state.get("is_global"),
        "asset_exists": final_state.get("asset_exists"),
        "selected_tools": final_state.get("selected_tools", []),
        "tool_results": final_state.get("tool_results", {}),
        "tool_trace": final_state.get("tool_trace", []),
        "evidence": final_state.get("evidence", {}),
        "final_answer": final_state.get("final_answer", ""),
        "errors": final_state.get("errors", []),
        "session_id": session_id,
        "last_assetnum": final_state.get("last_assetnum"),
        "last_task_type": final_state.get("last_task_type"),
    }
