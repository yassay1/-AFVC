from fastapi import APIRouter, HTTPException, Query

from backend.services.device_service import (
    get_device_list,
    get_device_history,
)
from backend.services.prediction_service import get_high_risk_devices


router = APIRouter(
    prefix="/devices",
    tags=["设备查询"]
)


@router.get("")
def list_devices():
    try:
        return get_device_list()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"设备列表获取失败：{str(e)}")


@router.get("/high-risk")
def list_high_risk_devices(top_n: int = Query(default=10, ge=1, le=50)):
    try:
        return get_high_risk_devices(top_n=top_n)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"高风险设备生成失败：{str(e)}")


@router.get("/{assetnum}/history")
def query_device_history(
    assetnum: str,
    limit: int = Query(default=50, ge=1, le=200)
):
    try:
        return get_device_history(assetnum=assetnum, limit=limit)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"设备历史查询失败：{str(e)}")