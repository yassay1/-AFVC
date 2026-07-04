from pathlib import Path
from typing import Any
import math

import polars as pl


PREDICTION_RESULT_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "mock"
    / "prediction_results.csv"
)


REQUIRED_PREDICTION_COLUMNS = [
    "assetnum",
    "risk_7d",
    "risk_14d",
    "risk_21d",
    "risk_30d",
    "risk_60d",
    "risk_90d",
]

RISK_COLUMNS = [
    "risk_7d",
    "risk_14d",
    "risk_21d",
    "risk_30d",
    "risk_60d",
    "risk_90d",
]


def _safe_risk_value(value: Any, default: float = 0.01) -> float:
    """安全转换外部 CSV 风险值，并限制在 0.01~0.95。"""
    try:
        risk = float(value)
    except (TypeError, ValueError):
        risk = default

    if math.isnan(risk) or math.isinf(risk):
        risk = default

    risk = max(0.01, min(0.95, risk))
    return round(risk, 2)


def _prediction_record_from_row(row: dict[str, Any], assetnum: str | None = None) -> dict[str, Any]:
    target_assetnum = (assetnum or str(row.get("assetnum", ""))).strip()
    record = {"assetnum": target_assetnum}
    for column in RISK_COLUMNS:
        record[column] = _safe_risk_value(row.get(column))
    return record


def has_external_prediction_file() -> bool:
    """
    判断是否存在外部预测结果文件。

    第一版用于读取队友输出的 CSV 预测结果。
    后续可扩展为：
    1. 读取 Excel；
    2. 加载模型文件；
    3. 调用模型 API；
    4. 从数据库读取预测结果。
    """
    return PREDICTION_RESULT_PATH.exists()


def load_prediction_result_table() -> pl.DataFrame:
    """
    读取队友提供的预测结果表。

    当前默认路径：
    backend/data/mock/prediction_results.csv
    """
    if not PREDICTION_RESULT_PATH.exists():
        raise FileNotFoundError(
            f"未找到预测结果文件：{PREDICTION_RESULT_PATH}"
        )

    df = pl.read_csv(PREDICTION_RESULT_PATH, infer_schema_length=0)

    df = df.rename({
        column: column.strip()
        for column in df.columns
        if isinstance(column, str)
    })

    missing_columns = [
        column
        for column in REQUIRED_PREDICTION_COLUMNS
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"预测结果表缺少必要字段：{missing_columns}"
        )

    return df


def get_external_prediction_by_assetnum(assetnum: str) -> dict[str, Any] | None:
    """
    根据设备编号，从外部预测结果表中读取预测结果。

    如果没有预测文件，或预测表中没有该设备，则返回 None。
    prediction_service.py 可以继续回退到 mock 预测。
    """
    if not has_external_prediction_file():
        return None

    target_assetnum = assetnum.strip()

    df = load_prediction_result_table()

    result_df = (
        df
        .with_columns(
            pl.col("assetnum")
            .cast(pl.Utf8)
            .fill_null("")
            .str.strip_chars()
            .alias("assetnum")
        )
        .filter(pl.col("assetnum") == target_assetnum)
    )

    if result_df.height == 0:
        return None

    row = result_df.head(1).to_dicts()[0]

    return {
        **_prediction_record_from_row(row, target_assetnum),
        "model_source": "external_prediction_csv",
        "model_note": "当前预测结果来自队友或外部模型输出的 prediction_results.csv 文件。",
    }

def get_external_high_risk_predictions(top_n: int = 10) -> list[dict[str, Any]]:
    """
    从外部预测结果表中读取高风险设备 Top N。

    排序逻辑：
    1. 优先按 risk_90d 从高到低排序；
    2. 如果 risk_90d 相同，再按 risk_30d 从高到低排序。

    返回内容只包含预测结果本身。
    设备车站、品牌、线路等信息由 prediction_service.py 再从工单数据中补充。
    """
    if not has_external_prediction_file():
        return []

    df = load_prediction_result_table()

    result_df = (
        df
        .with_columns(
            pl.col("assetnum")
            .cast(pl.Utf8)
            .fill_null("")
            .str.strip_chars()
            .alias("assetnum")
        )
        .filter(pl.col("assetnum") != "")
    )

    records = result_df.to_dicts()
    sanitized_records = [
        {
            **_prediction_record_from_row(row),
            "model_source": "external_prediction_csv",
        }
        for row in records
    ]
    sanitized_records.sort(key=lambda row: (row["risk_90d"], row["risk_30d"]), reverse=True)
    return sanitized_records[:top_n]
