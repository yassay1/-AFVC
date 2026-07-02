"""LangGraph Agent 状态定义。

设计原则：
1. 每个节点只读写自己负责的字段；
2. 工具结果必须保留，确保最终报告可追溯；
3. 状态不要太复杂；
4. 多轮对话字段用于 checkpointer 恢复上下文，实现指代补全。
"""

from typing import TypedDict, Optional, Any
from langchain_core.messages import BaseMessage


class AfcAgentState(TypedDict, total=False):
    """AFC 诊断 Agent 的 LangGraph 状态。

    各节点职责：
    - parse_question_node → 写入 assetnum / task_type / time_window
    - resolve_asset_node → 校验 assetnum 是否存在
    - route_task_node   → 写入 selected_tools
    - execute_tools_node → 写入 tool_results
    - merge_evidence_node → 写入 evidence
    - generate_report_node → 写入 final_answer
    """

    # ── 用户输入 ──
    query: str

    # ── parse_question_node 输出 ──
    assetnum: Optional[str]
    task_type: Optional[str]
    time_window: Optional[str]

    # ── resolve_asset_node 输出 ──
    asset_exists: Optional[bool]

    # ── route_task_node 输出 ──
    selected_tools: list[str]

    # ── execute_tools_node 输出 ──
    tool_results: dict[str, Any]

    # ── merge_evidence_node 输出 ──
    evidence: dict[str, Any]

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
        "assetnum": None,
        "task_type": None,
        "time_window": None,
        "asset_exists": None,
        "selected_tools": [],
        "tool_results": {},
        "evidence": {},
        "final_answer": "",
        "errors": [],
        "messages": [],
        "last_assetnum": None,
        "last_task_type": None,
        "last_time_window": None,
        "last_tool_results_summary": {},
    }
