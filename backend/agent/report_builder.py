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
