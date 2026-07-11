"""Agent fault-type prediction tests."""

from typing import get_args

import pytest

from backend.agent.nodes.plan_tools import _extract_window_days, _plan_by_route
from backend.agent.nodes.understand_query import _detect_business_goal
from backend.agent.schemas import EvidencePacket, QueryUnderstanding
from backend.agent.tools import ALL_TOOLS, TOOL_BY_NAME, predict_device_fault_type_tool


def test_fault_type_tool_registered():
    assert "predict_device_fault_type_tool" in TOOL_BY_NAME
    assert "predict_device_fault_type_tool" in [tool.name for tool in ALL_TOOLS]


def test_fault_type_tool_invoke_handles_known_device():
    result = predict_device_fault_type_tool.invoke(
        {"assetnum": "1000029970", "window_days": 30, "top_k": 3}
    )
    assert result["status"] in {"success", "error", "unavailable"}


def test_business_goal_literal_includes_fault_type():
    goals = get_args(QueryUnderstanding.model_fields["business_goal"].annotation)
    assert "fault_type_prediction" in goals


@pytest.mark.parametrize(
    "query",
    [
        "\u8bbe\u59071000029970\u4f1a\u53d1\u751f\u4ec0\u4e48\u6545\u969c",
        "1000029970\u6700\u53ef\u80fd\u53d1\u751f\u4ec0\u4e48\u6545\u969c",
        "EX011115\u53ef\u80fd\u51fa\u73b0\u4ec0\u4e48\u9519\u8bef",
        "1000029970\u54ea\u4e2a\u6a21\u5757\u6700\u53ef\u80fd\u6545\u969c",
    ],
)
def test_detect_fault_type_intent(query):
    assert _detect_business_goal(query) == "fault_type_prediction"


def test_fault_type_prediction_plan():
    query_understanding = {
        "route": "business_device",
        "business_goal": "fault_type_prediction",
        "assetnum": "1000029970",
    }
    state = {"query": "1000029970\u672a\u676530\u5929\u4f1a\u53d1\u751f\u4ec0\u4e48\u6545\u969c"}

    plan = _plan_by_route(query_understanding, state)
    assert plan["answer_mode"] == "evidence_based"
    assert [call["tool_name"] for call in plan["tool_calls"]] == [
        "predict_device_fault_type_tool"
    ]


def test_fault_type_missing_asset_asks_for_asset():
    query_understanding = {
        "route": "business_device",
        "business_goal": "fault_type_prediction",
        "assetnum": None,
    }
    plan = _plan_by_route(query_understanding, {"query": "\u4f1a\u53d1\u751f\u4ec0\u4e48\u6545\u969c"})
    assert plan["answer_mode"] == "ask_for_assetnum"


def test_window_days_extraction():
    assert _extract_window_days("\u672a\u676560\u5929\u4f1a\u53d1\u751f\u4ec0\u4e48\u6545\u969c") == 60
    assert _extract_window_days("\u672a\u676590\u5929\u98ce\u9669") == 90
    assert _extract_window_days("\u672a\u676530\u5929") == 30
    assert _extract_window_days("\u4f1a\u53d1\u751f\u4ec0\u4e48\u6545\u969c") == 30


def test_evidence_packet_has_fault_prediction_field():
    packet = EvidencePacket(fault_prediction={"status": "success"})
    assert packet.fault_prediction == {"status": "success"}


def test_missing_evidence_includes_fault_prediction():
    packet = EvidencePacket(
        assetnum="1000029970",
        fault_prediction=None,
        missing_evidence=["fault_prediction"],
    )
    assert "fault_prediction" in packet.missing_evidence
