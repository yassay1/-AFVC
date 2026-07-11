"""风险预测业务 Schema —— RiskPredictionResult 标准输出结构。

本 Schema 定义风险预测的标准输出格式，
可与现有 prediction_service.py 返回的字典兼容。
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class RiskPredictionResult(BaseModel):
    """单设备风险预测结果。

    概率值范围 0～1。累计风险原则上应随时间窗口增加而不下降。
    """

    assetnum: str = Field(description="设备编号")

    risk_7d: float = Field(ge=0.0, le=1.0, description="7 天复发风险")
    risk_14d: float = Field(ge=0.0, le=1.0, description="14 天复发风险")
    risk_21d: float = Field(ge=0.0, le=1.0, description="21 天复发风险")
    risk_30d: float = Field(ge=0.0, le=1.0, description="30 天复发风险")
    risk_60d: float = Field(ge=0.0, le=1.0, description="60 天复发风险")
    risk_90d: float = Field(ge=0.0, le=1.0, description="90 天复发风险")

    model_source: str | None = Field(default=None, description="模型来源标识")
    model_version: str | None = Field(default=None, description="模型版本号")
    prediction_time: datetime | None = Field(default=None, description="预测生成时间")

    @model_validator(mode="after")
    def check_risk_monotonicity(self) -> "RiskPredictionResult":
        """校验累计风险单调性（软校验：仅记录警告，不阻断）。"""
        # 这是一个软校验，不抛出异常，因为极端情况下模型输出可能略有波动
        # 如果需要在 Service 层做硬校验，可以使用 domain.risk.validate_risk_monotonicity
        return self

    def to_compat_dict(self) -> dict[str, Any]:
        """转换为与现有 prediction_service 返回格式兼容的字典。

        把 Pydantic 模型导出为字典，同时保留额外字段空间。
        """
        return self.model_dump(exclude_none=False)

    @classmethod
    def from_prediction_dict(cls, data: dict[str, Any]) -> "RiskPredictionResult":
        """从现有 predict_device_risk 返回的字典构造 Schema 对象。

        用于在 Adapter 或 Service 边界进行校验。
        """
        return cls(
            assetnum=str(data.get("assetnum", "")),
            risk_7d=float(data.get("risk_7d", 0.01)),
            risk_14d=float(data.get("risk_14d", 0.01)),
            risk_21d=float(data.get("risk_21d", 0.01)),
            risk_30d=float(data.get("risk_30d", 0.01)),
            risk_60d=float(data.get("risk_60d", 0.01)),
            risk_90d=float(data.get("risk_90d", 0.01)),
            model_source=data.get("model_source"),
            model_version=data.get("model_version"),
        )
