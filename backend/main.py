"""AFC 故障复发风险预测与智能维修建议系统 —— FastAPI 入口。

启动方式：
    python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import (
    PROJECT_NAME,
    PROJECT_VERSION,
    LANGSMITH_TRACING,
    LANGSMITH_API_KEY,
    LANGSMITH_PROJECT,
)

# ── 日志 ──────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("afc_agent")

# ── LangSmith 初始化 ──────────────────────────────────────────

if LANGSMITH_TRACING.lower() == "true" and LANGSMITH_API_KEY:
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = LANGSMITH_API_KEY
    os.environ["LANGSMITH_PROJECT"] = LANGSMITH_PROJECT


# ── 应用生命周期 ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的操作。"""
    # 启动时
    from pathlib import Path
    raw_dir = Path(__file__).parent / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    logger.info("AFC 智能系统 v%s 启动，数据目录：%s", PROJECT_VERSION, raw_dir)
    yield
    # 关闭时
    logger.info("AFC 智能系统关闭")


# ── FastAPI 应用 ──────────────────────────────────────────────

app = FastAPI(
    title=PROJECT_NAME,
    description=(
        "面向地铁 AFC 闸机维修工单数据的智能运维系统。"
        "支持工单上传、数据概览、设备历史查询、多时间窗口风险预测、"
        "红橙黄绿预警、维修建议生成，以及基于 LangGraph 的 Agent 智能诊断。"
    ),
    version=PROJECT_VERSION,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 健康检查 ──────────────────────────────────────────────────

@app.get("/health", tags=["健康检查"])
def health_check():
    return {
        "status": "ok",
        "message": "AFC 故障智能系统后端运行正常",
        "version": PROJECT_VERSION,
    }


# ── 注册路由 ──────────────────────────────────────────────────

from backend.api.upload_api import router as upload_router
from backend.api.data_api import router as data_router
from backend.api.device_api import router as device_router
from backend.api.predict_api import router as predict_router
from backend.api.advice_api import router as advice_router
from backend.api.analysis_api import router as analysis_router
from backend.api.agent_api import router as agent_router

app.include_router(upload_router)
app.include_router(data_router)
app.include_router(device_router)
app.include_router(predict_router)
app.include_router(advice_router)
app.include_router(analysis_router)
app.include_router(agent_router)
