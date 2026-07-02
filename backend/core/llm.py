"""统一 LLM 封装模块。

为 Agent 的不同节点（parse / report）提供 LLM 实例。
"""

from langchain_openai import ChatOpenAI
from backend.core.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL


def get_llm(temperature: float = 0.0) -> ChatOpenAI:
    """获取标准 LLM 实例，用于解析和报告生成。"""
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


def get_parse_llm() -> ChatOpenAI:
    """用于问题解析的 LLM，温度较低以保证输出稳定。"""
    return get_llm(temperature=0.0)


def get_report_llm() -> ChatOpenAI:
    """用于报告生成的 LLM，温度适中。"""
    return get_llm(temperature=0.3)
