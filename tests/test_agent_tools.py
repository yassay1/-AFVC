"""LangChain Tools 层测试。

测试每个工具：
1. 能正确调用底层 Service
2. 正常参数返回 success
3. 异常参数返回 error 而非崩溃
"""

import pytest

from backend.agent.tools import (
    get_data_summary_tool,
    list_devices_tool,
    get_device_history_tool,
    predict_device_risk_tool,
    get_warning_level_tool,
    get_maintenance_advice_tool,
    get_integrated_analysis_tool,
    get_high_risk_devices_tool,
    ALL_TOOLS,
    TOOL_BY_NAME,
)

KNOWN_ASSETNUM = "1000029970"
UNKNOWN_ASSETNUM = "ZZZ99999"


# ═══════════════════════════════════════════════════════════════
# 工具注册表测试
# ═══════════════════════════════════════════════════════════════

class TestToolRegistry:

    def test_all_tools_registered(self):
        """应有 8 个工具。"""
        assert len(ALL_TOOLS) == 8

    def test_tool_by_name_matches(self):
        """TOOL_BY_NAME 应与 ALL_TOOLS 一致。"""
        assert len(TOOL_BY_NAME) == len(ALL_TOOLS)
        for tool in ALL_TOOLS:
            assert tool.name in TOOL_BY_NAME

    def test_all_tools_have_descriptions(self):
        """每个工具都应有 docstring。"""
        for tool in ALL_TOOLS:
            assert tool.description, f"{tool.name} 缺少描述"


# ═══════════════════════════════════════════════════════════════
# 数据概览工具
# ═══════════════════════════════════════════════════════════════

class TestDataSummaryTool:

    def test_invoke_returns_success(self):
        result = get_data_summary_tool.invoke({"top_n": 5})
        assert result["status"] == "success"
        assert result["basic_metrics"]["workorder_count"] > 0


# ═══════════════════════════════════════════════════════════════
# 设备列表工具
# ═══════════════════════════════════════════════════════════════

class TestListDevicesTool:

    def test_invoke_returns_devices(self):
        result = list_devices_tool.invoke({})
        assert result["status"] == "success"
        assert len(result["devices"]) > 0

    def test_invoke_includes_known_device(self):
        result = list_devices_tool.invoke({})
        ids = {d["assetnum"] for d in result["devices"]}
        assert KNOWN_ASSETNUM in ids


# ═══════════════════════════════════════════════════════════════
# 设备历史工具
# ═══════════════════════════════════════════════════════════════

class TestDeviceHistoryTool:

    def test_invoke_known_device(self):
        result = get_device_history_tool.invoke({"assetnum": KNOWN_ASSETNUM, "limit": 5})
        assert result["status"] == "success"
        assert result["history_count"] <= 5

    def test_invoke_unknown_device(self):
        result = get_device_history_tool.invoke({"assetnum": UNKNOWN_ASSETNUM})
        assert result["status"] == "error"


# ═══════════════════════════════════════════════════════════════
# 风险预测工具
# ═══════════════════════════════════════════════════════════════

class TestPredictDeviceRiskTool:

    def test_invoke_known(self):
        result = predict_device_risk_tool.invoke({"assetnum": KNOWN_ASSETNUM})
        assert result["status"] == "success"
        for w in ["risk_7d", "risk_14d", "risk_21d", "risk_30d", "risk_60d", "risk_90d"]:
            assert 0.01 <= result[w] <= 0.95

    def test_invoke_unknown(self):
        result = predict_device_risk_tool.invoke({"assetnum": UNKNOWN_ASSETNUM})
        assert result["status"] == "error"


# ═══════════════════════════════════════════════════════════════
# 预警等级工具
# ═══════════════════════════════════════════════════════════════

class TestWarningLevelTool:

    def test_invoke_red(self):
        result = get_warning_level_tool.invoke({"risk_30d": 0.80, "risk_90d": 0.92})
        assert result["warning_level"] == "红色预警"

    def test_invoke_green(self):
        result = get_warning_level_tool.invoke({"risk_30d": 0.10, "risk_90d": 0.20})
        assert result["warning_level"] == "绿色关注"


# ═══════════════════════════════════════════════════════════════
# 维修建议工具
# ═══════════════════════════════════════════════════════════════

class TestMaintenanceAdviceTool:

    def test_invoke_known(self):
        result = get_maintenance_advice_tool.invoke({"assetnum": KNOWN_ASSETNUM})
        assert result["status"] == "success"
        assert "recognized_fault_phenomena" in result

    def test_invoke_unknown(self):
        result = get_maintenance_advice_tool.invoke({"assetnum": UNKNOWN_ASSETNUM})
        assert result["status"] == "error"


# ═══════════════════════════════════════════════════════════════
# 综合分析工具
# ═══════════════════════════════════════════════════════════════

class TestIntegratedAnalysisTool:

    def test_invoke_known(self):
        result = get_integrated_analysis_tool.invoke({"assetnum": KNOWN_ASSETNUM, "history_limit": 10})
        assert result["status"] == "success"
        assert "device_profile" in result
        assert "risk_prediction" in result
        assert "maintenance_advice" in result

    def test_invoke_unknown(self):
        result = get_integrated_analysis_tool.invoke({"assetnum": UNKNOWN_ASSETNUM})
        assert result["status"] == "error"


# ═══════════════════════════════════════════════════════════════
# 高风险设备工具
# ═══════════════════════════════════════════════════════════════

class TestHighRiskDevicesTool:

    def test_invoke_returns_sorted(self):
        result = get_high_risk_devices_tool.invoke({"top_n": 5})
        assert result["status"] == "success"
        devices = result["devices"]
        assert 0 < len(devices) <= 5
        if len(devices) >= 2:
            assert devices[0]["risk_90d"] >= devices[1]["risk_90d"]
