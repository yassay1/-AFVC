"""AFC 业务领域层 —— 纯业务规则与稳定概念。

本层不包含任何文件读取、HTTP 调用、LLM 调用或 FastAPI 依赖。
只放纯函数业务逻辑。
"""

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

__all__ = [
    # fault
    "FaultCategory",
    "FAULT_CODE_TO_NAME",
    "FAULT_NAME_TO_CODE",
    "is_valid_fault_code",
    "normalize_fault_code",
    # risk
    "SUPPORTED_PREDICTION_WINDOWS",
    "PROBABILITY_MIN",
    "PROBABILITY_MAX",
    "compute_estimated_occurrence_probability",
    "validate_probability_range",
    "validate_risk_monotonicity",
    "get_risk_for_window",
    # warning
    "WarningLevel",
    "generate_warning_info",
]
