"""故障领域定义单元测试。

测试 backend/domain/ 层的纯函数逻辑。
"""

import pytest

from backend.domain.fault import (
    FaultCategory,
    FAULT_CODE_TO_NAME,
    FAULT_NAME_TO_CODE,
    is_valid_fault_code,
    normalize_fault_code,
)
from backend.domain.risk import (
    SUPPORTED_PREDICTION_WINDOWS,
    PROBABILITY_MIN,
    PROBABILITY_MAX,
    compute_estimated_occurrence_probability,
    validate_probability_range,
    validate_risk_monotonicity,
    get_risk_for_window,
)
from backend.domain.warning import (
    WarningLevel,
    generate_warning_info,
)


# ═══════════════════════════════════════════════════════════════
# FaultCategory 枚举测试
# ═══════════════════════════════════════════════════════════════

class TestFaultCategory:
    """故障类别枚举测试。"""

    def test_all_categories_have_names(self):
        """每个故障代码都应有中文名称映射。"""
        for category in FaultCategory:
            assert category.value in FAULT_CODE_TO_NAME
            assert isinstance(FAULT_CODE_TO_NAME[category.value], str)
            assert len(FAULT_CODE_TO_NAME[category.value]) > 0

    def test_enum_values_are_unique(self):
        """故障代码应唯一。"""
        values = [c.value for c in FaultCategory]
        assert len(values) == len(set(values))

    def test_name_mapping_is_bijective(self):
        """中文名称反向映射应完整。"""
        assert len(FAULT_CODE_TO_NAME) == len(FAULT_NAME_TO_CODE)
        for code, name in FAULT_CODE_TO_NAME.items():
            assert FAULT_NAME_TO_CODE[name] == code


class TestFaultValidation:
    """故障代码校验测试。"""

    @pytest.mark.parametrize("code", [
        "TICKET_CARD",
        "SERVICE_SUSPENDED",
        "SYSTEM",
        "COMMUNICATION",
        "GATE_CONTROL",
        "OTHER",
    ])
    def test_valid_fault_codes(self, code):
        """合法的故障代码应通过校验。"""
        assert is_valid_fault_code(code) is True
        assert normalize_fault_code(code) == code

    @pytest.mark.parametrize("code", [
        "INVALID",
        "",
        "ABC",
        "ticket",
        None,
        123,
    ])
    def test_invalid_fault_codes(self, code):
        """非法的故障代码应被拒绝。"""
        if isinstance(code, str):
            assert is_valid_fault_code(code) is False
            assert normalize_fault_code(code) is None
        else:
            assert is_valid_fault_code(code) is False

    def test_case_insensitive_normalization(self):
        """标准化应处理大小写。"""
        assert normalize_fault_code("ticket_card") == "TICKET_CARD"
        assert normalize_fault_code("Ticket_Card") == "TICKET_CARD"
        assert normalize_fault_code("  ticket_card  ") == "TICKET_CARD"


# ═══════════════════════════════════════════════════════════════
# 风险领域测试
# ═══════════════════════════════════════════════════════════════

class TestPredictionWindows:
    """预测窗口测试。"""

    def test_supported_windows(self):
        """支持的预测窗口应为 7/14/21/30/60/90。"""
        expected = (7, 14, 21, 30, 60, 90)
        assert SUPPORTED_PREDICTION_WINDOWS == expected

    def test_get_risk_for_window_valid(self):
        """应正确提取各窗口风险值。"""
        risk_result = {
            "risk_7d": 0.10, "risk_14d": 0.20, "risk_21d": 0.30,
            "risk_30d": 0.40, "risk_60d": 0.60, "risk_90d": 0.80,
        }
        assert get_risk_for_window(risk_result, 7) == 0.10
        assert get_risk_for_window(risk_result, 30) == 0.40
        assert get_risk_for_window(risk_result, 90) == 0.80

    def test_get_risk_for_window_invalid(self):
        """非法窗口应抛出 ValueError。"""
        with pytest.raises(ValueError):
            get_risk_for_window({}, 999)

    def test_get_risk_for_window_missing(self):
        """缺少字段时应返回 None。"""
        assert get_risk_for_window({"risk_30d": 0.5}, 7) is None


class TestEstimatedProbability:
    """综合发生概率计算测试。"""

    def test_basic_calculation(self):
        """测试基本计算公式。"""
        result = compute_estimated_occurrence_probability(0.68, 0.50)
        assert result == 0.34

    def test_boundary_values(self):
        """测试边界值。"""
        assert compute_estimated_occurrence_probability(1.0, 0.5) == 0.5
        assert compute_estimated_occurrence_probability(0.0, 0.5) == 0.0
        assert compute_estimated_occurrence_probability(0.5, 1.0) == 0.5
        assert compute_estimated_occurrence_probability(0.5, 0.0) == 0.0

    def test_probability_multiplication_clamping(self):
        """概率相乘后应在 [0, 1] 内。"""
        result = compute_estimated_occurrence_probability(0.95, 0.95)
        assert 0.0 <= result <= 1.0

    def test_invalid_overall_risk(self):
        """非法 overall_failure_risk 应抛出 ValueError。"""
        with pytest.raises(ValueError):
            compute_estimated_occurrence_probability(1.5, 0.5)
        with pytest.raises(ValueError):
            compute_estimated_occurrence_probability(-0.1, 0.5)

    def test_invalid_conditional_prob(self):
        """非法 conditional_probability 应抛出 ValueError。"""
        with pytest.raises(ValueError):
            compute_estimated_occurrence_probability(0.5, 1.5)
        with pytest.raises(ValueError):
            compute_estimated_occurrence_probability(0.5, -0.1)


class TestProbabilityRangeValidation:
    """概率范围校验测试。"""

    def test_valid_probability(self):
        """合法概率不应抛出异常。"""
        validate_probability_range(0.0)
        validate_probability_range(0.5)
        validate_probability_range(1.0)

    def test_invalid_probability_too_high(self):
        """超过 1 的概率应抛出 ValueError。"""
        with pytest.raises(ValueError):
            validate_probability_range(1.5)

    def test_invalid_probability_negative(self):
        """负概率应抛出 ValueError。"""
        with pytest.raises(ValueError):
            validate_probability_range(-0.1)

    def test_non_numeric(self):
        """非数字类型应抛出 TypeError。"""
        with pytest.raises(TypeError):
            validate_probability_range("high")


class TestRiskMonotonicity:
    """风险单调性校验测试。"""

    def test_valid_monotonicity(self):
        """单调递增的风险值应无警告。"""
        risks = {7: 0.10, 14: 0.20, 30: 0.40, 60: 0.70, 90: 0.90}
        warnings = validate_risk_monotonicity(risks)
        assert len(warnings) == 0

    def test_invalid_monotonicity(self):
        """违反单调性应产生警告。"""
        risks = {7: 0.50, 14: 0.30, 30: 0.80}
        warnings = validate_risk_monotonicity(risks)
        assert len(warnings) > 0
        assert "14" in warnings[0] and "7" in warnings[0]

    def test_equal_risks(self):
        """相等的风险值不应触发警告。"""
        risks = {7: 0.30, 14: 0.30, 30: 0.30}
        warnings = validate_risk_monotonicity(risks)
        assert len(warnings) == 0


# ═══════════════════════════════════════════════════════════════
# 预警规则测试
# ═══════════════════════════════════════════════════════════════

class TestWarningLevels:
    """预警等级规则测试。"""

    def test_red_warning(self):
        """红色预警条件。"""
        result = generate_warning_info(0.80, 0.85)
        assert result["warning_level"] == WarningLevel.RED.value

        result = generate_warning_info(0.50, 0.95)
        assert result["warning_level"] == WarningLevel.RED.value

    def test_orange_warning(self):
        """橙色预警条件。"""
        result = generate_warning_info(0.60, 0.70)
        assert result["warning_level"] == WarningLevel.ORANGE.value

        result = generate_warning_info(0.40, 0.80)
        assert result["warning_level"] == WarningLevel.ORANGE.value

    def test_yellow_warning(self):
        """黄色预警条件。"""
        result = generate_warning_info(0.40, 0.50)
        assert result["warning_level"] == WarningLevel.YELLOW.value

        result = generate_warning_info(0.30, 0.60)
        assert result["warning_level"] == WarningLevel.YELLOW.value

    def test_green_warning(self):
        """绿色关注条件。"""
        result = generate_warning_info(0.10, 0.20)
        assert result["warning_level"] == WarningLevel.GREEN.value

    def test_warning_has_required_fields(self):
        """预警信息应包含所有必要字段。"""
        result = generate_warning_info(0.40, 0.60)
        assert "warning_level" in result
        assert "suggested_inspection_window" in result
        assert "warning_reason" in result

    def test_warning_level_enum_values(self):
        """预警等级应与 WarningLevel 枚举一致。"""
        expected_levels = {e.value for e in WarningLevel}
        for r30, r90 in [(0.80, 0.95), (0.60, 0.80), (0.40, 0.60), (0.10, 0.20)]:
            result = generate_warning_info(r30, r90)
            assert result["warning_level"] in expected_levels
