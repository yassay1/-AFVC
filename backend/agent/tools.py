"""LangChain Tools 工具层：把 Service 层封装成 Agent 可调用的工具。

每个工具只做薄封装，业务逻辑全在 Service 层。
"""

from langchain.tools import tool

from backend.services.data_service import get_data_summary as _get_data_summary
from backend.services.device_service import get_device_list as _get_device_list
from backend.services.device_service import get_device_history as _get_device_history
from backend.services.prediction_service import predict_device_risk as _predict_device_risk
from backend.services.prediction_service import get_high_risk_devices as _get_high_risk_devices
from backend.services.warning_service import generate_warning_info as _generate_warning_info
from backend.services.advice_service import generate_device_advice as _generate_device_advice
from backend.services.analysis_service import generate_device_analysis as _generate_device_analysis
from backend.services.rag_service import search_manual as _search_manual
from backend.services.fault_prediction_service import predict_device_fault_type as _predict_device_fault_type


@tool
def get_data_summary_tool(top_n: int = 10) -> dict:
    """获取 AFC 工单数据概览统计。

    返回工单总数、设备数量、车站/线路/品牌数量、工单时间范围、
    品牌分布、线路分布、高频故障描述 Top N、工单类型分布。

    适用场景：
    - 用户想了解这批工单的整体情况
    - 用户问“现在工单数据怎么样”

    Args:
        top_n: Top N 统计数量，默认 10。
    """
    try:
        return _get_data_summary(top_n=top_n)
    except FileNotFoundError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"数据概览获取失败：{str(e)}"}


@tool
def list_devices_tool() -> dict:
    """获取所有 AFC 设备列表，按历史工单数量降序排列。

    每条记录包含设备编号、车站、线路、品牌、工单数量、最近记录时间。

    适用场景：
    - 校验设备编号是否存在
    - 用户需要查看设备列表
    - Agent 解析设备编号后需要确认设备存在
    """
    try:
        return _get_device_list()
    except FileNotFoundError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"设备列表获取失败：{str(e)}"}


@tool
def get_device_history_tool(assetnum: str, limit: int = 50) -> dict:
    """查询指定 AFC 设备的历史故障工单记录。

    返回该设备的历史工单列表，按工单记录时间降序排列。
    包含故障描述、工单时间、工单类型、品牌、子系统等字段。

    适用场景：
    - 用户问“设备 XXX 以前出过什么故障”
    - 用户问“设备 XXX 最近有哪些故障”
    - 分析时作为风险判断依据

    Args:
        assetnum: 设备编号，如 "1000029970"、"EX011115"。
        limit: 返回的历史工单最大条数，默认 50。
    """
    try:
        return _get_device_history(assetnum=assetnum.strip(), limit=limit)
    except FileNotFoundError as e:
        return {"status": "error", "message": str(e)}
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"设备历史查询失败：{str(e)}"}


@tool
def predict_device_risk_tool(assetnum: str) -> dict:
    """预测指定 AFC 设备未来多个时间窗口内再次产生故障工单的风险。

    返回 7/14/21/30/60/90 天的复发风险值（0.01～0.95）、
    预警等级（红/橙/黄/绿）、建议巡检窗口、主要风险因素、
    特征快照和预测来源说明。

    注意：风险值表示再次产生故障工单的概率，不等同于精确预测
    物理故障发生日期。

    适用场景：
    - 用户问“设备 XXX 未来风险高吗”
    - 用户问“设备 XXX 未来 30 天风险高不高”
    - 作为诊断报告中的风险依据

    Args:
        assetnum: 设备编号。
    """
    try:
        return _predict_device_risk(assetnum=assetnum.strip())
    except FileNotFoundError as e:
        return {"status": "error", "message": str(e)}
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"风险预测失败：{str(e)}"}


@tool
def get_warning_level_tool(risk_30d: float, risk_90d: float) -> dict:
    """根据 30 天和 90 天风险值生成红橙黄绿预警等级。

    预警规则：
    - 红色预警：risk_30d >= 0.75 或 risk_90d >= 0.90，建议 3～7 天内巡检
    - 橙色预警：risk_30d >= 0.55 或 risk_90d >= 0.75，建议 7～14 天内巡检
    - 黄色预警：risk_30d >= 0.35 或 risk_90d >= 0.55，建议 14～30 天内关注
    - 绿色关注：其他，常规周期巡检

    适用场景：
    - 用户问“为什么设备 XXX 是红色预警”
    - 预测之后需要解释预警含义
    - 高风险设备排序时生成预警等级

    Args:
        risk_30d: 30 天复发风险值，范围 0.01～0.95。
        risk_90d: 90 天复发风险值，范围 0.01～0.95。
    """
    try:
        return _generate_warning_info(risk_30d=risk_30d, risk_90d=risk_90d)
    except Exception as e:
        return {"status": "error", "message": f"预警等级生成失败：{str(e)}"}


@tool
def get_maintenance_advice_tool(assetnum: str) -> dict:
    """根据设备历史故障描述生成维修与巡检建议。

    基于历史工单 description 字段匹配故障规则库，返回：
    - 识别到的故障现象类别
    - 可能的原因
    - 建议检查方向
    - 备件准备建议

    注意：维修建议是巡检方向参考，不是最终根因诊断结论。

    适用场景：
    - 用户问“设备 XXX 建议检查什么”
    - 用户问“设备 XXX 应该怎么处理”
    - 作为诊断报告中的维修建议部分

    Args:
        assetnum: 设备编号。
    """
    try:
        return _generate_device_advice(assetnum=assetnum.strip())
    except FileNotFoundError as e:
        return {"status": "error", "message": str(e)}
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"维修建议生成失败：{str(e)}"}


@tool
def get_integrated_analysis_tool(assetnum: str, history_limit: int = 50) -> dict:
    """对单台 AFC 设备进行综合分析，聚合设备信息、历史工单、
    风险预测、预警等级和维修建议。

    这是 Agent 最核心的工具，一次调用即可获取完整诊断所需数据。
    返回结构包含：
    - device_profile：设备基础信息
    - history_summary：历史工单摘要
    - risk_prediction：6 个时间窗口风险预测
    - maintenance_advice：维修与巡检建议
    - called_tools：记录调用了哪些子工具

    适用场景：
    - 用户问“帮我分析设备 XXX”
    - 需要全维度了解一台设备状况时

    Args:
        assetnum: 设备编号。
        history_limit: 历史工单分析数量，默认 50。
    """
    try:
        return _generate_device_analysis(
            assetnum=assetnum.strip(),
            history_limit=history_limit,
        )
    except FileNotFoundError as e:
        return {"status": "error", "message": str(e)}
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"综合分析失败：{str(e)}"}


@tool
def get_high_risk_devices_tool(top_n: int = 10) -> dict:
    """获取当前高风险 AFC 设备 Top N 列表。

    优先使用外部模型预测结果；如果不存在外部预测结果，
    则回退到基于历史工单统计的 baseline 预测排序。

    返回每台设备的风险值（7/14/21/30/60/90 天）、预警等级、
    建议巡检窗口、车站、线路、品牌等信息。

    适用场景：
    - 用户问“今天优先巡检哪些设备”
    - 用户问“高风险设备有哪些”
    - 运维主管查看巡检重点

    Args:
        top_n: 返回的高风险设备数量，默认 10。
    """
    try:
        return _get_high_risk_devices(top_n=top_n)
    except FileNotFoundError as e:
        return {"status": "error", "message": str(e)}
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"高风险设备查询失败：{str(e)}"}


@tool
def predict_device_fault_type_tool(
    assetnum: str,
    window_days: int = 30,
    top_k: int = 3,
) -> dict:
    """预测指定 AFC 设备在未来时间窗口内最可能出现的故障类别。

    返回整体故障风险、各故障类别的条件概率，以及综合估计发生概率。
    该工具用于回答“最可能发生什么故障”“下一次可能坏在哪里”等问题。

    概率含义：
    - overall_failure_risk：预测窗口内发生故障工单的总体风险
    - conditional_probability：若发生故障，属于某一类别的条件概率
    - estimated_occurrence_probability：总体风险与条件概率的组合估计

    注意：故障类型概率表示相对可能性，不代表故障一定发生。

    适用场景：
    - 用户问“设备 XXX 最可能发生什么故障”
    - 用户问“未来 30 天可能出现什么错误”
    - 用户问“下一次可能坏在哪里”
    - 用户问“最可能出问题的是哪个模块”
    - 用户问“会发生什么故障”

    Args:
        assetnum: 设备编号。
        window_days: 预测时间窗口（天），默认 30。
        top_k: 返回的故障类别数量，默认 3。
    """
    try:
        return _predict_device_fault_type(
            assetnum=assetnum.strip(),
            window_days=window_days,
            top_k=top_k,
        )
    except FileNotFoundError as e:
        return {"status": "error", "message": str(e)}
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"故障类型预测失败：{str(e)}"}


@tool
def search_maintenance_manual_tool(
    query: str,
    assetnum: str | None = None,
    subsystem: str | None = None,
    fault_phenomenon: str | None = None,
    top_k: int = 5,
) -> dict:
    """检索 AFC 设备维修手册和规程文件。

    根据用户问题在知识库中搜索相关维修检查步骤、可能原因、
    备件建议等内容。

    适用场景：
    - 用户明确要求按维修手册/规程/标准流程回答
    - device_advice 需要维修手册依据增强时
    - full_diagnosis 需要维修建议时
    - 用户问“按手册应该先查哪里”

    Args:
        query: 检索查询文本（通常是用户问题或故障现象）。
        assetnum: 设备编号（可选，用于增加相关检索词）。
        subsystem: 子系统名称（可选，如票卡/扇门/通信/主控）。
        fault_phenomenon: 故障现象描述（可选）。
        top_k: 返回结果数，默认 5。
    """
    try:
        return _search_manual(
            query=query,
            assetnum=assetnum,
            subsystem=subsystem,
            fault_phenomenon=fault_phenomenon,
            top_k=top_k,
        )
    except Exception as e:
        return {"status": "error", "message": f"维修手册检索失败：{str(e)}"}


ALL_TOOLS = [
    get_data_summary_tool,
    list_devices_tool,
    get_device_history_tool,
    predict_device_risk_tool,
    get_warning_level_tool,
    get_maintenance_advice_tool,
    get_integrated_analysis_tool,
    get_high_risk_devices_tool,
    search_maintenance_manual_tool,
    predict_device_fault_type_tool,
]

TOOL_BY_NAME = {tool.name: tool for tool in ALL_TOOLS}
