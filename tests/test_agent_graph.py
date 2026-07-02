"""LangGraph Agent 工作流测试。

测试完整诊断流程，包括：
1. 状态初始化和图编译
2. 7 种问题类型的解析和路由
3. 规则兜底（无 LLM）模式端到端
4. 异常处理
"""

import pytest

from backend.agent.state import AfcAgentState, create_initial_state
from backend.agent.graph import create_agent_graph, run_diagnosis
from backend.agent.nodes import (
    parse_question_node,
    resolve_asset_node,
    route_task_node,
    execute_tools_node,
    merge_evidence_node,
    generate_report_node,
    TASK_TOOL_MAP,
    _rule_based_parse_task_type,
    _extract_assetnum_from_query,
)

KNOWN_ASSETNUM = "1000029970"


# ═══════════════════════════════════════════════════════════════
# State 测试
# ═══════════════════════════════════════════════════════════════

class TestAgentState:

    def test_create_initial_state(self):
        state = create_initial_state("帮我分析设备 1000029970")
        assert state["query"] == "帮我分析设备 1000029970"
        assert state["assetnum"] is None
        assert state["task_type"] is None
        assert state["selected_tools"] == []
        assert state["tool_results"] == {}
        assert state["evidence"] == {}
        assert state["final_answer"] == ""
        assert state["errors"] == []

    def test_state_has_all_keys(self):
        keys = set(create_initial_state("test").keys())
        required = {"query", "assetnum", "task_type", "time_window",
                     "asset_exists", "selected_tools", "tool_results",
                     "evidence", "final_answer", "errors"}
        assert required.issubset(keys)


# ═══════════════════════════════════════════════════════════════
# 规则兜底解析测试
# ═══════════════════════════════════════════════════════════════

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
        assert _rule_based_parse_task_type("你好") == "full_diagnosis"


# ═══════════════════════════════════════════════════════════════
# 节点单元测试
# ═══════════════════════════════════════════════════════════════

class TestNodes:

    # ── parse_question_node ──

    def test_parse_without_llm_falls_back(self):
        """无 LLM 时，parse_question_node 应触发规则兜底。"""
        state = create_initial_state("帮我分析设备 1000029970")
        result = parse_question_node(state)
        assert result["assetnum"] == "1000029970"
        assert result["task_type"] in TASK_TOOL_MAP
        assert len(result["errors"]) >= 1  # 应有兜底提示

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
        result = execute_tools_node(state)
        assert "get_integrated_analysis_tool" in result["tool_results"]
        tool_result = result["tool_results"]["get_integrated_analysis_tool"]
        assert tool_result["status"] == "success"

    def test_execute_with_empty_tools(self):
        state = create_initial_state("test")
        state["selected_tools"] = []
        result = execute_tools_node(state)
        assert result["tool_results"] == {}

    # ── merge_evidence_node ──

    def test_merge_from_integrated_analysis(self):
        state = create_initial_state("test")
        state["assetnum"] = KNOWN_ASSETNUM
        state["selected_tools"] = ["get_integrated_analysis_tool"]

        # 先执行工具
        exec_result = execute_tools_node(state)
        state["tool_results"] = exec_result["tool_results"]

        result = merge_evidence_node(state)
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

        exec_result = execute_tools_node(state)
        state["tool_results"] = exec_result["tool_results"]

        merge_result = merge_evidence_node(state)
        state["evidence"] = merge_result["evidence"]

        result = generate_report_node(state)
        report = result["final_answer"]
        assert "AFC 设备智能诊断报告" in report
        assert "设备识别结果" in report
        assert "科学边界" in report


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
        """图应能正常运行完整流程。"""
        graph = create_agent_graph()
        state = create_initial_state(f"帮我分析设备 {KNOWN_ASSETNUM}")
        final_state = graph.invoke(state)
        assert len(final_state["final_answer"]) > 0
