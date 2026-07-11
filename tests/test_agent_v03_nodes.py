"""Node-level tests for route + business_goal Agent semantics."""

import pytest

from backend.agent.nodes.execute_tools import execute_tools_node
from backend.agent.nodes.generate_answer import generate_answer_node
from backend.agent.nodes.merge_evidence import merge_evidence_node
from backend.agent.nodes.plan_tools import plan_tools_node
from backend.agent.nodes.prepare_context import prepare_context_node
from backend.agent.nodes.understand_query import (
    _detect_business_goal,
    _has_device_switch,
    _has_reference_pronoun,
    understand_query_node,
)
from backend.agent.nodes.update_memory import update_memory_node
from backend.agent.state import CAPABILITY_BOUNDARY, create_initial_state

KNOWN_ASSETNUM = "1000029970"
Q_RISK = f"\u8bbe\u5907 {KNOWN_ASSETNUM} \u672a\u676530\u5929\u98ce\u9669\u9ad8\u5417"
Q_HISTORY = f"\u8bbe\u5907 {KNOWN_ASSETNUM} \u6700\u8fd1\u6709\u54ea\u4e9b\u6545\u969c"
Q_ADVICE = f"\u8bbe\u5907 {KNOWN_ASSETNUM} \u5e94\u8be5\u5148\u68c0\u67e5\u4ec0\u4e48"
Q_MANUAL = f"\u8bbe\u5907 {KNOWN_ASSETNUM} \u6309\u7ef4\u4fee\u624b\u518c\u67e5\u54ea\u91cc"
Q_FAULT_TYPE = f"\u8bbe\u5907 {KNOWN_ASSETNUM} \u53ef\u80fd\u53d1\u751f\u4ec0\u4e48\u6545\u969c"
Q_FOLLOWUP_HISTORY = "\u90a3\u5b83\u6700\u8fd1\u6709\u54ea\u4e9b\u6545\u969c"
Q_SWITCH = "\u6362\u6210 EX011115"
Q_MISSING = "\u5e2e\u6211\u67e5\u4e00\u4e0b\u98ce\u9669"
Q_CAPABILITY = "\u4f60\u4f1a\u5e72\u4ec0\u4e48"
Q_GLOBAL = "\u5f53\u524d\u9ad8\u98ce\u9669\u8bbe\u5907\u6709\u54ea\u4e9b"


@pytest.fixture(autouse=True)
def disable_llm(monkeypatch):
    def fail():
        raise RuntimeError("disable llm in tests")

    monkeypatch.setattr("backend.agent.nodes.understand_query.get_parse_llm", fail)
    monkeypatch.setattr("backend.agent.nodes.plan_tools.get_parse_llm", fail)
    monkeypatch.setattr("backend.agent.nodes.generate_answer.get_report_llm", fail)


def _context(active_assetnum=None, active_route=None, active_business_goal=None):
    return {
        "active_assetnum": active_assetnum,
        "active_route": active_route,
        "active_business_goal": active_business_goal,
        "capability_boundary": CAPABILITY_BOUNDARY,
        "known_entities": [active_assetnum] if active_assetnum else [],
        "recent_messages": [],
    }


def test_prepare_context_uses_route_memory():
    state = create_initial_state(Q_FOLLOWUP_HISTORY)
    state["last_assetnum"] = KNOWN_ASSETNUM
    state["last_route"] = "business_device"
    state["last_business_goal"] = "full_diagnosis"

    packet = prepare_context_node(state)["context_packet"]
    assert packet["active_assetnum"] == KNOWN_ASSETNUM
    assert packet["active_route"] == "business_device"
    assert packet["active_business_goal"] == "full_diagnosis"


def test_reference_and_switch_helpers():
    assert _has_reference_pronoun(Q_FOLLOWUP_HISTORY)
    assert not _has_reference_pronoun(Q_RISK)
    assert _has_device_switch(Q_SWITCH) == "EX011115"


@pytest.mark.parametrize(
    "query,goal",
    [
        (Q_RISK, "device_risk"),
        (Q_HISTORY, "device_history"),
        (Q_ADVICE, "device_advice"),
        (Q_MANUAL, "manual_search"),
        (Q_FAULT_TYPE, "fault_type_prediction"),
    ],
)
def test_detect_business_goal(query, goal):
    assert _detect_business_goal(query) == goal


def test_understand_missing_asset():
    state = create_initial_state(Q_MISSING)
    state["context_packet"] = _context()
    understanding = understand_query_node(state)["query_understanding"]
    assert understanding["route"] == "needs_clarification"
    assert understanding["business_goal"] is None
    assert "task" + "_type" not in understanding


def test_understand_history_followup_inherits_asset():
    state = create_initial_state(Q_FOLLOWUP_HISTORY)
    state["context_packet"] = _context(KNOWN_ASSETNUM, "business_device", "full_diagnosis")
    understanding = understand_query_node(state)["query_understanding"]
    assert understanding["assetnum"] == KNOWN_ASSETNUM
    assert understanding["route"] == "business_device"
    assert understanding["business_goal"] == "device_history"


def test_plan_risk_route():
    state = create_initial_state(Q_RISK)
    state["query_understanding"] = {
        "route": "business_device",
        "business_goal": "device_risk",
        "assetnum": KNOWN_ASSETNUM,
        "needs_asset": True,
        "needs_tools": True,
    }
    plan = plan_tools_node(state)["tool_plan"]
    assert [c["tool_name"] for c in plan["tool_calls"]] == ["predict_device_risk_tool"]


def test_plan_history_route():
    state = create_initial_state(Q_HISTORY)
    state["query_understanding"] = {
        "route": "business_device",
        "business_goal": "device_history",
        "assetnum": KNOWN_ASSETNUM,
        "needs_asset": True,
        "needs_tools": True,
    }
    plan = plan_tools_node(state)["tool_plan"]
    assert [c["tool_name"] for c in plan["tool_calls"]] == ["get_device_history_tool"]


def test_plan_global_high_risk():
    state = create_initial_state(Q_GLOBAL)
    state["query_understanding"] = {
        "route": "business_global",
        "business_goal": "high_risk_ranking",
        "assetnum": None,
        "needs_asset": False,
        "needs_tools": True,
    }
    plan = plan_tools_node(state)["tool_plan"]
    assert [c["tool_name"] for c in plan["tool_calls"]] == ["get_high_risk_devices_tool"]


def test_execute_merge_generate_for_no_tool_mode():
    state = create_initial_state(Q_CAPABILITY)
    state["query_understanding"] = {"route": "capability_query", "business_goal": None}
    state["tool_plan"] = {"tool_calls": [], "answer_mode": "capability_intro"}

    state.update(execute_tools_node(state))
    state.update(merge_evidence_node(state))
    answer = generate_answer_node(state)
    assert answer["final_answer"]


def test_update_memory_stores_route_goal():
    state = create_initial_state(Q_HISTORY)
    state["query_understanding"] = {
        "route": "business_device",
        "business_goal": "device_history",
        "assetnum": KNOWN_ASSETNUM,
        "time_window": None,
    }
    state["final_answer"] = "ok"
    result = update_memory_node(state)
    assert result["last_assetnum"] == KNOWN_ASSETNUM
    assert result["last_route"] == "business_device"
    assert result["last_business_goal"] == "device_history"
