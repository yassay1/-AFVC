"""AFC 业务 Schema 层 —— 输入输出数据结构定义。

本层使用 Pydantic 定义系统各层的标准数据格式。
Agent 中间结构由 backend/agent/schemas.py 管理，
本层管理业务输入输出结构。
"""

from backend.schemas.risk_prediction import RiskPredictionResult
from backend.schemas.fault_prediction import (
    FaultTypeScore,
    FaultTypePredictionResult,
)
from backend.schemas.device_analysis import DeviceAnalysisResult

__all__ = [
    "RiskPredictionResult",
    "FaultTypeScore",
    "FaultTypePredictionResult",
    "DeviceAnalysisResult",
]
