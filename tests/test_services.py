"""Service 层单元测试。

测试 data / device / prediction / warning / advice / analysis 六个核心服务。
使用真实工单数据进行测试。
"""

import pytest
from pathlib import Path

from backend.services.data_service import (
    get_latest_raw_file,
    read_workorder_file,
    get_basic_data_info,
    get_data_summary,
    RAW_DATA_DIR,
)
from backend.services.device_service import (
    get_device_list,
    get_device_history,
)
from backend.services.prediction_service import (
    predict_device_risk,
    get_high_risk_devices,
)
from backend.services.warning_service import generate_warning_info
from backend.services.advice_service import generate_device_advice
from backend.services.analysis_service import generate_device_analysis
from backend.services import model_adapter

# ── 测试常量（基于真实数据中的设备） ──
KNOWN_ASSETNUM = "1000029970"   # 花地湾站，163 条工单
UNKNOWN_ASSETNUM = "ZZZ99999"   # 不存在的设备


# ═══════════════════════════════════════════════════════════════
# data_service 测试
# ═══════════════════════════════════════════════════════════════

class TestDataService:

    def test_get_latest_raw_file(self):
        """应能获取最新上传的文件。"""
        file = get_latest_raw_file()
        assert file.exists()
        assert file.suffix in [".xlsx", ".xls", ".csv"]

    def test_read_workorder_file(self):
        """应能读取真实工单数据。"""
        df = read_workorder_file()
        assert df.height > 0
        assert "assetnum" in df.columns

    def test_get_basic_data_info(self):
        """应返回数据基础信息。"""
        info = get_basic_data_info()
        assert info["status"] == "success"
        assert info["row_count"] > 0
        assert "assetnum" in info["columns"]

    def test_get_data_summary(self):
        """应返回完整的数据概览。"""
        summary = get_data_summary(top_n=5)
        assert summary["status"] == "success"
        metrics = summary["basic_metrics"]
        assert metrics["workorder_count"] > 0
        assert metrics["device_count"] > 0
        assert metrics["station_count"] > 0
        assert "time_range" in summary
        assert "brand_distribution" in summary

    def test_default_file_exists(self):
        """默认数据文件应存在于 backend/data/raw/ 目录。"""
        default_file = RAW_DATA_DIR / "afc非首次故障-L01线.xlsx"
        assert default_file.exists(), (
            f"默认数据文件不存在于 {default_file}。"
            f"请将 afc非首次故障-L01线.xlsx 放置到 {RAW_DATA_DIR} 目录下。"
        )

    def test_default_file_readable(self):
        """默认数据文件应可成功读取。"""
        default_file = RAW_DATA_DIR / "afc非首次故障-L01线.xlsx"
        if not default_file.exists():
            pytest.skip("默认数据文件不存在，跳过读取测试")
        df = read_workorder_file(default_file)
        assert df.height > 0
        assert "assetnum" in df.columns

    def test_get_latest_raw_file_finds_default(self):
        """没有用户上传文件时，应自动使用默认文件。"""
        file = get_latest_raw_file()
        assert file.exists()
        assert file.suffix in [".xlsx", ".xls", ".csv"]


# ═══════════════════════════════════════════════════════════════
# device_service 测试
# ═══════════════════════════════════════════════════════════════

class TestDeviceService:

    def test_get_device_list(self):
        """应返回设备列表。"""
        result = get_device_list()
        assert result["status"] == "success"
        devices = result["devices"]
        assert len(devices) > 0
        # 应有 assetnum、station_name 等字段
        first = devices[0]
        assert "assetnum" in first
        assert "workorder_count" in first

    def test_get_device_history_known(self):
        """应能查询已知设备的历史工单。"""
        result = get_device_history(KNOWN_ASSETNUM, limit=10)
        assert result["status"] == "success"
        assert result["history_count"] > 0
        assert result["history_count"] <= 10

    def test_get_device_history_unknown(self):
        """未知设备应抛出 ValueError。"""
        with pytest.raises(ValueError):
            get_device_history(UNKNOWN_ASSETNUM)


# ═══════════════════════════════════════════════════════════════
# prediction_service 测试
# ═══════════════════════════════════════════════════════════════

class TestPredictionService:

    def test_predict_device_risk_known(self):
        """已知设备应返回 6 个时间窗口风险值。"""
        result = predict_device_risk(KNOWN_ASSETNUM)
        assert result["status"] == "success"
        for window in ["risk_7d", "risk_14d", "risk_21d", "risk_30d", "risk_60d", "risk_90d"]:
            val = result[window]
            assert 0.01 <= val <= 0.95, f"{window}={val} 超出范围"

    def test_predict_device_risk_unknown(self):
        """未知设备应抛出 ValueError。"""
        with pytest.raises(ValueError):
            predict_device_risk(UNKNOWN_ASSETNUM)

    def test_predict_returns_warning_level(self):
        """预测结果应包含预警等级。"""
        result = predict_device_risk(KNOWN_ASSETNUM)
        assert "warning_level" in result
        assert result["warning_level"] in ["红色预警", "橙色预警", "黄色预警", "绿色关注"]

    def test_get_high_risk_devices(self):
        """应返回高风险设备列表。"""
        result = get_high_risk_devices(top_n=5)
        assert result["status"] == "success"
        devices = result["devices"]
        assert 0 < len(devices) <= 5
        # 应按风险降序
        if len(devices) >= 2:
            assert devices[0]["risk_90d"] >= devices[1]["risk_90d"]

    def test_external_prediction_invalid_values_are_sanitized(self, monkeypatch):
        """外部 CSV 风险值非法时不应导致读取崩溃。"""
        csv_path = Path(__file__).resolve().parent / "_tmp_prediction_results.csv"
        try:
            csv_path.write_text(
                "assetnum,risk_7d,risk_14d,risk_21d,risk_30d,risk_60d,risk_90d\n"
                "BAD001,NaN,abc,-0.2,1.8,,inf\n"
                "BAD002,0.2,0.3,0.4,0.5,0.6,0.7\n",
                encoding="utf-8",
            )
            monkeypatch.setattr(model_adapter, "PREDICTION_RESULT_PATH", csv_path)

            result = model_adapter.get_external_prediction_by_assetnum("BAD001")
            assert result is not None
            for window in ["risk_7d", "risk_14d", "risk_21d", "risk_30d", "risk_60d", "risk_90d"]:
                assert 0.01 <= result[window] <= 0.95
                assert round(result[window], 2) == result[window]

            assert result["risk_21d"] == 0.01
            assert result["risk_30d"] == 0.95

            ranked = model_adapter.get_external_high_risk_predictions(top_n=2)
            assert len(ranked) == 2
            assert ranked[0]["risk_90d"] >= ranked[1]["risk_90d"]
        finally:
            if csv_path.exists():
                csv_path.unlink()


# ═══════════════════════════════════════════════════════════════
# warning_service 测试
# ═══════════════════════════════════════════════════════════════

class TestWarningService:

    def test_red_warning(self):
        result = generate_warning_info(risk_30d=0.80, risk_90d=0.92)
        assert result["warning_level"] == "红色预警"

    def test_orange_warning(self):
        result = generate_warning_info(risk_30d=0.60, risk_90d=0.80)
        assert result["warning_level"] == "橙色预警"

    def test_yellow_warning(self):
        result = generate_warning_info(risk_30d=0.40, risk_90d=0.60)
        assert result["warning_level"] == "黄色预警"

    def test_green_warning(self):
        result = generate_warning_info(risk_30d=0.20, risk_90d=0.30)
        assert result["warning_level"] == "绿色关注"

    def test_red_by_30d_only(self):
        """仅 30 天超标也应触发红色。"""
        result = generate_warning_info(risk_30d=0.76, risk_90d=0.50)
        assert result["warning_level"] == "红色预警"

    def test_orange_by_90d_only(self):
        """仅 90 天超标也应触发橙色。"""
        result = generate_warning_info(risk_30d=0.30, risk_90d=0.76)
        assert result["warning_level"] == "橙色预警"


# ═══════════════════════════════════════════════════════════════
# advice_service 测试
# ═══════════════════════════════════════════════════════════════

class TestAdviceService:

    def test_generate_advice_known(self):
        """已知设备应返回维修建议。"""
        result = generate_device_advice(KNOWN_ASSETNUM)
        assert result["status"] == "success"
        assert "recognized_fault_phenomena" in result
        assert "possible_causes" in result
        assert "inspection_suggestions" in result
        assert "spare_part_suggestions" in result

    def test_generate_advice_unknown(self):
        """未知设备应抛出 ValueError。"""
        with pytest.raises(ValueError):
            generate_device_advice(UNKNOWN_ASSETNUM)


# ═══════════════════════════════════════════════════════════════
# analysis_service 测试
# ═══════════════════════════════════════════════════════════════

class TestAnalysisService:

    def test_generate_analysis_known(self):
        """已知设备应返回完整综合分析。"""
        result = generate_device_analysis(KNOWN_ASSETNUM, history_limit=20)
        assert result["status"] == "success"
        assert "device_profile" in result
        assert "history_summary" in result
        assert "risk_prediction" in result
        assert "maintenance_advice" in result
        assert "called_tools" in result
        assert "analysis_statement" in result

    def test_analysis_profile_has_required_fields(self):
        """设备 profile 应包含必要字段。"""
        result = generate_device_analysis(KNOWN_ASSETNUM)
        profile = result["device_profile"]
        assert "assetnum" in profile
        assert "station_name" in profile
        assert "line" in profile
        assert "brand" in profile
