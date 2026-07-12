"""Prompt-shape regressions for QueryUnderstanding."""
from backend.agent.nodes.understand_query import _build_understand_prompt


def test_understand_prompt_uses_text_examples_and_one_root_object_contract():
    prompt = _build_understand_prompt("当前高风险设备有哪些", {})

    assert "Route 合法值" in prompt
    assert "BusinessGoal 合法值" in prompt
    assert "当前高风险设备有哪些" in prompt
    assert '"route": "business_global"' in prompt
    assert '"business_goal": "high_risk_ranking"' in prompt
    assert "禁止 JSON array" in prompt
    assert "禁止 input/output 包装" in prompt
    assert "禁止 Markdown 代码块" in prompt
    assert "QueryUnderstanding JSON 骨架" in prompt
    assert '[\n  {\n    "输入"' not in prompt
    assert '"input"' not in prompt
    assert '"output"' not in prompt
