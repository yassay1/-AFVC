"""AFC 故障复发风险预测与智能维修建议系统 —— Streamlit 前端。

启动方式：
    streamlit run frontend/streamlit_app.py
"""

import uuid
import requests
import streamlit as st


API_BASE_URL = "http://127.0.0.1:8000"


st.set_page_config(
    page_title="AFC 故障复发风险预测与智能维修建议系统",
    page_icon="🚇",
    layout="wide",
)


# ── API 工具函数 ──────────────────────────────────────────────

def api_post(path: str, json_data: dict | None = None) -> dict | None:
    """统一封装 POST 请求。"""
    try:
        response = requests.post(f"{API_BASE_URL}{path}", json=json_data, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("无法连接 FastAPI 后端，请先启动后端服务。")
        st.code("python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000")
        return None
    except requests.exceptions.HTTPError:
        try:
            error_detail = response.json()
        except Exception:
            error_detail = response.text
        st.error(f"接口请求失败：{error_detail}")
        return None
    except Exception as e:
        st.error(f"请求异常：{e}")
        return None


def agent_diagnose(query: str, session_id: str | None = None) -> dict | None:
    """调用 Agent 诊断 API，自动附带 session_id。"""
    json_data: dict = {"query": query}
    if session_id:
        json_data["session_id"] = session_id
    return api_post("/agent/diagnose", json_data=json_data)


def api_get(path: str, params: dict | None = None) -> dict | None:
    """统一封装 GET 请求。"""
    try:
        response = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("无法连接 FastAPI 后端，请先启动后端服务。")
        st.code("python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000")
        return None
    except requests.exceptions.HTTPError:
        try:
            error_detail = response.json()
        except Exception:
            error_detail = response.text
        st.error(f"接口请求失败：{error_detail}")
        return None
    except Exception as e:
        st.error(f"请求异常：{e}")
        return None


def upload_file_to_backend(uploaded_file) -> dict | None:
    """上传 Excel / CSV 文件到 FastAPI 后端。"""
    try:
        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
        response = requests.post(f"{API_BASE_URL}/upload/workorders", files=files, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("无法连接 FastAPI 后端，请先启动后端服务。")
        return None
    except requests.exceptions.HTTPError:
        try:
            error_detail = response.json()
        except Exception:
            error_detail = response.text
        st.error(f"文件上传失败：{error_detail}")
        return None
    except Exception as e:
        st.error(f"上传异常：{e}")
        return None


# ── 侧边栏：后端状态 ──────────────────────────────────────────

def show_backend_status():
    result = api_get("/health")
    if result and result.get("status") == "ok":
        st.sidebar.success("后端连接正常")
    else:
        st.sidebar.error("后端未连接")


# ── 页面 1：首页 ──────────────────────────────────────────────

def page_home():
    st.title("🚇 AFC 故障复发风险预测与智能维修建议系统")

    st.markdown("""
    本系统面向地铁 AFC 闸机维修工单数据，基于 **LangGraph + LangChain Tools** 架构：

    1. 工单数据上传与读取
    2. 数据概览统计
    3. 设备历史工单查询
    4. 高风险设备 Top N 展示
    5. 单设备多时间窗口风险预测
    6. 维修建议生成
    7. **Agent 智能诊断工作台**（LangGraph 编排 + LLM + 工具调用）

    ---
    """)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("系统定位", "工单驱动风险预警")
    with col2:
        st.metric("Agent 架构", "LangGraph + Tools")
    with col3:
        st.metric("当前阶段", "MVP 演示版 v0.2")

    st.subheader("系统流程")
    steps = st.columns(5)
    flow_steps = [
        ("📤", "上传工单", "Excel/CSV"),
        ("📊", "数据解析", "Polars 引擎"),
        ("🔧", "业务服务", "预测/预警/建议"),
        ("🧠", "Agent 编排", "LangGraph 6节点"),
        ("📋", "诊断报告", "工作台展示"),
    ]
    for i, (icon, title, desc) in enumerate(flow_steps):
        with steps[i]:
            st.markdown(f"<div style='text-align:center;padding:12px 4px;border-radius:8px;"
                        f"background:{'#DBEAFE' if i%2==0 else '#F1F5FD'};"
                        f"border:1px solid #BFDBFE;'>"
                        f"<span style='font-size:28px;'>{icon}</span><br>"
                        f"<b>{title}</b><br><small>{desc}</small></div>",
                        unsafe_allow_html=True)

    st.warning(
        "科学边界说明：本系统预测的是未来若干时间窗口内再次产生故障工单的风险，"
        "不等同于精确预测真实物理故障发生日期；维修建议基于工单现象生成，"
        "只作为巡检方向参考。"
    )


# ── 页面 2：数据上传 ──────────────────────────────────────────

def page_upload():
    st.title("📤 数据上传")
    st.markdown("上传 AFC 维修工单文件。支持格式：`.xlsx`、`.xls`、`.csv`")

    uploaded_file = st.file_uploader("请选择 AFC 工单文件", type=["xlsx", "xls", "csv"])

    if uploaded_file is not None:
        st.info(f"已选择文件：{uploaded_file.name}")
        if st.button("上传到后端", type="primary"):
            result = upload_file_to_backend(uploaded_file)
            if result:
                st.success("文件上传成功")
                st.json(result)


# ── 页面 3：数据概览 ──────────────────────────────────────────

def page_data_summary():
    st.title("📊 数据概览")

    top_n = st.slider("Top N 统计数量", min_value=5, max_value=30, value=10, step=5)

    if st.button("刷新数据概览", type="primary"):
        st.session_state["summary_data"] = api_get("/data/summary", params={"top_n": top_n})

    summary = st.session_state.get("summary_data")
    if not summary:
        st.info("点击 [刷新数据概览] 获取最新统计结果。")
        return

    basic = summary.get("basic_metrics", {})

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("工单总数", basic.get("workorder_count", "-"))
    with col2:
        st.metric("设备数量", basic.get("device_count", "-"))
    with col3:
        st.metric("车站数量", basic.get("station_count", "-"))
    with col4:
        st.metric("线路数量", basic.get("line_count", "-"))
    with col5:
        st.metric("品牌数量", basic.get("brand_count", "-"))

    st.subheader("工单记录时间范围")
    st.json(summary.get("time_range", {}))

    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("品牌分布")
        st.dataframe(summary.get("brand_distribution", []), use_container_width=True)
        st.subheader("线路分布")
        st.dataframe(summary.get("line_distribution", []), use_container_width=True)
    with col_right:
        st.subheader("故障描述 Top N")
        st.dataframe(summary.get("fault_description_top", []), use_container_width=True)
        st.subheader("工单类型分布")
        st.dataframe(summary.get("worktype_distribution", []), use_container_width=True)

    st.subheader("字段解释")
    st.json(summary.get("field_note", {}))


# ── 页面 4：高风险设备 ────────────────────────────────────────

def page_high_risk():
    st.title("🚨 高风险设备 Top N")

    top_n = st.slider("选择展示的高风险设备数量", min_value=5, max_value=50, value=10, step=5)

    if st.button("生成高风险设备清单", type="primary"):
        st.session_state["high_risk_data"] = api_get("/devices/high-risk", params={"top_n": top_n})

    data = st.session_state.get("high_risk_data")
    if not data:
        st.info("点击 [生成高风险设备清单] 查看模拟高风险设备。")
        return

    st.warning(data.get("model_note", "当前为模拟预测结果。"))
    devices = data.get("devices", [])
    if not devices:
        st.info("暂无高风险设备数据。")
        return

    st.subheader("高风险设备列表")

    for dev in devices:
        level_color = {
            "红色预警": ("#DC2626", "#FEE2E2"),
            "橙色预警": ("#EA580C", "#FFF7ED"),
            "黄色预警": ("#CA8A04", "#FEFCE8"),
            "绿色关注": ("#16A34A", "#F0FDF4"),
        }
        wl = dev.get("warning_level", "绿色关注")
        color, bg = level_color.get(wl, ("#64748B", "#F8FAFC"))

        col1, col2, col3 = st.columns([2, 3, 1])
        with col1:
            st.markdown(f"**{dev.get('assetnum', '-')}**  \n"
                        f"{dev.get('station_name', '-')} · {dev.get('line', '-')}")
        with col2:
            r90 = dev.get("risk_90d", 0)
            st.progress(min(float(r90), 1.0), text=f"90天风险 {r90}")
        with col3:
            st.markdown(f"<span style='padding:4px 12px;border-radius:12px;font-size:13px;"
                        f"background:{bg};color:{color};font-weight:600;'>{wl}</span>",
                        unsafe_allow_html=True)

    st.divider()

    st.subheader("说明")
    st.markdown("""
    当前高风险排序基于第一版 mock 预测服务生成。
    后续队友真实模型完成后，可以替换 `prediction_service.py` 内部逻辑，前端页面基本不需要改动。
    """)


# ── 页面 5：单设备分析 ────────────────────────────────────────

def get_device_options() -> list[str]:
    result = api_get("/devices")
    if not result:
        return []
    devices = result.get("devices", [])
    return [device.get("assetnum") for device in devices if device.get("assetnum")]


def page_single_device():
    st.title("🔍 单设备综合分析")

    st.markdown("""
    本页面用于围绕单台 AFC 设备形成完整分析结果：
    - 设备基础信息
    - 历史工单摘要
    - 高频故障现象
    - 多时间窗口风险预测
    - 预警等级
    - 维修建议
    """)

    if st.button("加载设备列表"):
        st.session_state["device_options"] = get_device_options()

    device_options = st.session_state.get("device_options", [])

    if not device_options:
        st.info("请先点击 [加载设备列表]。")
        assetnum = st.text_input("也可以手动输入设备编号")
    else:
        assetnum = st.selectbox("请选择设备编号", options=device_options)

    history_limit = st.slider("历史工单分析数量", min_value=10, max_value=200, value=50, step=10)

    if not assetnum:
        st.warning("请先选择或输入设备编号。")
        return

    if st.button("生成单设备综合分析", type="primary"):
        result = api_get(f"/analysis/{assetnum}", params={"history_limit": history_limit})
        st.session_state["analysis_result"] = result

    analysis = st.session_state.get("analysis_result")
    if not analysis:
        st.info("点击 [生成单设备综合分析] 后查看结果。")
        return

    if analysis.get("status") != "success":
        st.error(analysis)
        return

    st.divider()

    profile = analysis.get("device_profile", {})
    history_summary = analysis.get("history_summary", {})
    risk = analysis.get("risk_prediction", {})
    advice = analysis.get("maintenance_advice", {})

    st.subheader("一、设备基础信息")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("设备编号", profile.get("assetnum", "-"))
    with col2:
        st.metric("车站", profile.get("station_name", "-"))
    with col3:
        st.metric("线路", profile.get("line", "-"))
    with col4:
        st.metric("品牌", profile.get("brand", "-"))
    with col5:
        st.metric("历史工单数", profile.get("history_workorder_count", "-"))
    st.caption(f"最近工单记录时间：{profile.get('last_record_time', '-')}")

    st.subheader("二、历史工单摘要")
    col_left, col_right = st.columns(2)
    with col_left:
        st.write("最近故障描述：")
        recent = history_summary.get("recent_descriptions", [])
        if recent:
            for item in recent:
                st.write(f"- {item}")
        else:
            st.info("暂无最近故障描述。")
    with col_right:
        st.write("高频故障描述：")
        top_faults = history_summary.get("top_fault_descriptions", [])
        if top_faults:
            st.dataframe(top_faults, use_container_width=True)
        else:
            st.info("暂无高频故障描述。")

    st.subheader("三、多时间窗口风险预测")
    risk_levels = [
        ("7天", risk.get("risk_7d", 0)), ("14天", risk.get("risk_14d", 0)),
        ("21天", risk.get("risk_21d", 0)), ("30天", risk.get("risk_30d", 0)),
        ("60天", risk.get("risk_60d", 0)), ("90天", risk.get("risk_90d", 0)),
    ]
    for label, val in risk_levels:
        v = float(val) if val else 0
        bar_color = "normal" if v < 0.35 else ("normal" if v < 0.55 else "orange" if v < 0.75 else "red")
        # Streamlit progress bar doesn't support color, use the bar with label
        st.progress(min(v, 1.0), text=f"{label}风险：{v}")

    warning_level = risk.get("warning_level", "-")
    wl_colors = {
        "红色预警": ("#DC2626", "#FEE2E2"), "橙色预警": ("#EA580C", "#FFF7ED"),
        "黄色预警": ("#CA8A04", "#FEFCE8"), "绿色关注": ("#16A34A", "#F0FDF4"),
    }
    wl_color, wl_bg = wl_colors.get(warning_level, ("#64748B", "#F8FAFC"))
    st.markdown(f"<div style='padding:12px 16px;border-radius:8px;background:{wl_bg};"
                f"border-left:4px solid {wl_color};margin:8px 0;'>"
                f"<b style='color:{wl_color};'>预警等级：{warning_level}</b>　|　"
                f"建议巡检窗口：{risk.get('suggested_inspection_window', '-')}</div>",
                unsafe_allow_html=True)

    st.write("主要风险因素：")
    for factor in risk.get("main_risk_factors", []):
        st.write(f"- {factor}")

    with st.expander("查看特征快照"):
        st.json(risk.get("feature_snapshot", {}))

    st.subheader("四、维修建议")
    st.write("识别到的故障现象：")
    for item in advice.get("recognized_fault_phenomena", []):
        st.write(f"- {item}")
    st.write("可能原因：")
    for item in advice.get("possible_causes", []):
        st.write(f"- {item}")
    st.write("建议检查方向：")
    for item in advice.get("inspection_suggestions", []):
        st.write(f"- {item}")
    st.write("备件准备建议：")
    for item in advice.get("spare_part_suggestions", []):
        st.write(f"- {item}")

    st.subheader("五、工具调用记录")
    called_tools = analysis.get("called_tools", [])
    if called_tools:
        for tool in called_tools:
            st.code(tool)
    else:
        st.info("暂无工具调用记录。")

    st.subheader("六、分析边界说明")
    st.warning(analysis.get("analysis_statement", ""))


# ── 页面 6：Agent 诊断工作台（聊天对话框版）────────────────────

QUICK_QUESTIONS = [
    "帮我分析设备 1000029970",
    "设备 EX011115 最近有哪些故障？",
    "当前高风险设备有哪些？",
    "这批工单整体情况怎么样？",
    "那它为什么是橙色预警？",
    "那应该先检查什么？",
    "那它最近有哪些故障？",
    "换成 EX011115 呢？",
]


def _init_agent_session():
    """初始化 Agent 会话状态（仅在首次进入时执行）。"""
    defaults = {
        "agent_session_id": str(uuid.uuid4()),
        "agent_messages": [],
        "agent_last_assetnum": None,
        "agent_last_task_type": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _new_agent_session():
    """创建新会话：重置 session_id 和全部展示状态。"""
    st.session_state["agent_session_id"] = str(uuid.uuid4())
    st.session_state["agent_messages"] = []
    st.session_state["agent_last_assetnum"] = None
    st.session_state["agent_last_task_type"] = None


def _handle_agent_query(question: str):
    """调用后端 Agent，将问答追加到 agent_messages。

    这是前端内部函数，不向用户展示过程。
    """
    session_id = st.session_state["agent_session_id"]

    # 1. 追加用户消息
    st.session_state["agent_messages"].append({
        "role": "user",
        "content": question,
        "meta": None,
    })

    # 2. 调用后端
    with st.spinner("Agent 正在诊断中..."):
        result = agent_diagnose(question, session_id=session_id)

    if result is None:
        st.session_state["agent_messages"].append({
            "role": "assistant",
            "content": "⚠️ 无法连接到后端服务，请确认后端已启动。",
            "meta": None,
        })
        return

    # 3. 更新多轮上下文
    if result.get("status") == "success":
        st.session_state["agent_last_assetnum"] = (
            result.get("last_assetnum") or result.get("assetnum")
        )
        st.session_state["agent_last_task_type"] = (
            result.get("last_task_type") or result.get("task_type")
        )

    # 4. 追加 assistant 消息（含折叠调试信息）
    st.session_state["agent_messages"].append({
        "role": "assistant",
        "content": result.get("final_answer", "未生成报告"),
        "meta": {
            "assetnum": result.get("assetnum"),
            "task_type": result.get("task_type"),
            "time_window": result.get("time_window"),
            "selected_tools": result.get("selected_tools", []),
            "tool_results": result.get("tool_results", {}),
            "errors": result.get("errors", []),
            "session_id": result.get("session_id"),
            "last_assetnum": result.get("last_assetnum"),
            "last_task_type": result.get("last_task_type"),
            "status": result.get("status", "unknown"),
        },
    })


def _render_assistant_meta(meta: dict):
    """在 assistant 消息下方折叠展示调试信息。"""
    if meta is None:
        return

    # ── 工具轨迹（一行小字，默认折叠） ──
    selected = meta.get("selected_tools", [])
    tool_results = meta.get("tool_results", {})

    if selected:
        tool_labels = []
        for t in selected:
            tr = tool_results.get(t, {})
            icon = "✅" if tr.get("status") == "success" else "❌"
            tool_labels.append(f"{icon} `{t}`")
        st.caption(" | ".join(tool_labels))

    # ── 异常（区分"多轮补全提示"和真正错误） ──
    errors = meta.get("errors", [])
    if errors:
        info_errors = [e for e in errors if "多轮" in e or "上下文" in e]
        real_errors = [e for e in errors if e not in info_errors]
        for err in info_errors:
            st.info(f"💡 {err}")
        for err in real_errors:
            st.warning(f"⚠️ {err}")

    # ── 折叠调试详情 ──
    with st.expander("🔍 调试详情", expanded=False):
        st.markdown("**诊断元信息**")
        st.text(
            f"设备编号：{meta.get('assetnum') or '无'}\n"
            f"任务类型：{meta.get('task_type') or '无'}\n"
            f"时间窗口：{meta.get('time_window') or '无'}\n"
            f"Session ID：{meta.get('session_id') or '无'}\n"
            f"Last Assetnum：{meta.get('last_assetnum') or '无'}\n"
            f"Last TaskType：{meta.get('last_task_type') or '无'}"
        )

        if selected:
            st.markdown("**工具调用轨迹**")
            for t in selected:
                tr = tool_results.get(t, {})
                status = tr.get("status", "unknown")
                if status == "success":
                    st.success(f"{t}")
                elif status == "error":
                    st.error(f"{t}: {tr.get('message', '')}")

        st.markdown("**工具结果 JSON**")
        st.json(tool_results)


def page_agent_workstation():
    # ── 初始化 ──
    _init_agent_session()
    session_id = st.session_state["agent_session_id"]

    # ═══════════════════════════════════════════════════════════
    # 顶部状态栏
    # ═══════════════════════════════════════════════════════════

    st.title("🤖 AFC 智能诊断 Agent")
    st.caption("支持多轮追问：*它 / 这个设备 / 刚才那个 / 换成 XXX*")

    col_status, col_btn = st.columns([4, 1])
    with col_status:
        last_asset = st.session_state.get("agent_last_assetnum")
        last_task = st.session_state.get("agent_last_task_type")
        asset_text = last_asset if last_asset else "暂无"
        task_text = last_task if last_task else "暂无"
        st.markdown(
            f"📌 当前设备：**{asset_text}**　|　"
            f"上次任务：**{task_text}**　|　"
            f"会话：`{session_id[:8]}...`"
        )
    with col_btn:
        if st.button("🆕 新建会话", use_container_width=True):
            _new_agent_session()
            st.rerun()

    st.divider()

    # ═══════════════════════════════════════════════════════════
    # 快捷问题（直接发送，不填入输入框）
    # ═══════════════════════════════════════════════════════════

    with st.expander("📌 快捷问题", expanded=False):
        cols = st.columns(4)
        for i, q in enumerate(QUICK_QUESTIONS):
            with cols[i % 4]:
                if st.button(q, key=f"quick_{i}", use_container_width=True):
                    _handle_agent_query(q)
                    st.rerun()

    # ═══════════════════════════════════════════════════════════
    # 聊天消息流
    # ═══════════════════════════════════════════════════════════

    messages = st.session_state.get("agent_messages", [])

    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("meta"):
                _render_assistant_meta(msg["meta"])

    # ═══════════════════════════════════════════════════════════
    # 底部聊天输入框
    # ═══════════════════════════════════════════════════════════

    prompt = st.chat_input("请输入你的问题，例如：帮我分析设备 1000029970")

    if prompt:
        _handle_agent_query(prompt)
        st.rerun()


# ── 主入口 ────────────────────────────────────────────────────

def main():
    st.sidebar.title("AFC 智能系统")
    st.sidebar.caption("v0.2.0 · LangGraph + Tools")
    show_backend_status()

    page = st.sidebar.radio(
        "请选择功能页面",
        ["首页", "数据上传", "数据概览", "高风险设备", "单设备分析", "Agent 诊断工作台"],
    )

    if page == "首页":
        page_home()
    elif page == "数据上传":
        page_upload()
    elif page == "数据概览":
        page_data_summary()
    elif page == "高风险设备":
        page_high_risk()
    elif page == "单设备分析":
        page_single_device()
    elif page == "Agent 诊断工作台":
        page_agent_workstation()


if __name__ == "__main__":
    main()
