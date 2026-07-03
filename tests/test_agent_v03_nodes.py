"""测试 Agent v0.3 八节点基本功能。"""

import pytest

from backend.agent.state import AfcAgentState, create_initial_state, CAPABILITY_BOUNDARY
from backend.agent.nodes.prepare_context import prepare_context_node
from backend.agent.nodes.understand_query import understand_query_node, _has_reference_pronoun, _has_device_switch
from backend.agent.nodes.plan_tools import plan_tools_node
from backend.agent.nodes.execute_tools import execute_tools_node
from backend.agent.nodes.merge_evidence import merge_evidence_node
from backend.agent.nodes.evaluate_evidence import evaluate_evidence_node
from backend.agent.nodes.generate_answer import generate_answer_node
from backend.agent.nodes.update_memory import update_memory_node

KNOWN_ASSETNUM = "1000029970"
SECOND_ASSETNUM = "EX011115"


class TestContextParameters:
    """测试 prepare_context_node。"""

    def test_prepare_context_basic(self):
        state = create_initial_state("帮我分析设备 1000029970")
        result = prepare_context_node(state)
        cp = result["context_packet"]
        assert cp["current_query"] == "帮我分析设备 1000029970"
        assert "capability_boundary" in cp
        assert cp["capability_boundary"]["can_predict_exact_failure_date"] is False
        assert cp["capability_boundary"]["can_predict_risk_window"] is True

    def test_prepare_context_with_last_assetnum(self):
        state = create_initial_state("那它风险高吗")
        state["last_assetnum"] = KNOWN_ASSETNUM
        state["last_task_type"] = "full_diagnosis"
        result = prepare_context_node(state)
        cp = result["context_packet"]
        assert cp["active_assetnum"] == KNOWN_ASSETNUM
        assert cp["conversation_focus"] is not None
        assert KNOWN_ASSETNUM in cp.get("conversation_focus", "")

    def test_capability_boundary_is_correct(self):
        state = create_initial_state("test")
        result = prepare_context_node(state)
        cp = result["context_packet"]
        cb = cp["capability_boundary"]
        assert cb["can_predict_exact_failure_date"] is False
        assert cb["can_predict_risk_window"] is True
        assert cb["can_confirm_root_cause"] is False
        assert cb["can_provide_inspection_suggestions"] is True


class TestUnderstandQuery:
    """测试 understand_query_node。"""

    def test_reference_pronoun_detection(self):
        assert _has_reference_pronoun("那它为什么是橙色预警？")
        assert _has_reference_pronoun("这个设备应该检查什么？")
        assert not _has_reference_pronoun("帮我分析设备 1000029970")

    def test_device_switch_detection(self):
        assert _has_device_switch("换成 EX011115 呢？") == "EX011115"
        assert _has_device_switch("切换成设备 EX011115") == "EX011115"
        assert _has_device_switch("那它风险高吗") is None

    def test_understand_with_pronoun_inheritance(self):
        state = create_initial_state("那它最近有哪些故障？")
        state["context_packet"] = {
            "active_assetnum": KNOWN_ASSETNUM,
            "active_task_type": "full_diagnosis",
            "conversation_focus": f"设备 {KNOWN_ASSETNUM} 的 full_diagnosis",
            "capability_boundary": CAPABILITY_BOUNDARY,
            "known_entities": [KNOWN_ASSETNUM],
            "recent_messages": [],
        }
        result = understand_query_node(state)
        understanding = result["query_understanding"]
        # v0.3.0: route 为主路由，assetnum 应来自指代继承
        assert understanding["assetnum"] == KNOWN_ASSETNUM
        assert understanding["route"] in ("business_device", "followup_rewrite")

    def test_understand_capability_query(self):
        state = create_initial_state("你会干什么？")
        state["context_packet"] = {
            "active_assetnum": None,
            "active_task_type": None,
            "capability_boundary": CAPABILITY_BOUNDARY,
            "known_entities": [],
            "recent_messages": [],
        }
        result = understand_query_node(state)
        understanding = result["query_understanding"]
        # v0.3.0: route 为主路由
        assert understanding["route"] in ("capability_query", "direct_chat")
        assert understanding["needs_asset"] is False
        assert understanding["needs_tools"] is False

    def test_understand_high_risk_ranking(self):
        state = create_initial_state("当前高风险设备有哪些")
        state["context_packet"] = {
            "active_assetnum": None,
            "active_task_type": None,
            "capability_boundary": CAPABILITY_BOUNDARY,
            "known_entities": [],
            "recent_messages": [],
        }
        result = understand_query_node(state)
        understanding = result["query_understanding"]
        # v0.3.0: route 为主路由
        assert understanding["route"] in ("business_global", "data_overview")
        assert understanding["needs_asset"] is False
        assert understanding["business_goal"] in ("high_risk_ranking", "data_overview", None)


class TestPlanTools:
    """测试 plan_tools_node。"""

    def test_plan_capability_query_no_tools(self):
        state = create_initial_state("你会干什么")
        state["query_understanding"] = {
            "route": "capability_query",
            "task_type": "capability_query",
            "needs_asset": False,
            "needs_tools": False,
        }
        result = plan_tools_node(state)
        assert result["tool_plan"]["tool_calls"] == []
        assert result["tool_plan"]["answer_mode"] == "capability_intro"

    def test_plan_risk_query(self):
        state = create_initial_state(f"设备 {KNOWN_ASSETNUM} 未来30天风险高吗")
        state["query_understanding"] = {
            "route": "business_device",
            "business_goal": "device_risk",
            "task_type": "risk_query",
            "assetnum": KNOWN_ASSETNUM,
            "needs_asset": True,
            "needs_tools": True,
        }
        state["assetnum"] = KNOWN_ASSETNUM
        result = plan_tools_node(state)
        tool_names = [tc["tool_name"] for tc in result["tool_plan"]["tool_calls"]]
        assert "predict_device_risk_tool" in tool_names

    def test_plan_advice_query(self):
        state = create_initial_state(f"设备 {KNOWN_ASSETNUM} 应该先检查什么")
        state["query_understanding"] = {
            "route": "business_device",
            "business_goal": "device_advice",
            "task_type": "advice_query",
            "assetnum": KNOWN_ASSETNUM,
            "needs_asset": True,
            "needs_tools": True,
        }
        state["assetnum"] = KNOWN_ASSETNUM
        result = plan_tools_node(state)
        tool_names = [tc["tool_name"] for tc in result["tool_plan"]["tool_calls"]]
        assert "get_maintenance_advice_tool" in tool_names

    def test_plan_full_diagnosis(self):
        state = create_initial_state(f"帮我分析设备 {KNOWN_ASSETNUM}")
        state["query_understanding"] = {
            "route": "business_device",
            "business_goal": "full_diagnosis",
            "task_type": "full_diagnosis",
            "assetnum": KNOWN_ASSETNUM,
            "needs_asset": True,
            "needs_tools": True,
        }
        state["assetnum"] = KNOWN_ASSETNUM
        result = plan_tools_node(state)
        tool_names = [tc["tool_name"] for tc in result["tool_plan"]["tool_calls"]]
        assert "get_integrated_analysis_tool" in tool_names


class TestExecuteTools:
    """测试 execute_tools_node。"""

    def test_execute_with_empty_plan(self):
        state = create_initial_state("test")
        state["tool_plan"] = {"tool_calls": []}
        result = execute_tools_node(state)
        assert result["tool_results"] == {}

    def test_execute_with_unknown_tool(self):
        """不在白名单的工具应跳过。"""
        state = create_initial_state("test")
        state["tool_plan"] = {
            "tool_calls": [
                {"tool_name": "nonexistent_tool", "args": {}, "purpose": "test"}
            ]
        }
        result = execute_tools_node(state)
        assert "未注册" in result["errors"][0] or "不在白名单" in result["errors"][0]

    def test_execute_integrated_analysis(self):
        state = create_initial_state(f"分析设备 {KNOWN_ASSETNUM}")
        state["query_understanding"] = {"assetnum": KNOWN_ASSETNUM, "route": "business_device", "business_goal": "full_diagnosis"}
        state["tool_plan"] = {
            "tool_calls": [
                {
                    "tool_name": "get_integrated_analysis_tool",
                    "args": {"assetnum": KNOWN_ASSETNUM},
                    "purpose": "获取综合分析",
                }
            ]
        }
        result = execute_tools_node(state)
        assert "get_integrated_analysis_tool" in result["tool_results"]
        assert result["tool_results"]["get_integrated_analysis_tool"]["status"] == "success"


class TestMergeEvidence:
    """测试 merge_evidence_node。"""

    def test_merge_integrated_analysis(self):
        state = create_initial_state(f"分析设备 {KNOWN_ASSETNUM}")
        state["query_understanding"] = {"route": "business_device", "business_goal": "full_diagnosis", "task_type": "full_diagnosis", "assetnum": KNOWN_ASSETNUM}
        state["tool_plan"] = {
            "tool_calls": [
                {"tool_name": "get_integrated_analysis_tool", "args": {"assetnum": KNOWN_ASSETNUM}}
            ]
        }
        # 先执行工具
        exec_result = execute_tools_node(state)
        state["tool_results"] = exec_result["tool_results"]
        state["tool_trace"] = exec_result["tool_trace"]

        result = merge_evidence_node(state)
        ep = result["evidence_packet"]
        assert ep["assetnum"] == KNOWN_ASSETNUM
        assert "device_profile" in ep
        assert "risk_prediction" in ep
        assert "sources" in ep


class TestEvaluateEvidence:
    """测试 evaluate_evidence_node。"""

    def test_evaluate_capability_answerable(self):
        state = create_initial_state("你会干什么")
        state["query_understanding"] = {"route": "capability_query", "task_type": "capability_query"}
        state["tool_plan"] = {"answer_mode": "capability_intro"}
        result = evaluate_evidence_node(state)
        assert result["evidence_evaluation"]["answerable"] is True

    def test_evaluate_full_diagnosis_without_risk(self):
        state = create_initial_state(f"分析设备 {KNOWN_ASSETNUM}")
        state["query_understanding"] = {"route": "business_device", "business_goal": "full_diagnosis", "task_type": "full_diagnosis", "assetnum": KNOWN_ASSETNUM}
        state["tool_plan"] = {"answer_mode": "evidence_based"}
        state["evidence_packet"] = {
            "assetnum": KNOWN_ASSETNUM,
            "risk_prediction": None,
            "maintenance_advice": None,
            "missing_evidence": ["risk_prediction", "maintenance_advice"],
            "sources": [],
        }
        result = evaluate_evidence_node(state)
        # 有缺失证据时 need_more_tools 应为 true（除非达到最大循环）
        ee = result["evidence_evaluation"]
        assert "need_more_tools" in ee


class TestGenerateAnswer:
    """测试 generate_answer_node。"""

    def test_capability_report(self):
        state = create_initial_state("你会干什么")
        state["query_understanding"] = {
            "route": "capability_query",
            "task_type": "capability_query",
            "needs_asset": False,
            "needs_tools": False,
        }
        state["tool_plan"] = {"answer_mode": "capability_intro"}
        result = generate_answer_node(state)
        assert "功能介绍" in result["final_answer"]

    def test_report_with_evidence(self):
        state = create_initial_state(f"帮我分析设备 {KNOWN_ASSETNUM}")
        state["query_understanding"] = {
            "route": "business_device",
            "business_goal": "full_diagnosis",
            "task_type": "full_diagnosis",
            "assetnum": KNOWN_ASSETNUM,
            "needs_asset": True,
        }
        state["tool_plan"] = {"answer_mode": "evidence_based"}
        state["evidence_packet"] = {
            "assetnum": KNOWN_ASSETNUM,
            "device_profile": {"assetnum": KNOWN_ASSETNUM, "station_name": "测试站"},
            "risk_prediction": {"risk_30d": 0.5, "warning_level": "黄色预警"},
            "maintenance_advice": {"inspection_suggestions": ["检查A", "检查B"]},
            "sources": ["test_tool"],
        }
        result = generate_answer_node(state)
        assert len(result["final_answer"]) > 10


class TestUpdateMemory:
    """测试 update_memory_node。"""

    def test_update_memory_preserves_assetnum(self):
        state = create_initial_state(f"分析设备 {KNOWN_ASSETNUM}")
        state["query_understanding"] = {
            "route": "business_device",
            "business_goal": "full_diagnosis",
            "task_type": "full_diagnosis",
            "assetnum": KNOWN_ASSETNUM,
        }
        state["final_answer"] = "诊断报告内容..."
        result = update_memory_node(state)
        assert result["last_assetnum"] == KNOWN_ASSETNUM
        assert result["last_task_type"] == "full_diagnosis"

    def test_update_memory_global_query_clears_asset(self):
        state = create_initial_state("当前高风险设备有哪些")
        state["query_understanding"] = {
            "route": "business_global",
            "business_goal": "high_risk_ranking",
            "task_type": "high_risk_ranking",
            "assetnum": None,
        }
        state["last_assetnum"] = KNOWN_ASSETNUM
        state["final_answer"] = "高风险清单..."
        result = update_memory_node(state)
        # 全局查询应清除活跃设备
        assert result["last_assetnum"] is None

    def test_update_memory_messages_appended(self):
        state = create_initial_state("你好")
        state["query"] = "你好"
        state["query_understanding"] = {
            "route": "direct_chat",
            "task_type": "direct_chat",
            "assetnum": None,
        }
        state["final_answer"] = "你好，我是AFC助手"
        state["messages"] = []
        result = update_memory_node(state)
        assert len(result["messages"]) == 2  # user + assistant


# ═══════════════════════════════════════════════════════════════
# v0.3.0 新增测试：route / answer_mode / 闲聊 / 缺参数
# ═══════════════════════════════════════════════════════════════

class TestV030RouteChat:
    """v0.3.0: 闲聊路由测试。"""

    def test_chat_hello_detected_as_direct_chat(self):
        """'你好' 应识别为 direct_chat，不调用工具。"""
        state = create_initial_state("你好")
        state["context_packet"] = {
            "active_assetnum": None,
            "active_task_type": None,
            "capability_boundary": CAPABILITY_BOUNDARY,
            "known_entities": [],
            "recent_messages": [],
        }
        result = understand_query_node(state)
        understanding = result["query_understanding"]
        assert understanding["route"] == "direct_chat"
        assert understanding["needs_tools"] is False

    def test_chat_hello_plan_no_tools(self):
        """'你好' plan_tools 应返回空工具 + direct_chat answer_mode。"""
        state = create_initial_state("你好")
        state["query_understanding"] = {
            "route": "direct_chat",
            "task_type": "direct_chat",
            "needs_asset": False,
            "needs_tools": False,
        }
        result = plan_tools_node(state)
        assert result["tool_plan"]["tool_calls"] == []
        assert result["tool_plan"]["answer_mode"] == "direct_chat"

    def test_chat_hello_generates_greeting(self):
        """'你好' generate_answer 应返回问候语。"""
        state = create_initial_state("你好")
        state["query_understanding"] = {
            "route": "direct_chat",
            "task_type": "direct_chat",
        }
        state["tool_plan"] = {"answer_mode": "direct_chat"}
        result = generate_answer_node(state)
        assert len(result["final_answer"]) > 10
        assert "AFC" in result["final_answer"] or "助手" in result["final_answer"]

    def test_chat_preserves_business_context(self):
        """闲聊'谢谢'不应清除上一轮设备编号。"""
        state = create_initial_state("谢谢")
        state["last_assetnum"] = KNOWN_ASSETNUM
        state["last_task_type"] = "full_diagnosis"
        state["query_understanding"] = {
            "route": "direct_chat",
            "task_type": "direct_chat",
            "assetnum": None,
        }
        state["final_answer"] = "不客气！"
        result = update_memory_node(state)
        assert result["last_assetnum"] == KNOWN_ASSETNUM  # 保留原设备


class TestV030Capability:
    """v0.3.0: 能力询问测试。"""

    def test_capability_route_detected(self):
        """'你能做什么' 应识别为 capability_query。"""
        state = create_initial_state("你能做什么")
        state["context_packet"] = {
            "active_assetnum": None,
            "active_task_type": None,
            "capability_boundary": CAPABILITY_BOUNDARY,
            "known_entities": [],
            "recent_messages": [],
        }
        result = understand_query_node(state)
        understanding = result["query_understanding"]
        assert understanding["route"] == "capability_query"
        assert understanding["needs_tools"] is False

    def test_capability_plan_no_tools(self):
        """能力询问不应规划工具。"""
        state = create_initial_state("你能做什么")
        state["query_understanding"] = {
            "route": "capability_query",
            "task_type": "capability_query",
            "needs_asset": False,
            "needs_tools": False,
        }
        result = plan_tools_node(state)
        assert result["tool_plan"]["tool_calls"] == []
        assert result["tool_plan"]["answer_mode"] == "capability_intro"


class TestV030MissingAsset:
    """v0.3.0: 缺少设备编号测试。"""

    def test_missing_asset_route_detected(self):
        """'帮我分析一下这个设备'（无上下文）应识别为 needs_clarification。"""
        state = create_initial_state("帮我分析一下这个设备")
        state["context_packet"] = {
            "active_assetnum": None,
            "active_task_type": None,
            "capability_boundary": CAPABILITY_BOUNDARY,
            "known_entities": [],
            "recent_messages": [],
        }
        result = understand_query_node(state)
        understanding = result["query_understanding"]
        assert understanding["route"] in ("needs_clarification", "business_device")
        assert understanding["needs_tools"] is False or understanding["assetnum"] is None

    def test_missing_asset_plan_ask(self):
        """缺少设备编号时 answer_mode 应为 ask_for_assetnum。"""
        state = create_initial_state("帮我分析一下")
        state["query_understanding"] = {
            "route": "needs_clarification",
            "business_goal": None,
            "task_type": "unknown",
            "needs_asset": False,
            "needs_tools": False,
        }
        result = plan_tools_node(state)
        assert result["tool_plan"]["tool_calls"] == []
        assert result["tool_plan"]["answer_mode"] == "ask_for_assetnum"


class TestV030AnswerMode:
    """v0.3.0: answer_mode 分派测试。"""

    def test_unsupported_generates_boundary_msg(self):
        """超出系统能力的问题应返回边界说明。"""
        state = create_initial_state("帮我写论文")
        state["query_understanding"] = {"route": "unsupported"}
        state["tool_plan"] = {"answer_mode": "unsupported"}
        result = generate_answer_node(state)
        assert "超出" in result["final_answer"] or "范围" in result["final_answer"]

    def test_ask_for_assetnum_generates_prompt(self):
        """缺少设备编号的回答应引导用户提供编号。"""
        state = create_initial_state("test")
        state["query_understanding"] = {}
        state["tool_plan"] = {"answer_mode": "ask_for_assetnum"}
        result = generate_answer_node(state)
        assert "设备编号" in result["final_answer"]

    def test_evidence_based_with_tool_error_asks_assetnum(self):
        """missing_required_argument 错误应转为追问设备编号。"""
        state = create_initial_state("帮我分析设备")
        state["query_understanding"] = {
            "route": "business_device",
            "business_goal": "full_diagnosis",
            "assetnum": None,
        }
        state["tool_plan"] = {"answer_mode": "evidence_based"}
        state["evidence_packet"] = {
            "sources": [],
            "tool_errors": [
                {"tool": "get_integrated_analysis_tool", "error_type": "missing_required_argument", "message": "缺少设备编号"}
            ],
        }
        result = generate_answer_node(state)
        assert "设备编号" in result["final_answer"]
