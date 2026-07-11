"""预警等级领域定义 —— 红橙黄绿四级预警规则。

本模块封装预警等级判断逻辑，保持与现有 backend/services/warning_service.py 一致。
迁移策略：先在 domain 层建立标准定义，后续 Service 层通过调用此函数收敛逻辑。
"""

from enum import Enum
from typing import Any


class WarningLevel(str, Enum):
    """预警等级枚举。"""

    RED = "红色预警"       # 短期或中长期复发风险较高
    ORANGE = "橙色预警"     # 设备存在较明显的故障工单复发风险
    YELLOW = "黄色预警"     # 设备存在一定复发风险
    GREEN = "绿色关注"     # 当前风险较低


def generate_warning_info(risk_30d: float, risk_90d: float) -> dict[str, Any]:
    """根据 30 天和 90 天风险生成预警等级与巡检建议。

    规则（与现有 warning_service.py 保持一致）：
    - 红色预警：risk_30d ≥ 0.75 或 risk_90d ≥ 0.90
    - 橙色预警：risk_30d ≥ 0.55 或 risk_90d ≥ 0.75
    - 黄色预警：risk_30d ≥ 0.35 或 risk_90d ≥ 0.55
    - 绿色关注：其他

    Args:
        risk_30d: 30 天复发风险值，范围 0.01～0.95。
        risk_90d: 90 天复发风险值，范围 0.01～0.95。

    Returns:
        包含 warning_level、suggested_inspection_window、warning_reason 的字典。
    """
    if risk_30d >= 0.75 or risk_90d >= 0.90:
        return {
            "warning_level": WarningLevel.RED.value,
            "suggested_inspection_window": "建议未来 3～7 天内安排重点巡检",
            "warning_reason": "短期或中长期复发风险较高，需要优先关注",
        }

    if risk_30d >= 0.55 or risk_90d >= 0.75:
        return {
            "warning_level": WarningLevel.ORANGE.value,
            "suggested_inspection_window": "建议未来 7～14 天内安排巡检",
            "warning_reason": "设备存在较明显的故障工单复发风险",
        }

    if risk_30d >= 0.35 or risk_90d >= 0.55:
        return {
            "warning_level": WarningLevel.YELLOW.value,
            "suggested_inspection_window": "建议未来 14～30 天内持续关注",
            "warning_reason": "设备存在一定复发风险，建议纳入常规关注清单",
        }

    return {
        "warning_level": WarningLevel.GREEN.value,
        "suggested_inspection_window": "按常规周期巡检即可",
        "warning_reason": "当前模拟风险较低",
    }
