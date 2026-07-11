"""风险领域定义 —— 预测窗口、概率计算与校验函数。

本模块提供风险预测相关的纯业务规则：
- 支持的预测窗口
- 综合发生概率计算公式
- 概率范围校验
- 累计风险单调性校验
"""

from typing import Any

# ── 预测窗口 ──────────────────────────────────────────────────────

SUPPORTED_PREDICTION_WINDOWS: tuple[int, ...] = (7, 14, 21, 30, 60, 90)

# ── 概率边界 ──────────────────────────────────────────────────────

PROBABILITY_MIN: float = 0.0
PROBABILITY_MAX: float = 1.0


# ── 风险字段映射 ──────────────────────────────────────────────────

_WINDOW_TO_RISK_FIELD: dict[int, str] = {
    7: "risk_7d",
    14: "risk_14d",
    21: "risk_21d",
    30: "risk_30d",
    60: "risk_60d",
    90: "risk_90d",
}


def get_risk_for_window(risk_result: dict[str, Any], window_days: int) -> float | None:
    """从风险预测结果字典中提取指定窗口的风险值。

    Args:
        risk_result: predict_device_risk 返回的结果字典。
        window_days: 预测窗口天数，必须在 SUPPORTED_PREDICTION_WINDOWS 中。

    Returns:
        对应窗口的风险浮点值，若不存在则返回 None。

    Raises:
        ValueError: window_days 不是受支持的预测窗口。
    """
    if window_days not in _WINDOW_TO_RISK_FIELD:
        raise ValueError(
            f"不支持的预测窗口 {window_days} 天，"
            f"支持窗口：{list(SUPPORTED_PREDICTION_WINDOWS)}"
        )
    field = _WINDOW_TO_RISK_FIELD[window_days]
    value = risk_result.get(field)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ── 综合发生概率 ──────────────────────────────────────────────────

def compute_estimated_occurrence_probability(
    overall_failure_risk: float,
    conditional_probability: float,
) -> float:
    """计算某类故障的综合估计发生概率。

    公式：
        estimated_occurrence_probability
        = overall_failure_risk × conditional_probability

    含义：
        overall_failure_risk: 预测窗口内发生任何故障工单的总体风险。
        conditional_probability: 如果发生故障，属于某一类别的条件概率。
        两者相乘得到"该类别故障在预测窗口内实际发生的估计概率"。

    Args:
        overall_failure_risk: 总体故障风险，范围 [0, 1]。
        conditional_probability: 条件概率，范围 [0, 1]。

    Returns:
        综合估计发生概率，范围 [0, 1]。

    Raises:
        ValueError: 任一输入不在 [0, 1] 范围内。
    """
    if not (PROBABILITY_MIN <= overall_failure_risk <= PROBABILITY_MAX):
        raise ValueError(
            f"overall_failure_risk 必须在 [{PROBABILITY_MIN}, {PROBABILITY_MAX}] 之间，"
            f"实际值：{overall_failure_risk}"
        )
    if not (PROBABILITY_MIN <= conditional_probability <= PROBABILITY_MAX):
        raise ValueError(
            f"conditional_probability 必须在 [{PROBABILITY_MIN}, {PROBABILITY_MAX}] 之间，"
            f"实际值：{conditional_probability}"
        )
    result = overall_failure_risk * conditional_probability
    return round(result, 4)


# ── 概率范围校验 ──────────────────────────────────────────────────

def validate_probability_range(value: float, field_name: str = "概率值") -> None:
    """校验概率值是否在 [0, 1] 范围内。

    Args:
        value: 待校验的概率值。
        field_name: 字段名称，用于错误消息。

    Raises:
        ValueError: 概率不在 [0, 1] 范围内。
    """
    if not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} 必须是数字类型，实际类型：{type(value).__name__}")
    if value < PROBABILITY_MIN or value > PROBABILITY_MAX:
        raise ValueError(
            f"{field_name} 必须在 [{PROBABILITY_MIN}, {PROBABILITY_MAX}] 之间，"
            f"实际值：{value}"
        )


# ── 累计风险单调性校验 ───────────────────────────────────────────

def validate_risk_monotonicity(risks: dict[int, float]) -> list[str]:
    """校验不同时间窗口的累计风险是否单调不下降。

    规则：累计风险原则上应随预测窗口增加而不下降。
    例如：risk_14d >= risk_7d, risk_30d >= risk_21d 等。

    Args:
        risks: 窗口天数 → 风险值的映射。

    Returns:
        违反单调性的警告列表，每项描述一处不单调。
        空列表表示所有校验通过。
    """
    warnings: list[str] = []
    sorted_windows = sorted(risks.keys())

    for i in range(1, len(sorted_windows)):
        prev_window = sorted_windows[i - 1]
        curr_window = sorted_windows[i]
        prev_risk = risks[prev_window]
        curr_risk = risks[curr_window]

        if curr_risk < prev_risk:
            warnings.append(
                f"风险单调性异常：{curr_window}天风险({curr_risk}) < "
                f"{prev_window}天风险({prev_risk})，"
                f"累计风险应随时间窗口增加而不下降"
            )

    return warnings
