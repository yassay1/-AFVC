"""故障类型预测 Service —— 组合 Adapter、Domain 和 Schema 完成完整业务用例。

对外提供 predict_device_fault_type() 函数。
"""

from typing import Any

from backend.adapters.fault_prediction_adapter import (
    get_fault_type_scores,
    has_fault_prediction_file,
)
from backend.domain.risk import (
    SUPPORTED_PREDICTION_WINDOWS,
    compute_estimated_occurrence_probability,
    get_risk_for_window,
)
from backend.schemas.fault_prediction import (
    FaultTypeScore,
    FaultTypePredictionResult,
)

# ── 常量 ──────────────────────────────────────────────────────────

DEFAULT_WINDOW_DAYS = 30
DEFAULT_TOP_K = 3

PREDICTION_STATEMENT = (
    "故障类型概率表示在预测窗口内发生故障时，"
    "各故障类别的相对可能性，不代表故障一定发生。"
)


# ── 辅助函数 ──────────────────────────────────────────────────────

def _normalize_conditional_probabilities(
    scores: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """归一化条件概率，使同一设备同一窗口下总和为 1。

    对列表中的 conditional_probability 进行归一化处理。
    如果总和为 0 或列表为空，则不做处理。

    Args:
        scores: 故障类型评分列表。

    Returns:
        归一化后的列表（原地修改）。
    """
    if not scores:
        return scores

    total = sum(s["conditional_probability"] for s in scores)
    if total <= 0:
        return scores

    for s in scores:
        s["conditional_probability"] = round(s["conditional_probability"] / total, 4)

    return scores


# ── 公开函数 ──────────────────────────────────────────────────────

def predict_device_fault_type(
    assetnum: str,
    window_days: int = DEFAULT_WINDOW_DAYS,
    top_k: int = DEFAULT_TOP_K,
) -> dict[str, Any]:
    """预测设备在指定时间窗口内最可能出现的故障类别。

    执行流程：
    1. 校验设备编号和预测窗口
    2. 调用 predict_device_risk 获取总体风险
    3. 根据 window_days 读取对应 risk 字段
    4. 调用 fault_prediction_adapter 获取故障类别条件概率
    5. 如果没有故障类型预测结果，返回 unavailable 状态
    6. 对条件概率进行归一化
    7. 计算每一类故障的 estimated_occurrence_probability
    8. 按条件概率从高到低排序
    9. 截取 top_k
    10. 生成 most_likely_fault
    11. 使用 FaultTypePredictionResult 做最终校验
    12. 返回兼容字典

    Args:
        assetnum: 设备编号。
        window_days: 预测时间窗口（天），默认 30。
        top_k: 返回的故障类别数量，默认 3。

    Returns:
        FaultTypePredictionResult 的兼容字典。
    """
    # ── 1. 参数校验 ──
    target_assetnum = assetnum.strip()
    if not target_assetnum:
        return {
            "status": "error",
            "message": "设备编号不能为空",
            "assetnum": "",
            "prediction_window_days": window_days,
            "overall_failure_risk": 0.0,
            "most_likely_fault": None,
            "fault_type_predictions": [],
            "model_source": None,
            "model_version": None,
            "prediction_statement": PREDICTION_STATEMENT,
        }

    if window_days not in SUPPORTED_PREDICTION_WINDOWS:
        return {
            "status": "error",
            "message": (
                f"不支持的预测窗口 {window_days} 天，"
                f"支持窗口：{list(SUPPORTED_PREDICTION_WINDOWS)}"
            ),
            "assetnum": target_assetnum,
            "prediction_window_days": window_days,
            "overall_failure_risk": 0.0,
            "most_likely_fault": None,
            "fault_type_predictions": [],
            "model_source": None,
            "model_version": None,
            "prediction_statement": PREDICTION_STATEMENT,
        }

    # ── 2. 获取总体风险 ──
    try:
        from backend.services.prediction_service import predict_device_risk

        risk_result = predict_device_risk(target_assetnum)
        if risk_result.get("status") != "success":
            return {
                "status": "error",
                "message": f"设备 {target_assetnum} 风险预测失败：{risk_result.get('message', '未知错误')}",
                "assetnum": target_assetnum,
                "prediction_window_days": window_days,
                "overall_failure_risk": 0.0,
                "most_likely_fault": None,
                "fault_type_predictions": [],
                "model_source": None,
                "model_version": None,
                "prediction_statement": PREDICTION_STATEMENT,
            }
    except ValueError as e:
        return {
            "status": "error",
            "message": str(e),
            "assetnum": target_assetnum,
            "prediction_window_days": window_days,
            "overall_failure_risk": 0.0,
            "most_likely_fault": None,
            "fault_type_predictions": [],
            "model_source": None,
            "model_version": None,
            "prediction_statement": PREDICTION_STATEMENT,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"风险预测服务异常：{str(e)}",
            "assetnum": target_assetnum,
            "prediction_window_days": window_days,
            "overall_failure_risk": 0.0,
            "most_likely_fault": None,
            "fault_type_predictions": [],
            "model_source": None,
            "model_version": None,
            "prediction_statement": PREDICTION_STATEMENT,
        }

    # ── 3. 提取对应窗口的风险值 ──
    try:
        overall_failure_risk = get_risk_for_window(risk_result, window_days)
        if overall_failure_risk is None:
            return {
                "status": "error",
                "message": f"风险预测结果中未找到 {window_days} 天风险值",
                "assetnum": target_assetnum,
                "prediction_window_days": window_days,
                "overall_failure_risk": 0.0,
                "most_likely_fault": None,
                "fault_type_predictions": [],
                "model_source": None,
                "model_version": None,
                "prediction_statement": PREDICTION_STATEMENT,
            }
    except ValueError as e:
        return {
            "status": "error",
            "message": str(e),
            "assetnum": target_assetnum,
            "prediction_window_days": window_days,
            "overall_failure_risk": 0.0,
            "most_likely_fault": None,
            "fault_type_predictions": [],
            "model_source": None,
            "model_version": None,
            "prediction_statement": PREDICTION_STATEMENT,
        }

    # ── 4. 获取故障类别条件概率 ──
    if not has_fault_prediction_file():
        return {
            "status": "unavailable",
            "message": "当前暂无故障类型预测模型结果，系统仅支持风险预测。",
            "assetnum": target_assetnum,
            "prediction_window_days": window_days,
            "overall_failure_risk": overall_failure_risk,
            "most_likely_fault": None,
            "fault_type_predictions": [],
            "model_source": None,
            "model_version": None,
            "prediction_statement": PREDICTION_STATEMENT,
        }

    try:
        scores = get_fault_type_scores(target_assetnum, window_days)
    except Exception as e:
        return {
            "status": "error",
            "message": f"故障类型预测数据读取异常：{str(e)}",
            "assetnum": target_assetnum,
            "prediction_window_days": window_days,
            "overall_failure_risk": overall_failure_risk,
            "most_likely_fault": None,
            "fault_type_predictions": [],
            "model_source": None,
            "model_version": None,
            "prediction_statement": PREDICTION_STATEMENT,
        }

    # ── 5. 无结果 → unavailable ──
    if not scores:
        return {
            "status": "unavailable",
            "message": (
                f"设备 {target_assetnum} 在 {window_days} 天窗口下暂无故障类型预测结果。"
            ),
            "assetnum": target_assetnum,
            "prediction_window_days": window_days,
            "overall_failure_risk": overall_failure_risk,
            "most_likely_fault": None,
            "fault_type_predictions": [],
            "model_source": None,
            "model_version": None,
            "prediction_statement": PREDICTION_STATEMENT,
        }

    # ── 6. 归一化条件概率 ──
    scores = _normalize_conditional_probabilities(scores)

    # ── 7. 计算综合估计发生概率 ──
    model_version = None
    for s in scores:
        s["estimated_occurrence_probability"] = compute_estimated_occurrence_probability(
            overall_failure_risk=overall_failure_risk,
            conditional_probability=s["conditional_probability"],
        )
        # 从第一条记录提取 model_version
        if model_version is None:
            model_version = s.get("model_version")

    # ── 8. 已排序（Adapter 保证），截取 top_k ──
    scores = scores[:top_k]

    # ── 9. 构建 FaultTypeScore 列表 ──
    fault_scores = []
    for s in scores:
        try:
            fs = FaultTypeScore(
                fault_code=s["fault_code"],
                fault_name=s["fault_name"],
                conditional_probability=s["conditional_probability"],
                estimated_occurrence_probability=s["estimated_occurrence_probability"],
            )
            fault_scores.append(fs)
        except ValueError:
            # 跳过校验失败的条目
            continue

    if not fault_scores:
        return {
            "status": "error",
            "message": "故障类型预测结果校验失败，无有效条目。",
            "assetnum": target_assetnum,
            "prediction_window_days": window_days,
            "overall_failure_risk": overall_failure_risk,
            "most_likely_fault": None,
            "fault_type_predictions": [],
            "model_source": None,
            "model_version": None,
            "prediction_statement": PREDICTION_STATEMENT,
        }

    # ── 10. most_likely_fault ──
    most_likely = fault_scores[0]

    # ── 11. 最终校验 ──
    result = FaultTypePredictionResult(
        status="success",
        message="故障类型预测成功",
        assetnum=target_assetnum,
        prediction_window_days=window_days,
        overall_failure_risk=overall_failure_risk,
        most_likely_fault=most_likely,
        fault_type_predictions=fault_scores,
        model_source="fault_type_prediction_csv",
        model_version=model_version,
        prediction_statement=PREDICTION_STATEMENT,
    )

    # ── 12. 返回兼容字典 ──
    return result.to_compat_dict()
