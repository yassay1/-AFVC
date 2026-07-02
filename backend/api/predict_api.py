from fastapi import APIRouter, HTTPException

from backend.services.prediction_service import predict_device_risk


router = APIRouter(
    prefix="/predict",
    tags=["风险预测"]
)


@router.get("/{assetnum}")
def predict_asset_risk(assetnum: str):
    try:
        return predict_device_risk(assetnum)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"风险预测失败：{str(e)}")