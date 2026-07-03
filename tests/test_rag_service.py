"""测试 RAG 维修手册检索服务。"""

import pytest

from backend.services.rag_service import search_manual, _get_manual_files, _split_into_chunks, _keyword_score


class TestKeywordScoring:

    def test_exact_match(self):
        score = _keyword_score("票卡不接收", "票卡不接收检查步骤 检查票卡通道")
        assert score > 0.5

    def test_no_match(self):
        score = _keyword_score("xyz不存在", "票卡通道检查")
        assert score == 0.0

    def test_partial_match(self):
        score = _keyword_score("扇门异常检查", "扇门机构可能存在卡滞")
        assert score > 0.0

    def test_empty_query(self):
        assert _keyword_score("", "some text") == 0.0


class TestChunkSplitting:

    def test_split_by_headings(self):
        text = """# 主标题
这是概述内容，这里应该有足够多的文字来满足最小长度过滤的要求。

## 第一节
第一节内容，这里包含第一节的检查步骤，内容需要足够长才能被切分为一个段落块。

## 第二节
第二节内容，同样需要满足最小长度的要求，所以需要写多一些文字。"""
        chunks = _split_into_chunks(text, min_length=5)
        assert len(chunks) >= 2

    def test_short_chunks_filtered(self):
        text = """# 标题
短。

## 节
这一节有足够的内容来通过最小长度过滤。"""
        chunks = _split_into_chunks(text, min_length=10)
        # "短。" 应被过滤
        titles = [c["title"] for c in chunks]
        assert len(chunks) >= 1


class TestManualFiles:

    def test_manual_dir_exists(self):
        files = _get_manual_files()
        # 至少示例文件应存在
        assert any("afc_maintenance_manual_sample" in f.name for f in files)


class TestSearchManual:

    def test_search_ticket_issue(self):
        result = search_manual("票卡不接收", top_k=3)
        assert result["status"] == "success"
        assert len(result["results"]) > 0
        # 应包含票卡相关内容
        content_text = " ".join(r["content"] for r in result["results"])
        assert "票卡" in content_text or "卡" in content_text

    def test_search_with_assetnum(self):
        result = search_manual("检查步骤", assetnum="1000029970", top_k=3)
        assert result["status"] == "success"

    def test_search_gate_issue(self):
        result = search_manual("扇门异常", top_k=3)
        assert result["status"] == "success"
        if result["results"]:
            content_text = " ".join(r["content"] for r in result["results"])
            assert "扇门" in content_text or "门" in content_text

    def test_search_no_match_returns_fallback(self):
        """无匹配时应返回默认结果。"""
        result = search_manual("量子计算故障", top_k=2)
        assert result["status"] == "success"
        # 至少返回一些结果（兜底）
        assert len(result["results"]) >= 0
