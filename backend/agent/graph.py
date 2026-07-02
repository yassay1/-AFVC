"""LangGraph 工作流 —— AFCDiagnosisAgent 编排层。

工作流：
START → parse_question → resolve_asset → route_task
→ execute_tools → merge_evidence → generate_report → END
"""

from typing import Literal

from langgraph.graph import StateGraph, END

from backend.agent.state import AfcAgentState, create_initial_state
from backend.agent.nodes import (
    parse_question_node,
    resolve_asset_node,
    route_task_node,
    execute_tools_node,
    merge_evidence_node,
    generate_report_node,
)


def _should_continue(state: AfcAgentState) -> Literal["route_task_node", "generate_report_node"]:
    """条件边：设备校验通过则继续路由，失败则跳过工具调用直接报告。"""
    asset_exists = state.get("asset_exists", True)
    task_type = state.get("task_type", "full_diagnosis")

    # 全局类任务不需要设备，直接路由
    no_device_tasks = {"data_overview", "high_risk_ranking"}
    if task_type in no_device_tasks:
        return "route_task_node"

    if not asset_exists:
        # 设备不存在或未识别，跳过工具调用
        return "generate_report_node"

    return "route_task_node"


def create_agent_graph() -> StateGraph:
    """创建 AFCDiagnosisAgent 的 LangGraph 工作流。

    Returns:
        已编译的 StateGraph 实例，可通过 .invoke(state) 运行。
    """
    workflow = StateGraph(AfcAgentState)

    # 注册节点
    workflow.add_node("parse_question_node", parse_question_node)
    workflow.add_node("resolve_asset_node", resolve_asset_node)
    workflow.add_node("route_task_node", route_task_node)
    workflow.add_node("execute_tools_node", execute_tools_node)
    workflow.add_node("merge_evidence_node", merge_evidence_node)
    workflow.add_node("generate_report_node", generate_report_node)

    # 设置入口
    workflow.set_entry_point("parse_question_node")

    # 普通边
    workflow.add_edge("parse_question_node", "resolve_asset_node")

    # 条件边：校验通过 → 路由；失败 → 直接生成错误报告
    workflow.add_conditional_edges(
        "resolve_asset_node",
        _should_continue,
        {
            "route_task_node": "route_task_node",
            "generate_report_node": "generate_report_node",
        },
    )

    # 后续普通边
    workflow.add_edge("route_task_node", "execute_tools_node")
    workflow.add_edge("execute_tools_node", "merge_evidence_node")
    workflow.add_edge("merge_evidence_node", "generate_report_node")
    workflow.add_edge("generate_report_node", END)

    return workflow.compile()


# ── 顶层调用入口 ──────────────────────────────────────────────

_AGENT_GRAPH = None


def get_agent_graph():
    """获取（懒加载的）Agent 工作流实例。"""
    global _AGENT_GRAPH
    if _AGENT_GRAPH is None:
        _AGENT_GRAPH = create_agent_graph()
    return _AGENT_GRAPH


def run_diagnosis(query: str) -> dict:
    """运行 AFC 诊断 Agent，返回完整诊断结果。

    这是外部（FastAPI / 测试）调用 Agent 的统一入口。

    Args:
        query: 用户的自然语言问题。

    Returns:
        包含解析、工具调用和最终报告的完整诊断结果。
    """
    graph = get_agent_graph()
    initial_state = create_initial_state(query)

    try:
        final_state = graph.invoke(initial_state)
    except Exception as e:
        return {
            "status": "error",
            "query": query,
            "assetnum": None,
            "task_type": None,
            "selected_tools": [],
            "tool_results": {},
            "final_answer": f"Agent 工作流执行异常：{str(e)}",
            "errors": [str(e)],
        }

    return {
        "status": "success",
        "query": final_state.get("query", query),
        "assetnum": final_state.get("assetnum"),
        "task_type": final_state.get("task_type"),
        "time_window": final_state.get("time_window"),
        "selected_tools": final_state.get("selected_tools", []),
        "tool_results": final_state.get("tool_results", {}),
        "final_answer": final_state.get("final_answer", ""),
        "errors": final_state.get("errors", []),
    }
