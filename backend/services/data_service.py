from pathlib import Path
from typing import Any

import polars as pl


# 原始上传文件目录：backend/data/raw
RAW_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


# 第一版系统重点关注的核心字段
REQUIRED_COLUMNS = [
    "assetnum",
    "station_name",
    "cust_linenum",
    "current_faildate",
    "prev_faildate",
    "total_failure_count",
    "description",
    "cust_brand",
]


def get_latest_raw_file() -> Path:
    """
    获取 backend/data/raw/ 目录下的工单文件。

    优先级：
    1. 用户上传的最新文件（按修改时间排序）
    2. 系统默认文件 afc非首次故障-L01线.xlsx
    3. 以上都不存在时给出明确错误提示

    后续可以升级为：
    1. 数据库记录上传批次；
    2. 用户选择指定文件；
    3. 多文件版本管理。
    """
    DEFAULT_DATA_FILE = "afc非首次故障-L01线.xlsx"

    if not RAW_DATA_DIR.exists():
        RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 收集目录下所有支持的数据文件
    all_files = [
        file
        for file in RAW_DATA_DIR.iterdir()
        if file.is_file() and file.suffix.lower() in [".xlsx", ".xls", ".csv"]
    ]

    # 1. 分离用户上传文件（带时间戳前缀）和默认文件
    #    用户上传文件命名规则：YYYYMMDD_HHMMSS_原文件名
    user_files = [
        f for f in all_files
        if f.name != DEFAULT_DATA_FILE
    ]

    if user_files:
        # 用户上传过文件，取最新
        latest_file = max(user_files, key=lambda file: file.stat().st_mtime)
        return latest_file

    # 2. 检查默认文件
    default_file = RAW_DATA_DIR / DEFAULT_DATA_FILE
    if default_file.exists():
        return default_file

    # 3. 如果还有其他文件（非时间戳命名的），也尝试读取
    if all_files:
        return max(all_files, key=lambda file: file.stat().st_mtime)

    raise FileNotFoundError(
        f"未找到工单数据文件。请：\n"
        f"1. 通过 POST /upload/workorders 上传 AFC 工单 Excel/CSV 文件；或\n"
        f"2. 将默认数据文件 {DEFAULT_DATA_FILE} 放置到 {RAW_DATA_DIR} 目录下。"
    )


def read_workorder_file(file_path: Path | None = None) -> pl.DataFrame:
    """
    使用 Polars 读取 AFC 工单 Excel / CSV 文件。

    参数：
        file_path: 指定文件路径。若不传，则默认读取最新上传的文件。

    返回：
        Polars DataFrame
    """
    if file_path is None:
        file_path = get_latest_raw_file()

    suffix = file_path.suffix.lower()

    if suffix in [".xlsx", ".xls"]:
        df = pl.read_excel(file_path)
    elif suffix == ".csv":
        try:
            df = pl.read_csv(file_path)
        except Exception:
            df = pl.read_csv(file_path, encoding="gbk")
    else:
        raise ValueError("不支持的文件格式，请上传 .xlsx、.xls 或 .csv 文件")

    # 去除字段名前后的空格，避免 Excel 表头中存在隐藏空格
    df = df.rename({
        column: column.strip()
        for column in df.columns
        if isinstance(column, str)
    })

    return df


def get_basic_data_info() -> dict[str, Any]:
    """
    返回当前工单数据的基础信息。

    注意：
    这里暂时只做"读取和字段检查"，不做复杂统计。
    复杂统计会在下一步 /data/summary 中继续完善。
    """
    latest_file = get_latest_raw_file()
    df = read_workorder_file(latest_file)

    existing_columns = df.columns

    required_column_status = {
        column: column in existing_columns
        for column in REQUIRED_COLUMNS
    }

    missing_columns = [
        column
        for column, exists in required_column_status.items()
        if not exists
    ]

    return {
        "status": "success",
        "message": "工单数据读取成功",
        "current_file": latest_file.name,
        "file_path": str(latest_file),
        "row_count": df.height,
        "column_count": df.width,
        "columns": existing_columns,
        "required_column_status": required_column_status,
        "missing_columns": missing_columns,
        "note": "当前接口只用于确认数据是否能被系统读取，后续会继续实现数据概览、设备查询和风险预测。"
    }

def _get_unique_count(df: pl.DataFrame, column: str) -> int:
    """
    统计某一列的非空唯一值数量。
    """
    if column not in df.columns:
        return 0

    return df[column].drop_nulls().n_unique()


def _get_top_counts(df: pl.DataFrame, column: str, top_n: int = 10) -> list[dict[str, Any]]:
    """
    统计某个字段中出现频率最高的 Top N。

    返回格式：
    [
        {"name": "某品牌", "count": 100},
        {"name": "另一品牌", "count": 80}
    ]
    """
    if column not in df.columns:
        return []

    result_df = (
        df
        .select(
            pl.col(column)
            .cast(pl.Utf8)
            .fill_null("未知")
            .str.strip_chars()
            .alias("name")
        )
        .with_columns(
            pl.when(pl.col("name") == "")
            .then(pl.lit("空值"))
            .otherwise(pl.col("name"))
            .alias("name")
        )
        .group_by("name")
        .len()
        .sort("len", descending=True)
        .head(top_n)
    )

    return [
        {
            "name": row["name"],
            "count": row["len"]
        }
        for row in result_df.to_dicts()
    ]


def _format_time_value(value: Any) -> str | None:
    """
    将时间值转换为适合接口返回的字符串。
    """
    if value is None:
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value)


def _get_time_range(df: pl.DataFrame, column: str = "current_faildate") -> dict[str, Any]:
    """
    获取工单记录时间范围。

    注意：
    current_faildate 在本项目中更稳妥地表述为"工单记录时间"，
    不直接等同于真实物理故障发生时刻。
    """
    if column not in df.columns:
        return {
            "start_time": None,
            "end_time": None,
            "note": f"未找到时间字段 {column}"
        }

    try:
        time_df = (
            df
            .select(
                pl.col(column)
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.to_datetime(strict=False)
                .alias("record_time")
            )
            .filter(pl.col("record_time").is_not_null())
        )

        if time_df.height == 0:
            return {
                "start_time": None,
                "end_time": None,
                "note": "时间字段存在，但未能成功解析为日期时间"
            }

        start_time = time_df["record_time"].min()
        end_time = time_df["record_time"].max()

        return {
            "start_time": _format_time_value(start_time),
            "end_time": _format_time_value(end_time),
            "note": "这里统计的是工单记录时间范围，不直接等同于真实物理故障发生时间"
        }

    except Exception as e:
        return {
            "start_time": None,
            "end_time": None,
            "note": f"时间范围解析失败：{str(e)}"
        }


def get_data_summary(top_n: int = 10) -> dict[str, Any]:
    """
    获取 AFC 工单数据概览统计信息。

    第一版用于：
    1. 数据概览页面；
    2. 比赛演示首页；
    3. 后续高风险设备分析的数据基础。
    """
    latest_file = get_latest_raw_file()
    df = read_workorder_file(latest_file)

    summary = {
        "status": "success",
        "message": "工单数据概览统计成功",
        "current_file": latest_file.name,
        "basic_metrics": {
            "workorder_count": df.height,
            "column_count": df.width,
            "device_count": _get_unique_count(df, "assetnum"),
            "station_count": _get_unique_count(df, "station_name"),
            "line_count": _get_unique_count(df, "cust_linenum"),
            "brand_count": _get_unique_count(df, "cust_brand"),
        },
        "time_range": _get_time_range(df, "current_faildate"),
        "brand_distribution": _get_top_counts(df, "cust_brand", top_n),
        "fault_description_top": _get_top_counts(df, "description", top_n),
        "line_distribution": _get_top_counts(df, "cust_linenum", top_n),
        "subsystem_distribution": _get_top_counts(df, "cust_subsys", top_n),
        "worktype_distribution": _get_top_counts(df, "worktype", top_n),
        "field_note": {
            "current_faildate": "本系统将 current_faildate 作为工单记录时间使用，不直接宣称其等同于真实物理故障发生时刻。",
            "description": "description 表示工单中的故障现象描述，后续维修建议只作为检查方向参考，不直接等同于真实根因。",
            "pre_type_and_pre_value": "pre_type / pre_value 缺失情况可能较多，第一版暂不作为核心预测标签。"
        }
    }

    return summary
