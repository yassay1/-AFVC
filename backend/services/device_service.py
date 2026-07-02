from typing import Any

import polars as pl

from backend.services.data_service import read_workorder_file


def _json_safe_value(value: Any) -> Any:
    """
    将 Polars / Python 中不方便直接 JSON 返回的值转换为普通类型。
    """
    if value is None:
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return value


def _records_to_json_safe(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    将记录列表中的时间类型等转换为 JSON 友好格式。
    """
    return [
        {
            key: _json_safe_value(value)
            for key, value in row.items()
        }
        for row in records
    ]


def get_device_list() -> dict[str, Any]:
    """
    获取设备列表。

    用途：
    1. 给 Streamlit 前端下拉框使用；
    2. 给单设备分析页面选择设备；
    3. 后续用于批量预测和高风险设备筛选。
    """
    df = read_workorder_file()

    if "assetnum" not in df.columns:
        raise ValueError("数据中缺少 assetnum 字段，无法生成设备列表")

    device_df = (
        df
        .with_columns(
            pl.col("assetnum")
            .cast(pl.Utf8)
            .fill_null("")
            .str.strip_chars()
            .alias("assetnum")
        )
        .filter(pl.col("assetnum") != "")
        .with_columns(
            pl.col("current_faildate")
            .cast(pl.Utf8)
            .str.to_datetime(strict=False)
            .alias("_record_time")
        )
        .group_by("assetnum")
        .agg(
            pl.len().alias("workorder_count"),
            pl.col("station_name").cast(pl.Utf8).drop_nulls().first().alias("station_name"),
            pl.col("cust_linenum").cast(pl.Utf8).drop_nulls().first().alias("line"),
            pl.col("cust_brand").cast(pl.Utf8).drop_nulls().first().alias("brand"),
            pl.col("_record_time").max().alias("last_record_time"),
        )
        .sort("workorder_count", descending=True)
    )

    records = _records_to_json_safe(device_df.to_dicts())

    return {
        "status": "success",
        "message": "设备列表获取成功",
        "device_count": len(records),
        "devices": records,
    }


def get_device_history(assetnum: str, limit: int = 50) -> dict[str, Any]:
    """
    查询单台设备的历史工单记录。

    注意：
    current_faildate 在本系统中表述为“工单记录时间”，
    不直接宣称其等同于真实物理故障发生时间。
    """
    df = read_workorder_file()

    if "assetnum" not in df.columns:
        raise ValueError("数据中缺少 assetnum 字段，无法查询设备历史")

    target_assetnum = assetnum.strip()

    history_df = (
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

    if history_df.height == 0:
        raise ValueError(f"未找到设备 {target_assetnum} 的历史工单记录")

    selected_columns = [
        column
        for column in [
            "assetnum",
            "station_name",
            "cust_linenum",
            "current_faildate",
            "prev_faildate",
            "total_failure_count",
            "worktype",
            "description",
            "cust_brand",
            "cust_subsys",
            "pre_type",
            "pre_value",
        ]
        if column in history_df.columns
    ]

    history_df = (
        history_df
        .select(selected_columns)
        .with_columns(
            pl.col("current_faildate")
            .cast(pl.Utf8)
            .str.to_datetime(strict=False)
            .alias("_record_time")
        )
        .sort("_record_time", descending=True)
        .drop("_record_time")
        .head(limit)
    )

    records = _records_to_json_safe(history_df.to_dicts())

    return {
        "status": "success",
        "message": f"设备 {target_assetnum} 历史工单查询成功",
        "assetnum": target_assetnum,
        "history_count": len(records),
        "history": records,
        "field_note": {
            "current_faildate": "工单记录时间，不直接等同于真实物理故障发生时刻",
            "description": "工单故障现象描述，不直接等同于真实故障根因",
        },
    }