from fastapi import APIRouter, HTTPException

from backend.services.advice_service import generate_device_advice


router = APIRouter(
    prefix="/advice",
    tags=["维修建议"]
)


@router.get("/{assetnum}")
def get_advice(assetnum: str):
    """
    获取某台设备的维修建议。

    第一版基于规则模板生成。
    后续可升级为 RAG + Agent。
    """
    try:
        return generate_device_advice(assetnum)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"维修建议生成失败：{str(e)}")