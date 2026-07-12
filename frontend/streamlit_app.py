"""Streamlit frontend for the AFC fault prediction and maintenance platform."""
from __future__ import annotations

import uuid
import sys
from pathlib import Path
from typing import Any

import requests
import streamlit as st

# Streamlit may execute this file with ``frontend`` as the import root. Ensure
# project packages remain importable regardless of the caller's working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.config import is_llm_enabled
from frontend.styles import inject_app_styles
from frontend.ui_components import (
    BUSINESS_GOAL_LABELS,
    ROUTE_LABELS,
    display_label,
    render_mode_card,
    render_page_header,
    render_route_panel,
    render_sidebar_brand,
)

API_BASE_URL = "http://127.0.0.1:8000"
NAVIGATION = {
    "首页概览": "home",
    "数据上传": "upload",
    "数据概览": "overview",
    "高风险设备": "high_risk",
    "设备分析": "device_analysis",
    "Agent 工作台": "agent",
}

st.set_page_config(
    page_title="AFC 智能运维",
    page_icon="AFC",
    layout="wide",
    initial_sidebar_state="expanded",
)


def api_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    try:
        response = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("无法连接 FastAPI 后端，请确认服务已启动。")
    except requests.exceptions.HTTPError:
        st.error(f"API 请求失败：{response.text}")
    except Exception as exc:
        st.error(f"请求异常：{exc}")
    return None


def api_post(path: str, json_data: dict[str, Any] | None = None) -> dict[str, Any] | None:
    try:
        response = requests.post(f"{API_BASE_URL}{path}", json=json_data, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("无法连接 FastAPI 后端，请确认服务已启动。")
    except requests.exceptions.HTTPError:
        st.error(f"API 请求失败：{response.text}")
    except Exception as exc:
        st.error(f"请求异常：{exc}")
    return None


def upload_file(uploaded_file) -> dict[str, Any] | None:
    try:
        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
        response = requests.post(f"{API_BASE_URL}/upload/workorders", files=files, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("无法连接 FastAPI 后端，请确认服务已启动。")
    except requests.exceptions.HTTPError:
        st.error(f"上传失败：{response.text}")
    except Exception as exc:
        st.error(f"上传异常：{exc}")
    return None


def _header(title: str, english: str, description: str, scene: str | None = None) -> None:
    render_page_header(
        st,
        title=title,
        english_title=english,
        description=description,
        llm_enabled=is_llm_enabled(),
        scene=scene,
    )


def page_home() -> None:
    _header(
        "AFC 故障预测与维护系统",
        "AFC Fault Prediction & Maintenance Agent",
        "面向 AFC 设备的故障预测、风险分析与智能维护决策平台",
        "系统概览",
    )
    render_mode_card(st, is_llm_enabled())
    st.markdown('<div class="afc-section-label">业务能力</div>', unsafe_allow_html=True)
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.info("**风险分析**\n\n评估设备在多个时间窗口内再次产生故障工单的可能性。")
    with col_b:
        st.info("**维护决策**\n\n结合历史工单与维护规则，提供可执行的巡检方向。")
    with col_c:
        st.info("**Agent 协同**\n\n通过八节点工作流完成理解、规划、取证、评估与回答。")
    st.markdown('<div class="afc-section-label">路由示例</div>', unsafe_allow_html=True)
    render_route_panel(st, "business_device", "device_history", "1000029970")
    st.caption("示例仅用于说明路由字段的友好展示；实际工作台状态来自 Agent 接口响应。")


def page_upload() -> None:
    _header("数据上传", "Work-order Data Upload", "上传 AFC 工单 Excel 或 CSV 文件，供后续统计和分析使用。", "数据接入")
    uploaded = st.file_uploader("选择工单文件", type=["xlsx", "xls", "csv"], help="支持 xlsx、xls 和 csv 格式。")
    if uploaded and st.button("上传并处理", type="primary"):
        result = upload_file(uploaded)
        if result:
            st.success("文件上传成功。")
            with st.expander("查看上传响应", expanded=False):
                st.json(result)


def page_data_overview() -> None:
    _header("数据概览", "Work-order Data Overview", "查看当前工单数据的规模、分布和高频故障摘要。", "全局数据分析")
    top_n = st.number_input("统计条数 Top N", min_value=1, max_value=50, value=10)
    if st.button("刷新数据概览", type="primary"):
        result = api_get("/data/summary", params={"top_n": int(top_n)})
        if result:
            st.json(result)


def page_high_risk() -> None:
    _header("高风险设备", "High-risk Device Prioritization", "按预测风险识别需要优先关注的 AFC 设备。", "风险排序")
    top_n = st.number_input("设备数量 Top N", min_value=1, max_value=50, value=10)
    if st.button("生成风险列表", type="primary"):
        result = api_get("/devices/high-risk", params={"top_n": int(top_n)})
        if result:
            devices = result.get("devices") if isinstance(result, dict) else None
            if devices:
                st.dataframe(devices, use_container_width=True, hide_index=True)
            with st.expander("查看原始响应", expanded=False):
                st.json(result)


def page_device_analysis() -> None:
    _header("设备分析", "Device Analysis", "查询单台设备的历史、风险、预警与维护建议。", "单设备诊断")
    assetnum = st.text_input("设备编号", value="1000029970", help="例如：1000029970 或 EX011115。")
    if st.button("开始分析", type="primary") and assetnum.strip():
        result = api_get(f"/analysis/{assetnum.strip()}")
        if result:
            st.json(result)


def _init_agent_session() -> None:
    defaults = {
        "agent_session_id": str(uuid.uuid4()),
        "agent_messages": [],
        "agent_last_assetnum": None,
        "agent_last_route": None,
        "agent_last_business_goal": None,
        "agent_is_processing": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _new_agent_session() -> None:
    st.session_state["agent_session_id"] = str(uuid.uuid4())
    st.session_state["agent_messages"] = []
    st.session_state["agent_last_assetnum"] = None
    st.session_state["agent_last_route"] = None
    st.session_state["agent_last_business_goal"] = None
    st.session_state["agent_is_processing"] = False


def _clear_stale_agent_processing() -> None:
    """Clear a transient flag left by a browser refresh or interrupted run."""
    if st.session_state.get("agent_is_processing", False):
        st.session_state["agent_is_processing"] = False


def _agent_diagnose(question: str) -> dict[str, Any] | None:
    return api_post(
        "/agent/diagnose",
        {"query": question, "session_id": st.session_state["agent_session_id"]},
    )


def _handle_agent_query(question: str) -> bool:
    """Execute one Agent request and always clear its transient loading state."""
    if st.session_state.get("agent_is_processing", False):
        return False

    st.session_state["agent_is_processing"] = True
    thinking_placeholder = st.empty()
    st.session_state["agent_messages"].append({"role": "user", "content": question, "meta": None})

    try:
        thinking_placeholder.markdown("AFC Agent 正在分析问题并整理证据……")
        result = _agent_diagnose(question)

        if not result:
            st.session_state["agent_messages"].append(
                {"role": "assistant", "content": "后端服务暂不可用，请确认 FastAPI 服务已启动后重试。", "meta": None}
            )
            return True

        if result.get("status") == "success":
            st.session_state["agent_last_assetnum"] = result.get("last_assetnum") or result.get("assetnum")
            st.session_state["agent_last_route"] = result.get("last_route") or result.get("route")
            st.session_state["agent_last_business_goal"] = result.get("last_business_goal") or result.get("business_goal")

        st.session_state["agent_messages"].append(
            {
                "role": "assistant",
                "content": result.get("final_answer") or "本次未生成有效回答。",
                "meta": {
                    "assetnum": result.get("assetnum"),
                    "route": result.get("route"),
                    "business_goal": result.get("business_goal"),
                    "answer_mode": result.get("answer_mode"),
                    "time_window": result.get("time_window"),
                    "selected_tools": result.get("selected_tools", []),
                    "tool_trace": result.get("tool_trace", []),
                    "query_understanding": result.get("query_understanding", {}),
                    "tool_plan": result.get("tool_plan", {}),
                    "evidence_packet": result.get("evidence_packet", {}),
                    "evidence_evaluation": result.get("evidence_evaluation", {}),
                    "generated_answer": result.get("generated_answer", {}),
                    "errors": result.get("errors", []),
                    "session_id": result.get("session_id"),
                    "last_assetnum": result.get("last_assetnum"),
                    "last_route": result.get("last_route"),
                    "last_business_goal": result.get("last_business_goal"),
                    "raw_response": result,
                },
            }
        )
        return True
    except Exception as exc:
        st.session_state["agent_messages"].append(
            {
                "role": "assistant",
                "content": f"Agent 调用异常：{exc}。请稍后重试。",
                "meta": None,
            }
        )
        return True
    finally:
        st.session_state["agent_is_processing"] = False
        thinking_placeholder.empty()


def _render_message_meta(meta: dict[str, Any]) -> None:
    selected_tools = meta.get("selected_tools", [])
    if selected_tools:
        st.caption("证据工具：" + " · ".join(str(name) for name in selected_tools))
    for error in meta.get("errors", []):
        st.warning(str(error))


def _latest_agent_meta() -> dict[str, Any] | None:
    for message in reversed(st.session_state.get("agent_messages", [])):
        if message.get("role") == "assistant" and message.get("meta"):
            return message["meta"]
    return None


def _render_agent_debug(meta: dict[str, Any] | None) -> None:
    with st.expander("调试信息", expanded=False):
        st.caption("仅用于开发和问题排查，默认不展示内部工作流数据。")
        if not meta:
            st.write("当前会话尚无 Agent 响应。")
            return
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("Route", meta.get("route") or "None")
        col_b.metric("Business Goal", meta.get("business_goal") or "None")
        col_c.metric("Answer Mode", meta.get("answer_mode") or "None")
        col_d.metric("Session", str(meta.get("session_id") or "None")[:12])
        for label in (
            "query_understanding",
            "tool_plan",
            "evidence_packet",
            "evidence_evaluation",
            "generated_answer",
            "tool_trace",
            "raw_response",
        ):
            value = meta.get(label)
            if value:
                st.markdown(f"**{label}**")
                st.json(value)


def page_agent() -> None:
    _init_agent_session()
    # A browser refresh or an interrupted previous run must not resurrect a
    # transient loading indicator. Requests are synchronous within one run.
    _clear_stale_agent_processing()
    route = st.session_state.get("agent_last_route")
    goal = st.session_state.get("agent_last_business_goal")
    scene = display_label(goal, BUSINESS_GOAL_LABELS, "Agent 对话")
    _header("Agent 工作台", "AFC Intelligent Operations Assistant", "通过自然语言查询设备风险、历史工单、维护建议和综合诊断。", scene)

    col_status, col_button = st.columns([5, 1])
    with col_status:
        render_route_panel(st, route, goal, st.session_state.get("agent_last_assetnum"))
    with col_button:
        st.write("")
        if st.button("新建会话", use_container_width=True):
            _new_agent_session()
            st.rerun()

    render_mode_card(st, is_llm_enabled())

    quick_questions = [
        "帮我分析设备 1000029970",
        "设备 1000029970 未来30天风险高吗",
        "设备 1000029970 最近有哪些故障",
        "设备 1000029970 应该先检查什么",
        "当前高风险设备有哪些",
        "那它最近有哪些故障",
    ]
    with st.expander("常用问题", expanded=False):
        cols = st.columns(3)
        for index, question in enumerate(quick_questions):
            with cols[index % 3]:
                if st.button(question, key=f"quick_{index}", use_container_width=True):
                    if _handle_agent_query(question):
                        st.rerun()

    st.markdown('<div class="afc-section-label">对话记录</div>', unsafe_allow_html=True)
    messages = st.session_state.get("agent_messages", [])
    if not messages:
        st.info("尚无对话。你可以输入设备编号、故障现象或维护问题开始分析。")
    for message in messages:
        role = message.get("role", "assistant")
        with st.chat_message(role):
            if role == "assistant":
                st.caption("AFC 智能运维助手")
            st.markdown(message.get("content") or "（空消息）")
            if role == "assistant" and message.get("meta"):
                _render_message_meta(message["meta"])

    prompt = st.chat_input("请输入设备编号、故障现象或维护问题")
    if prompt and not st.session_state.get("agent_is_processing", False):
        if _handle_agent_query(prompt):
            st.rerun()

    st.markdown('<div class="afc-section-label">辅助信息</div>', unsafe_allow_html=True)
    _render_agent_debug(_latest_agent_meta())


def main() -> None:
    inject_app_styles(st)
    with st.sidebar:
        render_sidebar_brand(st)
        selected = st.radio("主导航", list(NAVIGATION), label_visibility="collapsed")
        st.caption("AFC Fault Prediction & Maintenance")

    page = NAVIGATION[selected]
    if page == "home":
        page_home()
    elif page == "upload":
        page_upload()
    elif page == "overview":
        page_data_overview()
    elif page == "high_risk":
        page_high_risk()
    elif page == "device_analysis":
        page_device_analysis()
    else:
        page_agent()


if __name__ == "__main__":
    main()
