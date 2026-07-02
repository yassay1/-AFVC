from fastapi import APIRouter, HTTPException, Query

from backend.services.analysis_service import generate_device_analysis


router = APIRouter(
    prefix="/analysis",
    tags=["单设备综合分析"]
)


@router.get("/{assetnum}")
def analyze_device(
    assetnum: str,
    history_limit: int = Query(default=50, ge=1, le=200)
):
    """
    获取单设备综合分析结果。

    整合内容包括：
    1. 设备基础信息；
    2. 历史工单摘要；
    3. 风险预测；
    4. 预警等级；
    5. 维修建议。
    """
    try:
        return generate_device_analysis(
            assetnum=assetnum,
            history_limit=history_limit,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"单设备综合分析失败：{str(e)}")