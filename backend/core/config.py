"""项目配置模块，从 .env 文件读取环境变量。"""

import os
from dotenv import load_dotenv

load_dotenv()


OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_TIMEOUT_SECONDS: float = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "10"))
OPENAI_MAX_RETRIES: int = int(os.getenv("OPENAI_MAX_RETRIES", "0"))
AFVC_USE_LLM: str = os.getenv("AFVC_USE_LLM", "false")

LANGSMITH_TRACING: str = os.getenv("LANGSMITH_TRACING", "false")
LANGSMITH_API_KEY: str = os.getenv("LANGSMITH_API_KEY", "")
LANGSMITH_PROJECT: str = os.getenv("LANGSMITH_PROJECT", "afc-riskops-agent")

PROJECT_NAME: str = "AFC 故障复发风险预测与智能维修建议系统"
PROJECT_VERSION: str = "0.3.0"


def is_llm_enabled() -> bool:
    """Return whether real LLM calls are enabled for this process."""
    return AFVC_USE_LLM.strip().lower() in {"1", "true", "yes", "on"}
