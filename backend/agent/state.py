"""LangGraph Agent 状态定义。

v0.3 升级：新增八节点 Agent 所需的全部状态字段。

状态分类：
1. 跨轮记忆：last_assetnum / last_task_type / last_time_window / messages 等。
2. v0.3 节点状态：context_packet / query_understanding / tool_plan / evidence_packet 等。
3. 旧 API 字段只应在 run_diagnosis() 返回层回填，不进入八节点内部主逻辑。
"""

from typing import Any, Optional

from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict


class AfcAgentState(TypedDict, total=False):
    """AFC 诊断 Agent 的 LangGraph 状态（v0.3 升级版）。"""

    # ── 用户输入 ──
    query: str

    # ── v0.3 新增：prepare_context_node 输出 ──
    context_packet: dict[str, Any]

    # ── v0.3 新增：understand_query_node 输出 ──
    query_understanding: dict[str, Any]

    # ── v0.3 新增：plan_tools_node 输出 ──
    tool_plan: dict[str, Any]

    # ── v0.3 新增：execute_tools_node 输出 ──
    tool_results: dict[str, Any]
    tool_trace: list[dict[str, Any]]

    # ── v0.3 新增：merge_evidence_node 输出 ──
    evidence_packet: dict[str, Any]

    # ── v0.3 新增：evaluate_evidence_node 输出 ──
    evidence_evaluation: dict[str, Any]

    # ── v0.3 新增：answer_policy ──
    answer_policy: dict[str, Any]

    # ── v0.3 新增：generate_answer_node 输出 ──
    final_answer: str

    # ── v0.3 新增：update_memory_node 输出 ──
    memory_update: dict[str, Any]

    # ── v0.3 新增：工具循环控制 ──
    tool_loop_count: int

    # ── v0.3 新增：证据摘要（跨轮）──
    last_evidence_summary: dict[str, Any]

    # ── 异常与可观测 ──
    errors: list[str]

    # ── 多轮对话上下文（checkpointer 持久化）──
    messages: list[BaseMessage]
    last_assetnum: Optional[str]
    last_task_type: Optional[str]
    last_time_window: Optional[str]
    last_tool_results_summary: dict[str, Any]


# ── 能力边界常量 ──────────────────────────────────────────────

CAPABILITY_BOUNDARY: dict[str, Any] = {
    "can_predict_exact_failure_date": False,
    "can_predict_risk_window": True,
    "can_confirm_root_cause": False,
    "can_provide_inspection_suggestions": True,
    "can_retrieve_maintenance_manual": False,  # RAG 实现后变为 True
    "risk_prediction_is_probabilistic": True,
    "maintenance_advice_is_directional": True,
    "data_dependent_on_uploaded_workorders": True,
}


# ── 否认全局问题设备 ──────────────────────────────────────────

NO_DEVICE_TASKS = {"capability_query", "data_overview", "high_risk_ranking"}


def create_initial_state(query: str) -> AfcAgentState:
    """创建一个干净的 v0.3 初始状态。"""
    return {
        # 用户输入
        "query": query.strip(),
        # v0.3 新增
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
        "last_evidence_summary": {},
        "errors": [],
        "messages": [],
        "last_assetnum": None,
        "last_task_type": None,
        "last_time_window": None,
        "last_tool_results_summary": {},
    }
