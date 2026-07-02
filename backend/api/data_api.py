from fastapi import APIRouter, HTTPException, Query

from backend.services.data_service import (
    get_basic_data_info,
    get_data_summary,
)


router = APIRouter(
    prefix="/data",
    tags=["工单数据读取与统计"]
)


@router.get("/basic-info")
def get_data_basic_info():
    """
    获取当前上传工单文件的基础信息。

    返回内容包括：
    1. 当前读取的文件名；
    2. 行数；
    3. 列数；
    4. 字段名；
    5. 核心字段是否存在。
    """
    try:
        return get_basic_data_info()
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"工单数据读取失败：{str(e)}"
        )


@router.get("/summary")
def get_summary(top_n: int = Query(default=10, ge=1, le=30)):
    """
    获取 AFC 工单数据概览统计结果。

    参数：
        top_n: 排名前 N 的统计结果，默认 10，最大 30。
    """
    try:
        return get_data_summary(top_n=top_n)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"数据概览统计失败：{str(e)}"
        )