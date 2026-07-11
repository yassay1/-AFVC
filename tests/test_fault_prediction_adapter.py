"""故障类型预测 Adapter 单元测试。

测试 backend/adapters/fault_prediction_adapter.py 的 CSV 读取与校验。
"""

import pytest

from backend.adapters.fault_prediction_adapter import (
    has_fault_prediction_file,
    get_fault_type_scores,
    load_fault_prediction_table,
)


class TestFaultPredictionFile:
    """CSV 文件存在性测试。"""

    def test_has_fault_prediction_file(self):
        """mock CSV 文件应存在。"""
        assert has_fault_prediction_file() is True

    def test_load_prediction_table(self):
        """应能加载 CSV 为 DataFrame。"""
        df = load_fault_prediction_table()
        assert df.height > 0
        required_cols = ["assetnum", "window_days", "fault_code", "fault_name", "conditional_probability"]
        for col in required_cols:
            assert col in df.columns


class TestGetFaultTypeScores:
    """get_fault_type_scores 函数测试。"""

    def test_known_device_window_30(self):
        """已知设备在窗口 30 应有预测结果。"""
        scores = get_fault_type_scores("1000029970", 30)
        assert len(scores) > 0
        # 验证排序
        probs = [s["conditional_probability"] for s in scores]
        assert probs == sorted(probs, reverse=True)

    def test_unknown_device(self):
        """未知设备应返回空列表。"""
        scores = get_fault_type_scores("UNKNOWN_DEVICE", 30)
        assert scores == []

    def test_different_windows(self):
        """不同窗口应返回不同结果。"""
        scores_30 = get_fault_type_scores("1000029970", 30)
        scores_90 = get_fault_type_scores("1000029970", 90)
        assert len(scores_30) > 0
        assert len(scores_90) > 0
        # 90 天可能有更多类别
        assert len(scores_90) >= 2

    def test_fault_codes_are_valid(self):
        """所有返回的 fault_code 应为合法枚举。"""
        scores = get_fault_type_scores("1000029970", 30)
        from backend.domain.fault import is_valid_fault_code
        for s in scores:
            assert is_valid_fault_code(s["fault_code"])

    def test_probabilities_in_range(self):
        """条件概率应在 [0, 1] 内。"""
        scores = get_fault_type_scores("EX011115", 30)
        for s in scores:
            assert 0.0 <= s["conditional_probability"] <= 1.0

    def test_fault_names_match_code(self):
        """fault_name 应与 fault_code 定义一致。"""
        from backend.domain.fault import FAULT_CODE_TO_NAME
        scores = get_fault_type_scores("1000029970", 30)
        for s in scores:
            assert s["fault_name"] == FAULT_CODE_TO_NAME.get(s["fault_code"], "")

    def test_ex011115_system_top(self):
        """EX011115 在窗口 30 应以 SYSTEM 为首。"""
        scores = get_fault_type_scores("EX011115", 30)
        assert len(scores) > 0
        assert scores[0]["fault_code"] == "SYSTEM"

    def test_conditional_probability_sorted(self):
        """所有结果应按条件概率降序排列。"""
        for device in ["1000029970", "EX011115"]:
            for window in [7, 30, 90]:
                scores = get_fault_type_scores(device, window)
                probs = [s["conditional_probability"] for s in scores]
                assert probs == sorted(probs, reverse=True), \
                    f"未正确排序: device={device}, window={window}, probs={probs}"
