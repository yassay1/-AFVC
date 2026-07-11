"""故障类型预测 Schema 单元测试。

测试 backend/schemas/ 层的数据结构校验。
"""

import pytest
from pydantic import ValidationError

from backend.schemas.risk_prediction import RiskPredictionResult
from backend.schemas.fault_prediction import (
    FaultTypeScore,
    FaultTypePredictionResult,
)


class TestRiskPredictionResult:
    """风险预测 Schema 测试。"""

    def test_valid_result(self):
        """合法数据应通过校验。"""
        r = RiskPredictionResult(
            assetnum="1000029970",
            risk_7d=0.02, risk_14d=0.05, risk_21d=0.10,
            risk_30d=0.20, risk_60d=0.45, risk_90d=0.68,
        )
        assert r.assetnum == "1000029970"
        assert r.risk_30d == 0.20

    def test_probability_in_range(self):
        """概率必须在 [0, 1] 范围内。"""
        with pytest.raises(ValidationError):
            RiskPredictionResult(
                assetnum="test",
                risk_7d=1.5, risk_14d=0.5, risk_21d=0.5,
                risk_30d=0.5, risk_60d=0.5, risk_90d=0.5,
            )

    def test_negative_probability(self):
        """负概率应被拒绝。"""
        with pytest.raises(ValidationError):
            RiskPredictionResult(
                assetnum="test",
                risk_7d=-0.1, risk_14d=0.5, risk_21d=0.5,
                risk_30d=0.5, risk_60d=0.5, risk_90d=0.5,
            )

    def test_to_compat_dict(self):
        """应能转换为兼容字典。"""
        r = RiskPredictionResult(
            assetnum="EX011115",
            risk_7d=0.1, risk_14d=0.2, risk_21d=0.3,
            risk_30d=0.4, risk_60d=0.6, risk_90d=0.8,
            model_source="test", model_version="v1.0",
        )
        d = r.to_compat_dict()
        assert d["assetnum"] == "EX011115"
        assert d["risk_30d"] == 0.4

    def test_from_prediction_dict(self):
        """应能从现有字典构造。"""
        data = {
            "assetnum": "1000029970",
            "risk_7d": 0.10, "risk_14d": 0.20,
            "risk_21d": 0.30, "risk_30d": 0.40,
            "risk_60d": 0.60, "risk_90d": 0.80,
        }
        r = RiskPredictionResult.from_prediction_dict(data)
        assert r.assetnum == "1000029970"
        assert r.risk_90d == 0.80


class TestFaultTypeScore:
    """故障类型评分 Schema 测试。"""

    def test_valid_score(self):
        """合法评分应通过校验。"""
        fs = FaultTypeScore(
            fault_code="TICKET_CARD",
            fault_name="票卡处理异常",
            conditional_probability=0.50,
            estimated_occurrence_probability=0.34,
        )
        assert fs.fault_code == "TICKET_CARD"
        assert fs.conditional_probability == 0.50

    def test_invalid_fault_code(self):
        """非法故障代码应被拒绝。"""
        with pytest.raises(ValidationError):
            FaultTypeScore(
                fault_code="INVALID_CODE",
                fault_name="无效代码",
                conditional_probability=0.50,
                estimated_occurrence_probability=0.34,
            )

    def test_probability_range(self):
        """条件概率必须在 [0, 1] 内。"""
        with pytest.raises(ValidationError):
            FaultTypeScore(
                fault_code="TICKET_CARD",
                fault_name="票卡处理异常",
                conditional_probability=1.5,
                estimated_occurrence_probability=0.34,
            )

    def test_estimated_probability_range(self):
        """综合估计概率必须在 [0, 1] 内。"""
        with pytest.raises(ValidationError):
            FaultTypeScore(
                fault_code="TICKET_CARD",
                fault_name="票卡处理异常",
                conditional_probability=0.50,
                estimated_occurrence_probability=-0.1,
            )


class TestFaultTypePredictionResult:
    """故障类型预测结果 Schema 测试。"""

    def make_valid_result(self) -> FaultTypePredictionResult:
        """构建合法的预测结果。"""
        ml = FaultTypeScore(
            fault_code="TICKET_CARD",
            fault_name="票卡处理异常",
            conditional_probability=0.50,
            estimated_occurrence_probability=0.34,
        )
        return FaultTypePredictionResult(
            assetnum="1000029970",
            prediction_window_days=30,
            overall_failure_risk=0.68,
            most_likely_fault=ml,
            fault_type_predictions=[ml],
        )

    def test_valid_result(self):
        """合法结果应通过校验。"""
        fr = self.make_valid_result()
        assert fr.status == "success"
        assert fr.assetnum == "1000029970"

    def test_consistency_validation(self):
        """most_likely_fault 应与 predictions 的第一项一致。"""
        ml = FaultTypeScore(
            fault_code="TICKET_CARD",
            fault_name="票卡处理异常",
            conditional_probability=0.50,
            estimated_occurrence_probability=0.34,
        )
        ml2 = FaultTypeScore(
            fault_code="COMMUNICATION",
            fault_name="通信异常",
            conditional_probability=0.30,
            estimated_occurrence_probability=0.20,
        )
        with pytest.raises(ValidationError):
            FaultTypePredictionResult(
                assetnum="1000029970",
                prediction_window_days=30,
                overall_failure_risk=0.68,
                most_likely_fault=ml,          # TICKET_CARD
                fault_type_predictions=[ml2],   # COMMUNICATION — mismatch!
            )

    def test_to_compat_dict(self):
        """应能转换为兼容字典。"""
        fr = self.make_valid_result()
        d = fr.to_compat_dict()
        assert d["status"] == "success"
        assert d["assetnum"] == "1000029970"
        assert d["most_likely_fault"] is not None

    def test_unavailable_status(self):
        """unavailable 状态不需要 most_likely_fault。"""
        fr = FaultTypePredictionResult(
            status="unavailable",
            assetnum="1000029970",
            prediction_window_days=30,
            overall_failure_risk=0.0,
            most_likely_fault=None,
            fault_type_predictions=[],
        )
        assert fr.status == "unavailable"

    def test_prediction_statement_default(self):
        """prediction_statement 应有默认值。"""
        fr = FaultTypePredictionResult(
            assetnum="1000029970",
            prediction_window_days=30,
            overall_failure_risk=0.5,
        )
        assert len(fr.prediction_statement) > 0
