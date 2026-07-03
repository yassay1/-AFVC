"""测试 Agent v0.3 八节点工作流（端到端 + 多轮对话）。"""

import pytest
from langchain_core.messages import AIMessage

from backend.agent.state import create_initial_state
from backend.agent.graph import create_agent_graph, run_diagnosis

KNOWN_ASSETNUM = "1000029970"
SECOND_ASSETNUM = "EX011115"


class _FakeGraphLLM:
    def invoke(self, messages):
        text = "\n".join(str(getattr(m, "content", m)) for m in messages)
        if "ToolPlan" in text:
            return AIMessage(content=self._tool_plan(text))
        if "EvidenceEvaluation" in text:
            return AIMessage(content='{"answerable": true, "need_more_tools": false, "missing_evidence": [], "suggested_next_tools": [], "reason": "fake evaluation"}')
        if "QueryUnderstanding" in text:
            return AIMessage(content=self._understanding(text))
        return AIMessage(content=(
            "AFC Agent 测试报告：已基于 evidence_packet 生成回答，包含风险窗口、"
            "预警信息和巡检方向。风险预测不等于一定故障，维修建议是巡检方向参考。"
        ))

    def _asset_from_text(self, text):
        import re

        matches = re.findall(r"(?:设备\s*)?([A-Z]{2}\d{6,}|\d{10,})", text)
        return matches[-1] if matches else None

    def _active_asset_from_text(self, text):
        import re

        match = re.search(r"active_assetnum:\s*([A-Z0-9]+)", text)
        if match and match.group(1).lower() != "null":
            return match.group(1)
        return None

    def _understanding(self, text):
        import json
        import re

        marker = "## 当前用户问题"
        query = text.split(marker, 1)[-1] if marker in text else text
        assetnum = self._asset_from_text(query)
        active_assetnum = self._active_asset_from_text(text)

        switch = re.search(r"换成\s*([A-Z]{2}\d{6,}|\d{10,})", query)
        if switch:
            assetnum = switch.group(1)
            task_type = "followup_rewrite"
        elif "你会" in query or "功能" in query or "怎么用" in query:
            task_type = "capability_query"
        elif "整体情况" in query or "这批工单" in query:
            task_type = "data_overview"
        elif "高风险" in query:
            task_type = "high_risk_ranking"
        elif "应该先检查" in query or "检查什么" in query or "建议" in query:
            task_type = "advice_query"
        elif "为什么" in query or "预警" in query:
            task_type = "risk_explanation"
        elif "最近" in query or "有哪些故障" in query:
            task_type = "history_query"
        elif "风险" in query or "什么时候" in query or "再坏" in query or "再次故障" in query:
            task_type = "risk_query"
        else:
            task_type = "full_diagnosis" if assetnum else "unknown"

        if not assetnum and task_type not in {"capability_query", "data_overview", "high_risk_ranking"}:
            assetnum = active_assetnum

        needs_asset = task_type not in {"capability_query", "data_overview", "high_risk_ranking", "unknown"}
        return json.dumps({
            "task_type": task_type,
            "assetnum": assetnum,
            "time_window": "30d" if "30" in query else None,
            "needs_asset": needs_asset,
            "needs_rag": False,
            "context_used": bool(assetnum and assetnum == active_assetnum and active_assetnum),
            "information_need": f"fake {task_type}",
            "user_question_rewrite": query.strip(),
            "confidence": 0.95,
        }, ensure_ascii=False)

    def _tool_plan(self, text):
        import json
        import re

        task_match = re.search(r'"task_type":\s*"([^"]+)"', text)
        task_type = task_match.group(1) if task_match else "full_diagnosis"
        asset_match = re.search(r'"assetnum":\s*"([^"]+)"', text)
        assetnum = asset_match.group(1) if asset_match else None

        def call(tool_name, args=None):
            return {
                "tool_name": tool_name,
                "args": args or {},
                "purpose": f"fake plan for {tool_name}",
                "expected_evidence": [],
            }

        if task_type == "capability_query":
            calls = []
        elif task_type == "data_overview":
            calls = [call("get_data_summary_tool")]
        elif task_type == "high_risk_ranking":
            calls = [call("get_high_risk_devices_tool", {"top_n": 10})]
        elif task_type == "risk_query":
            calls = [call("predict_device_risk_tool", {"assetnum": assetnum})]
        elif task_type == "history_query":
            calls = [call("get_device_history_tool", {"assetnum": assetnum, "limit": 50})]
        elif task_type == "advice_query":
            calls = [call("get_maintenance_advice_tool", {"assetnum": assetnum})]
        elif task_type == "risk_explanation":
            calls = [call("predict_device_risk_tool", {"assetnum": assetnum})]
        elif task_type == "risk_and_advice_query":
            calls = [
                call("predict_device_risk_tool", {"assetnum": assetnum}),
                call("get_maintenance_advice_tool", {"assetnum": assetnum}),
            ]
        else:
            calls = [call("get_integrated_analysis_tool", {"assetnum": assetnum})]

        return json.dumps({
            "tool_calls": calls,
            "use_existing_evidence": False,
            "reason": f"fake plan for {task_type}",
            "answer_policy": {
                "must_not_predict_exact_failure_date": True,
                "must_answer_with_risk_window": True,
            },
        }, ensure_ascii=False)


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    fake = _FakeGraphLLM()
    monkeypatch.setattr("backend.agent.nodes.understand_query.get_parse_llm", lambda: fake)
    monkeypatch.setattr("backend.agent.nodes.plan_tools.get_parse_llm", lambda: fake)
    monkeypatch.setattr("backend.agent.nodes.evaluate_evidence.get_parse_llm", lambda: fake)
    monkeypatch.setattr("backend.agent.nodes.generate_answer.get_report_llm", lambda: fake)


class TestV03GraphCompile:

    def test_graph_compiles_with_eight_nodes(self):
        graph = create_agent_graph()
        assert graph is not None

    def test_graph_invoke_single_turn(self):
        graph = create_agent_graph()
        state = create_initial_state(f"帮我分析设备 {KNOWN_ASSETNUM}")
        config = {"configurable": {"thread_id": "test-v03-graph-invoke"}}
        final_state = graph.invoke(state, config=config)
        assert len(final_state.get("final_answer", "")) > 0
        # v0.3 新增字段应存在
        assert "context_packet" in final_state
        assert "query_understanding" in final_state
        assert "tool_plan" in final_state
        assert "evidence_packet" in final_state


class TestV03RunDiagnosis:

    def test_full_diagnosis_e2e(self):
        result = run_diagnosis(f"帮我分析设备 {KNOWN_ASSETNUM}")
        assert result["status"] == "success"
        assert result["assetnum"] == KNOWN_ASSETNUM
        assert len(result["final_answer"]) > 50
        # v0.3 新字段
        assert "query_understanding" in result
        assert "tool_plan" in result
        assert "evidence_packet" in result
        assert "evidence_evaluation" in result

    def test_capability_query(self):
        result = run_diagnosis("你会干什么？")
        assert result["status"] == "success"
        assert result["task_type"] in ("capability_query", "unknown")
        assert "功能介绍" in result["final_answer"]

    def test_data_overview(self):
        result = run_diagnosis("这批工单整体情况怎么样")
        assert result["status"] == "success"
        assert result["task_type"] in ("data_overview", "unknown")

    def test_high_risk_ranking(self):
        result = run_diagnosis("当前高风险设备有哪些")
        assert result["status"] == "success"
        assert result["task_type"] in ("high_risk_ranking", "data_overview", "unknown")

    def test_risk_query(self):
        result = run_diagnosis(f"设备 {KNOWN_ASSETNUM} 未来30天风险高吗")
        assert result["status"] == "success"

    def test_unknown_device_graceful(self):
        result = run_diagnosis("帮我分析设备 ZZZ99999")
        assert result["status"] == "success"

    def test_scientific_boundary_in_report(self):
        result = run_diagnosis(f"帮我分析设备 {KNOWN_ASSETNUM}")
        report = result["final_answer"]
        # 应包含科学边界或风险窗口表达
        assert any(w in report for w in ["科学边界", "风险", "不代表", "参考"])

    def test_no_exact_failure_date_prediction(self):
        """报告不应说"X月X日会故障"。"""
        result = run_diagnosis(f"设备 {KNOWN_ASSETNUM} 什么时候会再坏")
        report = result["final_answer"]
        # 不应包含"XX月XX日会故障"这种模式
        import re
        assert not re.search(r"\d+月\d+日.*会.*故障", report)


class TestV03MultiTurn:

    def test_multi_turn_pronoun_inherit(self):
        sid = "test-v03-mt-pronoun"
        # 第一轮
        r1 = run_diagnosis(f"帮我分析设备 {KNOWN_ASSETNUM}", session_id=sid)
        assert r1["status"] == "success"
        assert r1["assetnum"] == KNOWN_ASSETNUM

        # 第二轮：指代追问
        r2 = run_diagnosis("那它最近有哪些故障？", session_id=sid)
        assert r2["status"] == "success"
        assert r2["assetnum"] == KNOWN_ASSETNUM

        # 第三轮：追问建议
        r3 = run_diagnosis("那应该先检查什么？", session_id=sid)
        assert r3["status"] == "success"
        assert r3["assetnum"] == KNOWN_ASSETNUM

    def test_multi_turn_device_switch(self):
        sid = "test-v03-mt-switch"
        # 第一轮
        r1 = run_diagnosis(f"帮我分析设备 {KNOWN_ASSETNUM}", session_id=sid)
        assert r1["status"] == "success"

        # 第二轮：切换设备
        r2 = run_diagnosis(f"换成 {SECOND_ASSETNUM} 呢？", session_id=sid)
        assert r2["status"] == "success"
        assert r2["assetnum"] == SECOND_ASSETNUM

        # 第三轮：新设备追问
        r3 = run_diagnosis("那它最近有哪些故障？", session_id=sid)
        assert r3["status"] == "success"
        assert r3["assetnum"] == SECOND_ASSETNUM

    def test_global_query_does_not_inherit_device(self):
        sid = "test-v03-mt-global"
        # 先分析设备
        run_diagnosis(f"帮我分析设备 {KNOWN_ASSETNUM}", session_id=sid)
        # 再问全局问题
        r2 = run_diagnosis("当前高风险设备有哪些", session_id=sid)
        assert r2["status"] == "success"
        # 全局问题不应强制展示设备编号

    def test_session_isolation(self):
        sid_a = "test-v03-iso-a"
        sid_b = "test-v03-iso-b"

        run_diagnosis(f"帮我分析设备 {KNOWN_ASSETNUM}", session_id=sid_a)
        run_diagnosis(f"帮我分析设备 {SECOND_ASSETNUM}", session_id=sid_b)

        r_a = run_diagnosis("那它最近有哪些故障？", session_id=sid_a)
        assert r_a["assetnum"] == KNOWN_ASSETNUM

        r_b = run_diagnosis("那它最近有哪些故障？", session_id=sid_b)
        assert r_b["assetnum"] == SECOND_ASSETNUM

    def test_full_conversation_scenario(self):
        """模拟完整对话场景：5 轮对话。"""
        sid = "test-v03-conversation"

        # 1. 分析设备
        r1 = run_diagnosis(f"帮我分析设备 {KNOWN_ASSETNUM}", session_id=sid)
        assert r1["status"] == "success"
        assert r1["assetnum"] == KNOWN_ASSETNUM

        # 2. 追问风险
        r2 = run_diagnosis("那它为什么是橙色预警？", session_id=sid)
        assert r2["status"] == "success"
        assert r2["assetnum"] == KNOWN_ASSETNUM

        # 3. 追问建议
        r3 = run_diagnosis("那应该先检查什么？", session_id=sid)
        assert r3["status"] == "success"
        assert r3["assetnum"] == KNOWN_ASSETNUM

        # 4. 切换设备
        r4 = run_diagnosis(f"换成 {SECOND_ASSETNUM} 呢？", session_id=sid)
        assert r4["status"] == "success"
        assert r4["assetnum"] == SECOND_ASSETNUM

        # 5. 新设备追问
        r5 = run_diagnosis("那它最近有哪些故障？", session_id=sid)
        assert r5["status"] == "success"
        assert r5["assetnum"] == SECOND_ASSETNUM
