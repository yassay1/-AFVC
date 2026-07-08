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


SOP_TEMPLATES = [
    {
        "priority_order": ["票卡通道", "票箱/回收模块", "通道传感器", "扇门机构", "电源/通信/主控模块"],
        "onsite_steps": [
            "打开票卡通道维护盖板，检查入口、传输通道和回收通道是否有异物、卡票、积灰或明显磨损。",
            "取出并重新安装票箱/回收箱，确认安装到位、锁止可靠，容量和状态识别正常。",
            "使用测试票卡连续走票 10 次，观察接收、传输、分析、回收各环节是否顺畅。",
            "在维护界面查看票卡相关传感器状态，手动遮挡和放开传感器，确认状态能同步变化。",
        ],
        "abnormal_criteria": [
            "连续走票 10 次中出现卡票、吞卡失败、回收失败、票卡识别失败或走票声音明显异常。",
            "遮挡或放开传感器后，维护界面状态不变化、变化延迟明显或状态反复跳变。",
            "票箱/回收箱重新安装后仍提示未到位、容量异常或回收模块状态异常。",
        ],
        "repair_actions": [
            "发现异物、积灰或轻微卡滞时，先清洁票卡通道、入口导向件和回收通道，再复位测试。",
            "票箱状态异常时，重新安装票箱并检查锁扣、导轨和到位检测点，必要时更换票箱相关组件。",
            "传感器状态不变化时，先重新插拔传感器线束并检查接插件，仍异常则更换通道传感器。",
            "走票机构磨损或动作不稳定时，更换票卡通道组件或回收模块相关组件。",
        ],
        "verification_steps": [
            "维修后连续走票 10 次，确认无卡票、吞卡失败、回收失败或票卡识别失败。",
            "连续刷卡通行 10 次，确认票卡处理和放行逻辑正常。",
            "观察设备运行日志 10 到 15 分钟，确认同类票卡处理异常不再复现。",
        ],
        "escalation_conditions": [
            "清洁、复位和重新安装票箱后仍连续复现同类故障。",
            "短时间内同类票卡处理故障重复 3 次以上。",
            "更换传感器或通道组件后仍存在状态不变化、走票失败或主控日志异常。",
        ],
    },
    {
        "priority_order": ["设备运行状态", "本地日志", "电源模块", "通信模块", "主控模块"],
        "onsite_steps": [
            "进入维护界面查看设备服务状态、暂停服务原因码和最近告警记录。",
            "检查急停、维护门、票箱、回收箱、扇门等关键联锁状态是否处于允许服务条件。",
            "检查电源模块指示灯和输出状态，确认无掉电、欠压、过流或模块告警。",
            "检查通信链路和后台连接状态，确认设备未因离线或通信异常进入暂停服务。",
            "复位设备后观察 10 到 15 分钟，记录是否再次进入暂停服务。",
        ],
        "abnormal_criteria": [
            "复位后 10 到 15 分钟内再次暂停服务或服务中止。",
            "维护界面存在无法清除的联锁异常、模块告警、电源告警或通信告警。",
            "本地日志持续出现主控、电源、通信或外设初始化失败记录。",
        ],
        "repair_actions": [
            "联锁状态异常时，按提示处理维护门、票箱、回收箱或扇门状态，并重新复位设备。",
            "电源或通信接插件松动时，断电后重新插拔线束和接插件，确认固定可靠后上电测试。",
            "电源模块持续告警时，更换电源模块并复测服务状态。",
            "主控或软件状态异常时，先按规程重启恢复；重启后仍复现则升级二线检查主控模块和程序状态。",
        ],
        "verification_steps": [
            "复位后观察设备 10 到 15 分钟，确认不再自动暂停服务。",
            "连续刷卡通行 10 次，确认进出站业务动作完整。",
            "检查后台和本地日志，确认无新的服务中止、主控、电源或通信连续告警。",
        ],
        "escalation_conditions": [
            "清除联锁、复位和重启后仍暂停服务。",
            "短时间内暂停服务重复 3 次以上。",
            "主控、电源或通信日志持续异常，现场无法通过备件替换定位。",
        ],
    },
    {
        "priority_order": ["主控模块", "电源模块", "显示模块", "系统日志", "通信/外设连接"],
        "onsite_steps": [
            "查看主控模块、显示屏和电源模块指示灯，确认上电和运行状态。",
            "检查显示屏、主控板、电源模块相关线束和接插件，确认无松动、虚接或破损。",
            "查看系统日志和重启记录，确认是否存在死机、重启、黑屏或程序异常记录。",
            "断电后重新插拔主控、显示和电源相关线束，上电后观察启动过程是否完整。",
        ],
        "abnormal_criteria": [
            "设备出现黑屏、无显示、频繁重启、启动不完整或维护界面无法进入。",
            "日志中持续出现主控异常、程序异常、电源异常或显示模块通信失败。",
            "重新插拔线束后显示或主控运行状态仍不稳定。",
        ],
        "repair_actions": [
            "显示异常时，先重新插拔显示线束和电源线，仍异常则更换显示屏模块。",
            "电源输出异常或指示灯异常时，更换电源模块并复测。",
            "主控频繁重启或死机时，按规程重启恢复；仍复现则更换主控板或升级二线处理程序状态。",
        ],
        "verification_steps": [
            "上电启动后观察 10 到 15 分钟，确认无死机、黑屏或重启。",
            "连续执行 10 次刷卡通行或维护测试动作，确认显示、主控和业务流程正常。",
            "复查日志，确认无新的主控、显示或电源连续异常。",
        ],
        "escalation_conditions": [
            "更换显示或电源模块后仍出现死机、重启或黑屏。",
            "主控日志持续异常且现场无法完成程序或配置恢复。",
            "同类系统运行异常短时间重复 3 次以上。",
        ],
    },
    {
        "priority_order": ["网线/端口", "设备网络配置", "通信模块", "交换机/后台链路", "主控模块"],
        "onsite_steps": [
            "检查设备网线、交换机端口和通信模块指示灯，确认链路灯状态正常。",
            "重新插拔网线和通信模块接插件，确认端口卡扣和线缆固定可靠。",
            "核对设备 IP、网关、子网掩码等网络配置是否与现场台账一致。",
            "查看后台和本地日志，确认离线、通信中断或连接失败发生时间是否与现场操作一致。",
            "恢复链路后观察 10 到 15 分钟，确认通信状态稳定。",
        ],
        "abnormal_criteria": [
            "链路灯不亮、频繁闪断，或更换端口/网线后仍离线。",
            "后台持续显示设备离线、通信中断或连接失败。",
            "网络配置正确但通信模块无响应或日志持续报通信异常。",
        ],
        "repair_actions": [
            "网线或端口异常时，更换网线、调整交换机端口并重新固定线缆。",
            "通信模块接触不良时，断电后重新插拔通信模块和线束。",
            "通信模块无响应或持续异常时，更换通信模块。",
            "后台链路或交换机侧异常时，升级网络或二线人员协同处理。",
        ],
        "verification_steps": [
            "确认后台连续在线 10 到 15 分钟，无离线或通信中断记录。",
            "连续刷卡通行 10 次，确认交易和状态能正常上传。",
            "复查本地与后台日志，确认无新的通信失败告警。",
        ],
        "escalation_conditions": [
            "更换网线、端口和通信模块后仍持续离线。",
            "同一设备短时间通信异常重复 3 次以上。",
            "多台设备同端口或同交换机下同时异常，需升级网络侧排查。",
        ],
    },
    {
        "priority_order": ["扇门机构", "通行传感器", "读写器模块", "放行控制逻辑", "电源/主控模块"],
        "onsite_steps": [
            "打开维护盖板，检查扇门摆臂、阻挡区域和通道内是否有异物、卡滞或机械干涉。",
            "手动或维护模式驱动扇门开合，观察动作是否顺畅、是否到位、是否有异常声音。",
            "使用测试卡连续刷卡通行 10 次，观察读卡、放行、扇门打开和关闭全过程。",
            "查看通行传感器状态，遮挡和放开时确认状态变化及时、稳定。",
            "检查读写器、通行传感器和扇门机构线束，必要时断电后重新插拔接插件。",
        ],
        "abnormal_criteria": [
            "连续通行 10 次中出现不放行、误拦截、扇门打不开、关闭不到位或动作卡滞。",
            "通行传感器遮挡/放开后状态不变化、延迟明显或反复跳变。",
            "读写器识别成功但放行逻辑未触发，或扇门动作与放行指令不一致。",
        ],
        "repair_actions": [
            "发现异物或机械干涉时，清理通道并检查扇门摆臂和限位位置。",
            "扇门动作卡滞或不到位时，调整机构位置；仍异常则更换扇门机构组件。",
            "传感器状态异常时，重新插拔线束，仍异常则更换通行传感器。",
            "读写器识别异常时，重新插拔读写器线束，仍异常则更换读写器模块。",
        ],
        "verification_steps": [
            "连续刷卡通行 10 次，确认读卡、放行、开门、关门动作完整且无卡滞。",
            "连续遮挡/放开通行传感器 10 次，确认维护界面状态变化一致。",
            "观察设备 10 到 15 分钟，确认无不放行、扇门异常或通行传感器告警复现。",
        ],
        "escalation_conditions": [
            "清理、调整和重新插拔线束后扇门仍不到位或反复卡滞。",
            "更换传感器或读写器后仍无法稳定放行。",
            "短时间内通行控制或扇门异常重复 3 次以上。",
        ],
    },
]


GENERAL_MAINTENANCE_SOP = {
    "priority_order": ["历史高频现象", "设备本地日志", "电源/通信状态", "关键外设模块", "主控模块"],
    "onsite_steps": [
        "先查看最近历史工单和本地日志，确认重复出现的故障现象和发生时间。",
        "检查设备维护界面中的电源、通信、票卡、扇门、传感器等关键状态。",
        "对相关外设线束和接插件执行断电后重新插拔，确认固定可靠后上电。",
        "按业务类型连续执行 10 次测试动作，例如走票、刷卡通行或开关门测试。",
        "复位后观察设备 10 到 15 分钟，记录是否再次出现同类告警。",
    ],
    "abnormal_criteria": [
        "连续 10 次测试中出现任意一次业务失败、卡滞、状态不变化或动作不到位。",
        "维护界面或日志持续出现电源、通信、主控、传感器或外设模块异常。",
        "复位后 10 到 15 分钟内同类故障再次出现。",
    ],
    "repair_actions": [
        "发现异物、积灰或机械卡滞时，先清洁并复位对应通道或机构。",
        "发现接插件松动或状态不稳定时，断电后重新插拔线束并固定。",
        "定位到单一传感器、读写器、通信、电源或执行机构异常时，优先替换对应备件。",
        "无法定位或更换备件后仍复现时，保留日志和测试记录并升级二线处理。",
    ],
    "verification_steps": [
        "维修后连续执行 10 次对应业务测试，确认无同类异常。",
        "观察设备运行日志 10 到 15 分钟，确认无连续告警。",
        "确认后台状态、设备服务状态和现场业务动作均恢复正常。",
    ],
    "escalation_conditions": [
        "清洁、复位、重新插拔线束后仍复现。",
        "短时间内同类故障重复 3 次以上。",
        "主控、电源、通信或关键外设日志持续异常，现场无法闭环定位。",
    ],
}


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


def _merge_sop_items(sop_list: list[dict[str, list[str]]]) -> dict[str, list[str]]:
    keys = [
        "priority_order",
        "onsite_steps",
        "abnormal_criteria",
        "repair_actions",
        "verification_steps",
        "escalation_conditions",
    ]
    return {
        key: _unique_keep_order([
            item
            for sop in sop_list
            for item in sop.get(key, [])
        ])
        for key in keys
    }


def _build_maintenance_sop(matched_rules: list[dict[str, Any]]) -> dict[str, list[str]]:
    """
    根据已匹配规则生成现场维修 SOP。未匹配到具体规则时返回通用 SOP。
    """
    if not matched_rules:
        return _merge_sop_items([GENERAL_MAINTENANCE_SOP])

    sop_list = []
    for rule in matched_rules:
        try:
            rule_index = ADVICE_RULES.index(rule)
        except ValueError:
            continue
        if rule_index < len(SOP_TEMPLATES):
            sop_list.append(SOP_TEMPLATES[rule_index])

    if not sop_list:
        sop_list.append(GENERAL_MAINTENANCE_SOP)

    return _merge_sop_items(sop_list)


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

    maintenance_sop = _build_maintenance_sop(matched_rules)

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
        "maintenance_sop": maintenance_sop,
        "advice_note": "以上建议基于历史工单中的故障现象描述自动生成，仅作为巡检方向和维修排查参考，不代表系统已经准确判断真实故障根因。",
        "upgrade_note": "第一版采用规则模板生成建议；后续可接入维修手册 RAG、LangChain 工具调用和 LangGraph 多步骤诊断流程。",
    }
