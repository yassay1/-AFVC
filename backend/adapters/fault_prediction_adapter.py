"""故障类型预测 Adapter —— 读取 fault_prediction_results.csv 并返回标准结果。

职责：
1. 定位 fault_prediction_results.csv
2. 读取 CSV
3. 校验必要字段
4. 清洗 assetnum
5. 转换 window_days 为整数
6. 转换 conditional_probability 为浮点数
7. 将概率限制在 0～1
8. 校验 fault_code 是否属于统一故障枚举
9. 根据 assetnum 和 window_days 筛选结果
10. 返回经 FaultTypeScore 校验的标准结果
11. 按 conditional_probability 从高到低排序

不负责：调用风险预测、计算综合概率、生成预警、生成报告、调用 LLM。
"""

import math
from pathlib import Path
from typing import Any

import polars as pl

from backend.domain.fault import (
    is_valid_fault_code,
    normalize_fault_code,
    FAULT_CODE_TO_NAME,
)
from backend.schemas.fault_prediction import FaultTypeScore

# ── CSV 路径 ──────────────────────────────────────────────────────

FAULT_PREDICTION_RESULT_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "mock"
    / "fault_prediction_results.csv"
)

REQUIRED_COLUMNS = [
    "assetnum",
    "window_days",
    "fault_code",
    "fault_name",
    "conditional_probability",
]


# ── 辅助函数 ──────────────────────────────────────────────────────

def _safe_float(value: Any, default: float = 0.0) -> float:
    """安全转换浮点数，并限制在 [0, 1]。"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(v) or math.isinf(v):
        return default
    return max(0.0, min(1.0, round(v, 4)))


def _safe_int(value: Any, default: int = 30) -> int:
    """安全转换整数。"""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


# ── 公开函数 ──────────────────────────────────────────────────────

def has_fault_prediction_file() -> bool:
    """判断是否存在故障类型预测结果文件。"""
    return FAULT_PREDICTION_RESULT_PATH.exists()


def load_fault_prediction_table() -> pl.DataFrame:
    """读取故障类型预测结果表。

    Returns:
        Polars DataFrame，已清洗和校验。

    Raises:
        FileNotFoundError: CSV 文件不存在。
        ValueError: 缺少必要字段。
    """
    if not FAULT_PREDICTION_RESULT_PATH.exists():
        raise FileNotFoundError(
            f"未找到故障类型预测结果文件：{FAULT_PREDICTION_RESULT_PATH}"
        )

    df = pl.read_csv(FAULT_PREDICTION_RESULT_PATH, infer_schema_length=0)

    # 清理列名
    df = df.rename({
        col: col.strip()
        for col in df.columns
        if isinstance(col, str)
    })

    # 校验必要字段
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(
            f"故障类型预测结果表缺少必要字段：{missing_cols}"
        )

    return df


def get_fault_type_scores(
    assetnum: str,
    window_days: int = 30,
) -> list[dict[str, Any]]:
    """根据设备编号和预测窗口获取故障类别条件概率列表。

    Args:
        assetnum: 设备编号。
        window_days: 预测时间窗口（天），默认 30。

    Returns:
        经过 FaultTypeScore 校验的故障类型评分列表，
        按 conditional_probability 从高到低排序。
        如果没有匹配结果，返回空列表。

    Raises:
        FileNotFoundError: CSV 文件不存在。
        ValueError: 缺少必要字段或数据异常。
    """
    if not has_fault_prediction_file():
        return []

    target_assetnum = assetnum.strip()
    target_window = int(window_days)

    df = load_fault_prediction_table()

    # 清洗 assetnum
    df = df.with_columns(
        pl.col("assetnum")
        .cast(pl.Utf8)
        .fill_null("")
        .str.strip_chars()
        .alias("assetnum")
    )

    # 筛选
    result_df = df.filter(
        (pl.col("assetnum") == target_assetnum)
        & (pl.col("window_days").cast(pl.Int64) == target_window)
    )

    if result_df.height == 0:
        return []

    # 转换为标准结果
    scores: list[dict[str, Any]] = []
    invalid_codes: list[str] = []

    for row in result_df.to_dicts():
        raw_code = str(row.get("fault_code", "")).strip()
        fault_code = normalize_fault_code(raw_code)

        if fault_code is None:
            invalid_codes.append(raw_code)
            continue

        conditional_prob = _safe_float(row.get("conditional_probability"))

        # 获取 fault_name：优先使用 CSV 中的值，否则使用枚举定义
        fault_name = str(row.get("fault_name", "")).strip()
        if not fault_name:
            fault_name = FAULT_CODE_TO_NAME.get(fault_code, fault_code)

        # 注意：Adapter 不计算 estimated_occurrence_probability，
        # 该值由 Service 层在获得 overall_failure_risk 后计算。
        # 这里使用 0.0 作为占位值。
        score = FaultTypeScore(
            fault_code=fault_code,
            fault_name=fault_name,
            conditional_probability=conditional_prob,
            estimated_occurrence_probability=0.0,  # Service 层填充
        )
        scores.append(score.model_dump())

    if invalid_codes:
        raise ValueError(
            f"CSV 中包含非法的故障代码：{invalid_codes}，"
            f"设备={target_assetnum}，窗口={target_window}天"
        )

    # 按 conditional_probability 从高到低排序
    scores.sort(key=lambda s: s["conditional_probability"], reverse=True)

    return scores
