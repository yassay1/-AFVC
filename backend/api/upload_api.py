from pathlib import Path
from datetime import datetime
import shutil

from fastapi import APIRouter, UploadFile, File, HTTPException


router = APIRouter(
    prefix="/upload",
    tags=["工单文件上传"]
)


# 项目根目录下的 backend/data/raw
RAW_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/workorders")
def upload_workorder_file(file: UploadFile = File(...)):
    """
    上传 AFC 维修工单文件。

    第一版只负责：
    1. 接收 Excel / CSV 文件；
    2. 保存到 backend/data/raw/；
    3. 返回文件保存结果。

    暂时不在这里解析数据。
    后续会交给 data_service.py 使用 Polars 读取和清洗。
    """

    allowed_suffixes = [".xlsx", ".xls", ".csv"]

    original_filename = file.filename

    if not original_filename:
        raise HTTPException(
            status_code=400,
            detail="未检测到上传文件名"
        )

    suffix = Path(original_filename).suffix.lower()

    if suffix not in allowed_suffixes:
        raise HTTPException(
            status_code=400,
            detail="文件格式不支持，请上传 .xlsx、.xls 或 .csv 文件"
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{original_filename}"

    save_path = RAW_DATA_DIR / safe_filename

    try:
        with save_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"文件保存失败：{str(e)}"
        )
    finally:
        file.file.close()

    return {
        "status": "success",
        "message": "工单文件上传成功",
        "original_filename": original_filename,
        "saved_filename": safe_filename,
        "saved_path": str(save_path),
        "file_suffix": suffix
    }