"""故障类别领域定义 —— 统一故障枚举与展示名称。

本模块定义 AFC 设备故障的标准分类，供 Adapter、Service、Agent 等各层使用。
所有故障类别以枚举形式定义，保证全系统一致。
"""

from enum import Enum


class FaultCategory(str, Enum):
    """AFC 设备故障统一枚举。

    所有系统模块引用故障类别时必须使用此枚举，不允许硬编码字符串。
    """

    TICKET_CARD = "TICKET_CARD"           # 票卡处理异常
    SERVICE_SUSPENDED = "SERVICE_SUSPENDED"  # 设备暂停服务或服务中止
    SYSTEM = "SYSTEM"                      # 主控、显示或系统运行异常
    COMMUNICATION = "COMMUNICATION"        # 通信异常
    GATE_CONTROL = "GATE_CONTROL"          # 通行控制或扇门异常
    OTHER = "OTHER"                        # 其他故障


# ── 中文展示名称映射 ──────────────────────────────────────────────

FAULT_CODE_TO_NAME: dict[str, str] = {
    FaultCategory.TICKET_CARD: "票卡处理异常",
    FaultCategory.SERVICE_SUSPENDED: "设备暂停服务或服务中止",
    FaultCategory.SYSTEM: "主控、显示或系统运行异常",
    FaultCategory.COMMUNICATION: "通信异常",
    FaultCategory.GATE_CONTROL: "通行控制或扇门异常",
    FaultCategory.OTHER: "其他故障",
}

# 反向映射：中文名 → 故障代码
FAULT_NAME_TO_CODE: dict[str, str] = {
    v: k for k, v in FAULT_CODE_TO_NAME.items()
}


# ── 合法故障代码集合 ──────────────────────────────────────────────

_VALID_FAULT_CODES: frozenset = frozenset(FAULT_CODE_TO_NAME.keys())


def is_valid_fault_code(fault_code: str) -> bool:
    """判断给定代码是否为合法故障类别。

    Args:
        fault_code: 故障类别代码，如 "TICKET_CARD"。

    Returns:
        True 如果 fault_code 属于 FaultCategory 枚举。
    """
    if not isinstance(fault_code, str):
        return False
    return fault_code.strip().upper() in _VALID_FAULT_CODES


def normalize_fault_code(fault_code: str) -> str | None:
    """将故障代码标准化为大写格式。

    Args:
        fault_code: 原始故障代码字符串。

    Returns:
        标准化后的故障代码，如果非法则返回 None。
    """
    if not isinstance(fault_code, str):
        return None
    normalized = fault_code.strip().upper()
    if normalized in _VALID_FAULT_CODES:
        return normalized
    return None
