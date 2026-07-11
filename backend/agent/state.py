"""LangGraph state for the current eight-node AFC Agent."""

from typing import Any, Optional

from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict


class AfcAgentState(TypedDict, total=False):
    query: str
    context_packet: dict[str, Any]
    query_understanding: dict[str, Any]
    tool_plan: dict[str, Any]
    tool_results: dict[str, Any]
    tool_trace: list[dict[str, Any]]
    evidence_packet: dict[str, Any]
    evidence_evaluation: dict[str, Any]
    answer_policy: dict[str, Any]
    final_answer: str
    memory_update: dict[str, Any]
    tool_loop_count: int
    last_evidence_summary: dict[str, Any]
    errors: list[str]

    messages: list[BaseMessage]
    last_assetnum: Optional[str]
    last_route: Optional[str]
    last_business_goal: Optional[str]
    last_time_window: Optional[str]
    last_tool_results_summary: dict[str, Any]


CAPABILITY_BOUNDARY: dict[str, Any] = {
    "can_predict_exact_failure_date": False,
    "can_predict_risk_window": True,
    "can_confirm_root_cause": False,
    "can_provide_inspection_suggestions": True,
    "can_retrieve_maintenance_manual": True,
    "risk_prediction_is_probabilistic": True,
    "maintenance_advice_is_directional": True,
    "data_dependent_on_uploaded_workorders": True,
}


NO_DEVICE_ROUTES = {
    "direct_chat",
    "capability_query",
    "business_global",
    "unsupported",
}

NO_TOOL_ROUTES = {
    "direct_chat",
    "capability_query",
    "needs_clarification",
    "unsupported",
}

CHAT_ROUTES = {
    "direct_chat",
    "capability_query",
    "unsupported",
}


def create_initial_state(query: str) -> AfcAgentState:
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
        "last_evidence_summary": {},
        "errors": [],
        "messages": [],
        "last_assetnum": None,
        "last_route": None,
        "last_business_goal": None,
        "last_time_window": None,
        "last_tool_results_summary": {},
    }
