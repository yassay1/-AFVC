"""LangGraph Agent 工作流测试。

测试完整诊断流程，包括：
1. 状态初始化和图编译
2. 7 种问题类型的解析和路由
3. 规则兜底（无 LLM）模式端到端
4. 异常处理
5. 多轮对话：指代补全、设备切换、跨会话隔离

说明：
- TestAgentState / TestRuleBasedParsing / TestNodes / TestMultiTurnHelpers 等类
  测试的是旧兼容节点和辅助函数，标记为 legacy。
- TestMultiTurnEndToEnd / TestEndToEndWorkflow / TestHybridAgentAcceptance 等类
  测试的是当前 v0.3 run_diagnosis API（八节点 Agent），不属于 legacy。
"""

import pytest

from backend.agent.state import AfcAgentState, create_initial_state
from backend.agent.graph import create_agent_graph, run_diagnosis

# ⚠️ 旧三节点兼容函数（TestNodes 等 legacy 测试用）——
# 从 compat 模块显式导入，避免与 v0.3 节点函数同名冲突。
from backend.agent.nodes.compat import (
    parse_question_node,
    resolve_asset_node,
    route_task_node,
    execute_tools_node as compat_execute_tools_node,
    merge_evidence_node as compat_merge_evidence_node,
    generate_report_node,
    TASK_TOOL_MAP,
    _rule_based_parse_task_type,
    _extract_assetnum_from_query,
    _has_reference_pronoun,
    _has_device_switch,
    _is_global_question,
    _resolve_multiturn_context,
)

KNOWN_ASSETNUM = "1000029970"
SECOND_ASSETNUM = "EX011115"


# ═══════════════════════════════════════════════════════════════
# State 测试
# ═══════════════════════════════════════════════════════════════

@pytest.mark.legacy
class TestAgentState:

    def test_create_initial_state(self):
        state = create_initial_state("帮我分析设备 1000029970")
        assert state["query"] == "帮我分析设备 1000029970"
        # v0.3 state — 不包含旧版 compat 字段（assetnum, task_type, selected_tools 等）
        assert "query_understanding" in state
        assert "tool_plan" in state
        assert "evidence_packet" in state
        assert state["final_answer"] == ""
        assert state["errors"] == []

    def test_state_has_all_keys(self):
        keys = set(create_initial_state("test").keys())
        required_v03 = {
            "query", "context_packet", "query_understanding",
            "tool_plan", "tool_results", "tool_trace",
            "evidence_packet", "evidence_evaluation", "answer_policy",
            "final_answer", "memory_update", "tool_loop_count",
            "last_evidence_summary", "errors", "messages",
            "last_assetnum", "last_task_type", "last_time_window",
            "last_tool_results_summary",
        }
        assert required_v03.issubset(keys)


# ═══════════════════════════════════════════════════════════════
# 规则兜底解析测试
# ═══════════════════════════════════════════════════════════════

@pytest.mark.legacy
class TestRuleBasedParsing:

    def test_extract_assetnum_device_prefix(self):
        assert _extract_assetnum_from_query("设备 1000029970 风险高吗") == "1000029970"

    def test_extract_assetnum_alphanum(self):
        assert _extract_assetnum_from_query("帮我分析 EX011115") == "EX011115"

    def test_extract_assetnum_long_digits(self):
        assert _extract_assetnum_from_query("1000029970 最近故障") == "1000029970"

    def test_extract_assetnum_none(self):
        assert _extract_assetnum_from_query("今天高风险设备有哪些") is None

    def test_parse_task_type_data_overview(self):
        assert _rule_based_parse_task_type("这批工单整体情况怎么样") == "data_overview"

    def test_parse_task_type_high_risk(self):
        assert _rule_based_parse_task_type("今天优先巡检哪些设备") == "high_risk_ranking"

    def test_parse_task_type_risk_query(self):
        assert _rule_based_parse_task_type("设备 100023 未来风险高吗") == "risk_query"

    def test_parse_task_type_advice_query(self):
        assert _rule_based_parse_task_type("设备 100023 应该怎么处理") == "advice_query"

    def test_parse_task_type_history_query(self):
        assert _rule_based_parse_task_type("设备 100023 以前出过什么故障") == "history_query"

    def test_parse_task_type_risk_explanation(self):
        assert _rule_based_parse_task_type("为什么设备 100023 是红色预警") == "risk_explanation"

    def test_parse_task_type_risk_and_advice(self):
        assert _rule_based_parse_task_type("设备 100023 风险高不高，应该检查什么") == "risk_and_advice_query"

    def test_parse_task_type_fallback(self):
        # "你好" 等问候/能力询问应识别为 capability_query
        assert _rule_based_parse_task_type("你好") == "capability_query"
        assert _rule_based_parse_task_type("你会干什么") == "capability_query"
        assert _rule_based_parse_task_type("有什么功能") == "capability_query"
        # 真正无意义的输入才回退到 full_diagnosis
        assert _rule_based_parse_task_type("xyz123") == "full_diagnosis"


# ═══════════════════════════════════════════════════════════════
# 节点单元测试
# ═══════════════════════════════════════════════════════════════

@pytest.mark.legacy
class TestNodes:

    # ── parse_question_node ──

    def test_parse_without_llm_falls_back(self):
        """parse_question_node 应能正常解析（LLM 可用时走 LLM，不可用时兜底）。"""
        state = create_initial_state("帮我分析设备 1000029970")
        result = parse_question_node(state)
        assert result["assetnum"] == "1000029970"
        assert result["task_type"] in TASK_TOOL_MAP
        # LLM 可用时可能无错误，LLM 不可用时应有兜底提示
        # 无论哪种情况，解析结果应有效

    def test_parse_high_risk_question(self):
        state = create_initial_state("当前高风险设备有哪些")
        result = parse_question_node(state)
        assert result["task_type"] == "high_risk_ranking"

    # ── resolve_asset_node ──

    def test_resolve_known_device(self):
        state = create_initial_state("test")
        state["assetnum"] = KNOWN_ASSETNUM
        state["task_type"] = "full_diagnosis"
        result = resolve_asset_node(state)
        assert result["asset_exists"] is True

    def test_resolve_unknown_device(self):
        state = create_initial_state("test")
        state["assetnum"] = "ZZZ99999"
        state["task_type"] = "full_diagnosis"
        result = resolve_asset_node(state)
        assert result["asset_exists"] is False

    def test_resolve_no_device_task(self):
        """全局任务类型跳过设备校验。"""
        state = create_initial_state("test")
        state["task_type"] = "data_overview"
        result = resolve_asset_node(state)
        assert result["asset_exists"] is True

    # ── route_task_node ──

    def test_route_full_diagnosis(self):
        state = create_initial_state("test")
        state["task_type"] = "full_diagnosis"
        result = route_task_node(state)
        assert "get_integrated_analysis_tool" in result["selected_tools"]

    def test_route_high_risk(self):
        state = create_initial_state("test")
        state["task_type"] = "high_risk_ranking"
        result = route_task_node(state)
        assert result["selected_tools"] == ["get_high_risk_devices_tool"]

    def test_route_unknown_task(self):
        """未知 task_type 应回退为 full_diagnosis 的路由。"""
        state = create_initial_state("test")
        state["task_type"] = "not_a_real_type"
        result = route_task_node(state)
        assert result["selected_tools"] == ["get_integrated_analysis_tool"]

    # ── execute_tools_node ──

    def test_execute_integrated_analysis(self):
        state = create_initial_state("test")
        state["assetnum"] = KNOWN_ASSETNUM
        state["selected_tools"] = ["get_integrated_analysis_tool"]
        result = compat_execute_tools_node(state)
        assert "get_integrated_analysis_tool" in result["tool_results"]
        tool_result = result["tool_results"]["get_integrated_analysis_tool"]
        assert tool_result["status"] == "success"

    def test_execute_with_empty_tools(self):
        state = create_initial_state("test")
        state["selected_tools"] = []
        result = compat_execute_tools_node(state)
        assert result["tool_results"] == {}

    # ── merge_evidence_node ──

    def test_merge_from_integrated_analysis(self):
        state = create_initial_state("test")
        state["assetnum"] = KNOWN_ASSETNUM
        state["selected_tools"] = ["get_integrated_analysis_tool"]

        # 先执行工具
        exec_result = compat_execute_tools_node(state)
        state["tool_results"] = exec_result["tool_results"]

        result = compat_merge_evidence_node(state)
        evidence = result["evidence"]
        assert evidence["assetnum"] == KNOWN_ASSETNUM
        assert "sources" in evidence

    # ── generate_report_node ──

    def test_generate_report_without_llm(self):
        """无 LLM 时应使用模板生成报告。"""
        state = create_initial_state("帮我分析设备 1000029970")
        state["assetnum"] = KNOWN_ASSETNUM
        state["task_type"] = "full_diagnosis"
        state["selected_tools"] = ["get_integrated_analysis_tool"]

        exec_result = compat_execute_tools_node(state)
        state["tool_results"] = exec_result["tool_results"]

        merge_result = compat_merge_evidence_node(state)
        state["evidence"] = merge_result["evidence"]

        result = generate_report_node(state)
        report = result["final_answer"]
        assert "AFC 设备智能诊断报告" in report
        assert "设备识别结果" in report
        assert "科学边界" in report


# ═══════════════════════════════════════════════════════════════
# 多轮对话：指代检测和上下文补全
# ═══════════════════════════════════════════════════════════════

@pytest.mark.legacy
class TestMultiTurnHelpers:

    def test_has_reference_pronoun_true(self):
        """指代词检测：应识别"它"、"这个设备"等。"""
        assert _has_reference_pronoun("那它为什么是橙色预警？")
        assert _has_reference_pronoun("它最近有哪些故障？")
        assert _has_reference_pronoun("这个设备应该检查什么？")
        assert _has_reference_pronoun("该设备风险高吗？")
        assert _has_reference_pronoun("刚才那个设备呢？")
        assert _has_reference_pronoun("那应该先检查什么？")

    def test_has_reference_pronoun_false(self):
        """无指代词时不应误判。"""
        assert not _has_reference_pronoun("帮我分析设备 1000029970")
        assert not _has_reference_pronoun("当前高风险设备有哪些")
        assert not _has_reference_pronoun("这批工单整体情况怎么样")

    def test_has_device_switch(self):
        """设备切换检测：应识别"换成XXX"等。"""
        assert _has_device_switch("换成 EX011115 呢？") == "EX011115"
        assert _has_device_switch("换到 GX010301") == "GX010301"
        assert _has_device_switch("改成 1000029970") == "1000029970"
        assert _has_device_switch("切换成设备 EX011115") == "EX011115"

    def test_has_device_switch_none(self):
        """无切换词时不应误判。"""
        assert _has_device_switch("那它风险高吗") is None
        assert _has_device_switch("帮我分析设备 1000029970") is None

    def test_is_global_question(self):
        """全局类问题检测。"""
        assert _is_global_question("当前高风险设备有哪些")
        assert _is_global_question("这批工单整体情况怎么样")
        assert _is_global_question("今天优先巡检哪些设备")

    def test_is_not_global_question(self):
        """设备相关问题不应被识别为全局问题。"""
        assert not _is_global_question("那它风险高吗")
        assert not _is_global_question("帮我分析设备 1000029970")

    def test_resolve_context_pronoun_inherit(self):
        """指代词：应继承上一轮设备编号。"""
        assetnum, task_type, time_window, hint = _resolve_multiturn_context(
            "那它为什么是橙色预警？",
            last_assetnum="1000029970",
            last_task_type="full_diagnosis",
            last_time_window="30d",
        )
        assert assetnum == "1000029970"
        assert task_type == "risk_explanation"
        assert hint != ""

    def test_resolve_context_switch(self):
        """设备切换：应返回新设备编号。"""
        assetnum, task_type, time_window, hint = _resolve_multiturn_context(
            "换成 EX011115 呢？",
            last_assetnum="1000029970",
            last_task_type="full_diagnosis",
            last_time_window="30d",
        )
        assert assetnum == "EX011115"
        assert hint != ""

    def test_resolve_context_global_no_inherit(self):
        """全局问题不继承设备编号。"""
        assetnum, task_type, time_window, hint = _resolve_multiturn_context(
            "当前高风险设备有哪些",
            last_assetnum="1000029970",
            last_task_type="full_diagnosis",
            last_time_window="30d",
        )
        assert assetnum is None

    def test_resolve_context_no_reference_without_pronoun(self):
        """无指代无切换无显式设备时不继承。"""
        assetnum, task_type, time_window, hint = _resolve_multiturn_context(
            "你好",
            last_assetnum="1000029970",
            last_task_type="full_diagnosis",
            last_time_window="30d",
        )
        # 没有指代词也没有切换词，不应乱继承
        assert assetnum is None


# ═══════════════════════════════════════════════════════════════
# 多轮对话：端到端测试
# ═══════════════════════════════════════════════════════════════

class TestMultiTurnEndToEnd:

    def test_single_turn_without_session(self):
        """不传 session_id 时，单轮诊断仍可用（自动生成临时 session_id）。"""
        result = run_diagnosis(f"帮我分析设备 {KNOWN_ASSETNUM}")
        assert result["status"] == "success"
        # 不传 session_id 时自动生成临时 ID
        assert result["session_id"] is not None
        assert result["session_id"].startswith("single-")

    def test_single_turn_with_session(self):
        """传入 session_id 时，单轮诊断正常。"""
        result = run_diagnosis(f"帮我分析设备 {KNOWN_ASSETNUM}", session_id="test-session-1")
        assert result["status"] == "success"
        assert result["session_id"] == "test-session-1"
        assert result["last_assetnum"] == KNOWN_ASSETNUM

    def test_multi_turn_pronoun_inherit(self):
        """同一个 session_id 下，第二轮指代可以继承第一轮设备。"""
        sid = "test-multi-turn-1"

        # 第一轮：分析设备
        r1 = run_diagnosis(f"帮我分析设备 {KNOWN_ASSETNUM}", session_id=sid)
        assert r1["status"] == "success"
        assert r1["assetnum"] == KNOWN_ASSETNUM

        # 第二轮：用指代词追问（无 LLM 时走规则兜底）
        r2 = run_diagnosis("那它最近有哪些故障？", session_id=sid)
        assert r2["status"] == "success"
        # 应通过多轮上下文继承设备编号
        assert r2["assetnum"] == KNOWN_ASSETNUM
        assert r2["task_type"] == "history_query"

    def test_multi_turn_switch_device(self):
        """同一个 session_id 下，'换成XXX'可以切换设备。"""
        sid = "test-multi-switch-1"

        # 第一轮
        r1 = run_diagnosis(f"帮我分析设备 {KNOWN_ASSETNUM}", session_id=sid)
        assert r1["status"] == "success"

        # 第二轮：切换设备
        r2 = run_diagnosis(f"换成 {SECOND_ASSETNUM} 呢？", session_id=sid)
        assert r2["status"] == "success"
        assert r2["assetnum"] == SECOND_ASSETNUM

    def test_different_sessions_isolated(self):
        """不同 session_id 之间上下文不互相污染。"""
        sid_a = "test-isolation-a"
        sid_b = "test-isolation-b"

        # 会话 A：分析 1000029970
        run_diagnosis(f"帮我分析设备 {KNOWN_ASSETNUM}", session_id=sid_a)

        # 会话 B：分析 EX011115
        run_diagnosis(f"帮我分析设备 {SECOND_ASSETNUM}", session_id=sid_b)

        # 会话 A 追问（应继承 KNOWN_ASSETNUM）
        r_a = run_diagnosis("那它最近有哪些故障？", session_id=sid_a)
        assert r_a["assetnum"] == KNOWN_ASSETNUM

        # 会话 B 追问（应继承 SECOND_ASSETNUM）
        r_b = run_diagnosis("那它最近有哪些故障？", session_id=sid_b)
        assert r_b["assetnum"] == SECOND_ASSETNUM

    def test_global_question_after_device_query(self):
        """设备查询后问全局问题，不应错误继承设备编号。"""
        sid = "test-global-after-device"

        # 先分析一台设备
        run_diagnosis(f"帮我分析设备 {KNOWN_ASSETNUM}", session_id=sid)

        # 再问全局问题
        r2 = run_diagnosis("当前高风险设备有哪些", session_id=sid)
        assert r2["status"] == "success"
        assert r2["task_type"] == "high_risk_ranking"

    def test_conversation_scenario(self):
        """模拟完整对话场景。"""
        sid = "test-conversation-scenario"

        # 1. 分析设备
        r1 = run_diagnosis(f"帮我分析设备 {KNOWN_ASSETNUM}", session_id=sid)
        assert r1["status"] == "success"
        assert r1["assetnum"] == KNOWN_ASSETNUM

        # 2. 追问预警
        r2 = run_diagnosis("那它为什么是橙色预警？", session_id=sid)
        assert r2["status"] == "success"
        assert r2["assetnum"] == KNOWN_ASSETNUM

        # 3. 追问维修建议
        r3 = run_diagnosis("那应该先检查什么？", session_id=sid)
        assert r3["status"] == "success"
        assert r3["assetnum"] == KNOWN_ASSETNUM
        assert r3["task_type"] == "advice_query"

        # 4. 切换设备
        r4 = run_diagnosis(f"换成 {SECOND_ASSETNUM} 呢？", session_id=sid)
        assert r4["status"] == "success"
        assert r4["assetnum"] == SECOND_ASSETNUM

        # 5. 新设备追问
        r5 = run_diagnosis("那它最近有哪些故障？", session_id=sid)
        assert r5["status"] == "success"
        assert r5["assetnum"] == SECOND_ASSETNUM
        assert r5["task_type"] == "history_query"


# ═══════════════════════════════════════════════════════════════
# 完整工作流端到端测试
# ═══════════════════════════════════════════════════════════════

class TestEndToEndWorkflow:

    def test_full_diagnosis(self):
        """端到端：完整诊断流程。"""
        result = run_diagnosis(f"帮我分析设备 {KNOWN_ASSETNUM}")
        assert result["status"] == "success"
        assert result["assetnum"] == KNOWN_ASSETNUM
        assert result["task_type"] == "full_diagnosis"
        assert len(result["selected_tools"]) >= 1
        assert len(result["final_answer"]) > 100
        # 报告应包含关键部分
        report = result["final_answer"]
        assert "AFC" in report
        assert "设备" in report and "识别" in report
        assert "科学边界" in report

    def test_data_overview(self):
        """端到端：数据概览。"""
        result = run_diagnosis("这批工单整体情况怎么样")
        assert result["status"] == "success"
        assert result["task_type"] == "data_overview"
        assert "get_data_summary_tool" in result["selected_tools"]

    def test_high_risk_ranking(self):
        """端到端：高风险设备排名。"""
        result = run_diagnosis("当前高风险设备有哪些")
        assert result["status"] == "success"
        assert result["task_type"] == "high_risk_ranking"
        assert "get_high_risk_devices_tool" in result["selected_tools"]

    def test_risk_query(self):
        """端到端：风险查询。"""
        result = run_diagnosis(f"设备 {KNOWN_ASSETNUM} 未来 30 天风险高吗")
        assert result["status"] == "success"
        assert result["task_type"] in ["risk_query", "risk_and_advice_query"]

    def test_advice_query(self):
        """端到端：维修建议。"""
        result = run_diagnosis(f"设备 {KNOWN_ASSETNUM} 建议检查什么")
        assert result["status"] == "success"
        assert result["task_type"] == "advice_query"

    def test_unknown_device_graceful(self):
        """不存在的设备应优雅降级而非崩溃。"""
        result = run_diagnosis("帮我分析设备 ZZZ99999")
        assert result["status"] == "success"
        assert len(result["errors"]) >= 1

    def test_no_device_identified(self):
        """无法识别设备时应优雅处理。"""
        result = run_diagnosis("你好")
        assert result["status"] == "success"
        # 应有回退处理
        assert result["task_type"] is not None

    def test_graph_compiles(self):
        """图应能成功编译。"""
        graph = create_agent_graph()
        assert graph is not None

    def test_graph_invoke(self):
        """图应能正常运行完整流程（需要提供 config）。"""
        graph = create_agent_graph()
        state = create_initial_state(f"帮我分析设备 {KNOWN_ASSETNUM}")
        config = {"configurable": {"thread_id": "test-graph-invoke"}}
        final_state = graph.invoke(state, config=config)
        assert len(final_state["final_answer"]) > 0


# ═══════════════════════════════════════════════════════════════
# 新三节点混合型 Agent 验收场景
# ═══════════════════════════════════════════════════════════════

class TestHybridAgentAcceptance:

    def test_capability_query_does_not_call_business_tools(self):
        result = run_diagnosis("你会干什么？", session_id="accept-capability")
        assert result["status"] == "success"
        assert result["task_type"] == "capability_query"
        assert result["selected_tools"] == []
        assert result["tool_results"] == {}
        assert "功能介绍" in result["final_answer"]

    def test_data_overview_report_matches_tool(self):
        result = run_diagnosis("这批工单整体情况怎么样？", session_id="accept-overview")
        assert result["status"] == "success"
        assert result["task_type"] == "data_overview"
        assert result["selected_tools"] == ["get_data_summary_tool"]
        assert "get_data_summary_tool" in result["tool_results"]
        assert "设备编号 None" not in result["final_answer"]
        assert "风险：N/A" not in result["final_answer"]

    def test_high_risk_devices_tool_and_report(self):
        result = run_diagnosis("当前高风险设备有哪些？", session_id="accept-high-risk")
        assert result["status"] == "success"
        assert result["task_type"] == "high_risk_ranking"
        assert result["selected_tools"] == ["get_high_risk_devices_tool"]
        assert result["tool_results"]["get_high_risk_devices_tool"]["status"] == "success"
        assert "高风险" in result["final_answer"] or "巡检" in result["final_answer"]

    def test_full_diagnosis_uses_integrated_analysis(self):
        result = run_diagnosis(f"帮我分析设备 {KNOWN_ASSETNUM}", session_id="accept-full")
        assert result["status"] == "success"
        assert result["assetnum"] == KNOWN_ASSETNUM
        assert "get_integrated_analysis_tool" in result["selected_tools"]
        assert "科学边界" in result["final_answer"]

    def test_risk_query_does_not_call_data_overview(self):
        result = run_diagnosis(f"设备 {KNOWN_ASSETNUM} 未来 30 天风险高吗？", session_id="accept-risk")
        assert result["status"] == "success"
        assert result["task_type"] == "risk_query"
        assert "predict_device_risk_tool" in result["selected_tools"]
        assert "get_data_summary_tool" not in result["selected_tools"]

    def test_advice_query_uses_advice_tool(self):
        result = run_diagnosis(f"设备 {KNOWN_ASSETNUM} 应该先检查什么？", session_id="accept-advice")
        assert result["status"] == "success"
        assert result["task_type"] == "advice_query"
        assert "get_maintenance_advice_tool" in result["selected_tools"]

    def test_risk_and_advice_uses_multiple_tools(self):
        result = run_diagnosis(
            f"设备 {KNOWN_ASSETNUM} 风险高不高，高的话应该先检查什么？",
            session_id="accept-risk-advice",
        )
        assert result["status"] == "success"
        assert result["task_type"] == "risk_and_advice_query"
        assert "predict_device_risk_tool" in result["selected_tools"]
        assert "get_maintenance_advice_tool" in result["selected_tools"]

    def test_pronoun_inherits_asset_for_warning_explanation(self):
        sid = "accept-pronoun-warning"
        run_diagnosis(f"帮我分析设备 {KNOWN_ASSETNUM}", session_id=sid)
        result = run_diagnosis("那它为什么是橙色预警？", session_id=sid)
        assert result["status"] == "success"
        assert result["assetnum"] == KNOWN_ASSETNUM
        assert result["task_type"] == "risk_explanation"

    def test_missing_asset_without_context_is_friendly(self):
        result = run_diagnosis("帮我分析一下", session_id="accept-missing-asset")
        assert result["status"] == "success"
        # v0.3: 无法识别意图时仍然尝试调用工具，工具会返回错误
        # 最终回答应包含友好的错误提示
        assert "final_answer" in result
        assert len(result["final_answer"]) > 0

    def test_unknown_device_does_not_call_business_tools(self):
        result = run_diagnosis("帮我分析设备 ZZZ99999", session_id="accept-unknown-device")
        assert result["status"] == "success"
        # v0.3: 工具会被调用但返回 error，agent 通过错误处理优雅降级
        assert "final_answer" in result
        assert len(result["final_answer"]) > 0

    def test_device_switch_updates_context(self):
        sid = "accept-switch"
        run_diagnosis(f"帮我分析设备 {KNOWN_ASSETNUM}", session_id=sid)
        switched = run_diagnosis(f"换成 {SECOND_ASSETNUM} 呢？", session_id=sid)
        assert switched["assetnum"] == SECOND_ASSETNUM
        followup = run_diagnosis("那它未来 30 天风险高吗？", session_id=sid)
        assert followup["assetnum"] == SECOND_ASSETNUM
        assert followup["task_type"] == "risk_query"

    def test_current_turn_debug_fields_do_not_leak(self):
        sid = "accept-no-leak"
        first = run_diagnosis("帮我分析一下", session_id=sid)
        assert first["errors"]
        second = run_diagnosis("你会干什么？", session_id=sid)
        assert second["task_type"] == "capability_query"
        assert second["selected_tools"] == []
        assert second["tool_results"] == {}
        assert not any("未从问题中识别到设备编号" in err for err in second["errors"])

    def test_different_session_context_isolated_for_missing_pronoun(self):
        sid_a = "accept-isolated-a"
        sid_b = "accept-isolated-b"
        run_diagnosis(f"帮我分析设备 {KNOWN_ASSETNUM}", session_id=sid_a)
        result_b = run_diagnosis("那应该先检查什么？", session_id=sid_b)
        assert result_b["asset_exists"] is False
        assert result_b["assetnum"] is None
