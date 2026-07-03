"""统一 LLM 封装模块。

为 Agent 的不同节点（parse / report）提供 LLM 实例。
实例采用懒加载单例模式缓存，避免重复创建。
"""

import logging
from langchain_openai import ChatOpenAI
from backend.core.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL

logger = logging.getLogger(__name__)

# ── 懒加载缓存 ──
_PARSE_LLM: ChatOpenAI | None = None
_REPORT_LLM: ChatOpenAI | None = None


def _create_chat_openai(temperature: float) -> ChatOpenAI:
    """创建 ChatOpenAI 实例，统一校验 API Key 配置。"""
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY 未配置，请在 .env 文件中设置，"
            "可参考 .env.example 文件。"
        )

    return ChatOpenAI(
        model=OPENAI_MODEL,
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL,
        temperature=temperature,
    )


def get_llm(temperature: float = 0.0) -> ChatOpenAI:
    """获取标准 LLM 实例，用于解析和报告生成。"""
    return _create_chat_openai(temperature=temperature)


def get_parse_llm() -> ChatOpenAI:
    """用于问题解析的 LLM（懒加载单例），温度较低以保证输出稳定。"""
    global _PARSE_LLM
    if _PARSE_LLM is None:
        logger.info("初始化 LLM 解析实例（model=%s）", OPENAI_MODEL)
        _PARSE_LLM = _create_chat_openai(temperature=0.0)
    return _PARSE_LLM


def get_report_llm() -> ChatOpenAI:
    """用于报告生成的 LLM（懒加载单例），温度适中。"""
    global _REPORT_LLM
    if _REPORT_LLM is None:
        logger.info("初始化 LLM 报告实例（model=%s）", OPENAI_MODEL)
        _REPORT_LLM = _create_chat_openai(temperature=0.3)
    return _REPORT_LLM
