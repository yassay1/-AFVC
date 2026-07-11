"""Plan tool calls from route + business_goal."""

from __future__ import annotations

from typing import Any

from backend.agent.schemas import ToolPlan
from backend.agent.state import AfcAgentState, NO_TOOL_ROUTES
from backend.agent.tools import TOOL_BY_NAME
from backend.core.llm import get_parse_llm
from backend.agent.llm_json import call_llm_json

_ASSET_REQUIRED_TOOLS = {
    "get_integrated_analysis_tool",
    "predict_device_risk_tool",
    "get_device_history_tool",
    "get_maintenance_advice_tool",
    "predict_device_fault_type_tool",
}

ROUTE_TOOL_PLAN: dict[str, dict[str, Any]] = {
    "direct_chat": {
        "tool_names": [],
        "answer_mode": "direct_chat",
        "reason": "casual chat",
    },
    "capability_query": {
        "tool_names": [],
        "answer_mode": "capability_intro",
        "reason": "capability question",
    },
    "needs_clarification": {
        "tool_names": [],
        "answer_mode": "ask_for_assetnum",
        "reason": "missing device id",
    },
    "unsupported": {
        "tool_names": [],
        "answer_mode": "unsupported",
        "reason": "unsupported question",
    },
    "business_global__data_overview": {
        "tool_names": ["get_data_summary_tool"],
        "answer_mode": "evidence_based",
        "reason": "global data overview",
    },
    "business_global__high_risk_ranking": {
        "tool_names": ["get_high_risk_devices_tool"],
        "answer_mode": "evidence_based",
        "reason": "high risk device ranking",
    },
    "business_device__device_risk": {
        "tool_names": ["predict_device_risk_tool"],
        "answer_mode": "evidence_based",
        "reason": "device recurrence risk",
    },
    "business_device__device_history": {
        "tool_names": ["get_device_history_tool"],
        "answer_mode": "evidence_based",
        "reason": "device work-order history",
    },
    "business_device__device_advice": {
        "tool_names": ["get_maintenance_advice_tool"],
        "answer_mode": "evidence_based",
        "reason": "device maintenance advice",
    },
    "business_device__fault_type_prediction": {
        "tool_names": ["predict_device_fault_type_tool"],
        "answer_mode": "evidence_based",
        "reason": "device fault type prediction",
    },
    "business_device__full_diagnosis": {
        "tool_names": ["get_integrated_analysis_tool"],
        "answer_mode": "evidence_based",
        "reason": "full device diagnosis",
    },
    "business_device__manual_search": {
        "tool_names": ["search_maintenance_manual_tool"],
        "answer_mode": "evidence_based",
        "reason": "maintenance manual search",
    },
}


def _extract_window_days(query: str) -> int:
    import re

    for pattern in (r"(\d+)\s*天", r"未来\s*(\d+)", r"(\d+)\s*日"):
        match = re.search(pattern, query)
        if not match:
            continue
        days = int(match.group(1))
        from backend.domain.risk import SUPPORTED_PREDICTION_WINDOWS

        if days in SUPPORTED_PREDICTION_WINDOWS:
            return days
    return 30


def _build_tool_descriptions() -> str:
    return "\n".join(
        f"- {name}: {getattr(tool, 'description', '')}"
        for name, tool in TOOL_BY_NAME.items()
    )


def _plan_key(route: str, business_goal: str | None) -> str:
    if route in {"business_global", "business_device"}:
        return f"{route}__{business_goal}"
    return route


def _tool_args(tool_name: str, state: AfcAgentState, assetnum: str | None) -> dict[str, Any]:
    args: dict[str, Any] = {}
    if assetnum and tool_name in _ASSET_REQUIRED_TOOLS:
        args["assetnum"] = assetnum
    if tool_name in {"get_data_summary_tool", "get_high_risk_devices_tool"}:
        args["top_n"] = 10
    if tool_name == "get_device_history_tool":
        args["assetnum"] = assetnum
        args["limit"] = 50
    if tool_name == "get_integrated_analysis_tool":
        args["assetnum"] = assetnum
        args["history_limit"] = 50
    if tool_name == "search_maintenance_manual_tool":
        args["query"] = state.get("query", "")
        args["assetnum"] = assetnum
    if tool_name == "predict_device_fault_type_tool":
        args["assetnum"] = assetnum
        args["window_days"] = _extract_window_days(state.get("query", ""))
        args["top_k"] = 3
    return args


def _plan_by_route(
    query_understanding: dict[str, Any],
    state: AfcAgentState,
) -> dict[str, Any]:
    route = query_understanding.get("route", "direct_chat")
    business_goal = query_understanding.get("business_goal")
    assetnum = query_understanding.get("assetnum")

    if route == "business_device" and not assetnum:
        return {
            "tool_calls": [],
            "use_existing_evidence": False,
            "reason": "missing device id",
            "answer_mode": "ask_for_assetnum",
            "answer_policy": {"missing_asset": True},
        }

    plan = ROUTE_TOOL_PLAN.get(_plan_key(route, business_goal))
    if plan is None:
        if route in NO_TOOL_ROUTES:
            plan = ROUTE_TOOL_PLAN[route]
        elif assetnum:
            plan = ROUTE_TOOL_PLAN["business_device__full_diagnosis"]
        else:
            return {
                "tool_calls": [],
                "use_existing_evidence": False,
                "reason": f"unknown route/goal: {route}/{business_goal}",
                "answer_mode": "ask_for_assetnum",
                "answer_policy": {},
            }

    tool_calls = [
        {
            "tool_name": tool_name,
            "args": _tool_args(tool_name, state, assetnum),
            "purpose": plan["reason"],
            "expected_evidence": [],
        }
        for tool_name in plan.get("tool_names", [])
    ]

    return {
        "tool_calls": tool_calls,
        "use_existing_evidence": len(tool_calls) == 0,
        "reason": plan["reason"],
        "answer_mode": plan["answer_mode"],
        "answer_policy": {
            "must_not_predict_exact_failure_date": True,
            "must_answer_with_risk_window": business_goal in {"device_risk", "full_diagnosis"},
        },
    }


TOOL_PLAN_SYSTEM = """You plan AFC Agent tool calls.
Use only route and business_goal. Return JSON matching ToolPlan.
"""


def _build_plan_tools_prompt(query_understanding: dict[str, Any], evidence_packet: dict[str, Any]) -> str:
    return (
        f"Available tools:\n{_build_tool_descriptions()}\n\n"
        f"Query understanding:\n{query_understanding}\n\n"
        f"Existing evidence:\n{evidence_packet}\n"
    )


def plan_tools_node(state: AfcAgentState) -> dict[str, Any]:
    query_understanding = state.get("query_understanding", {})
    route = query_understanding.get("route", "direct_chat")
    assetnum = query_understanding.get("assetnum")
    needs_tools = query_understanding.get(
        "needs_tools", route in {"business_global", "business_device"}
    )
    errors: list[str] = list(state.get("errors", []))

    if route in NO_TOOL_ROUTES or (route == "business_device" and not assetnum):
        plan = _plan_by_route(query_understanding, state)
        return {"tool_plan": plan, "answer_policy": plan.get("answer_policy", {}), "errors": errors}

    tool_plan: dict[str, Any] | None = None
    try:
        llm = get_parse_llm()
        prompt = _build_plan_tools_prompt(
            query_understanding, state.get("evidence_packet", {})
        )
        result = call_llm_json(
            llm=llm,
            prompt=prompt,
            schema=ToolPlan,
            system_prompt=TOOL_PLAN_SYSTEM,
            max_repair_attempts=2,
            repair_context=prompt,
        )
        tool_plan = result.model_dump()
    except Exception as exc:
        errors.append(f"LLM tool planning unavailable, used rule fallback: {str(exc)}")

    if tool_plan is None or (not tool_plan.get("tool_calls") and needs_tools):
        tool_plan = _plan_by_route(query_understanding, state)

    business_goal = query_understanding.get("business_goal")
    if business_goal == "manual_search" or query_understanding.get("needs_rag"):
        has_rag = any(
            call.get("tool_name") == "search_maintenance_manual_tool"
            for call in tool_plan.get("tool_calls", [])
        )
        if not has_rag and "search_maintenance_manual_tool" in TOOL_BY_NAME:
            tool_plan.setdefault("tool_calls", []).append(
                {
                    "tool_name": "search_maintenance_manual_tool",
                    "args": {"query": state.get("query", ""), "assetnum": assetnum},
                    "purpose": "maintenance manual search",
                    "expected_evidence": ["manual_steps", "manual_cause"],
                }
            )

    if assetnum:
        for call in tool_plan.get("tool_calls", []):
            if call.get("tool_name") in _ASSET_REQUIRED_TOOLS:
                call.setdefault("args", {}).setdefault("assetnum", assetnum)

    return {
        "tool_plan": tool_plan,
        "answer_policy": tool_plan.get("answer_policy", {}),
        "errors": errors,
    }
