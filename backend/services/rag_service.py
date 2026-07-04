"""第一版轻量 RAG 服务 —— 维修手册检索。

功能：
- 读取 backend/data/knowledge/manuals 下的 .txt / .md 文件
- 按段落切分
- 用关键词匹配 + 简单相似度评分
- 返回 top_k 结果

后续可升级为向量数据库 + embedding 方案。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 手册目录 ────────────────────────────────────────────────────────

MANUALS_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge" / "manuals"
MIN_MATCH_SCORE = 0.1


def _get_manual_files() -> list[Path]:
    """获取所有手册文件。"""
    if not MANUALS_DIR.exists():
        return []
    files = list(MANUALS_DIR.glob("*.txt")) + list(MANUALS_DIR.glob("*.md"))
    return sorted(files)


def _read_file_content(file_path: Path) -> str:
    """读取文件内容。"""
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return file_path.read_text(encoding="gbk")
        except Exception:
            return ""


def _split_into_chunks(text: str, min_length: int = 20) -> list[dict[str, str]]:
    """按段落切分文本，返回带标题和内容的 chunk 列表。

    策略：
    - ## 标记的段落单独成段，前一行作为 section 标题
    - 空行分隔的段落独立成段
    """
    chunks: list[dict[str, str]] = []
    lines = text.split("\n")
    current_title = ""
    current_content: list[str] = []

    for line in lines:
        stripped = line.strip()
        # Markdown 标题作为段落标题
        if stripped.startswith("## "):
            # 保存上一段
            if current_content:
                content = " ".join(current_content).strip()
                if len(content) >= min_length:
                    chunks.append({"title": current_title, "content": content})
            current_title = stripped.lstrip("# ").strip()
            current_content = []
        elif stripped.startswith("# "):
            if current_content:
                content = " ".join(current_content).strip()
                if len(content) >= min_length:
                    chunks.append({"title": current_title, "content": content})
            current_title = stripped.lstrip("# ").strip()
            current_content = []
        elif stripped == "":
            if current_content:
                content = " ".join(current_content).strip()
                if len(content) >= min_length:
                    chunks.append({"title": current_title, "content": content})
                current_content = []
        else:
            current_content.append(stripped)

    # 最后一段
    if current_content:
        content = " ".join(current_content).strip()
        if len(content) >= min_length:
            chunks.append({"title": current_title, "content": content})

    return chunks


def _keyword_score(query: str, chunk_text: str) -> float:
    """简单关键词匹配评分。

    使用字符级 n-gram 提取关键词，计算命中率。
    """
    if not query or not chunk_text:
        return 0.0

    text_lower = chunk_text.lower()
    query_lower = query.lower()

    # 提取 query 中的候选关键词（2-4 字滑动窗口）
    query_clean = re.sub(r"[^一-鿿\w]", "", query_lower)
    candidates: set[str] = set()

    # 整词匹配
    if len(query_clean) >= 2:
        candidates.add(query_clean)

    # 2-gram
    for i in range(len(query_clean) - 1):
        bigram = query_clean[i:i + 2]
        if len(bigram) == 2 and not bigram[0].isspace():
            candidates.add(bigram)

    # 3-gram
    for i in range(len(query_clean) - 2):
        trigram = query_clean[i:i + 3]
        if len(trigram) == 3:
            candidates.add(trigram)

    if not candidates:
        return 1.0 if query_lower in text_lower else 0.0

    hits = sum(1 for c in candidates if c in text_lower)
    return hits / len(candidates)


def search_manual(
    query: str,
    assetnum: str | None = None,
    subsystem: str | None = None,
    fault_phenomenon: str | None = None,
    top_k: int = 5,
) -> dict:
    """检索维修手册。

    Args:
        query: 检索查询文本。
        assetnum: 设备编号（可选，用于增加相关关键词）。
        subsystem: 子系统名称（可选）。
        fault_phenomenon: 故障现象描述（可选）。
        top_k: 返回结果数。

    Returns:
        包含 status 和 results 的字典。
    """
    manual_files = _get_manual_files()

    if not manual_files:
        return {
            "status": "empty",
            "message": "未找到维修手册文件，请将 .txt/.md 手册放入 backend/data/knowledge/manuals",
            "query": query,
            "results": [],
        }

    # 构建查询文本（合并所有提供的查询信息）
    search_query = query or ""
    if assetnum:
        search_query += f" {assetnum}"
    if subsystem:
        search_query += f" {subsystem}"
    if fault_phenomenon:
        search_query += f" {fault_phenomenon}"

    # 读取所有文件并分词
    all_chunks: list[dict] = []
    for file_path in manual_files:
        content = _read_file_content(file_path)
        chunks = _split_into_chunks(content)
        for chunk in chunks:
            chunk["source"] = file_path.name
            all_chunks.append(chunk)

    if not all_chunks:
        return {
            "status": "empty",
            "message": "手册文件存在但未提取到有效段落",
            "query": query,
            "results": [],
        }

    # 计算评分
    scored = []
    for chunk in all_chunks:
        # 标题和内容分别计算，加权合并
        title_score = _keyword_score(search_query, chunk.get("title", ""))
        content_score = _keyword_score(search_query, chunk.get("content", ""))
        # 综合评分：内容权重更高
        score = title_score * 0.3 + content_score * 0.7
        if score >= MIN_MATCH_SCORE:
            scored.append({
                "content": chunk["content"],
                "title": chunk.get("title", ""),
                "source": chunk.get("source", ""),
                "score": round(min(score, 1.0), 2),
            })

    # 按评分降序排序
    scored.sort(key=lambda x: x["score"], reverse=True)

    # 取 top_k
    results = scored[:top_k]

    if not results:
        return {
            "status": "no_match",
            "message": "未在当前维修手册知识库中找到与问题足够相关的内容，请尝试更具体的故障现象关键词。",
            "query": query,
            "total_documents": len(manual_files),
            "results": [],
        }

    return {
        "status": "success",
        "message": f"检索完成，返回 {len(results)} 条结果",
        "query": query,
        "total_documents": len(manual_files),
        "results": results,
    }
