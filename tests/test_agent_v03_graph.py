"""Eight-node Agent workflow tests."""

import pytest

from backend.agent.graph import create_agent_graph, run_diagnosis
from backend.agent.state import create_initial_state

KNOWN_ASSETNUM = "1000029970"
SECOND_ASSETNUM = "EX011115"

Q_FULL = f"\u5e2e\u6211\u5206\u6790\u8bbe\u5907 {KNOWN_ASSETNUM}"
Q_CAPABILITY = "\u4f60\u4f1a\u5e72\u4ec0\u4e48\uff1f"
Q_OVERVIEW = "\u8fd9\u6279\u5de5\u5355\u6574\u4f53\u60c5\u51b5\u600e\u4e48\u6837"
Q_RANKING = "\u5f53\u524d\u9ad8\u98ce\u9669\u8bbe\u5907\u6709\u54ea\u4e9b"
Q_RISK = f"\u8bbe\u5907 {KNOWN_ASSETNUM} \u672a\u676530\u5929\u98ce\u9669\u9ad8\u5417"
Q_HISTORY = f"\u8bbe\u5907 {KNOWN_ASSETNUM} \u6700\u8fd1\u6709\u54ea\u4e9b\u6545\u969c"
Q_ADVICE = f"\u8bbe\u5907 {KNOWN_ASSETNUM} \u5e94\u8be5\u5148\u68c0\u67e5\u4ec0\u4e48"
Q_FOLLOWUP_HISTORY = "\u90a3\u5b83\u6700\u8fd1\u6709\u54ea\u4e9b\u6545\u969c\uff1f"
Q_SWITCH = f"\u6362\u6210 {SECOND_ASSETNUM}"
Q_MISSING = "\u5e2e\u6211\u5206\u6790\u98ce\u9669"


@pytest.fixture(autouse=True)
def disable_llm(monkeypatch):
    def fail():
        raise RuntimeError("disable llm in tests")

    monkeypatch.setattr("backend.agent.nodes.understand_query.get_parse_llm", fail)
    monkeypatch.setattr("backend.agent.nodes.plan_tools.get_parse_llm", fail)
    monkeypatch.setattr("backend.agent.nodes.evaluate_evidence.get_parse_llm", fail)
    monkeypatch.setattr("backend.agent.nodes.generate_answer.get_report_llm", fail)


def test_graph_compiles_with_eight_nodes():
    assert create_agent_graph() is not None


def test_graph_invoke_single_turn():
    graph = create_agent_graph()
    state = create_initial_state(Q_FULL)
    final_state = graph.invoke(state, config={"configurable": {"thread_id": "test-v03-graph-invoke"}})
    assert final_state["query_understanding"]["route"] == "business_device"
    assert final_state["query_understanding"]["business_goal"] == "full_diagnosis"
    assert "final_answer" in final_state


def test_run_diagnosis_full_diagnosis():
    result = run_diagnosis(Q_FULL, session_id="test-v03-full")
    assert result["status"] == "success"
    assert result["assetnum"] == KNOWN_ASSETNUM
    assert result["route"] == "business_device"
    assert result["business_goal"] == "full_diagnosis"
    assert "task" + "_type" not in result


def test_capability_query():
    result = run_diagnosis(Q_CAPABILITY, session_id="test-v03-capability")
    assert result["status"] == "success"
    assert result["route"] == "capability_query"
    assert result["business_goal"] is None


def test_data_overview():
    result = run_diagnosis(Q_OVERVIEW, session_id="test-v03-overview")
    assert result["status"] == "success"
    assert result["route"] == "business_global"
    assert result["business_goal"] == "data_overview"


def test_high_risk_ranking():
    result = run_diagnosis(Q_RANKING, session_id="test-v03-ranking")
    assert result["status"] == "success"
    assert result["route"] == "business_global"
    assert result["business_goal"] == "high_risk_ranking"


def test_risk_route():
    result = run_diagnosis(Q_RISK, session_id="test-v03-risk")
    assert result["status"] == "success"
    assert result["route"] == "business_device"
    assert result["business_goal"] == "device_risk"


def test_history_route():
    result = run_diagnosis(Q_HISTORY, session_id="test-v03-history")
    assert result["status"] == "success"
    assert result["route"] == "business_device"
    assert result["business_goal"] == "device_history"


def test_advice_route():
    result = run_diagnosis(Q_ADVICE, session_id="test-v03-advice")
    assert result["status"] == "success"
    assert result["route"] == "business_device"
    assert result["business_goal"] == "device_advice"


def test_multi_turn_pronoun_inherit():
    sid = "test-v03-mt-pronoun"
    first = run_diagnosis(Q_FULL, session_id=sid)
    assert first["assetnum"] == KNOWN_ASSETNUM

    second = run_diagnosis(Q_FOLLOWUP_HISTORY, session_id=sid)
    assert second["assetnum"] == KNOWN_ASSETNUM
    assert second["business_goal"] == "device_history"


def test_multi_turn_device_switch():
    sid = "test-v03-mt-switch"
    first = run_diagnosis(Q_FULL, session_id=sid)
    assert first["assetnum"] == KNOWN_ASSETNUM

    second = run_diagnosis(Q_SWITCH, session_id=sid)
    assert second["assetnum"] == SECOND_ASSETNUM
    assert second["route"] == "business_device"


def test_missing_asset_clarification():
    result = run_diagnosis(Q_MISSING, session_id="test-v03-missing-asset")
    assert result["route"] == "needs_clarification"
    assert result["business_goal"] is None
    assert result["selected_tools"] == []
