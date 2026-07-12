"""Static compatibility tests for the Streamlit AFC operations UI."""
from pathlib import Path

from frontend.styles import APP_CSS
from frontend.ui_components import BUSINESS_GOAL_LABELS, ROUTE_LABELS, display_label

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "frontend" / "streamlit_app.py").read_text(encoding="utf-8")


def test_route_and_business_goal_display_mapping_has_safe_fallback():
    assert display_label("business_device", ROUTE_LABELS) == "设备业务"
    assert display_label("device_history", BUSINESS_GOAL_LABELS) == "设备历史分析"
    assert display_label("future_route", ROUTE_LABELS) == "future_route"
    assert display_label(None, ROUTE_LABELS) == "尚未识别"


def test_styles_define_responsive_container_and_accessibility_states():
    assert "max-width: 1280px" in APP_CSS
    assert "@media (max-width: 760px)" in APP_CSS
    assert "prefers-reduced-motion" in APP_CSS
    assert "focus-visible" in APP_CSS
    assert "min-height: 44px" in APP_CSS


def test_navigation_pages_and_agent_state_keys_are_preserved():
    for label in ("首页概览", "数据上传", "数据概览", "高风险设备", "设备分析", "Agent 工作台"):
        assert label in APP_SOURCE
    for key in ("agent_session_id", "agent_messages", "agent_last_assetnum", "agent_last_route", "agent_last_business_goal"):
        assert key in APP_SOURCE


def test_frontend_api_paths_remain_compatible():
    for path in ("/upload/workorders", "/data/summary", "/devices/high-risk", "/analysis/", "/agent/diagnose"):
        assert path in APP_SOURCE


def test_frontend_bootstraps_project_root_before_backend_import():
    bootstrap = APP_SOURCE.index("sys.path.insert")
    backend_import = APP_SOURCE.index("from backend.core.config import is_llm_enabled")
    assert bootstrap < backend_import


def test_llm_mode_uses_existing_backend_configuration():
    assert "from backend.core.config import is_llm_enabled" in APP_SOURCE
    assert "AFVC_USE_LLM=true" in (ROOT / "frontend" / "ui_components.py").read_text(encoding="utf-8")


def test_official_streamlit_chat_and_collapsed_debug_are_retained():
    assert "st.chat_message" in APP_SOURCE
    assert 'st.chat_input("请输入设备编号、故障现象或维护问题")' in APP_SOURCE
    assert 'st.expander("调试信息", expanded=False)' in APP_SOURCE
