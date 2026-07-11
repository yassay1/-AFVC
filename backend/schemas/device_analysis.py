"""设备综合分析业务 Schema —— DeviceAnalysisResult。

定义综合分析的标准输出结构，用于逐步替代现有字典格式。
"""

from typing import Any

from pydantic import BaseModel, Field


class DeviceAnalysisResult(BaseModel):
    """单设备综合分析结果。

    聚合设备信息、历史工单、风险预测、故障类型预测和维修建议。
    """

    status: str = Field(default="success", description="分析状态")
    message: str = Field(default="", description="状态说明")
    assetnum: str = Field(description="设备编号")

    device_profile: dict[str, Any] = Field(
        default_factory=dict, description="设备基本信息"
    )
    history_summary: dict[str, Any] = Field(
        default_factory=dict, description="历史工单摘要"
    )
    risk_prediction: dict[str, Any] = Field(
        default_factory=dict, description="风险预测结果"
    )
    maintenance_advice: dict[str, Any] = Field(
        default_factory=dict, description="维修与巡检建议"
    )

    # ── 新增：故障类型预测 ──
    fault_prediction: dict[str, Any] | None = Field(
        default=None,
        description="故障类型预测结果；无模型结果时为 unavailable 状态字典",
    )

    called_tools: list[str] = Field(
        default_factory=list, description="调用的子工具列表"
    )
    analysis_statement: str = Field(
        default="", description="分析说明与科学边界声明"
    )

    def to_compat_dict(self) -> dict[str, Any]:
        """转换为兼容字典。"""
        return self.model_dump(exclude_none=False)
