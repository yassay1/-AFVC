from typing import Any

import polars as pl

from backend.services.data_service import read_workorder_file


ADVICE_RULES = [
    {
        "phenomenon": "票卡处理异常",
        "keywords": ["卡票", "票卡", "不接收单程票", "不能分析车票", "车票"],
        "possible_causes": [
            "票卡通道可能存在异物、卡滞或磨损",
            "票箱或回收模块状态可能异常",
            "票卡识别传感器响应可能不稳定",
        ],
        "inspection_suggestions": [
            "检查票卡通道是否存在异物、灰尘或卡滞",
            "检查票箱安装状态、容量状态和回收机构",
            "检查票卡识别相关传感器是否触发正常",
            "结合近期相似工单，判断是否存在重复卡票现象",
        ],
        "spare_part_suggestions": [
            "票卡通道组件",
            "票箱相关组件",
            "通道传感器",
        ],
    },
    {
        "phenomenon": "设备暂停服务 / 服务中止",
        "keywords": ["暂停服务", "服务中止", "停止服务", "暂停"],
        "possible_causes": [
            "设备状态模块可能异常",
            "控制模块或软件状态可能异常",
            "电源、通信或外设异常可能触发暂停服务",
        ],
        "inspection_suggestions": [
            "查看设备运行状态和本地日志",
            "检查控制模块、电源模块和通信状态",
            "确认是否存在连续重复暂停服务工单",
            "必要时进行重启恢复后观察是否复现",
        ],
        "spare_part_suggestions": [
            "主控模块",
            "电源模块",
            "通信模块",
        ],
    },
    {
        "phenomenon": "主控 / 显示 / 系统运行异常",
        "keywords": ["死机", "重启", "黑屏", "无显示", "显示异常"],
        "possible_causes": [
            "主控单元可能运行异常",
            "系统软件或程序状态可能异常",
            "电源稳定性或显示模块可能存在问题",
        ],
        "inspection_suggestions": [
            "检查设备主控单元运行状态",
            "查看系统日志和异常重启记录",
            "检查电源输出是否稳定",
            "检查显示屏、连接线和显示模块",
        ],
        "spare_part_suggestions": [
            "主控板",
            "显示屏模块",
            "电源模块",
        ],
    },
    {
        "phenomenon": "通信异常",
        "keywords": ["通信中断", "网络异常", "通讯中断", "离线", "连接失败"],
        "possible_causes": [
            "网络链路可能不稳定",
            "通信模块可能异常",
            "交换机、网线或网络配置可能存在问题",
        ],
        "inspection_suggestions": [
            "检查网线、交换机端口和网络连接状态",
            "检查设备 IP、网关等网络配置",
            "查看后台系统是否存在离线记录",
            "检查通信模块是否工作正常",
        ],
        "spare_part_suggestions": [
            "通信模块",
            "网线",
            "交换机端口相关备件",
        ],
    },
    {
        "phenomenon": "通行控制 / 扇门异常",
        "keywords": ["不放行", "验票不放行", "扇门", "通行异常", "闸门"],
        "possible_causes": [
            "通行控制逻辑可能异常",
            "扇门机构可能存在卡滞或动作不到位",
            "读写器或通行传感器可能响应异常",
        ],
        "inspection_suggestions": [
            "检查扇门开合动作是否顺畅",
            "检查通行检测传感器是否正常触发",
            "检查读写器识别结果与放行逻辑",
            "检查是否存在机械卡滞或异物阻挡",
        ],
        "spare_part_suggestions": [
            "扇门机构组件",
            "通行传感器",
            "读写器模块",
        ],
    },
]


def _unique_keep_order(items: list[str]) -> list[str]:
    """
    去重但保持原有顺序。
    """
    result = []
    seen = set()

    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)

    return result


def _get_device_records(assetnum: str) -> pl.DataFrame:
    """
    获取某台设备的全部历史工单。
    """
    df = read_workorder_file()
    target_assetnum = assetnum.strip()

    if "assetnum" not in df.columns:
        raise ValueError("数据中缺少 assetnum 字段，无法生成维修建议")

    device_df = (
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

    if device_df.height == 0:
        raise ValueError(f"未找到设备 {target_assetnum} 的历史工单记录，无法生成维修建议")

    return device_df


def _extract_recent_descriptions(device_df: pl.DataFrame, limit: int = 20) -> list[str]:
    """
    提取设备最近若干条故障描述。
    """
    if "description" not in device_df.columns:
        return []

    work_df = device_df

    if "current_faildate" in work_df.columns:
        work_df = (
            work_df
            .with_columns(
                pl.col("current_faildate")
                .cast(pl.Utf8)
                .str.to_datetime(strict=False)
                .alias("_record_time")
            )
            .sort("_record_time", descending=True)
        )

    desc_df = (
        work_df
        .select(
            pl.col("description")
            .cast(pl.Utf8)
            .fill_null("")
            .str.strip_chars()
            .alias("description")
        )
        .filter(pl.col("description") != "")
        .head(limit)
    )

    return desc_df["description"].to_list()


def _match_advice_rules(descriptions: list[str]) -> list[dict[str, Any]]:
    """
    根据历史故障描述匹配维修建议规则。
    """
    combined_text = " ".join(descriptions)
    matched_rules = []

    for rule in ADVICE_RULES:
        if any(keyword in combined_text for keyword in rule["keywords"]):
            matched_rules.append(rule)

    return matched_rules


def generate_device_advice(assetnum: str) -> dict[str, Any]:
    """
    根据设备历史工单 description 生成维修建议。

    注意：
    这里的建议基于工单故障现象，不直接等同于真实故障根因。
    第一版采用规则模板，后续可升级为 RAG + Agent。
    """
    target_assetnum = assetnum.strip()
    device_df = _get_device_records(target_assetnum)

    recent_descriptions = _extract_recent_descriptions(device_df, limit=20)
    matched_rules = _match_advice_rules(recent_descriptions)

    first_row = device_df.head(1).to_dicts()[0]

    if matched_rules:
        recognized_phenomena = [
            rule["phenomenon"]
            for rule in matched_rules
        ]

        possible_causes = _unique_keep_order([
            cause
            for rule in matched_rules
            for cause in rule["possible_causes"]
        ])

        inspection_suggestions = _unique_keep_order([
            suggestion
            for rule in matched_rules
            for suggestion in rule["inspection_suggestions"]
        ])

        spare_part_suggestions = _unique_keep_order([
            part
            for rule in matched_rules
            for part in rule["spare_part_suggestions"]
        ])
    else:
        recognized_phenomena = ["未匹配到明确规则类型"]
        possible_causes = [
            "当前故障描述未匹配到第一版规则库中的典型模式",
            "可能需要结合现场情况、设备日志和维修手册进一步判断",
        ]
        inspection_suggestions = [
            "优先查看该设备最近历史工单的重复现象",
            "检查设备运行日志、通信状态、电源状态和关键模块状态",
            "将该设备纳入人工复核清单，必要时补充维修人员反馈",
        ]
        spare_part_suggestions = [
            "根据现场检查结果准备对应模块备件",
        ]

    return {
        "status": "success",
        "message": "设备维修建议生成成功",
        "assetnum": target_assetnum,
        "station_name": first_row.get("station_name"),
        "line": first_row.get("cust_linenum"),
        "brand": first_row.get("cust_brand"),
        "subsystem": first_row.get("cust_subsys"),
        "history_workorder_count": device_df.height,
        "analyzed_description_count": len(recent_descriptions),
        "recent_descriptions": recent_descriptions[:5],
        "recognized_fault_phenomena": recognized_phenomena,
        "possible_causes": possible_causes,
        "inspection_suggestions": inspection_suggestions,
        "spare_part_suggestions": spare_part_suggestions,
        "advice_note": "以上建议基于历史工单中的故障现象描述自动生成，仅作为巡检方向和维修排查参考，不代表系统已经准确判断真实故障根因。",
        "upgrade_note": "第一版采用规则模板生成建议；后续可接入维修手册 RAG、LangChain 工具调用和 LangGraph 多步骤诊断流程。",
    }