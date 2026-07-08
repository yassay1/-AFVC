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
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from backend.core.llm import get_parse_llm

logger = logging.getLogger(__name__)


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

    try:
        response = llm.invoke([
            SystemMessage(content="你是一个 JSON 修复助手。只输出修复后的 JSON 对象。"),
            HumanMessage(content=repair_prompt),
        ])
        content = response.content if hasattr(response, "content") else str(response)
        return extract_json_from_text(str(content))
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

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt),
        ])
        raw_output = response.content if hasattr(response, "content") else str(response)
    except Exception as exc:
        raise ValueError(f"LLM 调用失败: {str(exc)}") from exc

    logger.debug("LLM 调用耗时 %.2fs，输出长度 %d 字符", time.time() - t_start, len(raw_output))

    # 尝试 1：直接提取 + 校验
    errors: list[str] = []
    try:
        data = extract_json_from_text(raw_output)
        result = parse_json_with_schema(data, schema)
        logger.debug("一次解析成功（schema=%s）", schema.__name__)
        return result
    except ValueError as exc:
        errors.append(f"首次解析失败: {str(exc)}")
        logger.debug("首次解析失败，尝试修复（schema=%s）", schema.__name__)

    # 尝试 2：修复
    for attempt in range(max_repair_attempts):
        try:
            repaired_data = repair_json_output(
                raw_output=raw_output,
                error_message=errors[-1],
                target_schema=schema,
                llm=llm,
                repair_context=repair_context or prompt,
            )
            result = parse_json_with_schema(repaired_data, schema)
            logger.debug("修复第 %d 次成功（schema=%s）", attempt + 1, schema.__name__)
            return result
        except ValueError as exc:
            errors.append(f"修复第 {attempt + 1} 次失败: {str(exc)}")
            logger.warning("修复第 %d 次失败（schema=%s）", attempt + 1, schema.__name__)

    # 全部失败
    detailed_errors = "\n".join(errors)
    raise ValueError(
        f"LLM JSON 解析和 {max_repair_attempts} 次修复全部失败。\n"
        f"目标 Schema: {schema.__name__}\n"
        f"原始输出（前 500 字符）: {raw_output[:500]}\n"
        f"错误详情:\n{detailed_errors}"
    )
