"""故障类型预测业务 Schema —— FaultTypePredictionResult 标准输出结构。

定义故障类型预测的标准数据格式，包括：
- FaultTypeScore: 单个故障类别的条件概率与综合概率
- FaultTypePredictionResult: 完整的故障类型预测结果
"""

from typing import Any

from pydantic import BaseModel, Field, model_validator

from backend.domain.fault import is_valid_fault_code, FAULT_CODE_TO_NAME


class FaultTypeScore(BaseModel):
    """单个故障类别的预测评分。

    包含条件概率和综合估计发生概率两层信息。
    """

    fault_code: str = Field(description="故障类别代码，如 TICKET_CARD")
    fault_name: str = Field(description="故障类别中文名称，如 票卡处理异常")
    conditional_probability: float = Field(
        ge=0.0, le=1.0,
        description="如果发生故障，属于该类别的条件概率 P(category|failure)"
    )
    estimated_occurrence_probability: float = Field(
        ge=0.0, le=1.0,
        description="综合估计发生概率 = overall_failure_risk × conditional_probability"
    )

    @model_validator(mode="after")
    def validate_fault_code(self) -> "FaultTypeScore":
        """校验 fault_code 是否为合法故障类别。"""
        if not is_valid_fault_code(self.fault_code):
            raise ValueError(
                f"非法的故障代码：{self.fault_code}，"
                f"合法代码：{list(FAULT_CODE_TO_NAME.keys())}"
            )
        return self


class FaultTypePredictionResult(BaseModel):
    """设备故障类型预测完整结果。

    包含总体风险、最可能故障类型和所有候选故障类型列表。
    """

    status: str = Field(
        default="success",
        description="预测状态：success / unavailable / error"
    )
    message: str = Field(default="", description="状态说明消息")
    assetnum: str = Field(description="设备编号")
    prediction_window_days: int = Field(
        ge=7, le=90, description="预测时间窗口（天）"
    )
    overall_failure_risk: float = Field(
        ge=0.0, le=1.0, description="预测窗口内发生故障工单的总体风险"
    )
    most_likely_fault: FaultTypeScore | None = Field(
        default=None, description="最可能发生的故障类别（条件概率最高）"
    )
    fault_type_predictions: list[FaultTypeScore] = Field(
        default_factory=list,
        description="所有故障类别预测结果，按条件概率降序排列"
    )
    model_source: str | None = Field(default=None, description="模型来源标识")
    model_version: str | None = Field(default=None, description="模型版本号")
    prediction_statement: str = Field(
        default=(
            "故障类型概率表示在预测窗口内发生故障时，"
            "各故障类别的相对可能性，不代表故障一定发生。"
        ),
        description="预测结果说明",
    )

    @model_validator(mode="after")
    def validate_consistency(self) -> "FaultTypePredictionResult":
        """校验结果内部一致性。"""
        if self.status == "success":
            # most_likely_fault 应该与 fault_type_predictions 的第一个一致
            if self.most_likely_fault is not None and self.fault_type_predictions:
                if (self.most_likely_fault.fault_code
                        != self.fault_type_predictions[0].fault_code):
                    raise ValueError(
                        "most_likely_fault 必须与 fault_type_predictions 的第一项一致"
                    )
        return self

    def to_compat_dict(self) -> dict[str, Any]:
        """转换为兼容字典格式。"""
        return self.model_dump(exclude_none=False)
