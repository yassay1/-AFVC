"""LLM JSON 结构化输出工具。

功能：
1. extract_json_from_text — 从 LLM 文本中提取 JSON（支持纯 JSON / markdown 代码块 / 前后废话）
2. parse_json_with_schema — Pydantic 校验
3. call_llm_json — 统一的 LLM → JSON → Pydantic 调用
4. repair_json_output — 校验失败时让 LLM 修复

这不是规则兜底，这是结构化输出工程。
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from backend.core.llm import get_parse_llm

logger = logging.getLogger(__name__)


def _truncate_text(value: Any, limit: int = 4000) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... [truncated {len(text) - limit} chars]"


@dataclass
class LLMJsonAttempt:
    stage: str
    error: str | None = None
    raw_output: str | None = None
    extracted_json: dict[str, Any] | None = None


class LLMJsonError(ValueError):
    """Structured LLM JSON failure with parse, validation, and repair details."""

    def __init__(
        self,
        message: str,
        *,
        schema_name: str,
        attempts: list[LLMJsonAttempt] | None = None,
    ) -> None:
        super().__init__(message)
        self.schema_name = schema_name
        self.attempts = attempts or []

    @property
    def final_stage(self) -> str:
        for attempt in reversed(self.attempts):
            if attempt.error:
                return attempt.stage
        return "unknown"

    def to_log_message(self, *, include_raw: bool = True, raw_limit: int = 4000) -> str:
        lines = [f"schema={self.schema_name}", f"stage={self.final_stage}", f"error={str(self)}"]
        for index, attempt in enumerate(self.attempts, start=1):
            lines.append(f"attempt={index} stage={attempt.stage}")
            if attempt.error:
                lines.append(f"attempt={index} error={attempt.error}")
            if attempt.extracted_json is not None:
                lines.append(
                    f"attempt={index} extracted_json="
                    f"{json.dumps(attempt.extracted_json, ensure_ascii=False, default=str)}"
                )
            if include_raw and attempt.raw_output is not None:
                lines.append(f"attempt={index} raw_output={_truncate_text(attempt.raw_output, raw_limit)}")
        return "\n".join(lines)


# ── JSON 提取 ─────────────────────────────────────────────────────

def extract_json_from_text(text: str) -> dict[str, Any]:
    """从 LLM 文本中提取第一个合法 JSON 对象。

    支持：
    - 纯 JSON 文本
    - ```json ... ``` 代码块
    - 前后有解释文字的 JSON
    - 大括号嵌套

    Raises:
        ValueError: 无法提取合法 JSON 时抛出。
    """
    if not text or not text.strip():
        raise ValueError("输入文本为空，无法提取 JSON")

    text = text.strip()

    # 策略 1：直接 json.loads
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass

    # 策略 2：提取 markdown JSON 代码块
    code_block_patterns = [
        r"```json\s*\n?(.*?)\n?```",
        r"```\s*\n?(.*?)\n?```",
    ]
    for pattern in code_block_patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            try:
                result = json.loads(match.strip())
                if isinstance(result, dict):
                    return result
            except (json.JSONDecodeError, ValueError):
                continue

    # 策略 3：找到第一个 { 作为起点，用括号计数找到配对的 }
    start_idx = text.find("{")
    if start_idx == -1:
        raise ValueError("未在文本中找到 JSON 对象的起始 '{'")

    # 从 start_idx 开始，逐字符计数找到配对的 }
    brace_count = 0
    end_idx = -1
    for i in range(start_idx, len(text)):
        ch = text[i]
        if ch == "{":
            brace_count += 1
        elif ch == "}":
            brace_count -= 1
            if brace_count == 0:
                end_idx = i
                break

    if end_idx == -1:
        raise ValueError("找到 '{' 但未找到配对的 '}'")

    candidate = text[start_idx : end_idx + 1]
    try:
        result = json.loads(candidate)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    raise ValueError(
        f"从文本中提取了 JSON 候选串但解析失败。"
        f"候选串前 200 字符: {candidate[:200]}"
    )


# ── Pydantic 校验 ────────────────────────────────────────────────

def parse_json_with_schema(data: dict[str, Any], schema: type[BaseModel]) -> BaseModel:
    """将 dict 转换为 Pydantic 模型实例。

    Args:
        data: 待校验的字典。
        schema: Pydantic BaseModel 子类。

    Returns:
        校验通过的 Pydantic 模型实例。

    Raises:
        ValueError: Pydantic 校验失败时抛出（包含具体错误信息）。
    """
    try:
        return schema.model_validate(data)
    except Exception as exc:
        raise ValueError(f"Pydantic 校验失败（schema={schema.__name__}）: {str(exc)}") from exc


# ── JSON 修复 ─────────────────────────────────────────────────────

def repair_json_output(
    raw_output: str,
    error_message: str,
    target_schema: type[BaseModel],
    llm=None,
    repair_context: str | None = None,
) -> dict[str, Any]:
    """当 LLM 输出无法解析为合法 JSON 时，让 LLM 修复一次。

    把原始输出、错误信息、目标 schema 发给 LLM，要求只返回修复后的 JSON。
    """
    if llm is None:
        llm = get_parse_llm()

    schema_fields: list[str] = []
    if hasattr(target_schema, "model_fields"):
        for field_name, field_info in target_schema.model_fields.items():
            annotation = str(field_info.annotation).replace("typing.", "").replace("Optional", "optional")
            description = getattr(field_info, "description", "")
            schema_fields.append(f"  - {field_name}: {annotation} — {description}")
    schema_desc = "\n".join(schema_fields) if schema_fields else str(target_schema)

    repair_prompt = (
        "你是一个 JSON 修复助手。下面是一段 LLM 输出，它本应符合目标 Schema，"
        "但 JSON 解析或 Pydantic 校验失败了。\n\n"
        "## 原始 LLM 输出\n"
        f"{raw_output}\n\n"
        + (f"## 原始任务上下文\n{repair_context}\n\n" if repair_context else "")
        +
        "## 错误信息\n"
        f"{error_message}\n\n"
        "## 目标 Schema\n"
        f"类名: {target_schema.__name__}\n"
        f"字段:\n{schema_desc}\n\n"
        "## 要求\n"
        "请只输出一个修复后的、合法的、完整的 JSON 对象。"
        "不要添加任何解释、markdown 标记或多余文本。"
        "输出对象必须直接符合目标 Schema 的根对象字段，不要增加外层包装字段。"
        "确保所有必填字段都有值，类型正确，枚举值在合法范围内。"
    )

    return _repair_json_output_with_trace(
        raw_output=raw_output,
        error_message=error_message,
        target_schema=target_schema,
        llm=llm,
        repair_context=repair_context,
    )[1]


def _repair_json_output_with_trace(
    raw_output: str,
    error_message: str,
    target_schema: type[BaseModel],
    llm=None,
    repair_context: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Repair JSON output and return both raw repair text and extracted JSON."""
    if llm is None:
        llm = get_parse_llm()

    schema_fields: list[str] = []
    if hasattr(target_schema, "model_fields"):
        for field_name, field_info in target_schema.model_fields.items():
            annotation = str(field_info.annotation).replace("typing.", "").replace("Optional", "optional")
            description = getattr(field_info, "description", "")
            schema_fields.append(f"  - {field_name}: {annotation} — {description}")
    schema_desc = "\n".join(schema_fields) if schema_fields else str(target_schema)

    repair_prompt = (
        "你是一个 JSON 修复助手。下面是一段 LLM 输出，它本应符合目标 Schema，"
        "但 JSON 解析或 Pydantic 校验失败了。\n\n"
        "## 原始 LLM 输出\n"
        f"{raw_output}\n\n"
        + (f"## 原始任务上下文\n{repair_context}\n\n" if repair_context else "")
        +
        "## 错误信息\n"
        f"{error_message}\n\n"
        "## 目标 Schema\n"
        f"类名: {target_schema.__name__}\n"
        f"字段:\n{schema_desc}\n\n"
        "## 要求\n"
        "请只输出一个修复后的、合法的、完整的 JSON 对象。"
        "不要添加任何解释、markdown 标记或多余文本。"
        "输出对象必须直接符合目标 Schema 的根对象字段，不要增加外层包装字段。"
        "确保所有必填字段都有值，类型正确，枚举值在合法范围内。"
    )

    try:
        response = llm.invoke([
            SystemMessage(content="你是一个 JSON 修复助手。只输出修复后的 JSON 对象。"),
            HumanMessage(content=repair_prompt),
        ])
        content = response.content if hasattr(response, "content") else str(response)
        repair_raw_output = str(content)
        return repair_raw_output, extract_json_from_text(repair_raw_output)
    except Exception as exc:
        raise ValueError(f"JSON 修复也失败了: {str(exc)}") from exc


# ── 统一调用 ──────────────────────────────────────────────────────

def call_llm_json(
    llm,
    prompt: str,
    schema: type[BaseModel],
    system_prompt: str = "你是一个结构化输出助手。只输出符合要求的 JSON 对象。",
    max_repair_attempts: int = 1,
    repair_context: str | None = None,
) -> BaseModel:
    """统一的 LLM → JSON → Pydantic 调用。

    流程：
    1. LLM 生成文本
    2. extract_json_from_text 提取 JSON
    3. parse_json_with_schema Pydantic 校验
    4. 失败后 repair_json_output 修复一次
    5. 仍失败则抛出清晰错误

    Args:
        llm: LLM 实例。
        prompt: 用户提示词。
        schema: 目标 Pydantic 模型类。
        system_prompt: 系统提示词。
        max_repair_attempts: 最大修复次数（默认 1）。

    Returns:
        校验通过的 Pydantic 模型实例。

    Raises:
        ValueError: 所有尝试失败后抛出。
    """
    t_start = time.time()
    attempts: list[LLMJsonAttempt] = []

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt),
        ])
        raw_output = response.content if hasattr(response, "content") else str(response)
        raw_output = str(raw_output)
    except Exception as exc:
        raise LLMJsonError(
            f"LLM 调用失败: {str(exc)}",
            schema_name=schema.__name__,
            attempts=[LLMJsonAttempt(stage="llm_call", error=str(exc))],
        ) from exc

    logger.debug("LLM 调用耗时 %.2fs，输出长度 %d 字符", time.time() - t_start, len(raw_output))

    first_attempt = LLMJsonAttempt(stage="initial_parse", raw_output=raw_output)
    try:
        data = extract_json_from_text(raw_output)
        first_attempt.extracted_json = data
        result = parse_json_with_schema(data, schema)
        logger.debug("一次解析成功（schema=%s）", schema.__name__)
        return result
    except ValueError as exc:
        first_attempt.error = str(exc)
        attempts.append(first_attempt)
        logger.debug("首次解析失败，尝试修复（schema=%s）", schema.__name__)

    for attempt_index in range(max_repair_attempts):
        stage = f"repair_{attempt_index + 1}"
        repair_attempt = LLMJsonAttempt(stage=stage)
        try:
            repair_raw_output, repaired_data = _repair_json_output_with_trace(
                raw_output=raw_output,
                error_message=attempts[-1].error or "initial parse failed",
                target_schema=schema,
                llm=llm,
                repair_context=repair_context or prompt,
            )
            repair_attempt.raw_output = repair_raw_output
            repair_attempt.extracted_json = repaired_data
            result = parse_json_with_schema(repaired_data, schema)
            logger.debug("修复第 %d 次成功（schema=%s）", attempt_index + 1, schema.__name__)
            return result
        except ValueError as exc:
            repair_attempt.error = str(exc)
            attempts.append(repair_attempt)
            logger.warning("修复第 %d 次失败（schema=%s）", attempt_index + 1, schema.__name__)

    error = LLMJsonError(
        f"LLM JSON 解析和 {max_repair_attempts} 次修复全部失败。",
        schema_name=schema.__name__,
        attempts=attempts,
    )
    logger.error("LLM JSON failed\n%s", error.to_log_message(include_raw=True, raw_limit=8000))
    raise error
