"""Current AFC Agent graph smoke and business behavior tests."""

import pytest

from backend.agent.graph import run_diagnosis

KNOWN_ASSETNUM = "1000029970"

Q_RISK = f"\u8bbe\u5907 {KNOWN_ASSETNUM} \u672a\u676530\u5929\u98ce\u9669\u9ad8\u5417"
Q_HISTORY = f"\u8bbe\u5907 {KNOWN_ASSETNUM} \u6700\u8fd1\u6709\u54ea\u4e9b\u6545\u969c"
Q_GLOBAL = "\u5f53\u524d\u9ad8\u98ce\u9669\u8bbe\u5907\u6709\u54ea\u4e9b"
Q_FULL = f"\u5e2e\u6211\u5206\u6790\u8bbe\u5907 {KNOWN_ASSETNUM}"
Q_FOLLOWUP_HISTORY = "\u90a3\u5b83\u6700\u8fd1\u6709\u54ea\u4e9b\u6545\u969c"
Q_MISSING_RISK = "\u5e2e\u6211\u67e5\u4e00\u4e0b\u98ce\u9669"


@pytest.fixture(autouse=True)
def disable_llm(monkeypatch):
    def fail():
        raise RuntimeError("disable llm in tests")

    monkeypatch.setattr("backend.agent.nodes.understand_query.get_parse_llm", fail)
    monkeypatch.setattr("backend.agent.nodes.plan_tools.get_parse_llm", fail)
    monkeypatch.setattr("backend.agent.nodes.evaluate_evidence.get_parse_llm", fail)
    monkeypatch.setattr("backend.agent.nodes.generate_answer.get_report_llm", fail)


def test_device_risk_route_returns_route_and_goal():
    result = run_diagnosis(Q_RISK, session_id="test-current-risk")
    assert result["status"] == "success"
    assert result["route"] == "business_device"
    assert result["business_goal"] == "device_risk"
    assert "task" + "_type" not in result


def test_device_history_route_returns_route_and_goal():
    result = run_diagnosis(Q_HISTORY, session_id="test-current-history")
    assert result["status"] == "success"
    assert result["route"] == "business_device"
    assert result["business_goal"] == "device_history"


def test_global_query_returns_route_and_goal():
    result = run_diagnosis(Q_GLOBAL, session_id="test-current-global")
    assert result["status"] == "success"
    assert result["route"] == "business_global"
    assert result["business_goal"] == "high_risk_ranking"


def test_multi_turn_followup_uses_last_device():
    sid = "test-current-multiturn"
    first = run_diagnosis(Q_FULL, session_id=sid)
    assert first["status"] == "success"
    assert first["assetnum"] == KNOWN_ASSETNUM

    followup = run_diagnosis(Q_FOLLOWUP_HISTORY, session_id=sid)
    assert followup["status"] == "success"
    assert followup["assetnum"] == KNOWN_ASSETNUM
    assert followup["route"] == "business_device"
    assert followup["business_goal"] == "device_history"


def test_missing_asset_asks_for_clarification():
    result = run_diagnosis(Q_MISSING_RISK, session_id="test-current-missing")
    assert result["status"] == "success"
    assert result["route"] == "needs_clarification"
    assert result["business_goal"] is None
    assert result["selected_tools"] == []
