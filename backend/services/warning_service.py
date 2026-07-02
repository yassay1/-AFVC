def generate_warning_info(risk_30d: float, risk_90d: float) -> dict:
    """
    根据 30 天和 90 天风险生成预警等级与巡检建议。

    注意：
    这里是第一版规则预警，不是最终机器学习模型结论。
    """
    if risk_30d >= 0.75 or risk_90d >= 0.90:
        return {
            "warning_level": "红色预警",
            "suggested_inspection_window": "建议未来 3～7 天内安排重点巡检",
            "warning_reason": "短期或中长期复发风险较高，需要优先关注",
        }

    if risk_30d >= 0.55 or risk_90d >= 0.75:
        return {
            "warning_level": "橙色预警",
            "suggested_inspection_window": "建议未来 7～14 天内安排巡检",
            "warning_reason": "设备存在较明显的故障工单复发风险",
        }

    if risk_30d >= 0.35 or risk_90d >= 0.55:
        return {
            "warning_level": "黄色预警",
            "suggested_inspection_window": "建议未来 14～30 天内持续关注",
            "warning_reason": "设备存在一定复发风险，建议纳入常规关注清单",
        }

    return {
        "warning_level": "绿色关注",
        "suggested_inspection_window": "按常规周期巡检即可",
        "warning_reason": "当前模拟风险较低",
    }