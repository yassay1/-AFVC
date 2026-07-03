"""LangGraph Agent 状态定义。

状态分为两类：
1. 跨轮记忆：last_assetnum / last_task_type / last_time_window / messages。
2. 本轮临时状态：intent / selected_tools / tool_results / tool_trace / evidence / errors。

run_diagnosis 每轮都会显式重置临时状态，避免 checkpointer 把上一轮工具结果、
错误和报告带入下一轮。
"""

from typing import TypedDict, Optional, Any
from langchain_core.messages import BaseMessage


class AfcAgentState(TypedDict, total=False):
    """AFC 诊断 Agent 的 LangGraph 状态。"""

    # ── 用户输入 ──
    query: str

    # ── parse_intent_node 输出 ──
    intent: dict[str, Any]
    assetnum: Optional[str]
    task_type: Optional[str]
    time_window: Optional[str]
    requires_asset: bool
    is_global: bool

    # ── reason_act_node 输出 ──
    asset_exists: Optional[bool]
    selected_tools: list[str]
    tool_results: dict[str, Any]
    evidence: dict[str, Any]
    tool_trace: list[dict[str, Any]]

    # ── generate_report_node 输出 ──
    final_answer: str

    # ── 异常与可观测 ──
    errors: list[str]

    # ── 多轮对话上下文（checkpointer 持久化）──
    messages: list[BaseMessage]
    last_assetnum: Optional[str]
    last_task_type: Optional[str]
    last_time_window: Optional[str]
    last_tool_results_summary: dict[str, Any]


def create_initial_state(query: str) -> AfcAgentState:
    """创建一个干净的初始状态。"""
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
        "evidence": {},
        "tool_trace": [],
        "final_answer": "",
        "errors": [],
        "messages": [],
        "last_assetnum": None,
        "last_task_type": None,
        "last_time_window": None,
        "last_tool_results_summary": {},
    }
