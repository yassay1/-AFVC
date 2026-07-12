"""Loading-state lifecycle tests for Streamlit Agent submissions."""
from frontend import streamlit_app


class _Placeholder:
    def __init__(self):
        self.contents = []
        self.empty_calls = 0

    def markdown(self, text):
        self.contents.append(text)

    def empty(self):
        self.empty_calls += 1


class _FakeStreamlit:
    def __init__(self, processing=False):
        self.session_state = {
            "agent_session_id": "session-test",
            "agent_messages": [],
            "agent_last_assetnum": None,
            "agent_last_route": None,
            "agent_last_business_goal": None,
            "agent_is_processing": processing,
        }
        self.placeholders = []

    def empty(self):
        placeholder = _Placeholder()
        self.placeholders.append(placeholder)
        return placeholder


def _success_result(**overrides):
    result = {
        "status": "success",
        "final_answer": "分析完成",
        "assetnum": "1000029970",
        "route": "business_device",
        "business_goal": "device_risk",
        "errors": [],
    }
    result.update(overrides)
    return result


def _assert_cleaned(fake_st):
    assert fake_st.session_state["agent_is_processing"] is False
    assert len(fake_st.placeholders) == 1
    assert fake_st.placeholders[0].empty_calls == 1
    assert fake_st.placeholders[0].contents == ["AFC Agent 正在分析问题并整理证据……"]
    assert all(
        "正在分析问题并整理证据" not in message.get("content", "")
        for message in fake_st.session_state["agent_messages"]
    )


def test_success_and_rule_or_template_fallback_responses_clear_loading(monkeypatch):
    for result in (
        _success_result(),
        _success_result(errors=["LLM 问题理解不可用，使用规则兜底"]),
        _success_result(errors=["LLM 报告生成失败，使用模板兜底"]),
    ):
        fake_st = _FakeStreamlit()
        monkeypatch.setattr(streamlit_app, "st", fake_st)
        monkeypatch.setattr(streamlit_app, "_agent_diagnose", lambda question, value=result: value)

        assert streamlit_app._handle_agent_query("测试问题") is True
        _assert_cleaned(fake_st)
        assert fake_st.session_state["agent_messages"][-1]["content"] == "分析完成"


def test_empty_or_timeout_result_clears_loading(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(streamlit_app, "_agent_diagnose", lambda question: None)

    assert streamlit_app._handle_agent_query("测试问题") is True
    _assert_cleaned(fake_st)
    assert "后端服务暂不可用" in fake_st.session_state["agent_messages"][-1]["content"]


def test_agent_exception_clears_loading_and_saves_recoverable_error(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_st)

    def fail(_question):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(streamlit_app, "_agent_diagnose", fail)
    assert streamlit_app._handle_agent_query("测试问题") is True
    _assert_cleaned(fake_st)
    assert "simulated failure" in fake_st.session_state["agent_messages"][-1]["content"]


def test_duplicate_submission_is_ignored_without_extra_placeholder(monkeypatch):
    fake_st = _FakeStreamlit(processing=True)
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    called = False

    def diagnose(_question):
        nonlocal called
        called = True

    monkeypatch.setattr(streamlit_app, "_agent_diagnose", diagnose)
    assert streamlit_app._handle_agent_query("重复问题") is False
    assert called is False
    assert fake_st.placeholders == []
    assert fake_st.session_state["agent_messages"] == []


def test_refresh_clears_stale_processing_flag(monkeypatch):
    fake_st = _FakeStreamlit(processing=True)
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    streamlit_app._clear_stale_agent_processing()
    assert fake_st.session_state["agent_is_processing"] is False
