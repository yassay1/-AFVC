from fastapi import APIRouter, HTTPException, Query

from backend.services.prediction_service import predict_device_risk
from backend.services.fault_prediction_service import predict_device_fault_type
from backend.domain.risk import SUPPORTED_PREDICTION_WINDOWS


router = APIRouter(
    prefix="/predict",
    tags=["风险预测"]
)


@router.get("/{assetnum}")
def predict_asset_risk(assetnum: str):
    """预测设备未来多个时间窗口的故障工单复发风险。"""
    try:
        return predict_device_risk(assetnum)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"风险预测失败：{str(e)}")


@router.get("/fault-type/{assetnum}")
def predict_asset_fault_type(
    assetnum: str,
    window_days: int = Query(default=30, ge=7, le=90, description="预测时间窗口（天）"),
    top_k: int = Query(default=3, ge=1, le=10, description="返回的故障类别数量"),
):
    """预测设备在指定时间窗口内最可能出现的故障类别。

    返回整体故障风险、条件故障类型概率和综合估计发生概率。

    - **overall_failure_risk**：预测窗口内发生故障工单的总体风险
    - **conditional_probability**：如果发生故障，属于某一类别的条件概率
    - **estimated_occurrence_probability**：综合估计发生概率 = 前者 × 后者
    """
    # 参数校验
    if window_days not in SUPPORTED_PREDICTION_WINDOWS:
        raise HTTPException(
            status_code=422,
            detail=f"不支持的预测窗口 {window_days} 天，支持窗口：{list(SUPPORTED_PREDICTION_WINDOWS)}",
        )
    if top_k < 1:
        raise HTTPException(status_code=422, detail="top_k 必须 >= 1")

    try:
        result = predict_device_fault_type(
            assetnum=assetnum,
            window_days=window_days,
            top_k=top_k,
        )
        # 即使 status=unavailable，也返回 200（区别于服务器故障）
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"故障类型预测失败：{str(e)}")