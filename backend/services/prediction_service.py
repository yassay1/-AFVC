from typing import Any
from backend.services.model_adapter import (
    get_external_prediction_by_assetnum,
    get_external_high_risk_predictions,
)

import polars as pl

from backend.services.data_service import read_workorder_file
from backend.services.warning_service import generate_warning_info


def _round_risk(value: float) -> float:
    """
    风险值保留两位小数，并控制在 0～0.95 之间。
    """
    value = max(0.01, min(value, 0.95))
    return round(value, 2)


def _extract_device_df(df: pl.DataFrame, assetnum: str) -> pl.DataFrame:
    """
    从全量工单中筛选某台设备的记录。
    """
    target_assetnum = assetnum.strip()

    return (
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


def _calculate_recent_count(device_df: pl.DataFrame, days: int = 90) -> int:
    """
    计算数据集最新工单时间往前 days 天内，该设备出现的工单数量。

    注意：
    这里使用“数据集内部最新工单时间”作为参考点，
    不是使用今天日期。这样更适合比赛演示数据。
    """
    if "current_faildate" not in device_df.columns:
        return 0

    time_df = (
        device_df
        .with_columns(
            pl.col("current_faildate")
            .cast(pl.Utf8)
            .str.to_datetime(strict=False)
            .alias("_record_time")
        )
        .filter(pl.col("_record_time").is_not_null())
    )

    if time_df.height == 0:
        return 0

    max_time = time_df["_record_time"].max()
    start_time = max_time - pl.duration(days=days)

    recent_df = time_df.filter(pl.col("_record_time") >= start_time)

    return recent_df.height


def _calculate_average_interval_days(device_df: pl.DataFrame) -> float | None:
    """
    估算设备历史工单之间的平均间隔天数。
    """
    if "current_faildate" not in device_df.columns:
        return None

    time_df = (
        device_df
        .with_columns(
            pl.col("current_faildate")
            .cast(pl.Utf8)
            .str.to_datetime(strict=False)
            .alias("_record_time")
        )
        .filter(pl.col("_record_time").is_not_null())
        .select("_record_time")
        .sort("_record_time")
    )

    if time_df.height < 2:
        return None

    diff_df = time_df.with_columns(
        pl.col("_record_time").diff().dt.total_days().alias("_diff_days")
    ).filter(
        pl.col("_diff_days").is_not_null()
    )

    if diff_df.height == 0:
        return None

    return float(diff_df["_diff_days"].mean())


def _get_device_base_info(device_df: pl.DataFrame) -> dict[str, Any]:
    """
    获取设备的基础信息。
    """
    first_row = device_df.head(1).to_dicts()[0]

    return {
        "station_name": first_row.get("station_name"),
        "line": first_row.get("cust_linenum"),
        "brand": first_row.get("cust_brand"),
        "subsystem": first_row.get("cust_subsys"),
    }


def _predict_from_df(df: pl.DataFrame, assetnum: str) -> dict[str, Any]:
    """
    基于当前工单数据，为单台设备生成模拟风险预测结果。

    第一版说明：
    这里不是机器学习模型，而是 mock 风险服务。
    目的：
    1. 先跑通后端接口；
    2. 先支持前端展示；
    3. 后续可以替换为队友真实模型。
    """
    target_assetnum = assetnum.strip()
    device_df = _extract_device_df(df, target_assetnum)

    if device_df.height == 0:
        raise ValueError(f"未找到设备 {target_assetnum} 的工单记录，无法生成预测结果")

    workorder_count = device_df.height
    recent_90_count = _calculate_recent_count(device_df, days=90)
    average_interval_days = _calculate_average_interval_days(device_df)

    # 1. 历史工单数量越多，基础风险越高
    history_score = min(workorder_count / 80, 1.0) * 0.40

    # 2. 近 90 天工单越多，近期风险越高
    recent_score = min(recent_90_count / 10, 1.0) * 0.35

    # 3. 平均复发间隔越短，风险越高
    if average_interval_days is None:
        interval_score = 0.05
    elif average_interval_days <= 14:
        interval_score = 0.20
    elif average_interval_days <= 30:
        interval_score = 0.15
    elif average_interval_days <= 60:
        interval_score = 0.10
    else:
        interval_score = 0.05

    # 4. 让不同设备之间略有差异，但保持结果稳定
    stable_factor = (sum(ord(char) for char in target_assetnum) % 10) / 100

    base_risk = history_score + recent_score + interval_score + stable_factor
    base_risk = min(base_risk, 0.90)

    risk_7d = _round_risk(base_risk * 0.35)
    risk_14d = _round_risk(base_risk * 0.50)
    risk_21d = _round_risk(base_risk * 0.65)
    risk_30d = _round_risk(base_risk * 0.80)
    risk_60d = _round_risk(base_risk * 1.05)
    risk_90d = _round_risk(base_risk * 1.20)

    warning_info = generate_warning_info(
        risk_30d=risk_30d,
        risk_90d=risk_90d,
    )

    main_risk_factors = []

    if workorder_count >= 50:
        main_risk_factors.append("历史故障工单数量较多")
    elif workorder_count >= 20:
        main_risk_factors.append("历史故障工单数量中等偏高")
    else:
        main_risk_factors.append("历史故障工单数量相对较少")

    if recent_90_count >= 5:
        main_risk_factors.append("数据集最近 90 天内该设备工单较集中")
    elif recent_90_count > 0:
        main_risk_factors.append("数据集最近 90 天内该设备存在工单记录")
    else:
        main_risk_factors.append("数据集最近 90 天内未发现明显集中工单")

    if average_interval_days is not None and average_interval_days <= 30:
        main_risk_factors.append("历史工单平均间隔较短，存在重复报修特征")
    else:
        main_risk_factors.append("历史工单间隔未表现出明显高频特征")

    base_info = _get_device_base_info(device_df)

    return {
        "status": "success",
        "message": "设备故障工单复发风险模拟预测成功",
        "assetnum": target_assetnum,
        "station_name": base_info.get("station_name"),
        "line": base_info.get("line"),
        "brand": base_info.get("brand"),
        "subsystem": base_info.get("subsystem"),
        "risk_7d": risk_7d,
        "risk_14d": risk_14d,
        "risk_21d": risk_21d,
        "risk_30d": risk_30d,
        "risk_60d": risk_60d,
        "risk_90d": risk_90d,
        "warning_level": warning_info["warning_level"],
        "suggested_inspection_window": warning_info["suggested_inspection_window"],
        "warning_reason": warning_info["warning_reason"],
        "main_risk_factors": main_risk_factors,
        "feature_snapshot": {
            "history_workorder_count": workorder_count,
            "recent_90d_workorder_count_in_dataset": recent_90_count,
            "average_interval_days": round(average_interval_days, 2) if average_interval_days is not None else None,
        },
        "model_note": "当前结果由第一版 mock 预测服务生成，用于系统联调和比赛演示；后续可替换为队友训练的真实预测模型。",
        "risk_statement": "本系统预测的是未来多个时间窗口内再次产生故障工单的风险，不等同于精确预测真实物理故障发生日期。",
    }


def predict_device_risk(assetnum: str) -> dict[str, Any]:
    """
    对外暴露的单设备预测接口。

    当前逻辑：
    1. 优先尝试读取外部预测结果表；
    2. 如果没有外部预测结果，则回退到 mock 预测；
    3. FastAPI 路由和 Streamlit 前端不需要关心预测来源。
    """
    target_assetnum = assetnum.strip()

    df = read_workorder_file()

    external_prediction = get_external_prediction_by_assetnum(target_assetnum)

    if external_prediction is not None:
        device_df = _extract_device_df(df, target_assetnum)

        if device_df.height == 0:
            raise ValueError(f"未找到设备 {target_assetnum} 的工单记录，无法生成预测结果")

        base_info = _get_device_base_info(device_df)

        warning_info = generate_warning_info(
            risk_30d=external_prediction["risk_30d"],
            risk_90d=external_prediction["risk_90d"],
        )

        return {
            "status": "success",
            "message": "设备故障工单复发风险预测成功",
            "assetnum": target_assetnum,
            "station_name": base_info.get("station_name"),
            "line": base_info.get("line"),
            "brand": base_info.get("brand"),
            "subsystem": base_info.get("subsystem"),
            "risk_7d": external_prediction["risk_7d"],
            "risk_14d": external_prediction["risk_14d"],
            "risk_21d": external_prediction["risk_21d"],
            "risk_30d": external_prediction["risk_30d"],
            "risk_60d": external_prediction["risk_60d"],
            "risk_90d": external_prediction["risk_90d"],
            "warning_level": warning_info["warning_level"],
            "suggested_inspection_window": warning_info["suggested_inspection_window"],
            "warning_reason": warning_info["warning_reason"],
            "main_risk_factors": [
                "预测结果来自外部模型结果表",
                "系统根据模型输出风险生成预警等级",
                "后续可结合模型特征重要性补充风险解释",
            ],
            "feature_snapshot": {
                "prediction_source": external_prediction["model_source"],
            },
            "model_note": external_prediction["model_note"],
            "risk_statement": "本系统预测的是未来多个时间窗口内再次产生故障工单的风险，不等同于精确预测真实物理故障发生日期。",
        }

    return _predict_from_df(df, target_assetnum)

def get_high_risk_devices(top_n: int = 10) -> dict[str, Any]:
    """
    获取高风险设备 Top N。

    当前逻辑：
    1. 如果存在外部预测结果表 prediction_results.csv，
       优先按外部预测结果的 risk_90d 生成高风险设备清单；
    2. 如果不存在外部预测结果表，
       回退到第一版 mock 预测排序。

    这样做的好处：
    - 队友模型完成后，只需要提供预测结果表；
    - 前端和 Agent 不需要改；
    - 高风险设备页可以直接展示真实模型输出。
    """
    df = read_workorder_file()

    if "assetnum" not in df.columns:
        raise ValueError("数据中缺少 assetnum 字段，无法生成高风险设备列表")

    # 1. 优先尝试使用外部预测结果表
    external_records = get_external_high_risk_predictions(top_n=top_n)

    if external_records:
        risk_records = []

        for record in external_records:
            assetnum = record["assetnum"]
            device_df = _extract_device_df(df, assetnum)

            # 如果预测表里有设备编号，但工单数据里没有，跳过
            if device_df.height == 0:
                continue

            base_info = _get_device_base_info(device_df)

            warning_info = generate_warning_info(
                risk_30d=record["risk_30d"],
                risk_90d=record["risk_90d"],
            )

            risk_records.append({
                "assetnum": assetnum,
                "station_name": base_info.get("station_name"),
                "line": base_info.get("line"),
                "brand": base_info.get("brand"),
                "risk_7d": record["risk_7d"],
                "risk_14d": record["risk_14d"],
                "risk_21d": record["risk_21d"],
                "risk_30d": record["risk_30d"],
                "risk_60d": record["risk_60d"],
                "risk_90d": record["risk_90d"],
                "warning_level": warning_info["warning_level"],
                "suggested_inspection_window": warning_info["suggested_inspection_window"],
                "main_risk_factors": [
                    "预测结果来自外部模型结果表",
                    "系统按 90 天风险进行高风险设备排序",
                    "预警等级由模型风险结果转换生成",
                ],
            })

        return {
            "status": "success",
            "message": "高风险设备 Top N 生成成功",
            "top_n": top_n,
            "devices": risk_records,
            "prediction_source": "external_prediction_csv",
            "model_note": "当前高风险设备清单来自队友或外部模型输出的 prediction_results.csv 文件。",
        }

    # 2. 没有外部预测结果表时，回退到 mock 预测
    assetnums = (
        df
        .select(
            pl.col("assetnum")
            .cast(pl.Utf8)
            .fill_null("")
            .str.strip_chars()
            .alias("assetnum")
        )
        .filter(pl.col("assetnum") != "")
        .unique()
        .to_series()
        .to_list()
    )

    risk_records = []

    for assetnum in assetnums:
        try:
            prediction = _predict_from_df(df, assetnum)
            risk_records.append({
                "assetnum": prediction["assetnum"],
                "station_name": prediction["station_name"],
                "line": prediction["line"],
                "brand": prediction["brand"],
                "risk_7d": prediction["risk_7d"],
                "risk_14d": prediction["risk_14d"],
                "risk_21d": prediction["risk_21d"],
                "risk_30d": prediction["risk_30d"],
                "risk_60d": prediction["risk_60d"],
                "risk_90d": prediction["risk_90d"],
                "warning_level": prediction["warning_level"],
                "suggested_inspection_window": prediction["suggested_inspection_window"],
                "main_risk_factors": prediction["main_risk_factors"],
            })
        except Exception:
            continue

    risk_records = sorted(
        risk_records,
        key=lambda row: row["risk_90d"],
        reverse=True
    )[:top_n]

    return {
        "status": "success",
        "message": "高风险设备 Top N 生成成功",
        "top_n": top_n,
        "devices": risk_records,
        "prediction_source": "mock_prediction_service",
        "model_note": "当前高风险排序基于 mock 预测服务；后续可替换为队友真实模型输出。",
    }