"""测试 LLM JSON 结构化输出工具。"""

import pytest

from pydantic import BaseModel, Field

from backend.agent.llm_json import (
    extract_json_from_text,
    parse_json_with_schema,
)


class _TestSchema(BaseModel):
    name: str
    value: int
    tags: list[str] = Field(default_factory=list)


class TestExtractJsonFromText:

    def test_pure_json(self):
        """纯 JSON 文本应能直接解析。"""
        data = extract_json_from_text('{"hello": "world", "num": 42}')
        assert data == {"hello": "world", "num": 42}

    def test_markdown_json_block(self):
        """markdown ```json 代码块应能解析。"""
        text = '这是一些解释文字\n```json\n{"key": "value"}\n```\n后面还有文字'
        data = extract_json_from_text(text)
        assert data == {"key": "value"}

    def test_markdown_code_block_no_lang(self):
        """无语言标注的 markdown 代码块应能解析。"""
        text = '```\n{"a": 1}\n```'
        data = extract_json_from_text(text)
        assert data == {"a": 1}

    def test_text_with_json_in_middle(self):
        """前后有废话的 JSON 应能提取。"""
        text = '我来分析一下，结果是：{"type": "risk", "score": 0.85}，你看这个结果怎么样？'
        data = extract_json_from_text(text)
        assert data == {"type": "risk", "score": 0.85}

    def test_nested_json(self):
        """嵌套 JSON 应能正确处理大括号匹配。"""
        text = '{"outer": {"inner": [1, 2, 3]}, "list": [{"a": 1}, {"b": 2}]}'
        data = extract_json_from_text(text)
        assert data["outer"] == {"inner": [1, 2, 3]}
        assert len(data["list"]) == 2

    def test_empty_text_raises(self):
        """空文本应抛出 ValueError。"""
        with pytest.raises(ValueError):
            extract_json_from_text("")

    def test_text_no_braces_raises(self):
        """没有大括号的文本应抛出 ValueError。"""
        with pytest.raises(ValueError):
            extract_json_from_text("这是纯文本，没有 JSON。")

    def test_multiline_json(self):
        """多行 JSON 应能解析。"""
        text = """```json
{
    "name": "test",
    "items": [
        {"id": 1, "label": "first"},
        {"id": 2, "label": "second"}
    ]
}
```"""
        data = extract_json_from_text(text)
        assert data["name"] == "test"
        assert len(data["items"]) == 2

    def test_first_json_object_wins(self):
        """多个 JSON 对象时，应提取第一个。"""
        text = '{"first": 1} 和 {"second": 2}'
        data = extract_json_from_text(text)
        assert data == {"first": 1}


class TestParseJsonWithSchema:

    def test_valid_data(self):
        """合法数据应成功校验。"""
        result = parse_json_with_schema(
            {"name": "test", "value": 42, "tags": ["a", "b"]},
            _TestSchema,
        )
        assert isinstance(result, _TestSchema)
        assert result.name == "test"
        assert result.value == 42

    def test_missing_required_field_raises(self):
        """缺少必填字段应抛出 ValueError。"""
        with pytest.raises(ValueError, match="Pydantic 校验失败"):
            parse_json_with_schema({"name": "test"}, _TestSchema)

    def test_wrong_type_raises(self):
        """类型错误应抛出 ValueError。"""
        with pytest.raises(ValueError, match="Pydantic 校验失败"):
            parse_json_with_schema({"name": "test", "value": "not_a_number"}, _TestSchema)

    def test_extra_fields_ignored(self):
        """额外字段应被忽略（Pydantic 默认行为）。"""
        result = parse_json_with_schema(
            {"name": "test", "value": 100, "extra_field": "should_be_ignored"},
            _TestSchema,
        )
        assert result.value == 100
