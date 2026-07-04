"""报告生成器 —— 将证据打包成 FinalAnswer。

提供两种模式：
1. LLM 模式：在 nodes.py 的 generate_report_node 中直接调用
2. 模板模式：LLM 不可用时的兜底

本模块提供给外部（如测试）直接使用的报告构建函数。
"""

from typing import Any


def build_device_error_report(assetnum: str | None, query: str, errors: list[str]) -> str:
    """当设备无法识别或校验失败时,生成错误提示报告。"""
    lines = []
    lines.append("【AFC 设备智能诊断报告】")
    lines.append("")
    lines.append("⚠️ 诊断未完成")
    lines.append("")

    if not assetnum:
        lines.append("未能从您的问题中识别到设备编号。")
        lines.append("")
        lines.append("请尝试以下格式：")
        lines.append('- 帮我分析设备 1000029970')
        lines.append('- 设备 EX011115 最近有哪些故障?')
        lines.append('- 1000029970 未来 30 天风险高吗?')
    else:
        lines.append(f"设备编号 {assetnum} 在当前工单数据中未找到。")
        lines.append("")
        lines.append("请确认：")
        lines.append("1. 设备编号是否正确")
        lines.append("2. 是否已上传包含该设备的工单文件")

    if errors:
        lines.append("")
        lines.append("错误详情：")
        for err in errors:
            lines.append(f"- {err}")

    lines.append("")
    lines.append("---")
    lines.append(f"原始问题：{query}")
    return "\n".join(lines)


def build_data_overview_report(tool_results: dict[str, Any]) -> str:
    """生成数据概览报告。"""
    summary = tool_results.get("get_data_summary_tool", {})
    if summary.get("status") != "success":
        return f"数据概览获取失败：{summary.get('message', '未知错误')}"

    basic = summary.get("basic_metrics", {})
    time_range = summary.get("time_range", {})

    lines = []
    lines.append("【AFC 工单数据概览报告】")
    lines.append("")
    lines.append("一、基础指标")
    lines.append(f"- 工单总数：{basic.get('workorder_count', 'N/A')}")
    lines.append(f"- 设备数量：{basic.get('device_count', 'N/A')}")
    lines.append(f"- 车站数量：{basic.get('station_count', 'N/A')}")
    lines.append(f"- 线路数量：{basic.get('line_count', 'N/A')}")
    lines.append(f"- 品牌数量：{basic.get('brand_count', 'N/A')}")
    lines.append("")
    lines.append("二、时间范围")
    lines.append(f"- 起始时间：{time_range.get('start_time', 'N/A')}")
    lines.append(f"- 结束时间：{time_range.get('end_time', 'N/A')}")
    lines.append("")
    lines.append("三、当前数据文件")
    lines.append(f"- {summary.get('current_file', 'N/A')}")
    lines.append("")
    lines.append("---")
    lines.append("本报告由 AFCDiagnosisAgent 自动生成")
    return "\n".join(lines)


def build_high_risk_report(tool_results: dict[str, Any]) -> str:
    """生成高风险设备报告。"""
    result = tool_results.get("get_high_risk_devices_tool", {})
    if result.get("status") != "success":
        return f"高风险设备查询失败：{result.get('message', '未知错误')}"

    devices = result.get("devices", [])

    lines = []
    lines.append("【高风险设备巡检报告】")
    lines.append("")
    lines.append(f"共 {len(devices)} 台高风险设备需要优先关注：")
    lines.append("")

    for i, device in enumerate(devices, 1):
        lines.append(f"## {i}. 设备 {device.get('assetnum', 'N/A')}")
        lines.append(f"- 车站：{device.get('station_name', 'N/A')}　线路：{device.get('line', 'N/A')}")
        lines.append(f"- 品牌：{device.get('brand', 'N/A')}")
        lines.append(f"- 30 天风险：{device.get('risk_30d', 'N/A')}　90 天风险：{device.get('risk_90d', 'N/A')}")
        lines.append(f"- 预警等级：{device.get('warning_level', 'N/A')}")
        lines.append(f"- 建议巡检窗口：{device.get('suggested_inspection_window', 'N/A')}")
        lines.append("")

    lines.append("---")
    lines.append("提示：可点击设备编号进入单设备分析页查看详细诊断报告。")
    return "\n".join(lines)


def _scientific_boundary_lines() -> list[str]:
    return [
        "",
        "科学边界说明：",
        "- 风险预测表示未来时间窗口内再次产生故障工单的风险，不等同于一定发生物理故障。",
        "- 维修建议是基于历史工单现象形成的巡检方向参考，不是最终根因诊断结论。",
        "- 最终维修判断需结合现场检测、设备日志和人工经验。",
    ]


def _device_header(evidence: dict[str, Any]) -> list[str]:
    info = evidence.get("device_info", {}) or {}
    assetnum = info.get("assetnum") or evidence.get("assetnum")
    return [
        f"- 设备编号：{assetnum or '数据缺失'}",
        f"- 车站：{info.get('station_name') or '数据缺失'}",
        f"- 线路：{info.get('line') or '数据缺失'}",
        f"- 品牌：{info.get('brand') or '数据缺失'}",
        f"- 子系统：{info.get('subsystem') or '数据缺失'}",
    ]


def build_risk_report(evidence: dict[str, Any], query: str) -> str:
    """生成单设备风险查询报告。"""
    risk = evidence.get("risk_prediction", {}) or {}
    warning = evidence.get("warning_result", {}) or {}
    if not risk:
        return build_device_error_report(evidence.get("assetnum"), query, ["未获取到风险预测工具结果"])

    lines = ["【AFC 设备风险预测说明】", "", "一、设备信息"]
    lines.extend(_device_header(evidence))
    lines.extend([
        "",
        "二、复发风险",
        f"- 7 天风险：{risk.get('risk_7d', '数据缺失')}",
        f"- 14 天风险：{risk.get('risk_14d', '数据缺失')}",
        f"- 21 天风险：{risk.get('risk_21d', '数据缺失')}",
        f"- 30 天风险：{risk.get('risk_30d', '数据缺失')}",
        f"- 60 天风险：{risk.get('risk_60d', '数据缺失')}",
        f"- 90 天风险：{risk.get('risk_90d', '数据缺失')}",
        "",
        "三、预警结果",
        f"- 预警等级：{warning.get('warning_level') or risk.get('warning_level', '数据缺失')}",
        f"- 建议巡检窗口：{warning.get('suggested_inspection_window') or risk.get('suggested_inspection_window', '数据缺失')}",
        f"- 预警原因：{warning.get('warning_reason') or risk.get('warning_reason', '数据缺失')}",
    ])
    factors = risk.get("main_risk_factors", [])
    if factors:
        lines.append("")
        lines.append("四、主要风险因素")
        for factor in factors:
            lines.append(f"- {factor}")
    lines.extend(_scientific_boundary_lines())
    lines.append("")
    lines.append(f"工具来源：{', '.join(evidence.get('sources', []))}")
    return "\n".join(lines)


def build_history_report(evidence: dict[str, Any], query: str) -> str:
    """生成历史工单摘要报告。"""
    history = (evidence.get("history_summary", {}) or {}).get("raw", {})
    if not history:
        return build_device_error_report(evidence.get("assetnum"), query, ["未获取到历史工单工具结果"])

    lines = ["【AFC 设备历史工单摘要】", "", "一、设备信息"]
    lines.extend(_device_header(evidence))
    lines.extend(["", f"二、返回工单数：{history.get('history_count', '数据缺失')}", ""])
    records = history.get("history", [])[:5]
    if records:
        lines.append("三、最近工单")
        for i, row in enumerate(records, 1):
            lines.append(
                f"{i}. {row.get('current_faildate', '时间缺失')} | "
                f"{row.get('worktype', '类型缺失')} | "
                f"{row.get('description', '描述缺失')}"
            )
    else:
        lines.append("三、最近工单：工具未返回明细")
    lines.extend(_scientific_boundary_lines())
    lines.append("")
    lines.append(f"工具来源：{', '.join(evidence.get('sources', []))}")
    return "\n".join(lines)


def build_advice_report(evidence: dict[str, Any], query: str) -> str:
    """生成维修与巡检建议报告。"""
    advice = evidence.get("maintenance_advice", {}) or {}
    if not advice:
        return build_device_error_report(evidence.get("assetnum"), query, ["未获取到维修建议工具结果"])

    lines = ["【AFC 维修与巡检建议】", "", "一、设备信息"]
    lines.extend(_device_header(evidence))
    sections = [
        ("二、识别到的故障现象", advice.get("recognized_fault_phenomena", [])),
        ("三、可能原因", advice.get("possible_causes", [])),
        ("四、建议检查方向", advice.get("inspection_suggestions", [])),
        ("五、备件准备建议", advice.get("spare_part_suggestions", [])),
    ]
    for title, items in sections:
        lines.append("")
        lines.append(title)
        if items:
            for item in items:
                lines.append(f"- {item}")
        else:
            lines.append("- 工具未返回该项数据")
    lines.extend(_scientific_boundary_lines())
    lines.append("")
    lines.append(f"工具来源：{', '.join(evidence.get('sources', []))}")
    return "\n".join(lines)


def build_manual_report(evidence: dict[str, Any], query: str) -> str:
    """生成维修手册检索报告。"""
    manual_evidence = evidence.get("manual_evidence") or []
    assetnum = evidence.get("assetnum")

    lines = ["【AFC 维修手册检索报告】", ""]
    if assetnum:
        lines.append(f"- 设备编号：{assetnum}")
    lines.append(f"- 原始问题：{query}")
    lines.append("")

    if not manual_evidence:
        lines.append("未在当前维修手册知识库中找到足够相关的内容。")
        lines.append("")
        lines.append("建议：")
        lines.append("- 换用更具体的故障现象关键词，例如“票卡不接收”“扇门异常”“读卡失败”。")
        lines.append("- 检查 backend/data/knowledge/manuals 目录中是否已放入对应手册文件。")
        lines.extend(_scientific_boundary_lines())
        lines.append("")
        lines.append(f"工具来源：{', '.join(evidence.get('sources', []))}")
        return "\n".join(lines)

    lines.append(f"共匹配到 {len(manual_evidence)} 条手册证据：")
    lines.append("")
    for i, item in enumerate(manual_evidence, 1):
        title = item.get("title") or "未命名章节"
        source = item.get("source") or "未知来源"
        score = item.get("score", "N/A")
        content = str(item.get("content") or "").strip()
        if len(content) > 260:
            content = content[:260].rstrip() + "..."

        lines.append(f"## {i}. {title}")
        lines.append(f"- 来源文件：{source}")
        lines.append(f"- 匹配分数：{score}")
        lines.append(f"- 内容摘要：{content or '内容为空'}")
        lines.append("")

    lines.extend(_scientific_boundary_lines())
    lines.append("")
    lines.append("说明：手册检索结果用于辅助定位检查方向，不能替代现场检测、设备日志和维修人员判断。")
    lines.append(f"工具来源：{', '.join(evidence.get('sources', []))}")
    return "\n".join(lines)


def build_risk_explanation_report(evidence: dict[str, Any], query: str) -> str:
    """生成预警原因解释报告。"""
    return build_risk_report(evidence, query).replace("【AFC 设备风险预测说明】", "【AFC 预警原因解释】", 1)


def build_risk_advice_report(evidence: dict[str, Any], query: str) -> str:
    """生成风险 + 建议综合报告。"""
    risk_part = build_risk_report(evidence, query)
    advice_part = build_advice_report(evidence, query)
    return (
        risk_part
        + "\n\n"
        + advice_part.replace("【AFC 维修与巡检建议】", "【维修与巡检建议补充】", 1)
    )


def build_full_diagnosis_report(evidence: dict[str, Any], query: str) -> str:
    """生成单设备完整诊断报告。"""
    lines = ["【AFC 设备智能诊断报告】", "", "一、设备识别结果"]
    lines.extend(_device_header(evidence))

    history = evidence.get("history_summary", {}) or {}
    risk = evidence.get("risk_prediction", {}) or {}
    advice = evidence.get("maintenance_advice", {}) or {}
    warning = evidence.get("warning_result", {}) or {}

    lines.extend(["", "二、历史工单摘要"])
    lines.append(f"- 返回历史工单数：{history.get('returned_history_count', '数据缺失')}")
    recent = history.get("recent_descriptions", [])
    if recent:
        lines.append("- 最近故障描述：")
        for desc in recent[:3]:
            lines.append(f"  - {desc}")
    top_faults = history.get("top_fault_descriptions", [])
    if top_faults:
        lines.append("- 高频故障描述：")
        for row in top_faults[:3]:
            lines.append(f"  - {row.get('description')}（{row.get('count')} 次）")

    lines.extend([
        "",
        "三、多时间窗口复发风险",
        f"- 7 天风险：{risk.get('risk_7d', '数据缺失')}",
        f"- 14 天风险：{risk.get('risk_14d', '数据缺失')}",
        f"- 21 天风险：{risk.get('risk_21d', '数据缺失')}",
        f"- 30 天风险：{risk.get('risk_30d', '数据缺失')}",
        f"- 60 天风险：{risk.get('risk_60d', '数据缺失')}",
        f"- 90 天风险：{risk.get('risk_90d', '数据缺失')}",
        "",
        "四、预警等级与原因",
        f"- 当前预警等级：{warning.get('warning_level') or risk.get('warning_level', '数据缺失')}",
        f"- 建议巡检窗口：{warning.get('suggested_inspection_window') or risk.get('suggested_inspection_window', '数据缺失')}",
        f"- 预警原因：{warning.get('warning_reason') or risk.get('warning_reason', '数据缺失')}",
        "",
        "五、维修与巡检建议",
    ])
    for item in advice.get("inspection_suggestions", [])[:5]:
        lines.append(f"- {item}")
    if not advice.get("inspection_suggestions"):
        lines.append("- 工具未返回维修建议")

    lines.extend(["", "六、工具调用记录"])
    for tool in evidence.get("sources", []):
        lines.append(f"- {tool}")
    lines.extend(_scientific_boundary_lines())
    lines.append("")
    lines.append(f"原始问题：{query}")
    return "\n".join(lines)


def build_capability_report() -> str:
    """生成系统能力介绍报告（元问题，如"你会干什么""怎么用"）。"""
    lines = []
    lines.append("【AFC 智能诊断 Agent — 功能介绍】")
    lines.append("")
    lines.append("我是 AFC（地铁自动售检票）设备智能诊断助手。我可以帮你完成以下工作：")
    lines.append("")
    lines.append("📊 **数据概览** — 了解工单整体情况")
    lines.append('  试试问："这批工单整体情况怎么样？"')
    lines.append("")
    lines.append("🚨 **高风险设备** — 查看当前最需要关注的设备")
    lines.append('  试试问："当前高风险设备有哪些？""今天优先巡检什么？"')
    lines.append("")
    lines.append("🔍 **单设备诊断** — 分析某台设备的完整状况")
    lines.append('  试试问："帮我分析设备 1000029970"')
    lines.append("")
    lines.append("📈 **风险预测** — 查看设备未来复发风险")
    lines.append('  试试问："设备 1000029970 未来30天风险高吗？"')
    lines.append("")
    lines.append("⚠️ **预警解释** — 了解为什么某台设备触发预警")
    lines.append('  试试问："为什么设备 1000029970 是红色预警？"')
    lines.append("")
    lines.append("🔧 **维修建议** — 获得巡检方向参考")
    lines.append('  试试问："设备 1000029970 应该检查什么？"')
    lines.append("")
    lines.append("📋 **历史查询** — 查看设备过往故障记录")
    lines.append('  试试问："设备 1000029970 最近有哪些故障？"')
    lines.append("")
    lines.append("💬 **多轮对话** — 可以连续追问，Agent 会记住上下文")
    lines.append('  试试连续问："帮我分析设备 1000029970" → "那它为什么是橙色预警？"')
    lines.append("")
    lines.append("---")
    lines.append("请直接输入你的问题开始使用！")
    return "\n".join(lines)
