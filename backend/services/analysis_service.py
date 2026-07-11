from collections import Counter
from typing import Any

from backend.services.device_service import get_device_history
from backend.services.prediction_service import predict_device_risk
from backend.services.advice_service import generate_device_advice
from backend.services.fault_prediction_service import predict_device_fault_type


def _get_value_from_sources(key: str, *sources: dict[str, Any]) -> Any:
    """
    从多个结果字典中按顺序取值。
    """
    for source in sources:
        value = source.get(key)
        if value not in [None, ""]:
            return value
    return None


def _extract_recent_descriptions(history: list[dict[str, Any]], limit: int = 5) -> list[str]:
    """
    提取最近若干条故障描述。
    """
    descriptions = []

    for row in history:
        description = row.get("description")
        if description:
            descriptions.append(str(description))

    return descriptions[:limit]


def _extract_top_fault_descriptions(
    history: list[dict[str, Any]],
    top_n: int = 5
) -> list[dict[str, Any]]:
    """
    统计单台设备历史工单中的高频故障描述。
    """
    descriptions = []

    for row in history:
        description = row.get("description")
        if description:
            descriptions.append(str(description).strip())

    counter = Counter(descriptions)

    return [
        {
            "description": description,
            "count": count,
        }
        for description, count in counter.most_common(top_n)
    ]


def generate_device_analysis(assetnum: str, history_limit: int = 50) -> dict[str, Any]:
    """
    生成单设备综合分析结果。

    该函数是 Agent 后续最重要的工具之一。
    它负责把设备历史、风险预测和维修建议整合成一份结构化分析结果。
    """
    target_assetnum = assetnum.strip()

    history_result = get_device_history(
        assetnum=target_assetnum,
        limit=history_limit,
    )

    prediction_result = predict_device_risk(target_assetnum)

    advice_result = generate_device_advice(target_assetnum)

    # ── 故障类型预测（新增）──
    try:
        fault_prediction = predict_device_fault_type(
            assetnum=target_assetnum,
            window_days=30,
            top_k=3,
        )
    except Exception:
        fault_prediction = {
            "status": "unavailable",
            "message": "故障类型预测服务暂不可用",
            "assetnum": target_assetnum,
            "prediction_window_days": 30,
            "overall_failure_risk": 0.0,
            "most_likely_fault": None,
            "fault_type_predictions": [],
        }

    history = history_result.get("history", [])

    recent_descriptions = _extract_recent_descriptions(history, limit=5)
    top_fault_descriptions = _extract_top_fault_descriptions(history, top_n=5)

    last_record_time = None
    if history:
        last_record_time = history[0].get("current_faildate")

    device_profile = {
        "assetnum": target_assetnum,
        "station_name": _get_value_from_sources(
            "station_name",
            prediction_result,
            advice_result,
        ),
        "line": _get_value_from_sources(
            "line",
            prediction_result,
            advice_result,
        ),
        "brand": _get_value_from_sources(
            "brand",
            prediction_result,
            advice_result,
        ),
        "subsystem": _get_value_from_sources(
            "subsystem",
            prediction_result,
            advice_result,
        ),
        "history_workorder_count": advice_result.get("history_workorder_count"),
        "last_record_time": last_record_time,
    }

    risk_prediction = {
        "risk_7d": prediction_result.get("risk_7d"),
        "risk_14d": prediction_result.get("risk_14d"),
        "risk_21d": prediction_result.get("risk_21d"),
        "risk_30d": prediction_result.get("risk_30d"),
        "risk_60d": prediction_result.get("risk_60d"),
        "risk_90d": prediction_result.get("risk_90d"),
        "warning_level": prediction_result.get("warning_level"),
        "suggested_inspection_window": prediction_result.get("suggested_inspection_window"),
        "warning_reason": prediction_result.get("warning_reason"),
        "main_risk_factors": prediction_result.get("main_risk_factors", []),
        "feature_snapshot": prediction_result.get("feature_snapshot", {}),
    }

    maintenance_advice = {
        "recognized_fault_phenomena": advice_result.get("recognized_fault_phenomena", []),
        "possible_causes": advice_result.get("possible_causes", []),
        "inspection_suggestions": advice_result.get("inspection_suggestions", []),
        "spare_part_suggestions": advice_result.get("spare_part_suggestions", []),
        "maintenance_sop": advice_result.get("maintenance_sop", {}),
        "recent_descriptions_used": advice_result.get("recent_descriptions", []),
    }

    return {
        "status": "success",
        "message": "单设备综合分析生成成功",
        "assetnum": target_assetnum,
        "device_profile": device_profile,
        "history_summary": {
            "returned_history_count": history_result.get("history_count"),
            "recent_descriptions": recent_descriptions,
            "top_fault_descriptions": top_fault_descriptions,
        },
        "risk_prediction": risk_prediction,
        "maintenance_advice": maintenance_advice,
        "fault_prediction": fault_prediction,
        "called_tools": [
            "get_device_history",
            "predict_device_risk",
            "generate_device_advice",
            "predict_device_fault_type",
        ],
        "analysis_statement": (
            "本分析基于历史维修工单记录、模拟风险预测和规则维修建议生成。"
            "系统预测的是未来多个时间窗口内再次产生故障工单的风险，"
            "不等同于精确预测真实物理故障发生日期。维修建议仅作为巡检方向参考，"
            "不代表系统已经准确判断真实故障根因。"
        ),
    }
