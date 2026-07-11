"""Streamlit frontend for the AFC Agent demo."""

from __future__ import annotations

import uuid
from typing import Any

import requests
import streamlit as st

API_BASE_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="AFC Agent", page_icon="AFC", layout="wide")


def api_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    try:
        response = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to FastAPI backend.")
    except requests.exceptions.HTTPError:
        st.error(f"API request failed: {response.text}")
    except Exception as exc:
        st.error(f"Request error: {exc}")
    return None


def api_post(path: str, json_data: dict[str, Any] | None = None) -> dict[str, Any] | None:
    try:
        response = requests.post(f"{API_BASE_URL}{path}", json=json_data, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to FastAPI backend.")
    except requests.exceptions.HTTPError:
        st.error(f"API request failed: {response.text}")
    except Exception as exc:
        st.error(f"Request error: {exc}")
    return None


def upload_file(uploaded_file) -> dict[str, Any] | None:
    try:
        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
        response = requests.post(f"{API_BASE_URL}/upload/workorders", files=files, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to FastAPI backend.")
    except requests.exceptions.HTTPError:
        st.error(f"Upload failed: {response.text}")
    except Exception as exc:
        st.error(f"Upload error: {exc}")
    return None


def page_home() -> None:
    st.title("AFC Fault Prediction and Maintenance Agent")
    st.write("Eight-node Agent workflow with route + business_goal semantic routing.")
    st.code(
        '{"route": "business_device", "business_goal": "device_history"}',
        language="json",
    )


def page_upload() -> None:
    st.title("Data Upload")
    uploaded = st.file_uploader("Upload work-order Excel or CSV", type=["xlsx", "xls", "csv"])
    if uploaded and st.button("Upload", type="primary"):
        result = upload_file(uploaded)
        if result:
            st.success("Uploaded.")
            st.json(result)


def page_data_overview() -> None:
    st.title("Data Overview")
    top_n = st.number_input("Top N", min_value=1, max_value=50, value=10)
    if st.button("Refresh", type="primary"):
        result = api_get("/data/summary", params={"top_n": int(top_n)})
        if result:
            st.json(result)


def page_high_risk() -> None:
    st.title("High Risk Devices")
    top_n = st.number_input("Top N", min_value=1, max_value=50, value=10)
    if st.button("Generate", type="primary"):
        result = api_get("/devices/high-risk", params={"top_n": int(top_n)})
        if result:
            devices = result.get("devices") if isinstance(result, dict) else None
            if devices:
                st.dataframe(devices, use_container_width=True)
            st.json(result)


def page_device_analysis() -> None:
    st.title("Device Analysis")
    assetnum = st.text_input("Assetnum", value="1000029970")
    if st.button("Analyze", type="primary") and assetnum.strip():
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
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _new_agent_session() -> None:
    st.session_state["agent_session_id"] = str(uuid.uuid4())
    st.session_state["agent_messages"] = []
    st.session_state["agent_last_assetnum"] = None
    st.session_state["agent_last_route"] = None
    st.session_state["agent_last_business_goal"] = None


def _agent_diagnose(question: str) -> dict[str, Any] | None:
    return api_post(
        "/agent/diagnose",
        {
            "query": question,
            "session_id": st.session_state["agent_session_id"],
        },
    )


def _handle_agent_query(question: str) -> None:
    st.session_state["agent_messages"].append(
        {"role": "user", "content": question, "meta": None}
    )
    with st.spinner("Agent is diagnosing..."):
        result = _agent_diagnose(question)

    if not result:
        st.session_state["agent_messages"].append(
            {"role": "assistant", "content": "Backend unavailable.", "meta": None}
        )
        return

    if result.get("status") == "success":
        st.session_state["agent_last_assetnum"] = result.get("last_assetnum") or result.get("assetnum")
        st.session_state["agent_last_route"] = result.get("last_route") or result.get("route")
        st.session_state["agent_last_business_goal"] = (
            result.get("last_business_goal") or result.get("business_goal")
        )

    st.session_state["agent_messages"].append(
        {
            "role": "assistant",
            "content": result.get("final_answer") or "No answer generated.",
            "meta": {
                "assetnum": result.get("assetnum"),
                "route": result.get("route"),
                "business_goal": result.get("business_goal"),
                "time_window": result.get("time_window"),
                "selected_tools": result.get("selected_tools", []),
                "tool_trace": result.get("tool_trace", []),
                "query_understanding": result.get("query_understanding", {}),
                "tool_plan": result.get("tool_plan", {}),
                "evidence_packet": result.get("evidence_packet", {}),
                "evidence_evaluation": result.get("evidence_evaluation", {}),
                "errors": result.get("errors", []),
                "session_id": result.get("session_id"),
                "last_assetnum": result.get("last_assetnum"),
                "last_route": result.get("last_route"),
                "last_business_goal": result.get("last_business_goal"),
            },
        }
    )


def _render_agent_meta(meta: dict[str, Any]) -> None:
    selected_tools = meta.get("selected_tools", [])
    if selected_tools:
        st.caption(" | ".join(f"`{name}`" for name in selected_tools))
    for error in meta.get("errors", []):
        st.warning(error)
    with st.expander("Debug", expanded=False):
        st.text(
            "\n".join(
                [
                    f"Assetnum: {meta.get('assetnum') or 'None'}",
                    f"Route: {meta.get('route') or 'None'}",
                    f"Business Goal: {meta.get('business_goal') or 'None'}",
                    f"Time Window: {meta.get('time_window') or 'None'}",
                    f"Session ID: {meta.get('session_id') or 'None'}",
                    f"Last Assetnum: {meta.get('last_assetnum') or 'None'}",
                    f"Last Route: {meta.get('last_route') or 'None'}",
                    f"Last Business Goal: {meta.get('last_business_goal') or 'None'}",
                ]
            )
        )
        for label in (
            "query_understanding",
            "tool_plan",
            "evidence_packet",
            "evidence_evaluation",
            "tool_trace",
        ):
            value = meta.get(label)
            if value:
                st.markdown(f"**{label}**")
                st.json(value)


def page_agent() -> None:
    _init_agent_session()
    session_id = st.session_state["agent_session_id"]

    st.title("AFC Agent Workstation")
    col_status, col_button = st.columns([4, 1])
    with col_status:
        st.markdown(
            " | ".join(
                [
                    f"Assetnum: **{st.session_state.get('agent_last_assetnum') or 'None'}**",
                    f"Route: **{st.session_state.get('agent_last_route') or 'None'}**",
                    f"Business Goal: **{st.session_state.get('agent_last_business_goal') or 'None'}**",
                    f"Session: `{session_id[:8]}...`",
                ]
            )
        )
    with col_button:
        if st.button("New Session", use_container_width=True):
            _new_agent_session()
            st.rerun()

    quick_questions = [
        "\u5e2e\u6211\u5206\u6790\u8bbe\u5907 1000029970",
        "\u8bbe\u5907 1000029970 \u672a\u676530\u5929\u98ce\u9669\u9ad8\u5417",
        "\u8bbe\u5907 1000029970 \u6700\u8fd1\u6709\u54ea\u4e9b\u6545\u969c",
        "\u8bbe\u5907 1000029970 \u5e94\u8be5\u5148\u68c0\u67e5\u4ec0\u4e48",
        "\u5f53\u524d\u9ad8\u98ce\u9669\u8bbe\u5907\u6709\u54ea\u4e9b",
        "\u90a3\u5b83\u6700\u8fd1\u6709\u54ea\u4e9b\u6545\u969c",
    ]
    with st.expander("Quick Questions", expanded=False):
        cols = st.columns(3)
        for index, question in enumerate(quick_questions):
            with cols[index % 3]:
                if st.button(question, key=f"quick_{index}", use_container_width=True):
                    _handle_agent_query(question)
                    st.rerun()

    for message in st.session_state.get("agent_messages", []):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant" and message.get("meta"):
                _render_agent_meta(message["meta"])

    prompt = st.chat_input("Ask an AFC maintenance question")
    if prompt:
        _handle_agent_query(prompt)
        st.rerun()


def main() -> None:
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Page",
        [
            "Home",
            "Data Upload",
            "Data Overview",
            "High Risk Devices",
            "Device Analysis",
            "Agent Workstation",
        ],
    )
    if page == "Home":
        page_home()
    elif page == "Data Upload":
        page_upload()
    elif page == "Data Overview":
        page_data_overview()
    elif page == "High Risk Devices":
        page_high_risk()
    elif page == "Device Analysis":
        page_device_analysis()
    else:
        page_agent()


if __name__ == "__main__":
    main()
