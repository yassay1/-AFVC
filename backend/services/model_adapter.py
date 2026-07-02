from pathlib import Path
from typing import Any

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

    df = pl.read_csv(PREDICTION_RESULT_PATH)

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
        "assetnum": target_assetnum,
        "risk_7d": float(row["risk_7d"]),
        "risk_14d": float(row["risk_14d"]),
        "risk_21d": float(row["risk_21d"]),
        "risk_30d": float(row["risk_30d"]),
        "risk_60d": float(row["risk_60d"]),
        "risk_90d": float(row["risk_90d"]),
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

    # 保证风险字段是数值类型
    df = df.with_columns(
        pl.col("risk_7d").cast(pl.Float64),
        pl.col("risk_14d").cast(pl.Float64),
        pl.col("risk_21d").cast(pl.Float64),
        pl.col("risk_30d").cast(pl.Float64),
        pl.col("risk_60d").cast(pl.Float64),
        pl.col("risk_90d").cast(pl.Float64),
    )

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
        .sort(
            by=["risk_90d", "risk_30d"],
            descending=[True, True],
        )
        .head(top_n)
    )

    records = result_df.to_dicts()

    return [
        {
            "assetnum": row["assetnum"],
            "risk_7d": float(row["risk_7d"]),
            "risk_14d": float(row["risk_14d"]),
            "risk_21d": float(row["risk_21d"]),
            "risk_30d": float(row["risk_30d"]),
            "risk_60d": float(row["risk_60d"]),
            "risk_90d": float(row["risk_90d"]),
            "model_source": "external_prediction_csv",
        }
        for row in records
    ]